"""Render an output's edit document (``output render``): only the stages whose inputs changed run again.

Stage chain per target (the output's own canvas = ``primary``, or an extra platform from ``export_add``):

  canvas    the source on the target canvas: pipeline mode reframes the clean master (face-tracked, pad-blur
            fallback; same aspect = a plain scale); flattened mode uses the finished file (another aspect:
            reframe, or the ``band`` layout in the frame pass)                       key: source sig + canvas
  timeline  trim + inner cuts (+ transitions at the joins), speed, grade, end fade (ffmpeg)
                                                                                   key: canvas + those ops
  audio     timeline audio + SFX + music bed -> loudness target (two-pass)        key: timeline + audio ops
  final     frame pass (mask / band layout, punch-in, overlays, cards, title band, captions, progress bar) +
            encode with the audio stem; preview = low bitrate at the SAME resolution, final = delivery encode
                                                                                   key: timeline + audio + visual
  cover     a frame of the timeline + cover text (when ``cover`` is set)          key: timeline + cover

Each stage file is ``<edit dir>/cache/<stage>-<key>.*`` (a hit = no work); the result is copied to
``<edit dir>/renders/<target>.<quality>.mp4`` (+ ``.cover.jpg``) with ``renders/manifest.json``. Every render
writes ``.vstudio/status.json`` heartbeats (vstudio.batch.livestatus) into the edit folder and the owning
project / work folder (the owner's previous record is restored afterwards).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np

from vstudio.batch.util import read_json, sha1_json, write_json

from . import outfx as FX
from . import outputs as OUT

QUALITIES = ("preview", "final")
VOICE = None                 # tests / embedders: fn(text, lang, out_wav) -> out_wav (else vstudio.tts)
SOURCES_COVERAGE = 0.6       # matched share of an imported clip needed to rebuild a version from its footage
WIDER = 1.08                 # a target this much wider than the file takes its pixels from the footage
INTER = dict(preview=dict(crf=24, preset="ultrafast"), final=dict(crf=14, preset="veryfast"))
KEEP_PER_STAGE = 4


def _media():
    from vstudio import media
    return media


# --------------------------------------------------------------------------- targets
def targets_of(rec, st, wanted=None):
    """[{target, w, h, profile, layout}] - ``primary`` first, then the state's exports (``wanted`` filters)."""
    from vstudio import platform as P
    out = [dict(target="primary", w=rec["info"]["w"], h=rec["info"]["h"], profile=rec.get("profile"), layout="auto")]
    for x in st["exports"]:
        name, ori = x["target"].split(":")
        p = P.profile(name, ori)
        out.append(dict(target=x["target"], w=p.w, h=p.h, profile=p, layout=x.get("layout") or "auto",
                        lang=x.get("lang"), lines=x.get("lines") or [], voice=x.get("voice")))
    if wanted and wanted not in ("all", ["all"]):
        want = [wanted] if isinstance(wanted, str) else list(wanted)
        want = ["primary" if w == "primary" else OUT.target_key(w) for w in want]
        missing = [w for w in want if w not in [t["target"] for t in out]]
        if missing:
            raise OUT.OutputError("unknown-target", f"{', '.join(missing)} is not an export of this output (add it "
                                  "with export_add)", f"{', '.join(missing)} 不在导出列表里", targets=missing)
        out = [t for t in out if t["target"] in want]
    return out


def _safe(tg):
    from vstudio import platform as P
    W, H = tg["w"], tg["h"]
    p = tg.get("profile")
    if p is not None:
        x0, y0, x1, y1 = P.safe_box(p)
        sx, sy = W / p.w, H / p.h
        return (x0 * sx, y0 * sy, x1 * sx, y1 * sy)
    return (W * 0.05, H * 0.05, W * 0.95, H * 0.95)


def _caption_box(tg):
    from vstudio import platform as P
    W, H = tg["w"], tg["h"]
    p = tg.get("profile")
    if p is not None:
        x0, y0, x1, y1 = P.caption_box(p)
        sx, sy = W / p.w, H / p.h
        return (x0 * sx, y0 * sy, x1 * sx, y1 * sy)
    return (W * 0.08, H * 0.76, W * 0.92, H * 0.9)


# --------------------------------------------------------------------------- the plan (keys only, no media work)
def _src(rec):
    return rec["master"] if rec["mode"] == "pipeline" else rec["file"]


def watermark_spec(rec, tg, quality, override=None):
    """The creator's watermark for a FINAL render of this target (vstudio.watermark), or None: not set up, off by
    default / for this platform / for this export (``override`` False), or a flattened output whose file is an
    export that already carries it."""
    if quality != "final":
        return None
    from vstudio import watermark as WM
    prof = tg.get("profile")
    cfg = WM.resolve(prof.name if prof is not None else None, override=override)
    if not cfg:
        return None
    if rec["mode"] == "flattened" and WM.already_marked(rec["file"]):
        return None
    return WM.spec(cfg, tg["w"], tg["h"], prof)


