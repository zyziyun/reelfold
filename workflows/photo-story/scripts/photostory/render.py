#!/usr/bin/env python3
"""Render a photo-story spec to MP4: picture box (shots + overlays + transitions + film look),
running header with section progress, chapter cards, bilingual subtitles, voice + music mix.

    python3 render.py spec.py --stills 3,12.5,40        # JPEG stills (1/3 size; --full = full size)
    python3 render.py spec.py --preview 20 --from 60    # 20 s preview from 60 s -> cache/preview.mp4
    python3 render.py spec.py                           # full render -> spec OUT
    python3 render.py spec.py --platform douyin         # re-lay the story for another platform's canvas / safe zones
    python3 render.py spec.py --clean-master            # no burned subtitles + <out>.cues.json (for vstudio.export)

MODE = "music" in the spec (or --mode music): the BGM drives the timeline (cuts on bars/beats, see music.py).
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
import json
import os
import subprocess
import tempfile

import numpy as np
from PIL import Image

from vstudio import audio, media
from vstudio import platform as vplat
from vstudio.config import persona
from vstudio.subs import strip_markup

from photostory import overlays as ov
from photostory import audiomix
from photostory.ctx import Ctx, check_profile, load_spec
from photostory.looks import film_look
from photostory.shots import build, parse_src
from photostory.subtitles import (Header, make_chapter, make_label, make_sub, make_title_card, make_title_text,
                                  sub_backdrop)
from photostory.timeline import Timeline, load_timing, place_voice
from photostory.transitions import transition
from photostory.util import ease, paste_rgba


def prepare(spec_path, platform=None, mode=None):
    spec = load_spec(spec_path)
    if platform:
        spec.PLATFORM = platform
    if mode:
        spec.MODE = mode
    C = Ctx(spec)
    if C.MODE == "music":
        from photostory.music import MusicTimeline
        T = MusicTimeline(C)
        finish(C, T)
        return C, T, True
    timing, has_audio = load_timing(C)
    T = Timeline(C, timing)
    finish(C, T)
    return C, T, has_audio


def finish(C, T):
    """Per-shot decisions that need the shots' pictures: a dissolve that would ghost two framings of one subject
    becomes a cut (photostory/dissolves.py), and each shot's colour LUT (photostory/grade.py)."""
    from photostory import dissolves, grade
    dissolves.plan(C, T)
    grade.plan(C, T)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="story spec .py (paths inside are relative to its folder)")
    ap.add_argument("--preview", type=float, help="render only this many seconds")
    ap.add_argument("--from", dest="t_from", type=float, default=0.0, help="start time (s)")
    ap.add_argument("--stills", help="comma-separated times (s): write JPEG stills instead of a video")
    ap.add_argument("--full", action="store_true", help="stills at full canvas size (default 1/3)")
    ap.add_argument("--stills-dir", default=None, help="where stills go (default <spec dir>/stills)")
    ap.add_argument("--out", default=None, help="output mp4 (default spec OUT, or cache/preview.mp4 for --preview)")
    ap.add_argument("--platform", help="override spec PLATFORM, e.g. xiaohongshu:vertical, douyin, youtube")
    ap.add_argument("--mode", choices=["narration", "music"], help="override spec MODE")
    ap.add_argument("--clean-master", action="store_true",
                    help="do not burn subtitles/title text; write <out>.cues.json for python -m vstudio.export")
    a = ap.parse_args()

    C, T, has_audio = prepare(a.spec, a.platform, a.mode)
    print(f"canvas {C.W}x{C.H}{' (' + C.prof.key + ')' if C.prof is not None else ''}, header {C.HDR}, "
          f"box {C.BOX_W}x{C.BOX_H}, subs {C.SUB_H}@{C.SUB_Y0}{' (overlaid)' if C.overlay_subs else ''} | {T.summary()}")
    music_mode = C.MODE == "music"
    if music_mode:
        v = T.save(os.path.join(C.cache_dir, "music_cuts.json"), C.FPS)
        print(f"beats.verify: {'ok' if v['ok'] else 'BAD ' + str(v['bad'])}, max {v['max_abs_frames']:.2f} frames, "
              f"mean {v['mean_abs_ms']:.1f} ms over {len(T.cuts)} cuts")
    cp = check_profile(C)
    for w in (vplat.check_length(cp, T.total) if cp is not None else []):
        print("!", w)
    total = T.total
    t_from = a.t_from
    end_t = min(total, t_from + a.preview) if a.preview else total

    header = Header(C) if C.HDR > 0 else None
    title_card = make_title_card(C) if header is None and getattr(C.spec, "TITLE_CARD", True) else None
    chapters = {s: make_chapter(C, s) for s in range(1, len(C.SECTIONS))}
    for s in T.subs:
        s["_lay"] = (make_title_text if s.get("style") == "title" else make_sub)(C, s["en"], s["zh"])
    for sh in T.shots:
        if "label" in sh and not sh["src"].startswith("split:") and C.shown(sh["label"]):
            sh["_lab"] = make_label(C, sh["label"])       # a label with nothing in this version's language: none
        sh["_video"] = parse_src(C, sh["src"])[0] == "video"
    backdrop = sub_backdrop(C) if C.overlay_subs and getattr(C.spec, "SUB_BACKDROP", True) else None
    chap_len = float(getattr(C.spec, "CHAPTER_CARD", 2.2) or 0)
    end_fade = T.pace["end_fade"]

    stills = [float(x) for x in a.stills.split(",")] if a.stills else None
    if stills and any(t >= total for t in stills):   # past the end = a black (faded) frame, not a layout check
        print(f"! stills past the end ({total:.1f}s) skipped: {[t for t in stills if t >= total]}")
        stills = [t for t in stills if t < total] or [max(0.0, total - 1.0)]
    enc = None
    vid_tmp = os.path.join(C.cache_dir, "video_fx.mp4")
    if stills:
        sdir = a.stills_dir or C.path("stills")
        os.makedirs(sdir, exist_ok=True)
        frames = [int(t * C.FPS) for t in stills]
    else:
        enc = subprocess.Popen([media.ffmpeg_bin(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", f"{C.W}x{C.H}", "-r", str(C.FPS), "-i", "-",
                                "-vf", "scale=out_color_matrix=bt709:out_range=tv",   # matches the bt709 tags
                                *media.delivery_args(audio=False, faststart=False), vid_tmp], stdin=subprocess.PIPE)
        frames = range(int(t_from * C.FPS), int(end_t * C.FPS))

    live, shots = {}, T.shots
    for fi in frames:
        gt = fi / C.FPS
        need = [k for k, sh in enumerate(shots) if sh["start"] <= gt < sh["end"] + sh["tail"]] or [len(shots) - 1]
        for k in list(live):
            if k not in need:
                del live[k]
        for k in need:
            if k not in live:
                live[k] = build(C, shots[k], k)
        k = max(need)                                  # current shot = the latest one that started
        sh = shots[k]
        N = live[k].frame(gt - sh["start"])
        N = ov.overlays(C, sh, N.copy() if sh["_video"] else N, gt - sh["start"])
        if k - 1 in live and gt - sh["start"] < sh["trd"]:
            pv = shots[k - 1]
            P = live[k - 1].frame(gt - pv["start"])
            P = ov.overlays(C, pv, P.copy() if pv["_video"] else P, gt - pv["start"])
            box = transition(C, P, N, (gt - sh["start"]) / sh["trd"], sh["tr"])
        else:
            box = N.copy()
        sec = T.section_at(gt)
        box = film_look(C, box, gt, sec in C.FILM_SECTIONS or sh["src"].startswith("film:"))
        if "_lab" in sh:                               # picture label, bottom-left (upper-left: label_at="upper",
            fl = 0.6 if C.cinema else 0.3              # where the shot plan found room above the subject)
            la = ease(min(1, (gt - sh["start"] - 0.45) / fl, (sh["end"] - gt) / fl))
            if la > 0:
                m = C.b(44)
                lab_y = C.LAB_BOT - m - sh["_lab"].shape[0]
                if sh.get("label_at") == "upper":            # under the platform's top safe line
                    lab_y = max(m, C.SAFE[1] - C.HDR + m)
                rise = int((1 - la) * C.b(12)) if C.cinema else 0     # cinema: a quiet 12 px settle as it fades in
                paste_rgba(box, sh["_lab"], max(m, C.SAFE[0]), lab_y + rise, la)
        if chap_len and sec >= 1 and gt - T.sec_bounds[sec] < chap_len:     # chapter card
            lt = gt - T.sec_bounds[sec]
            fi, fo = (0.6, 0.7) if C.cinema else (0.3, 0.45)
            ca = ease(min(1, lt / fi, (chap_len - lt) / fo))
            paste_rgba(box, chapters[sec], 0, int((1 - ca) * C.b(16)) if C.cinema and lt < fi else 0, ca)
        if title_card is not None and gt < TITLE_HOLD[1]:                    # cinema: the film's title, once
            ta = ease(min((gt - TITLE_HOLD[0]) / 0.9, (TITLE_HOLD[1] - gt) / 0.9))
            if ta > 0:
                paste_rgba(box, title_card, 0, 0, ta)
        frame = C.BG.copy()
        frame[C.HDR:C.HDR + C.BOX_H] = box
        if header is not None:
            header.draw(frame, sec, gt, T.sec_bounds)
        cue = [] if a.clean_master else [s for s in T.subs if s["start"] <= gt < s["end"]]
        if backdrop is not None and not a.clean_master:
            ba = backdrop_alpha(T.subs, gt)
            if ba > 0:
                paste_rgba(frame, backdrop, 0, C.H - backdrop.shape[0], ba)
        for s in cue:
            paste_rgba(frame, s["_lay"], 0, C.SUB_Y0, cue_alpha(s, gt))
        if gt > total - end_fade:
            frame *= max(0, (total - gt) / end_fade)
        img = np.clip(frame, 0, 255).astype(np.uint8)
        if stills:
            im = Image.fromarray(img)
            if not a.full:
                im = im.resize((C.W // 3, C.H // 3), Image.LANCZOS)
            p = os.path.join(sdir, f"st_{gt:06.1f}.jpg")
            im.save(p, quality=90)
            print("still", p)
            continue
        enc.stdin.write(img.tobytes())
        if fi % (C.FPS * 30) == 0:
            print(f"  {gt:6.1f}s / {end_t:.1f}s", flush=True)
    if stills:
        return
    enc.stdin.close()
    enc.wait()
    out = a.out or (os.path.join(C.cache_dir, "preview.mp4") if a.preview else C.path(getattr(C.spec, "OUT", "out/story.mp4")))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    mix_audio(C, T, t_from, end_t, vid_tmp, out)
    if not a.preview and not t_from:
        write_edl(C, T, out)
    if not a.preview:
        from vstudio import flicker
        try:
            flicker.check(out, "energetic" if C.MODE == "music" else "calm",
                          flicker.mode_for({"qc": getattr(C.spec, "QC", None) or {}}))
        except flicker.FlickerError as e:
            sys.exit(f"!! render failed - {e}")
    if a.clean_master:
        from vstudio.subs import Cue
        cues = [Cue(s["start"] - t_from, s["end"] - t_from, strip_markup(s["zh"] or ""), strip_markup(s["en"] or "")).to_dict()
                for s in T.subs if s["end"] > t_from and s["start"] < end_t]
        cp_ = os.path.splitext(out)[0] + ".cues.json"
        json.dump(cues, open(cp_, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("cues:", cp_, f"({len(cues)})  ->  python3 -m vstudio.export {out} --platforms ... --cues {cp_}")


def write_edl(C, T, out):
    """``<out>.edl.json``: the story's per-shot source edit list - where each shot sits (from the middle of the join
    into it), which file it shows (a clip and its in-point, or a still), its join and label place, and the editor
    brain's shot id when the spec came from its plan (``brain``)."""
    rows = []
    n = len(T.shots)
    for k, sh in enumerate(T.shots):
        kind, arg = parse_src(C, sh["src"])
        src = None
        try:
            src = C.find_video(arg) if kind == "video" else (C.find_image(arg) if kind == "img" else None)
        except Exception:  # noqa: BLE001  (a composite shot: no single source)
            src = None
        t0 = 0.0 if k == 0 else sh["start"] + (sh.get("trd") or 0) / 2
        t1 = T.total if k == n - 1 else T.shots[k + 1]["start"] + (T.shots[k + 1].get("trd") or 0) / 2
        off = float(sh.get("off", 0.0) or 0.0)
        sp = float(sh.get("speed", 1.0) or 1.0)
        rows.append(dict(i=k, t0=round(t0, 3), t1=round(t1, 3), src=os.path.realpath(src) if src else None,
                         kind=kind, name=arg, src_in=round(off, 3) if kind == "video" else None,
                         src_out=round(off + (t1 - t0) * sp, 3) if kind == "video" else None, speed=sp,
                         join=None if k == 0 else ("dissolve" if sh.get("tr") == "fade" else sh.get("tr")),
                         join_s=round(float(sh.get("trd") or 0), 3), label=sh.get("label"),
                         label_at=sh.get("label_at"), brain=sh.get("brain")))
    with open(os.path.splitext(out)[0] + ".edl.json", "w", encoding="utf-8") as f:
        json.dump(dict(version=1, builder="photo-story", duration=round(T.total, 3), shots=rows), f,
                  ensure_ascii=False, indent=1)


TITLE_HOLD = (0.6, 5.2)    # cinema title card: on screen between these times (eased in and out)


def cue_alpha(s, gt):
    """Keep spoken text legible; only decorative music titles fade."""
    from vstudio.subs import cue_opacity
    if s.get("style") == "title":
        return min(1.0, max(0.0, (gt - s["start"]) / 0.6), max(0.0, (s["end"] - gt) / 0.6))
    return cue_opacity(s["start"], s["end"], gt)


def backdrop_alpha(subs, gt, lead=0.5, hold=0.9):
    """The shade behind overlaid subtitles: eased in ``lead`` s before a cue, kept through gaps shorter than
    ``hold`` s, eased out after - it never pops on and off with every cue."""
    best = 0.0
    for s in subs:
        if s.get("style") == "title":
            continue
        a = (gt - (s["start"] - lead)) / lead
        b = ((s["end"] + hold) - gt) / lead
        best = max(best, min(1.0, a, b))
        if best >= 1.0:
            break
    return ease(best)


def mix_audio(C, T, t0, t1, vid, out):
    """Voice units placed on the timeline (+ optional looping music bed via ``audio.mix_bed``), two-pass
    loudnorm to persona audio.loudness_lufs, muxed onto the silent picture track."""
    P = persona()
    lufs = C.LUFS
    abr = getattr(C.spec, "AUDIO_BITRATE", None) or (P.get("export") or {}).get("audio_bitrate", "192k")
    with tempfile.TemporaryDirectory(dir=C.cache_dir) as tmp:
        vo = place_voice(C, T, t0, t1, os.path.join(tmp, "voice.wav"))
        mix = os.path.join(tmp, "mix.wav")
        bgm = C.path(getattr(C.spec, "BGM", None))
        if bgm and not os.path.exists(bgm):
            print(f"! BGM not found: {bgm} - rendering without music")
            bgm = None
        music_mode = C.MODE == "music"
        if music_mode or any(str(sh.get("audio", "mute")).lower() not in ("mute", "none", "off", "false")
                             for sh in T.shots):
            _, clips = audiomix.mix(C, T, t0, t1, mix, voice_wav=None if music_mode else vo, music=bgm,
                                    music_mode=music_mode)
            for c in clips:
                print(f"clip audio: {c['shot']} {c['mode']} {c['gain']:+.0f} dB at {c['start']:.2f}s for {c['dur']:.2f}s")
        elif bgm:
            if hasattr(C.spec, "BGM_VOLUME") and not hasattr(C.spec, "BGM_LUFS"):
                print("note: BGM_VOLUME is no longer used; the bed is set by loudness "
                      "(BGM_LUFS, default persona audio.music_lufs -30)")
            audio.mix_bed(vo, bgm, mix, duck_db=float(getattr(C.spec, "BGM_DUCK", 0) or 0),
                          music_lufs=getattr(C.spec, "BGM_LUFS", None), lufs=lufs,
                          fade_in=2.0, fade_out=3.5, music_start=t0)
        else:
            audio.loudnorm_2pass(vo, mix, lufs=lufs, tp=C.TP)
        media.run(["ffmpeg", "-y", "-i", vid, "-i", mix, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                   "-c:a", "aac", "-b:a", str(abr), "-ar", str(audio.SR), "-ac", "2",
                   "-movflags", "+faststart", "-shortest", out])
    print("output:", out)


if __name__ == "__main__":
    main()