def framing_fallback(rec):
    """How a shot without a face fills another canvas when a chat edit exports a new platform: the project's own
    framing choice - a vlog follows the subject unless she picked the blurred fill - else the blurred fill. (A vlog
    re-exported from the clip page used to put its drone shots on a blurred band, unlike the project's own
    follow-the-subject vertical.)"""
    if rec.get("imported"):                  # a finished video imported: footage-led (drone, travel) - follow it
        return "subject"
    if rec.get("kind") != "project":
        return "pad-blur"
    try:
        import yaml
        with open(os.path.join(rec["owner"], "project.yaml"), encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
    except (OSError, ValueError, ImportError):
        return "pad-blur"
    if d.get("recipe") != "vlog":
        return "pad-blur"
    picks = [str((it.get("params") or {}).get("reframe") or "") for it in d.get("items") or []]
    picks.append(str((d.get("params") or {}).get("reframe") or ""))
    picks += [str((o or {}).get("reframe") or "") for o in (d.get("overrides") or {}).values() if isinstance(o, dict)]
    return "pad-blur" if "blur" in picks else "subject"


def plan(rec, doc, st, tg, quality, watermark=None):
    """-> dict of stage specs {canvas, timeline, audio, final, cover} with their keys (pure; used by render and by
    ``show`` to say whether a render is fresh). ``watermark``: True / False / None (the creator's default)."""
    info = rec["master_info"] if rec["mode"] == "pipeline" else rec["info"]
    src = _src(rec)
    sig = OUT.file_sig(src)
    dur = rec["info"]["duration"]
    tl = OUT.Timeline(st, dur)
    band = rec["mode"] == "flattened" and (tg["layout"] == "band" or
                                           (st["captions"].get("placement") or {}).get("mode") == "band")
    same = (info["w"], info["h"]) == (tg["w"], tg["h"])
    pieces = shot_pieces(rec, st, tg)
    splice = None
    if pieces and pieces["op"] == "splice":
        splice = dict(pieces, src=src, sig=sig, keep="title-bar:2")
        splice["key"] = sha1_json(["splice", splice, quality], 16)
    canvas = dict(src=src, sig=sig, w=tg["w"], h=tg["h"], src_wh=[info["w"], info["h"]],
                  op="none" if (same or band) else ("scale" if abs(info["w"] / info["h"] - tg["w"] / tg["h"]) < 0.01
                                                    else "reframe"),
                  safe=[round(x, 2) for x in _safe(tg)])
    if canvas["op"] == "reframe":
        canvas["fallback"] = framing_fallback(rec)
    if pieces and pieces["op"] == "sources":
        canvas.update(op="sources", pieces=pieces["pieces"], fps=pieces["fps"])
    if splice:
        canvas["splice"] = splice["key"]
    # no canvas work: the key is the source alone, so targets sharing it share the timeline / audio stages
    canvas["key"] = sha1_json((["canvas", src, sig, splice["key"]] if splice else ["canvas", src, sig])
                              if canvas["op"] == "none" else ["canvas", canvas, quality], 16)
    effs = st["effects"]
    grade = next((e["params"] for e in effs if e["effect"] == "vlog-grade"), None)
    endf = next((e["params"] for e in effs if e["effect"] == "end-fade"), None)
    morph = next((dict(max_move=float(e["params"].get("max_move") or 0.06)) for e in effs
                  if e["effect"] == "morph-cuts"), None)
    full = len(tl.segs) == 1 and abs(tl.segs[0][0]) < 1e-3 and abs(tl.segs[0][1] - dur) < 0.02
    timeline = dict(segs=tl.segs, joins=tl.joins, speed=tl.speed, grade=grade, end_fade=endf,
                    duration=round(tl.duration, 3), has_audio=info["has_audio"])
    if morph:
        timeline["morph"] = morph
    if len(tl.segs) > 1 and info["has_audio"] and OUT.cut_strategy(rec, doc.d.get("burned")) == "hard":
        # flattened, no burned captions: a 2-frame audio fade at every plain join (a hard cut of the finished mix)
        timeline["join_fade"] = round(2.0 / float(rec["info"]["fps"] or 30.0), 4)
    timeline["op"] = "none" if (full and tl.speed == 1.0 and not grade and not endf and not morph) else "ffmpeg"
    timeline["key"] = sha1_json(["timeline", canvas["key"], timeline, quality if timeline["op"] != "none" else None], 16)
    sfx = sorted([[round(tl.to_edit(e["start"], "start") or 0.0, 3), e["params"]["name"], e["params"].get("gain", 1.0)]
                  for e in effs if e["effect"] == "sfx-placement" and tl.span(e["start"], e["start"] + 0.05)])
    music = next((dict(e["params"], sig=OUT.file_sig(e["params"]["file"]))
                  if os.path.exists(e["params"].get("file") or "") else dict(e["params"], sig=["mood", e["params"]["mood"]])
                  for e in effs if e["effect"] == "music-bed" and (os.path.exists(e["params"].get("file") or "")
                                                                   or e["params"].get("mood"))), None)
    prof = tg.get("profile")
    lufs = st["loudness"].get("lufs") or (prof.loudness["lufs"] if prof is not None else -14.0)
    tp = st["loudness"].get("tp") or (prof.loudness["tp"] if prof is not None else -1.5)
    studio = next((dict(strength=e["params"].get("strength") or "standard")
                   for e in effs if e["effect"] == "studio-sound"), None)
    audio = dict(sfx=sfx, music=music, lufs=lufs, tp=tp, has_audio=info["has_audio"])
    if music and music.get("replace") and info["has_audio"]:
        # a swap, not a second bed: the finished mix stays only where someone speaks (its old music can't be
        # taken out from under a voice), the new bed carries the rest
        W = OUT.cached_words(doc) or []
        spans = []
        for w in W:
            sp = tl.span(max(0.0, w["t"] - 0.15), w["te"] + 0.15)
            if sp:
                if spans and sp[0] <= spans[-1][1] + 0.3:
                    spans[-1][1] = round(sp[1], 3)
                else:
                    spans.append([round(sp[0], 3), round(sp[1], 3)])
        audio["keep"] = spans
    if studio:
        audio["studio"] = studio
    if tg.get("lang") and tg.get("lines"):        # a language version: a new voice over a music bed
        vl = []
        for a_, b_, _said, text in tg["lines"]:
            sp = tl.span(a_, b_)
            if sp:
                vl.append([round(sp[0], 3), round(sp[1], 3), text])
        audio["voice"] = dict(lang=tg["lang"], lines=vl, voice=tg.get("voice") or "auto")
        if not audio["music"]:
            audio["music"] = dict(mood="calm", sig=["mood", "calm"], duck_db=-8, music_lufs=-26)
    vos = []
    if st.get("voiceovers"):                      # narrations over the clip (outvoice): in this version's language
        from . import outvoice as VO
        vlang = target_lang(tg) or VO.version_langs(rec, st, OUT.cached_words(doc) or [])[0]
        vos = [x for x in (VO.spec_for(v, vlang, tl) for v in st["voiceovers"]) if x]
        if vos:
            audio["vo"] = vos
    audio["op"] = "none" if not (info["has_audio"] or sfx or music or vos) else "mix"
    audio["key"] = sha1_json(["audio", timeline["key"], audio], 16)
    vis = visual_spec(rec, st, tl, tg, band)
    vo_caps = [[a_, b_, t_] for v in vos if v.get("captions") for a_, b_, t_ in v["lines"]]
    if vo_caps:                                    # the narration captioned in the version's language
        vis["captions"] = sorted(vis["captions"] + vo_caps)
        if rec["mode"] == "flattened" and canvas["op"] != "sources" and not vis.get("mask"):
            bt = (doc.d.get("burned") or {})
            if bt.get("captions") and bt.get("box"):
                vis["mask"] = dict(box=bt["box"], style="blur", always=True)
    if audio.get("voice"):                         # its captions: the translated lines (over the burned ones)
        vis["captions"] = sorted(vis["captions"] + [[a_, b_, t_] for a_, b_, t_ in audio["voice"]["lines"]])
        if rec["mode"] == "flattened" and canvas["op"] != "sources" and not vis.get("mask"):
            bt = (doc.d.get("burned") or {})
            if bt.get("captions") and bt.get("box"):
                vis["mask"] = dict(box=bt["box"], style="blur", always=True)
    wm = watermark_spec(rec, tg, quality, watermark)
    if wm:                                             # only when drawn: keys of unmarked renders stay as they were
        vis["watermark"] = wm
    final = dict(visual=vis, quality=quality, canvas=[tg["w"], tg["h"]],
                 encode=(prof.encode if prof is not None and quality == "final" else None))
    if picture_untouched(rec, st, tg, full) and not wm:
        # audio-only edit (studio sound, music, SFX, loudness): the output's own picture, stream-copied
        final["op"], final["picture"] = "remux", OUT.file_sig(rec["file"])
    else:
        final["op"] = "frames" if (vis["layers"] or vis["captions"] or vis["title"] or vis["mask"] or vis["band"] or
                                   vis["dips"] or (canvas["op"] == "none" and not same and not band)) else "encode"
    final["key"] = sha1_json(["final", timeline["key"], audio["key"], final], 16)
    cover = None
    if st.get("cover"):
        cv = st["cover"]
        cover = dict(cv, edit_t=tl.to_edit(cv["t"], "start"), size=_cover_size(tg))
        cover["key"] = sha1_json(["cover", timeline["key"], cover, rec["mode"]], 16)
    return dict(target=tg["target"], quality=quality, canvas=canvas, timeline=timeline, audio=audio, final=final,
                cover=cover, tl=tl, band=band, splice=splice)


def shot_pieces(rec, st, tg):
    """How an imported clip's picture is put together from its matched footage, or None (the file as it is):
    ``splice`` - the output's own canvas with swapped shots replaced by their new take (same framing, the finished
    grade); ``sources`` - a version whose canvas is wider than the file (or a language version, so no burned text
    comes along) rebuilt shot by shot from the full source frame (unmatched shots: the file, fitted)."""
    from vstudio import shotmatch as SM
    if rec["mode"] != "flattened":
        return None
    m = OUT.shot_map(rec)
    if not m:
        return None
    swaps = st.get("shots") or {}
    fw, fh = rec["info"]["w"], rec["info"]["h"]
    fps = round(float(rec["info"]["fps"] or 30.0), 3)
    srcs = {x["path"]: x for x in m.get("sources") or []}
    W, H = tg["w"], tg["h"]
    same = abs(W / H - fw / fh) < 0.01
    wider = (W / H) > (fw / fh) * WIDER
    rebuild = (wider or (tg.get("lang") and tg.get("lines"))) and (m.get("coverage") or 0) >= SOURCES_COVERAGE
    if not rebuild and not swaps:
        return None
    if not rebuild and tg["target"] != "primary" and not same:
        rebuild = False                   # another aspect: the canvas stage reframes the spliced file
    grades = {}
    for x in m["shots"]:
        if x.get("match") and x["match"].get("grade") and x["match"]["source"] not in grades:
            grades[x["match"]["source"]] = x["match"]["grade"]
    pieces = []
    for x in m["shots"]:
        mt, sw = x.get("match"), swaps.get(str(x["i"]))
        a, b = x["start"], x["end"]
        if sw and sw["source"] in srcs:
            s_ = srcs[sw["source"]]
            own = mt and mt["source"] == sw["source"]
            base = mt["box"] if own else [0.0, 0.0, 1.0, 1.0]
            if rebuild:
                box = SM.fit_box(base, (s_["w"], s_["h"]), W / H, widest=True)
                fbox = None
            else:
                fbox = mt["fbox"] if mt else None
                part = (fbox[2] * fw) / max(1e-6, fbox[3] * fh) if fbox else fw / fh
                box = SM.fit_box(base, (s_["w"], s_["h"]), part, widest=not own)
            pieces.append(dict(a=a, b=b, kind="source", src=sw["source"], t=sw["t"],
                               speed=(mt["speed"] if own else 1.0), box=box, fbox=fbox,
                               grade=(mt.get("grade") if own else grades.get(sw["source"]))))
        elif rebuild and mt and mt["source"] in srcs:
            s_ = srcs[mt["source"]]
            pieces.append(dict(a=a, b=b, kind="source", src=mt["source"], t=mt["t"], speed=mt["speed"],
                               box=SM.fit_box(mt["box"], (s_["w"], s_["h"]), W / H, widest=wider),
                               fbox=None, grade=mt.get("grade")))
        else:
            pieces.append(dict(a=a, b=b, kind="file"))
    if not any(pc["kind"] == "source" for pc in pieces):
        return None
    if rebuild:
        return dict(op="sources", pieces=pieces, fps=fps, w=W, h=H)
    return dict(op="splice", pieces=pieces, fps=fps, w=fw, h=fh)


def designed_bands(file, t, w, h):
    """Rows at the top / bottom of a finished frame that are a designed band (a title bar, a caption box: mostly one
    colour, its text on it) rather than video -> [(y0, y1)] in pixels. A new take keeps them over it."""
    from vstudio import shotmatch as SM
    sw = 320
    sh = max(2, int(round(sw * h / max(1, w))))
    try:
        _t, fr = SM._decode(file, sw, sh, start=t, frames=1, color=True)
    except Exception:  # noqa: BLE001
        return []
    if not len(fr):
        return []
    img = fr[0].astype(np.int16)

    def run(rows):
        ref = np.median(img[rows[0]].reshape(-1, 3), axis=0)
        k, miss = 0, 0
        for i, r in enumerate(rows):         # one colour, small text and thin rules on it
            close = (np.abs(img[r] - ref).max(axis=1) <= 6).mean()
            if close >= 0.6:
                k, miss = i + 1, 0
            else:
                miss += 1
                if miss > 3:
                    break
        return k
    top = run(list(range(sh)))
    if 0.04 * sh <= top <= 0.3 * sh:
        return [(0, int(round(top * h / sh)))]
    return []


def title_bar(file, duration, w, h):
    """A designed bar across the top of the whole video (the same height at 20 %, 50 % and 80 %) -> [(0, y1)] or []
    (a dark sky at the top of one shot is not a bar)."""
    got = [designed_bands(file, duration * f, w, h) for f in (0.2, 0.5, 0.8)]
    if all(got) and max(g[0][1] for g in got) - min(g[0][1] for g in got) <= max(4, h * 0.01):
        return [(0, min(g[0][1] for g in got))]
    return []


def run_pieces(spec, file, out, quality, workdir):
    """Pieces (``shot_pieces``) -> one video on spec's canvas: each piece encoded on its own (an exact frame
    count, so the joins never drift), joined, with the file's own sound."""
    from vstudio import shotmatch as SM
    m = _media()
    W, H, fps = spec["w"], spec["h"], spec["fps"]
    finfo = m.probe(file)
    fw, fh = finfo["w"], finfo["h"]
    parts = []
    bands = None
    enc = _enc("inter", quality, audio=False)
    for j, pc in enumerate(spec["pieces"]):
        n = int(round(pc["b"] * fps)) - int(round(pc["a"] * fps))
        if n <= 0:
            continue
        dst = os.path.join(workdir, f"piece{j:03d}.mp4")
        if pc["kind"] == "file":
            if (fw, fh) == (W, H):
                vf = f"fps={fps:g},format=yuv420p,setsar=1"
            else:                                      # the file fitted on a blurred fill of itself
                if W / H > fw / fh:
                    bw = (H * fw / fh) / W
                    fbox = [(1 - bw) / 2, 0.0, bw, 1.0]
                else:
                    bh = (W * fh / fw) / H
                    fbox = [0.0, (1 - bh) / 2, 1.0, bh]
                vf = SM.piece_filter([0.0, 0.0, 1.0, 1.0], W, H, fps, fbox=fbox)
            cmd = ["ffmpeg", "-y", "-ss", f"{pc['a']:.4f}", "-i", file]
        else:
            vf = SM.piece_filter(pc["box"], W, H, fps, speed=pc.get("speed") or 1.0, grade=pc.get("grade"),
                                 fbox=pc.get("fbox"))
            # camera footage (4K HEVC, 10-bit): decoded by VideoToolbox on a Mac (several times faster)
            hw = ["-hwaccel", "videotoolbox"] if sys.platform == "darwin" else []
            cmd = ["ffmpeg", "-y", *hw, "-ss", f"{max(0.0, pc['t']):.4f}", "-i", pc["src"]]
            if spec.get("op") == "splice" and bands is None:
                bands = title_bar(file, finfo["duration"], fw, fh)
            if bands and spec.get("op") == "splice":   # the finished video's title bar stays over the new take
                g = f"[0:v]{vf},tpad=stop_mode=clone:stop_duration=30[p0]"
                for k, (y0, y1) in enumerate(bands):
                    g += (f";[1:v]crop={fw}:{y1 - y0}:0:{y0},fps={fps:g},format=yuv420p,setsar=1[b{k}]"
                          f";[p{k}][b{k}]overlay=0:{y0}[p{k + 1}]")
                tail_ = ["-ss", f"{pc['a']:.4f}", "-i", file, "-an", "-filter_complex", g, "-map",
                         f"[p{len(bands)}]", "-frames:v", str(n), *enc, dst]
                try:
                    m.run(cmd + tail_)
                except Exception:  # noqa: BLE001
                    m.run([x for i, x in enumerate(cmd) if x != "-hwaccel" and (i == 0 or cmd[i - 1] != "-hwaccel")]
                          + tail_)
                parts.append(dst)
                continue
        vf += ",tpad=stop_mode=clone:stop_duration=30"     # a source that ends early holds its last frame
        try:
            m.run(cmd + ["-an", "-vf", vf, "-frames:v", str(n), *enc, dst])
        except Exception:  # noqa: BLE001  (no hardware decoder for this file: the software one)
            if "-hwaccel" not in cmd:
                raise
            m.run([x for i, x in enumerate(cmd) if x != "-hwaccel" and (i == 0 or cmd[i - 1] != "-hwaccel")]
                  + ["-an", "-vf", vf, "-frames:v", str(n), *enc, dst])
        parts.append(dst)
    lst = os.path.join(workdir, "pieces.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("".join(f"file '{x}'\n" for x in parts))
    joined = os.path.join(workdir, "pieces.mp4")
    m.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    if finfo["has_audio"]:
        m.run(["ffmpeg", "-y", "-i", joined, "-i", file, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a",
               "aac", "-b:a", "256k", "-shortest", out])
    else:
        shutil.copy2(joined, out)
    return out


def picture_untouched(rec, st, tg, full):
    """True when the edit changes nothing in the picture of the output's own canvas: no trim / cut / speed / grade /
    end fade / transition, no frame effect, captions / title / theme as the output came. Then the original file's
    video is exactly the answer and only the audio is new."""
    if tg["target"] != "primary" or not full or float(st.get("speed") or 1.0) != 1.0:
        return False
    if st.get("title") or st.get("theme") or st.get("shots"):
        return False
    if any(v.get("captions", True) for v in st.get("voiceovers") or []):     # a narration's captions are drawn
        return False
    for e in st["effects"]:
        if FX.SPECS[e["effect"]]["stage"] != "audio":
            return False
    c = st["captions"]
    if c["style"] or c["overrides"] or c["removed"] or c["added"] or c.get("placement"):
        return False
    return bool(c["enabled"]) == bool(rec.get("captions_on"))


def _cover_size(tg):
    from vstudio import platform as P
    p = tg.get("profile")
    if p is not None:
        return list(P.cover_size(p))
    return [tg["w"], tg["h"]]


def _recipe_of(rec):
    """The recipe id of the project an output belongs to (project.yaml ``recipe``), else None."""
    if rec.get("kind") != "project" or not rec.get("owner"):
        return None
    try:
        import yaml
        with open(os.path.join(rec["owner"], "project.yaml"), encoding="utf-8") as f:
            return (yaml.safe_load(f) or {}).get("recipe")
    except Exception:  # noqa: BLE001
        return None


def mono_caption(text, alt, lang, both=False):
    """One caption line set in the version's language (English on international platforms, 中文 on Chinese ones):
    of a bilingual cue (lines of both, or text + alt) only the lines in ``lang``; bilingual when persona
    ``subtitles.bilingual`` asks (``both``; never on YouTube). None / no line in that language: as is."""
    from vstudio.subs import _ZH
    text = str(text or "")
    if not lang or both:
        return text
    lines = [x for x in text.split("\n") if x.strip()] + ([str(alt)] if alt else [])
    keep = [x for x in lines if bool(_ZH.search(x)) == (lang == "zh")]
    return "\n".join(keep) if keep else text


def target_lang(tg):
    """The language a version shows: "en" on international platforms (YouTube, TikTok, Instagram, X ...), "zh" on
    Chinese ones (Xiaohongshu, Bilibili, Douyin ...); None for the primary file without a platform profile."""
    prof = tg.get("profile")
    if prof is None:
        return None
    from vstudio import platform as P
    return P.lang_for(prof.key, "en")


def visual_spec(rec, st, tl, tg, band):
    """Everything the frame pass draws, in edited seconds (JSON: it is part of the final key)."""
    layers = []
    lang = target_lang(tg)
    from vstudio import platform as _P
    from vstudio.subs import bilingual_wanted
    both = bilingual_wanted() and not (tg.get("profile") is not None and _P.lang_fixed(tg["profile"].key))
    for e in st["effects"]:
        if any(str(k).endswith(FX.LANG_SUFFIXES) for k in (e.get("params") or {})):
            e = dict(e, params=FX.localize(e["params"], lang))
        sp = FX.SPECS[e["effect"]]
        if sp["stage"] != "frame":
            continue
        if sp["kind"] == "progress":
            span = (0.0, tl.duration)
            chs = []
            for c in e["params"].get("chapters") or []:
                try:
                    s = tl.span(float(c.get("start", 0)), float(c.get("end", rec["info"]["duration"])))
                except (TypeError, ValueError):
                    s = None
                if s:
                    chs.append([round(s[0], 3), round(s[1], 3), str(c.get("label") or c.get("title") or "")])
            layers.append(dict(e, a=0.0, b=round(tl.duration, 3), _chapters_edit=chs))
            continue
        span = tl.span(e["start"], e["end"])
        if span:
            layers.append(dict(e, a=round(span[0], 3), b=round(span[1], 3)))
    dips = []
    jids = {j["id"] for j in tl.joins}
    for e in st["effects"]:
        if e["effect"] == "xfade-joins" and e["id"] not in jids:
            t = tl.to_edit(e["start"], "start")
            if t is not None:
                tr = e["params"].get("transition") or "fade"
                dips.append(dict(t=round(t, 3), d=float(e["params"].get("duration") or 0.4),
                                 color="white" if tr in ("flash", "light-leak", "whip", "zoom", "iris") else "black"))
    c = st["captions"]
    caps = []
    if rec["mode"] == "pipeline" and c["enabled"]:
        for i, cue in enumerate(rec.get("cues") or []):
            k = str(i)
            if k in c["removed"]:
                continue
            s = tl.span(cue["start"], cue["end"])
            if s:
                caps.append([round(s[0], 3), round(s[1], 3),
                             mono_caption(c["overrides"].get(k, cue["text"]), cue.get("alt"), lang, both)])
    for a in c["added"]:
        s = tl.span(a["start"], a["end"])
        if s:
            caps.append([round(s[0], 3), round(s[1], 3), mono_caption(a["text"], a.get("alt"), lang, both)])
    caps.sort()
    pl = c.get("placement") or {}
    mask = None
    if rec["mode"] == "flattened" and pl.get("mode") == "mask":
        mask = dict(box=pl["box"], style=pl.get("style") or "blur", always=pl.get("always", True))
    bandspec = None
    if band:
        bandspec = dict(band=float(pl.get("band") or 0.2), title=bool(st.get("title")))
    from vstudio import theme as TH
    fallback = TH.default_for(_recipe_of(rec))         # vlog / photo-story: cinema unless a theme is named
    with TH.fallback(fallback):
        look = TH.resolve(st.get("theme"))             # the resolved look is part of the final key: a persona /
    look = sha1_json({k: v for k, v in look.items() if k != "source"}, 12)   # client theme change re-renders
    return dict(layers=layers, captions=caps, style=c["style"], title=st.get("title"), theme=st.get("theme"),
                look=look, fallback_theme=fallback, mask=mask, band=bandspec,
                dips=dips, safe=[round(x, 2) for x in _safe(tg)], caption_box=[round(x, 2) for x in _caption_box(tg)],
                mode=rec["mode"])


# --------------------------------------------------------------------------- status / heartbeats
class Status:
    def __init__(self, rec, doc):
        from vstudio.batch import livestatus as LS
        self.LS = LS
        self.dirs = [doc.dir, rec["owner"]]
        self.prev = LS._read_raw(rec["owner"])
        self.label = rec["id"]

    def beat(self, stage, progress=None, message=None):
        for d in self.dirs:
            self.LS.write(d, "running", stage=f"output-edit:{stage}", progress=progress,
                          message=message or self.label, by="output-edit")

    def end(self, ok, message=None):
        self.LS.write(self.dirs[0], "done" if ok else "failed", stage="output-edit", progress=1.0 if ok else None,
                      message=message or self.label, by="output-edit")
        p = self.prev
        if p and p.get("status") in self.LS.STATES and p.get("status") != "running":
            self.LS.write(self.dirs[1], p["status"], stage=p.get("stage"), progress=p.get("progress"),
                          message=p.get("message"), eta=p.get("eta"), needs_you=p.get("needs_you"),
                          by=p.get("updated_by"))
        else:
            self.LS.write(self.dirs[1], "done" if ok else "failed", stage="output-edit",
                          message=message or self.label, by="output-edit")


# --------------------------------------------------------------------------- stage runners
def _enc(quality, crf=None, preset=None, audio=True, final_encode=None):
    m = _media()
    if quality == "preview":
        return m.delivery_args(crf=30, preset="ultrafast", maxrate="2M", bufsize="4M", audio=audio,
                               audio_bitrate="96k")
    if quality == "final":
        enc = final_encode or {}
        return m.delivery_args(crf=enc.get("crf"), preset="medium", maxrate=enc.get("maxrate"),
                               bufsize=enc.get("bufsize"), audio=audio)
    i = INTER[crf]
    return m.delivery_args(crf=i["crf"], preset=i["preset"], audio=audio, audio_bitrate="256k", faststart=False)


def run_canvas(spec, out, quality, safe):
    m = _media()
    if spec["op"] == "scale":
        m.run(["ffmpeg", "-y", "-v", "error", "-i", spec["src"], "-map", "0:v:0", "-map", "0:a:0?", "-vf",
               f"scale={spec['w']}:{spec['h']}:flags=lanczos,setsar=1", *_enc("inter", quality), out])
        return out
    from vstudio import reframe as R
    pl = R.plan(spec["src"], spec["w"], spec["h"], mode="face", safe=tuple(safe),
                fallback=spec.get("fallback") or "pad-blur")
    R.render(spec["src"], out, pl, encode_args=_enc("inter", quality))
    return out


def run_timeline(spec, src, out, quality, workdir):
    from vstudio import xfade
    m = _media()
    info = m.probe(src)
    fps = info["fps"] or 30.0
    has_a = bool(info["has_audio"])
    g, segs = [], spec["segs"]
    jd = {j["index"]: j for j in spec["joins"]}
    jf = float(spec.get("join_fade") or 0.0)
    for k, (a, b) in enumerate(segs):
        g.append(f"[0:v:0]trim=start={a:.6f}:end={b:.6f},setpts=PTS-STARTPTS,fps={fps:.6g},format=yuv420p,"
                 f"settb=AVTB[v{k}]")
        if has_a:
            fades = ""
            f = min(jf, (b - a) / 3)
            if f > 0 and k > 0 and (k - 1) not in jd:
                fades += f",afade=t=in:st=0:d={f:.4f}"
            if f > 0 and k < len(segs) - 1 and k not in jd:
                fades += f",afade=t=out:st={max(0.0, b - a - f):.6f}:d={f:.4f}"
            g.append(f"[0:a:0]atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS{fades},aresample=48000,"
                     f"aformat=channel_layouts=stereo[a{k}]")
    cv, ca, L = "v0", "a0", segs[0][1] - segs[0][0]
    cuts = []                                         # edited seconds (before speed) of the plain joins
    for k in range(1, len(segs)):
        n = segs[k][1] - segs[k][0]
        j = jd.get(k - 1)
        if j:
            tr = xfade.ffmpeg_transition(j["transition"])
            d = j["duration"]
            g.append(f"[{cv}][v{k}]xfade=transition={tr}:duration={d:.4f}:offset={max(0.0, L - d):.4f}[vx{k}]")
            if has_a:
                g.append(f"[{ca}][a{k}]acrossfade=d={d:.4f}[ax{k}]")
            L += n - d
        else:
            cuts.append(L)
            g.append(f"[{cv}][v{k}]concat=n=2:v=1:a=0[vx{k}]")
            if has_a:
                g.append(f"[{ca}][a{k}]concat=n=2:v=0:a=1[ax{k}]")
            L += n
        cv, ca = f"vx{k}", f"ax{k}"
    vch, ach = [], []
    s = spec["speed"]
    if abs(s - 1.0) > 1e-6:
        vch.append(f"setpts=PTS/{s:.6g}")
        ach.append(m.atempo_chain(s))
    gr = spec.get("grade")
    if gr:
        from vstudio import ffmpeg_filters as FF
        vch.append(FF.grade(saturation=round(float(gr.get('sat', 1.12)), 3),
                            contrast=round(float(gr.get('contrast', 1.05)), 3)))
        if gr.get("warm", True):
            vch.append("colorbalance=rs=0.04:gs=0.0:bs=-0.04:rm=0.03:bm=-0.03")
    ef = spec.get("end_fade")
    D = L / s
    if ef:
        d = min(float(ef.get("duration") or 1.0), D * 0.5)
        vch.append(f"fade=t=out:st={max(0.0, D - d):.4f}:d={d:.4f}")
        ach.append(f"afade=t=out:st={max(0.0, D - d):.4f}:d={d:.4f}")
    g.append(f"[{cv}]" + (",".join(vch) if vch else "null") + "[vout]")
    if has_a:
        g.append(f"[{ca}]" + (",".join(ach) if ach else "anull") + "[aout]")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", src, *m.filter_complex_args(";".join(g), workdir), "-map", "[vout]"]
    cmd += (["-map", "[aout]"] if has_a else [])
    cmd += _enc("inter", quality, audio=has_a) + [out]
    m.run(cmd)
    if spec.get("morph"):
        # smooth jump cuts: this edit's own plain joins + the cuts already baked into the source (a cleaned body)
        from vstudio import morphcut
        J = sorted(set(round(c / s, 4) for c in cuts) | set(morphcut.find_cuts(out)))
        morphcut.smooth_inplace(out, J, small=float(spec["morph"].get("max_move") or morphcut.SMALL),
                                report=os.path.join(workdir, "morph.json"))
    return out


def run_audio(spec, src, out, duration, workdir):
    from vstudio import audio as A
    m = _media()
    mix = os.path.join(workdir, "mix.wav")
    has_a = m.probe(src)["has_audio"] and not spec.get("voice")
    if spec.get("voice"):                            # a language version: the new voice replaces the old mix
        x = voice_track(spec["voice"], duration, workdir)
    elif has_a and spec.get("keep") is not None:     # the soundtrack swapped: the old mix only under the speech
        x = A.decode_audio(src, sr=A.SR, channels=2)
        g = np.zeros(len(x), np.float32)
        ramp = int(0.06 * A.SR)
        for a, b in spec["keep"]:
            i0, i1 = max(0, int(a * A.SR)), min(len(x), int(b * A.SR))
            if i1 > i0:
                g[i0:i1] = 1.0
        if ramp > 1 and g.any():
            k = np.ones(ramp, np.float32) / ramp
            g = np.convolve(g, k, mode="same").astype(np.float32)
        x = x * g[:, None]
    elif has_a:
        x = A.decode_audio(src, sr=A.SR, channels=2)
        if spec.get("studio"):
            from vstudio import studiosound
            x, _ = studiosound.enhance_array(x, A.SR, spec["studio"].get("strength") or "standard")
    else:
        x = np.zeros((int(round(duration * A.SR)), 2), np.float32)
    if spec.get("vo"):                               # narrations: laid over, the sound ducked under them
        from . import outvoice as VO
        x = VO.mix_in(x, spec["vo"], len(x) / A.SR, workdir)
    if spec["sfx"]:
        ev = [dict(t=t, sfx=name, gain_db=float(20 * np.log10(max(1e-3, float(g)))) if g else -60.0)
              for t, name, g in spec["sfx"]]
        A.place_sfx(x, ev, sr=A.SR)
    A.write_wav(mix, x, A.SR)
    if spec["music"]:
        mm = spec["music"]
        bed = os.path.join(workdir, "bed.wav")
        src_m = mm.get("file") if os.path.exists(mm.get("file") or "") else None
        if not src_m:                                  # a built-in mood: generated to this length (cached)
            from vstudio import music as MU
            src_m = MU.make(mm["mood"], max(4.0, len(x) / A.SR))
        A.mix_bed(mix, src_m, bed, duck_db=float(mm.get("duck_db", -10)), music_lufs=float(mm.get("music_lufs", -30)))
        mix = bed
    A.loudnorm_2pass(mix, out, lufs=float(spec["lufs"]), tp=float(spec["tp"]))
    return out


def _voice_for(lang, choice="auto"):
    from vstudio import tts
    eng = tts.available_engine()
    if choice and choice != "auto":
        return eng, choice
    if lang == "zh":
        return eng, tts.zh_voice(eng)
    if lang == "fr" and eng == "kokoro":
        return eng, "ff_siwis"
    return eng, tts.default_voice(eng)


def voice_track(v, duration, workdir):
    """The lines of a language version voiced (vstudio.tts, or the VOICE hook) and laid at their times -> float32
    (n, 2). A line longer than its slot is said up to 1.35x faster; past that it runs into the pause after it."""
    from vstudio import audio as A
    m = _media()
    n = int(round(max(duration, 0.5) * A.SR))
    x = np.zeros((n, 2), np.float32)
    eng = voice = None
    lines = v.get("lines") or []
    for k, (a, b, text) in enumerate(lines):
        wav = os.path.join(workdir, f"line{k:03d}.wav")
        if VOICE is not None:
            VOICE(text, v["lang"], wav)
        else:
            from vstudio import tts
            if eng is None:
                eng, voice = _voice_for(v["lang"], v.get("voice"))
            got = tts.synth(text, engine=eng, voice=voice, out=wav)
            if got and got != wav:
                shutil.copy2(got, wav)
        y = A.decode_audio(wav, sr=A.SR, channels=2)
        nxt = lines[k + 1][0] if k + 1 < len(lines) else duration
        slot = max(0.3, nxt - a - 0.08)
        have = len(y) / A.SR
        if have > slot:
            rate = min(1.35, have / slot)
            fast = os.path.join(workdir, f"line{k:03d}.fast.wav")
            m.run(["ffmpeg", "-y", "-i", wav, "-af", m.atempo_chain(rate), "-ar", str(A.SR), fast])
            y = A.decode_audio(fast, sr=A.SR, channels=2)
        i0 = int(round(a * A.SR))
        if i0 >= n:
            continue
        seg = y[: n - i0]
        x[i0: i0 + len(seg)] += seg
    return x


def run_cover(spec, src, out, mode):
    from PIL import Image

    from vstudio.batch.edits import _text_cover
    from vstudio import export as X
    m = _media()
    d = tempfile.mkdtemp(prefix="vcover-")
    try:
        fr = os.path.join(d, "frame.jpg")
        m.grab_frame(src, max(0.0, float(spec.get("edit_t") or 0.0)), fr)
        im = Image.open(fr).convert("RGB")
        W, H = spec["size"]
        im = X.fit_cover(im, (W, H)) if (im.width, im.height) != (W, H) else im
        im.save(fr, quality=95)
        style, text = spec.get("style") or "card", spec.get("text") or ""
        if style == "plain" or not text:
            shutil.copy(fr, out)
        elif style == "band":
            from vstudio import draw as Dr
            im = Image.open(fr).convert("RGBA")
            bh = int(H * 0.22)
            band = Image.new("RGBA", (W, bh), Dr.brand()["ground"] + (235,))
            im.alpha_composite(band, (0, H - bh))
            f = Dr.fit_font(text.replace("|", " "), "cjk-bold", int(bh * 0.36), int(W * 0.9))
            lay = Dr.text_layer(text.replace("|", " "), f, stroke=0, shadow_alpha=0, max_w=int(W * 0.9))
            im.alpha_composite(lay, ((W - lay.width) // 2, H - bh + (bh - lay.height) // 2))
            im.convert("RGB").save(out, quality=92)
        else:
            _text_cover(fr, text, out)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return out


# --------------------------------------------------------------------------- frame pass
class Captions:
    def __init__(self, vis, W, H, prof, band_rect=None, mask_rect=None):
        from vstudio import draw as Dr
        self.Dr = Dr
        self.cues = vis["captions"]
        self.st = dict(vis["style"] or {})
        self.W, self.H, self.prof = W, H, prof
        self.box = tuple(vis["caption_box"])
        self.band_rect, self.mask_rect = band_rect, mask_rect
        self.cache = {}

    def _size(self, text):
        from vstudio import platform as P
        if self.prof is not None:
            fit = P.fit_text_size(self.prof, text.replace("\n", " "))
            s = fit["size"] * self.W / self.prof.w
        else:
            s = min(self.W, self.H) * 0.055
        return max(14, int(s * float(self.st.get("size") or 1.0)))

    def _surface(self, img, cx, cy):
        """paper | video: what is under the caption (a flat area in the theme paper / a light flat band = paper)."""
        want = self.st.get("surface")
        if want in ("paper", "video"):
            return want
        if self.st.get("color") or self.st.get("stroke") is not None:
            return "legacy"                                    # explicit look: the old text_layer path
        if img is None:
            return "video"
        h = int(self.H * 0.05)
        x0, x1 = int(self.W * 0.1), int(self.W * 0.9)
        y0, y1 = max(0, int(cy - h)), min(self.H, int(cy + h))
        roi = img[y0:y1, x0:x1]
        if roi.size == 0:
            return "video"
        px = roi.reshape(-1, 3).astype(np.int16)
        med = np.median(px, axis=0)
        near = float((np.abs(px - med).max(axis=1) <= 10).mean())   # a flat paper band (a hairline or an edge of
        return "paper" if near >= 0.85 else "video"                  # video inside the probe is fine)

    def layer(self, k, text, surface="legacy"):
        key = (k, surface)
        if key not in self.cache:
            Dr = self.Dr
            from vstudio import theme as TH
            T = TH.current()
            size = self._size(text)
            x0, _, x1, _ = self.box
            maxw = (self.band_rect[2] - self.band_rect[0]) * 0.92 if self.band_rect else (x1 - x0)
            if surface in ("paper", "video"):
                role = self.st.get("font") or T["font_caption"]
                f = Dr.load_font(role, size)
                plain = Dr.std_markup(text).replace("\n", "")
                for k in range(1, 7):                       # a cue a little too wide: shrink up to ~15 % before
                    if Dr.text_width(plain.replace("【", "").replace("】", ""), f) <= maxw * 0.97:   # wrapping
                        break                               # (two balanced lines break words: 稻|草)
                    f = Dr.load_font(role, max(14, int(size * (1 - 0.025 * k))))
                else:                                       # two lines: smaller and tighter, so the block keeps
                    f = Dr.load_font(role, max(14, int(size * 0.82)))   # about the height of a one-line cue
                two = Dr.text_width(plain.replace("【", "").replace("】", ""), f) > maxw * 0.97
                ink = None
                if surface == "paper" and TH.is_dark(T) is False and self.paper_rgb is not None and \
                        TH.luminance(self.paper_rgb) < 0.2:
                    ink = TH.rgba(T, "over_ink")
                im = Dr.emph_layer(text, f, T, surface=surface, fill=ink, keywords=self.st.get("keywords") or None,
                                   max_w=int(maxw), align="center", line_gap=1.08 if two else 1.22,
                                   accent=self.st.get("highlight"))
                self.cache[key] = np.asarray(im)
                return self.cache[key]
            f = Dr.load_font(self.st.get("font") or "cjk-bold", size)
            stroke = max(2, int(size * float(self.st.get("stroke", 0.08) if self.st.get("stroke") is not None else 0.08)))
            if self.st.get("stroke") is not None and float(self.st.get("stroke")) == 0:
                stroke = 0
            im = Dr.text_layer(text, f, fill=Dr.rgba(self.st.get("color") or "#FFFFFF"),
                               hl_fill=self.st.get("highlight"), stroke=stroke,
                               stroke_fill=Dr.rgba(self.st.get("stroke_color") or (20, 20, 20)),
                               keywords=self.st.get("keywords") or None, max_w=int(maxw), pad=8,
                               shadow_alpha=150 if stroke else 0)
            if self.st.get("box"):
                from PIL import Image
                bg = Dr.rounded_rect((im.width + 24, im.height + 8), int(size * 0.3),
                                     Dr.rgba(self.st.get("box_color") or (0, 0, 0), 150))
                bg.alpha_composite(im, (12, 4))
                im = bg
                del Image
            self.cache[key] = np.asarray(im)
        return self.cache[key]

    paper_rgb = None

    def draw(self, img, t):
        from vstudio.subs import CUE_FADE, cue_opacity
        for k, (a, b, text) in enumerate(self.cues):    # eased, crossfading cues (no caption blink)
            if a - CUE_FADE <= t < b + CUE_FADE and cue_opacity(a, b, t) > 0:
                if self.band_rect:
                    x0, y0, x1, y1 = self.band_rect
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                elif self.mask_rect:
                    x0, y0, x1, y1 = self.mask_rect
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                else:
                    pos = self.st.get("position") or "bottom"
                    x0, y0, x1, y1 = self.box
                    cx = (x0 + x1) / 2
                    cy = {"bottom": (y0 + y1) / 2, "middle": self.H * 0.6, "top": self.H * 0.22}.get(
                        pos, float(self.st.get("y") or 0.8) * self.H)
                sf = self._surface(img, cx, cy)
                if sf == "paper" and self.paper_rgb is None:
                    h = int(self.H * 0.05)
                    roi = img[max(0, int(cy - h)):int(cy + h), int(self.W * 0.1):int(self.W * 0.9)]
                    if roi.size:
                        self.paper_rgb = tuple(int(v) for v in np.median(roi.reshape(-1, 3), axis=0)[::-1])
                L = self.layer(k, text, sf)
                h, w = L.shape[:2]
                if not self.band_rect and not self.mask_rect and (self.st.get("position") or "bottom") == "bottom":
                    cy = min(cy, self.box[3] - h / 2)
                self.Dr.alpha_paste(img, L, (cx, cy), opacity=cue_opacity(a, b, t), center=True, bgr=True)
        return img


def _title_layer(title, W, h_px, alpha=None):
    from vstudio import overlays as O
    im = O.title_band(str(title.get("text") or ""), W, h_px, color=title.get("color"),
                      band_color=title.get("band_color"), sub=title.get("sub") or None,
                      size=float(title.get("size") or 1.0), alpha=title.get("alpha") if alpha is None else alpha)
    return np.asarray(im)


def _flat(img, y, h, tol=6.0):
    """True when rows y..y+h of a BGR frame are one flat colour (a designed paper band, not video)."""
    roi = img[max(0, int(y)):int(y + h)]
    return bool(roi.size) and float(roi.reshape(-1, 3).std(axis=0).max()) < tol


def _band_layout(W, H, sw, sh, band_frac, title):
    """(video rect x, y, w, h on the canvas, top band rect, bottom band rect)."""
    top = int(H * 0.12) if title else 0
    bot = int(H * band_frac)
    avail_h = H - top - bot
    k = min(W / sw, avail_h / sh)
    vw, vh = int(sw * k) // 2 * 2, int(sh * k) // 2 * 2
    x = (W - vw) // 2
    y = top + (avail_h - vh) // 2
    return (x, y, vw, vh), (0, 0, W, top) if top else None, (0, y + vh, W, H)


def frame_pass(src, out, audio_wav, vis, tg, fps, quality, final_encode, beat):
    """The per-frame pass, drawn inside the output's theme (``theme`` op; None = the creator's default)."""
    from vstudio import theme as TH
    with TH.fallback(vis.get("fallback_theme")), TH.use(vis.get("theme")):
        return _frame_pass(src, out, audio_wav, vis, tg, fps, quality, final_encode, beat)


def _frame_pass(src, out, audio_wav, vis, tg, fps, quality, final_encode, beat):
    import cv2

    from vstudio import draw as Dr
    m = _media()
    info = m.probe(src)
    sw, sh = int(info["w"]), int(info["h"])
    W, H = tg["w"], tg["h"]
    n_total = max(1, int(round(float(info["duration"]) * fps)))
    safe = tuple(vis["safe"])
    layers = []
    for e in vis["layers"]:
        inst = dict(e, _chapters_edit=e.get("_chapters_edit") or [])
        L = FX.make_layer(inst, W if not FX.LAYERS[e["effect"]].camera else sw,
                          H if not FX.LAYERS[e["effect"]].camera else sh, safe if not FX.LAYERS[e["effect"]].camera else None)
        if L:
            layers.append((e["a"], e["b"], L))
    cams = [x for x in layers if x[2].camera]
    ovs = [x for x in layers if not x[2].camera]
    band = vis["band"]
    vid_rect = top_rect = bot_rect = None
    if band:
        vid_rect, top_rect, bot_rect = _band_layout(W, H, sw, sh, band["band"], bool(vis["title"]))
    mask = vis["mask"]
    mrect = None
    if mask:
        bx = mask["box"]
        mrect = (int(bx[0] * sw), int(bx[1] * sh), int(bx[2] * sw), int(bx[3] * sh))
    cap_mask_rect = None
    if mrect and not band:
        sx, sy = W / sw, H / sh
        cap_mask_rect = (mrect[0] * sx, mrect[1] * sy, mrect[2] * sx, mrect[3] * sy)
    caps = Captions(vis, W, H, tg.get("profile"), band_rect=bot_rect, mask_rect=cap_mask_rect) if vis["captions"] else None
    title = vis["title"]
    title_arr = title_y = None
    if title:
        if top_rect:
            title_arr = _title_layer(title, W, top_rect[3])
            title_y = 0
        else:
            hp = int(H * float(title.get("height") or 0.1))
            title_arr = _title_layer(title, W, hp)
            title_y = int(float(title["y"]) * H) if title.get("y") is not None else int(safe[1])
    title_flat = None
    cap_spans = [(a, b) for a, b, _ in (vis["captions"] or [])]
    ground = np.array(Dr.brand()["ground"][::-1], np.uint8)
    from vstudio import theme as TH
    _T = TH.current()
    band_paper = None if _T.get("band") == "blur" else np.array(TH.rgb(_T, "paper")[::-1], np.uint8)
    wm_draw = None
    if vis.get("watermark"):
        from vstudio import watermark as WM
        wm_draw = WM.overlay(WM.from_spec(vis["watermark"]), W, H, tg.get("profile"))

    dec = [m.ffmpeg_bin(), "-v", "error", "-i", src, "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    enc = [m.ffmpeg_bin(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", f"{fps:.6g}", "-i", "-"]
    has_a = audio_wav is not None
    if has_a:
        enc += ["-i", audio_wav, "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
    else:
        enc += ["-map", "0:v:0"]
    enc += _enc(quality, audio=has_a, final_encode=final_encode) + [out]
    pd = subprocess.Popen(dec, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    pe = subprocess.Popen(enc, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    fsz = sw * sh * 3
    i = 0
    try:
        while True:
            buf = pd.stdout.read(fsz)
            if len(buf) < fsz:
                break
            t = i / fps
            img = np.frombuffer(buf, np.uint8).reshape(sh, sw, 3).copy()
            if mrect and (mask.get("always", True) or any(a <= t < b for a, b in cap_spans)):
                x0, y0, x1, y1 = mrect
                roi = img[y0:y1, x0:x1]
                if roi.size:
                    if mask.get("style") == "solid":
                        img[y0:y1, x0:x1] = (roi.astype(np.float32) * 0.08 + ground * 0.92).astype(np.uint8)
                    else:
                        k = max(15, (min(roi.shape[:2]) // 3) | 1)
                        img[y0:y1, x0:x1] = (cv2.GaussianBlur(roi, (k, k), 0).astype(np.float32) * 0.55).astype(np.uint8)
            for a, b, L in cams:
                if a <= t < b:
                    L.draw(img, t - a, b - a)
            if band:
                x, y, vw, vh = vid_rect
                if band_paper is not None:
                    canvas = np.empty((H, W, 3), np.uint8)
                    canvas[:] = band_paper
                else:
                    small = cv2.resize(img, (max(2, W // 12), max(2, H // 12)), interpolation=cv2.INTER_AREA)
                    bg = cv2.GaussianBlur(cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR), (0, 0), 9)
                    canvas = (bg.astype(np.float32) * 0.35).astype(np.uint8)
                canvas[y:y + vh, x:x + vw] = cv2.resize(img, (vw, vh), interpolation=cv2.INTER_AREA)
                img = canvas
            elif (sw, sh) != (W, H):
                img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
            for a, b, L in ovs:
                if a <= t < b or (L.__class__.__name__ == "Progress" and a <= t <= b + 1.0):
                    L.draw(img, t - a, b - a)
            if title_arr is not None:
                if title_flat is None:                     # over a flat area (a master's own paper band): text only,
                    title_flat = _flat(img, title_y, title_arr.shape[0]) and not title.get("band_color") and not top_rect
                    if title_flat:                         # so no band edge shows against the master's paper
                        title_arr = _title_layer(title, W, title_arr.shape[0], alpha=0)
                Dr.alpha_paste(img, title_arr, (0, title_y), bgr=True)
            if caps:
                caps.draw(img, t)
            if wm_draw:
                wm_draw(img)
            for dp in vis["dips"]:
                u = abs(t - dp["t"]) / max(0.05, dp["d"] / 2)
                if u < 1:
                    k = 1 - u
                    col = 255.0 if dp["color"] == "white" else 0.0
                    img[:] = (img.astype(np.float32) * (1 - k) + col * k).astype(np.uint8)
            pe.stdin.write(img.tobytes())
            i += 1
            if i % 30 == 0:
                beat(i / n_total)
    except BrokenPipeError:
        pass
    finally:
        try:
            pe.stdin.close()
        except BrokenPipeError:
            pass
        pd.stdout.close()
        pd.wait()
        for _a, _b, L in layers:                       # trackers / models a layer holds (skin smoothing)
            getattr(L, "close", lambda: None)()
        err = pe.stderr.read().decode(errors="replace")
        rc = pe.wait()
    if rc != 0 or i == 0:
        raise RuntimeError(f"frame pass failed (encoder exit {rc}, {i} frames): {err[-400:]}")
    return out


def run_remux(picture, out, audio_wav):
    """The original output's video stream + the new audio stem (AAC); no frame is decoded."""
    m = _media()
    if not audio_wav:
        shutil.copy(picture, out)
        return out
    from vstudio import audio as A
    m.run(["ffmpeg", "-y", "-v", "error", "-i", picture, "-i", audio_wav, "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "copy", "-c:a", "aac", "-b:a", A._persona_export_bitrate(), "-ar", str(A.SR), "-shortest",
           "-movflags", "+faststart", out])
    return out


def run_encode(src, out, audio_wav, quality, final_encode, tg, wm=None):
    """Plain encode (+ scale to the target canvas); ``wm`` (a watermark spec) is laid over in the same pass."""
    m = _media()
    info = m.probe(src)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", src]
    vf = f"scale={tg['w']}:{tg['h']}:flags=lanczos,setsar=1" if (int(info["w"]), int(info["h"])) != (tg["w"], tg["h"]) \
        else None
    with tempfile.TemporaryDirectory(prefix="voutwm-") as td:
        if wm:
            from vstudio import watermark as WM
            png, x, y = WM.write_png(WM.from_spec(wm), tg["w"], tg["h"], tg.get("profile"), os.path.join(td, "wm.png"))
            k = 2 if audio_wav else 1
            cmd += (["-i", audio_wav] if audio_wav else []) + ["-i", png, "-filter_complex",
                                                               f"[0:v:0]{vf or 'null'}[b];" + WM.ffmpeg_overlay("[b]", k, x, y),
                                                               "-map", "[v]"]
            cmd += ["-map", "1:a:0", "-shortest"] if audio_wav else []
        else:
            if audio_wav:
                cmd += ["-i", audio_wav, "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
            else:
                cmd += ["-map", "0:v:0"]
            if vf:
                cmd += ["-vf", vf]
        cmd += _enc(quality, audio=bool(audio_wav), final_encode=final_encode) + [out]
        m.run(cmd)
    return out


# --------------------------------------------------------------------------- render
def _cache(doc, stage, key, ext):
    d = os.path.join(doc.dir, "cache")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{stage}-{key}{ext}")


def _gc(doc, stage, keep_path):
    d = os.path.join(doc.dir, "cache")
    rows = sorted((os.path.getmtime(os.path.join(d, f)), f) for f in os.listdir(d) if f.startswith(stage + "-"))
    for _, f in rows[:-KEEP_PER_STAGE]:
        p = os.path.join(d, f)
        if p != keep_path:
            try:
                os.remove(p)
            except OSError:
                pass


def _stage(doc, stages, stage, key, ext, fn, st_obj):
    path = _cache(doc, stage, key, ext)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        os.utime(path)
        stages.append(dict(stage=stage, key=key, cached=True, seconds=0.0, file=path))
        return path
    st_obj.beat(stage)
    t0 = time.time()
    # a part file of its own: two renders of the same stage (two windows, a CLI next to the app) wrote one shared
    # ".part" - the loser's faststart failed and the winner's rename cached a file without its index (N/A length)
    tmp = f"{path}.{os.getpid()}-{threading.get_ident()}.part{ext}"
    try:
        fn(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    stages.append(dict(stage=stage, key=key, cached=False, seconds=round(time.time() - t0, 2), file=path))
    _gc(doc, stage, path)
    return path


def manifest_path(doc):
    return os.path.join(doc.dir, "renders", "manifest.json")


def render_status(rec, doc, st):
    """Existing renders of the output and whether each is fresh (its key matches the current edit state). ``key``
    names the content: every render replaces ``renders/<target>.<quality>.mp4`` in place, so a player keys its media
    URL on it (a browser keeps a URL's bytes for minutes and would mix the old file into the new one)."""
    man = read_json(manifest_path(doc), {}) or {}
    out = []
    for tg in targets_of(rec, st):
        for q in QUALITIES:
            r = (man.get("renders") or {}).get(f"{tg['target']}.{q}")
            if not r:
                continue
            key = plan(rec, doc, st, tg, q)["final"]["key"]
            out.append(dict(target=tg["target"], quality=q, file=r["file"], exists=os.path.exists(r["file"]),
                            cover=r.get("cover"), fresh=r.get("key") == key and os.path.exists(r["file"]), at=r.get("at"),
                            duration=r.get("duration"), key=r.get("key")))
    return out


def fresh_finals(d, output):
    """The output as it should be published: its edit's FINAL renders that are fresh (key = the current edit state)
    -> {target: {file, cover, w, h, duration}} ({} when it was never edited, or edited since its last render - the
    original file / a stale render must not go out as if it were the edit; ``key`` versions the file, see
    render_status). Reads only the edit doc + the render
    manifest (no media work)."""
    rec, doc = OUT._load(d, output)
    if not doc.d.get("steps"):
        return {}
    st = doc.state()
    OUT._effective(rec, doc, st)
    man = (read_json(manifest_path(doc), {}) or {}).get("renders") or {}
    out = {}
    for tg in targets_of(rec, st):
        r = man.get(f"{tg['target']}.final")
        if not r or not os.path.exists(r.get("file") or ""):
            continue
        if r.get("key") != plan(rec, doc, st, tg, "final")["final"]["key"]:
            continue
        out[tg["target"]] = dict(file=r["file"], cover=r.get("cover") if r.get("cover") and os.path.exists(r["cover"])
                                 else None, w=tg["w"], h=tg["h"], duration=r.get("duration"), key=r.get("key"))
    return out


def render(d, output, quality="preview", targets=None, on_event=None, with_ops=None, watermark=None):
    """Render the output's current edit (preview or final) for ``targets`` (default primary; "all" = primary +
    every export). -> {ok, output, quality, targets [{target, file, cover, canvas, duration, key, cached, stages
    [{stage, key, cached, seconds}], warnings}], seconds}.

    ``with_ops``: a before / after preview of ops that are NOT applied (cuts, speed: what the player cannot fake):
    the ops are validated like ``edit`` against the current state, rendered at preview quality into
    ``renders/<target>.compare.mp4``; edit.json and the render manifest are not touched.

    ``watermark``: the creator's watermark on a final render (True / False; None = her default, vstudio.watermark)."""
    if quality not in QUALITIES:
        raise OUT.OutputError("bad-param", f"quality: {' | '.join(QUALITIES)}", "质量只能是 preview / final",
                              name="quality", value=quality)
    rec, doc = OUT._load(d, output)
    st = doc.state()
    compare = with_ops is not None
    if compare:
        if quality != "preview":
            raise OUT.OutputError("bad-param", "--with-ops renders a preview only", "对比预览只能是 preview 质量",
                                  name="quality", value=quality)
        ops = [with_ops] if isinstance(with_ops, dict) else with_ops
        if not isinstance(ops, list) or not ops:
            raise OUT.OutputError("no-ops", "--with-ops needs a JSON op or list of ops", "需要 --with-ops 操作")
        step, _, _ = OUT.apply_ops(doc, ops, dry=True)
        for n in step["ops"]:
            st = OUT.fold(st, n)
    tgs = targets_of(rec, st, targets or ["primary"])
    status = Status(rec, doc)
    t_all = time.time()
    results = []
    emit = on_event or (lambda ev: None)
    ok = False
    try:
        for n_t, tg in enumerate(tgs):
            emit(dict(event="target-start", target=tg["target"], quality=quality))
            p = plan(rec, doc, st, tg, quality, watermark=watermark)
            stages, warns = [], []
            work = tempfile.mkdtemp(prefix="voutedit-")
            try:
                src = p["canvas"]["src"]
                if p.get("splice"):                    # swapped shots: the file with their new takes, first
                    src = _stage(doc, stages, "splice", p["splice"]["key"], ".mp4",
                                 lambda o: run_pieces(p["splice"], p["splice"]["src"], o, quality, work), status)
                    emit(dict(event="stage-done", target=tg["target"], **{k: v for k, v in stages[-1].items()
                                                                          if k != "file"}))
                if p["canvas"]["op"] == "sources":
                    src = _stage(doc, stages, "canvas", p["canvas"]["key"], ".mp4",
                                 lambda o: run_pieces(dict(p["canvas"], w=tg["w"], h=tg["h"]), p["canvas"]["src"], o,
                                                      quality, work), status)
                    emit(dict(event="stage-done", target=tg["target"], **{k: v for k, v in stages[-1].items()
                                                                          if k != "file"}))
                elif p["canvas"]["op"] != "none":
                    src = _stage(doc, stages, "canvas", p["canvas"]["key"], ".mp4",
                                 lambda o, s0=src: run_canvas(dict(p["canvas"], src=s0), o, quality,
                                                              p["canvas"]["safe"]), status)
                    emit(dict(event="stage-done", target=tg["target"], **{k: v for k, v in stages[-1].items()
                                                                          if k != "file"}))
                if p["timeline"]["op"] != "none":
                    src = _stage(doc, stages, "timeline", p["timeline"]["key"], ".mp4",
                                 lambda o, s=src: run_timeline(p["timeline"], s, o, quality, work), status)
                    emit(dict(event="stage-done", target=tg["target"], **{k: v for k, v in stages[-1].items()
                                                                          if k != "file"}))
                wav = None
                if p["audio"]["op"] != "none":
                    wav = _stage(doc, stages, "audio", p["audio"]["key"], ".wav",
                                 lambda o, s=src: run_audio(p["audio"], s, o, p["timeline"]["duration"], work), status)
                    emit(dict(event="stage-done", target=tg["target"], **{k: v for k, v in stages[-1].items()
                                                                          if k != "file"}))
                fps = _media().probe(src)["fps"] or rec["info"]["fps"]

                def fin(o, s=src, w=wav):
                    if p["final"]["op"] == "remux":
                        run_remux(rec["file"], o, w)
                    elif p["final"]["op"] == "frames":
                        frame_pass(s, o, w, p["final"]["visual"], tg, fps, quality, p["final"]["encode"],
                                   lambda prog: status.beat("frames", progress=round((n_t + prog) / len(tgs), 3)))
                    else:
                        run_encode(s, o, w, quality, p["final"]["encode"], tg, wm=p["final"]["visual"].get("watermark"))
                    return o
                fpath = _stage(doc, stages, "final", p["final"]["key"], ".mp4", fin, status)
                emit(dict(event="stage-done", target=tg["target"], **{k: v for k, v in stages[-1].items() if k != "file"}))
                cpath = None
                if p["cover"]:
                    cpath = _stage(doc, stages, "cover", p["cover"]["key"], ".jpg",
                                   lambda o, s=src: run_cover(p["cover"], s, o, rec["mode"]), status)
            finally:
                shutil.rmtree(work, ignore_errors=True)
            rdir = os.path.join(doc.dir, "renders")
            os.makedirs(rdir, exist_ok=True)
            name = tg["target"].replace(":", "-")
            dst = os.path.join(rdir, f"{name}.{'compare' if compare else quality}.mp4")
            _link(fpath, dst)
            cdst = None
            if cpath and not compare:
                cdst = os.path.join(rdir, f"{name}.cover.jpg")
                _link(cpath, cdst)
            info = _media().probe(dst)
            if rec["mode"] == "flattened" and tg["target"] != "primary" and tg["layout"] == "auto":
                warns.append(OUT.msg("relayout-crops-burned", "re-layout of a flattened file: check that no burned "
                                     "text is cropped (layout band keeps the whole frame)",
                                     "成片重新构图：检查烧录文字是否被裁掉", target=tg["target"]))
            if quality == "final" and not compare:
                warns.extend(flicker_notes(dst, tg["target"]))
            if tg.get("profile") is not None:
                from vstudio import platform as P
                for w in P.check_length(tg["profile"], info["duration"]):
                    warns.append(OUT.msg("length", w, None, target=tg["target"]))
            res = dict(target=tg["target"], quality=quality, file=dst, cover=cdst, canvas=[tg["w"], tg["h"]],
                       layout=tg["layout"], duration=round(info["duration"], 3), key=p["final"]["key"],
                       watermark=bool(p["final"]["visual"].get("watermark")),
                       cached=all(s["cached"] for s in stages), stages=[{k: v for k, v in s.items() if k != "file"}
                                                                        for s in stages], warnings=warns)
            results.append(res)
            if compare:
                res["compare"] = True
                emit(dict(event="target-done", **{k: v for k, v in res.items() if k != "stages"}))
                continue
            man = read_json(manifest_path(doc), {}) or {}
            man.setdefault("renders", {})[f"{tg['target']}.{quality}"] = dict(file=dst, cover=cdst, key=res["key"],
                                                                             at=OUT._stamp(),
                                                                             duration=res["duration"],
                                                                             steps=len(doc.d["steps"]))
            man["output"] = rec["id"]
            write_json(manifest_path(doc), man)
            emit(dict(event="target-done", **{k: v for k, v in res.items() if k != "stages"}))
        ok = True
    except OUT.OutputError:
        raise
    except Exception as e:  # noqa: BLE001
        raise OUT.OutputError("render-failed", f"render failed: {str(e)[:300]}", "渲染失败", error=str(e)[:300]) from e
    finally:
        status.end(ok)
    return dict(ok=True, output=rec["id"], mode=rec["mode"], quality=quality, targets=results,
                seconds=round(time.time() - t_all, 2), edit_dir=doc.dir, compare=compare)


def flicker_notes(path, target):
    """vstudio.flicker on a final render -> [warning]. An output edit is her own choice of transitions / effects, so a
    flicker is reported (code ``flicker``, with the times), never a failed render; ``qc.flicker: off`` skips it."""
    from vstudio import flicker
    if flicker.mode_for() == "off":
        return []
    try:
        rep = flicker.analyze(path)
    except Exception:  # noqa: BLE001 - QC never breaks a render
        return []
    if rep["ok"]:
        return []
    at = ", ".join(f"{e['t']:.1f}s" for e in rep["events"][:6])
    return [OUT.msg("flicker", flicker.describe(rep), "成片有闪烁（" + at + "）", target=target, what=at)]


def _link(src, dst):
    if os.path.exists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)
