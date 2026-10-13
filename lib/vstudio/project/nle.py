"""A clip's edit for an editing program: Premiere Pro / DaVinci Resolve (FCP7 XML, ``xmeml`` v4), 剪映 / CapCut
drafts and OpenTimelineIO. The edit of a finished clip (``outputs``: trim, cuts, speed, loudness, captions, music
bed) becomes a timeline that points at the clip's own media, so an editor can go on cutting where Reelfold stopped.

    python -m vstudio.project output nle --project P --output O --format xmeml|jianying|capcut|otio
        [--out DIR] [--media link|copy] [--to-app] [--json]
    python -m vstudio.project output nle --project P --all --format xmeml ...      # every clip of the project
    python -m vstudio.project output nle-relink --out EXPORT --media-dir NEW_FOLDER # media moved: point at it

    from vstudio.project import nle
    tl = nle.plan(rec, doc, st)                  # the timeline as a table (frames), checkable on its own
    xml = nle.xmeml(tl); info, meta = nle.jianying_draft(tl, ...); doc = nle.otio(tl)

What goes over (a table in references/OUTPUT_EDIT.md section 8):
  * the picture: the clean master when the pipeline kept one (captions are then a track of their own), else the
    finished file (its burned captions come with it); a pickup's spliced file when there is one;
  * every kept piece (trim minus cuts) as its own clip, back to back; frames rounded edge by edge (a clip starts at
    round(t * fps) and ends at round(t_end * fps), so two neighbours share their cut and there is never a 1-frame gap);
  * speed: xmeml Time Remap, 剪映 segment speed, OTIO LinearTimeWarp;
  * sound linked to its picture, its level = the loudness the edit asked for (or the platform's) over what the source
    measures (+12 dB at most); a music bed on a track of its own at its level;
  * captions: 剪映 / CapCut text clips; xmeml and OTIO get an SRT next to the file (File > Import in Premiere /
    Resolve makes it a caption track) and OTIO markers;
  * what an editor cannot be told (overlays, title band, transitions, grade, cover) is listed in ``notes``.
Media: ``link`` points at the files where they are; ``copy`` puts an APFS clone / copy of each into ``media/`` next
to the timeline (one folder to hand to an editor). ``relink`` re-points an export at a folder the media moved to.

Ported from OpenFilm (github.com/openfilm/openfilm, MIT, Copyright (c) OpenFilm contributors):
``studio/server/nle.mjs`` (frame rounding edge by edge, xmeml file / clip / link / Audio Levels / rate writing) and
``studio/server/jianying.mjs`` (the 剪映 / CapCut draft: draft_info.json + draft_meta_info.json, microsecond times,
materials and the media library entries, subtitles as text clips). See THIRD_PARTY_NOTICES.md.
"""
import json
import math
import os
import re
import shutil
import subprocess
import time
import uuid
from urllib.parse import quote, unquote, urlparse

FORMATS = ("xmeml", "jianying", "capcut", "otio")
FORMAT_ALIASES = {"premiere": "xmeml", "resolve": "xmeml", "davinci": "xmeml", "fcp7": "xmeml", "xml": "xmeml",
                  "剪映": "jianying", "jy": "jianying", "opentimelineio": "otio"}
MAX_GAIN = 3.98109                   # +12 dB, the top of xmeml's Audio Levels
MUSIC_LEVEL = 0.25                   # a bed under the voice (-12 dB) when its own level is not known


class NleError(ValueError):
    def __init__(self, code, message, **params):
        super().__init__(message)
        self.code, self.params = code, params


def norm_format(f):
    f = str(f or "").strip().lower()
    f = FORMAT_ALIASES.get(f, f)
    if f not in FORMATS:
        raise NleError("unknown-format", f"unknown format {f!r}; formats: {', '.join(FORMATS)}", format=f)
    return f


# --------------------------------------------------------------------------- rate and frames
def rate_of(fps):
    """{fps, timebase, ntsc}: 29.97 -> 30 NTSC, 23.976 -> 24 NTSC, 59.94 -> 60 NTSC; other rates as they are."""
    fps = float(fps or 30.0)
    for nominal in (24, 30, 60, 120):
        if abs(fps - nominal * 1000 / 1001) < 0.01:
            return dict(fps=nominal * 1000 / 1001, timebase=nominal, ntsc=True)
    tb = max(1, int(round(fps)))
    return dict(fps=float(tb) if abs(fps - tb) < 0.01 else fps, timebase=tb, ntsc=False)


def frame(t, fps):
    return int(round(float(t) * fps + 1e-9))


# --------------------------------------------------------------------------- the plan
def _measured_lufs(path):
    try:
        from vstudio import audio
        v = audio.measure_loudness(path).get("input_i")
        return None if v is None or not math.isfinite(float(v)) else float(v)
    except Exception:  # noqa: BLE001  (no level is no reason to fail the export)
        return None


def _probe(path):
    from vstudio import media
    return media.probe(path)


def plan(rec, doc, st, measure=True, name=None):
    """The edit of one output as a timeline table -> {name, rate, width, height, duration, files, video, audio, cues,
    notes, source}. Frames are on the source's own rate."""
    from . import outputs as O
    pipe = rec["mode"] == "pipeline" and rec.get("master") and not st.get("base")
    src = rec["master"] if pipe else rec["file"]
    info = _probe(src)
    rate = rate_of(info.get("fps") or rec["info"].get("fps"))
    fps = rate["fps"]
    dur = float(rec["info"]["duration"])
    segs = O.segments(st, dur)
    speed = float(st.get("speed") or 1.0)
    w, h = int(info.get("w") or rec["info"]["w"]), int(info.get("h") or rec["info"]["h"])
    src_frames = max(1, frame(info.get("duration") or dur, fps))
    has_audio = bool(info.get("has_audio"))
    files = [dict(id="file-1", name=os.path.basename(src), path=os.path.abspath(src), duration=src_frames,
                  video=dict(w=w, h=h), audio=dict(channels=2, rate=48000) if has_audio else None)]
    # the level the edit asks for: its loudness op, else the platform's
    gain, notes = None, []
    want = (st.get("loudness") or {}).get("lufs")
    prof = rec.get("profile")
    if want is None and prof is not None and getattr(prof, "loudness", None):
        want = prof.loudness.get("lufs")
    if has_audio and want is not None and measure:
        got = _measured_lufs(src)
        if got is not None:
            gain = round(min(MAX_GAIN, 10 ** ((float(want) - got) / 20)), 4)
    # every kept piece, back to back; edges rounded once on the film's time so neighbours share their cut
    vclips, aclips, t = [], [], 0.0
    offs = []
    for k, (a, b) in enumerate(segs):
        offs.append(t)
        t1 = t + (b - a) / speed
        start, end = frame(t, fps), frame(t1, fps)
        if end <= start:
            t = t1
            continue
        fin = frame(a, fps)
        fout = min(src_frames, max(fin + 1, fin + int(round((end - start) * speed))))
        cid = f"clip-{k + 1}"
        link = f"link-{k + 1}" if has_audio else None
        vclips.append(dict(id=cid, name=f"{files[0]['name']} {k + 1}", file="file-1", start=start, end=end, cut_in=fin,
                           cut_out=fout, speed=speed, link=link, enabled=True))
        if has_audio:
            aclips.append(dict(id=f"{cid}-a", name=f"{files[0]['name']} {k + 1}", file="file-1", start=start, end=end,
                               cut_in=fin, cut_out=fout, speed=speed, link=link, gain=gain, enabled=True))
        t = t1
    total = frame(t, fps)
    video = [dict(name="V1", enabled=True, clips=vclips)]
    audio_tracks = [dict(name="A1", role="footage", enabled=True, clips=aclips)] if aclips else []

    def to_edit(x):
        for k, (a, b) in enumerate(segs):
            if a - 1e-6 <= x <= b + 1e-6:
                return offs[k] + (min(max(x, a), b) - a) / speed
        return None
    # captions: ours (the master's cues, her text) and the ones she added
    cues = []
    for r in O._cue_rows(rec, st):
        if r["removed"] or (not pipe and not r["added"]) or not str(r["text"]).strip():
            continue
        if not r["added"] and st["captions"].get("enabled") is False:
            continue
        a, b = to_edit(r["start"]), to_edit(r["end"])
        if a is None or b is None:                                   # partly cut: the kept part
            inside = [(max(r["start"], x), min(r["end"], y)) for x, y in segs if y > r["start"] and x < r["end"]]
            if not inside:
                continue
            a, b = to_edit(inside[0][0]), to_edit(inside[-1][1])
        if b - a >= 0.1:
            cues.append(dict(text=re.sub(r"[【】]", "", str(r["text"]).strip()), start=round(a, 3), end=round(b, 3)))
    # the music bed: its own track, at its level
    for e in st.get("effects") or []:
        p = e.get("params") or {}
        if e["effect"] == "music-bed" and p.get("file") and os.path.isfile(str(p["file"])):
            mi = _probe(p["file"])
            mf = dict(id=f"file-{len(files) + 1}", name=os.path.basename(p["file"]), path=os.path.abspath(p["file"]),
                      duration=max(1, frame(mi.get("duration") or 0, fps)), video=None, audio=dict(channels=2, rate=48000))
            files.append(mf)
            lvl = 10 ** (float(p["duck_db"]) / 20) if p.get("duck_db") not in (None, "") else MUSIC_LEVEL
            end = min(total, mf["duration"])
            if end > 0:
                audio_tracks.append(dict(name="Music", role="music", enabled=True, clips=[dict(
                    id="music-1", name=mf["name"], file=mf["id"], start=0, end=end, cut_in=0, cut_out=end, speed=1.0,
                    link=None, gain=round(min(MAX_GAIN, lvl), 4), enabled=True)]))
        elif e["effect"] != "music-bed":
            notes.append(f"effect {e['effect']} ({e['id']}) at {e['start']:g}s is drawn by Reelfold: not carried")
    if st.get("title"):
        notes.append("the title band is drawn by Reelfold: not carried")
    if O.joins(st, segs):
        notes.append("transitions at the cuts are not carried: the pieces are butt cuts")
    if not pipe and any(not r["added"] for r in O._cue_rows(rec, st)):
        notes.append("captions are burned into the picture of this clip (no clean master)")
    return dict(name=name or rec.get("title") or os.path.splitext(os.path.basename(rec["file"]))[0], rate=rate,
                width=w, height=h, duration=total, files=files, video=video, audio=audio_tracks, cues=cues,
                notes=notes, source=dict(file=src, mode="master" if pipe else "file", output=rec["id"]))


# --------------------------------------------------------------------------- xmeml (Premiere / Resolve)
def xml_escape(text):
    t = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t.replace("'", "&apos;"))


def path_url(path):
    """``file://localhost/Users/...``, each part percent-encoded (what Premiere writes)."""
    p = os.path.abspath(path).replace(os.sep, "/")
    if re.match(r"^[A-Za-z]:/", p):
        p = "/" + p
    return "file://localhost" + quote(p, safe="/:")


def url_path(url):
    u = urlparse(url)
    p = unquote(u.path)
    return p[1:] if re.match(r"^/[A-Za-z]:/", p) else p


def _b(v):
    return "TRUE" if v else "FALSE"


def _num(v):
    r = round(float(v), 6)
    return str(int(r)) if r == int(r) else str(r)


def _rate_xml(rate, pad):
    return f"{pad}<rate>\n{pad}  <timebase>{rate['timebase']}</timebase>\n{pad}  <ntsc>{_b(rate['ntsc'])}</ntsc>\n{pad}</rate>"


def _timecode_xml(rate, pad):
    return "\n".join([f"{pad}<timecode>", _rate_xml(rate, pad + "  "), f"{pad}  <string>00:00:00:00</string>",
                      f"{pad}  <frame>0</frame>", f"{pad}  <displayformat>NDF</displayformat>", f"{pad}</timecode>"])


def _file_xml(f, rate, pad):
    L = [f'{pad}<file id="{xml_escape(f["id"])}">', f"{pad}  <name>{xml_escape(f['name'])}</name>",
         f"{pad}  <pathurl>{xml_escape(path_url(f['path']))}</pathurl>", _rate_xml(rate, pad + "  "),
         f"{pad}  <duration>{f['duration']}</duration>", _timecode_xml(rate, pad + "  "), f"{pad}  <media>"]
    if f.get("video"):
        L += [f"{pad}    <video>", f"{pad}      <samplecharacteristics>", _rate_xml(rate, pad + "        "),
              f"{pad}        <width>{f['video']['w']}</width>", f"{pad}        <height>{f['video']['h']}</height>",
              f"{pad}        <anamorphic>FALSE</anamorphic>", f"{pad}        <pixelaspectratio>square</pixelaspectratio>",
              f"{pad}        <fielddominance>none</fielddominance>", f"{pad}      </samplecharacteristics>",
              f"{pad}    </video>"]
    if f.get("audio"):
        L += [f"{pad}    <audio>", f"{pad}      <samplecharacteristics>", f"{pad}        <depth>16</depth>",
              f"{pad}        <samplerate>{f['audio']['rate']}</samplerate>", f"{pad}      </samplecharacteristics>",
              f"{pad}      <channelcount>{f['audio']['channels']}</channelcount>", f"{pad}    </audio>"]
    L += [f"{pad}  </media>", f"{pad}</file>"]
    return "\n".join(L)


def _effect_xml(pad, name, eid, cat, media, params):
    L = [f"{pad}<filter>", f"{pad}  <effect>", f"{pad}    <name>{name}</name>", f"{pad}    <effectid>{eid}</effectid>",
         f"{pad}    <effectcategory>{cat}</effectcategory>", f"{pad}    <effecttype>{cat}</effecttype>",
         f"{pad}    <mediatype>{media}</mediatype>"]
    for pid, pname, lo, hi, val in params:
        L += [f"{pad}    <parameter>", f"{pad}      <parameterid>{pid}</parameterid>", f"{pad}      <name>{pname}</name>"]
        if lo is not None:
            L += [f"{pad}      <valuemin>{lo}</valuemin>", f"{pad}      <valuemax>{hi}</valuemax>"]
        L.append(f"{pad}      <value>{val}</value>")
        L.append(f"{pad}    </parameter>")
    L += [f"{pad}  </effect>", f"{pad}</filter>"]
    return "\n".join(L)


def _speed_xml(speed, media, pad):
    return _effect_xml(pad, "Time Remap", "timeremap", "motion", media, [
        ("variablespeed", "variablespeed", 0, 1, 0), ("speed", "speed", -100000, 100000, _num(speed * 100)),
        ("reverse", "reverse", None, None, "FALSE"), ("frameblending", "frameblending", None, None, "FALSE")])


def xmeml(tl):
    """The timeline as an xmeml v4 document (Premiere Pro: File > Import; Resolve: File > Import > Timeline). A file
    is written whole the first time a clip uses it and referred to by id after; a picture and its sound are linked."""
    files = {f["id"]: f for f in tl["files"]}
    rate = tl["rate"]
    written = set()
    place = {}
    for media, tracks in (("video", tl["video"]), ("audio", tl["audio"])):
        for ti, tr in enumerate(tracks):
            for ci, c in enumerate(tr["clips"]):
                if c.get("link"):
                    place.setdefault(c["link"], []).append((c["id"], media, ti + 1, ci + 1))

    def clip_xml(c, media, pad):
        f = files[c["file"]]
        L = [f'{pad}<clipitem id="{xml_escape(c["id"])}">', f"{pad}  <name>{xml_escape(c['name'])}</name>",
             f"{pad}  <enabled>{_b(c.get('enabled', True))}</enabled>", f"{pad}  <duration>{f['duration']}</duration>",
             _rate_xml(rate, pad + "  "), f"{pad}  <start>{c['start']}</start>", f"{pad}  <end>{c['end']}</end>",
             f"{pad}  <in>{c['cut_in']}</in>", f"{pad}  <out>{c['cut_out']}</out>"]
        if media == "video":
            L += [f"{pad}  <alphatype>none</alphatype>", f"{pad}  <pixelaspectratio>square</pixelaspectratio>",
                  f"{pad}  <anamorphic>FALSE</anamorphic>"]
        if f["id"] in written:
            L.append(f'{pad}  <file id="{xml_escape(f["id"])}"/>')
        else:
            written.add(f["id"])
            L.append(_file_xml(f, rate, pad + "  "))
        if abs(float(c.get("speed") or 1) - 1) > 1e-6:
            L.append(_speed_xml(float(c["speed"]), media, pad + "  "))
        if media == "audio":
            L += [f"{pad}  <sourcetrack>", f"{pad}    <mediatype>audio</mediatype>", f"{pad}    <trackindex>1</trackindex>",
                  f"{pad}  </sourcetrack>"]
            if c.get("gain") is not None:
                L.append(_effect_xml(pad + "  ", "Audio Levels", "audiolevels", "audiolevels", "audio",
                                     [("level", "Level", 0, MAX_GAIN, _num(c["gain"]))]))
        for cid, m, ti, ci in place.get(c.get("link"), []) if c.get("link") else []:
            L += [f"{pad}  <link>", f"{pad}    <linkclipref>{xml_escape(cid)}</linkclipref>",
                  f"{pad}    <mediatype>{m}</mediatype>", f"{pad}    <trackindex>{ti}</trackindex>",
                  f"{pad}    <clipindex>{ci}</clipindex>"] + \
                ([f"{pad}    <groupindex>1</groupindex>"] if m == "audio" else []) + [f"{pad}  </link>"]
        L.append(f"{pad}</clipitem>")
        return "\n".join(L)

    def track_xml(tr, media, pad):
        head = f'{pad}<track premiereTrackType="Stereo">' if media == "audio" else f"{pad}<track>"
        return "\n".join([head] + [clip_xml(c, media, pad + "  ") for c in tr["clips"]] +
                         [f"{pad}  <enabled>{_b(tr.get('enabled', True))}</enabled>", f"{pad}  <locked>FALSE</locked>",
                          f"{pad}</track>"])
    p = " " * 8
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE xmeml>", '<xmeml version="4">',
        '  <sequence id="sequence-1">', f"    <name>{xml_escape(tl['name'])}</name>",
        f"    <duration>{tl['duration']}</duration>", _rate_xml(rate, "    "), _timecode_xml(rate, "    "),
        "    <in>-1</in>", "    <out>-1</out>", "    <media>", "      <video>", f"{p}<format>",
        f"{p}  <samplecharacteristics>", _rate_xml(rate, p + "    "), f"{p}    <width>{tl['width']}</width>",
        f"{p}    <height>{tl['height']}</height>", f"{p}    <anamorphic>FALSE</anamorphic>",
        f"{p}    <pixelaspectratio>square</pixelaspectratio>", f"{p}    <fielddominance>none</fielddominance>",
        f"{p}  </samplecharacteristics>", f"{p}</format>"] +
        [track_xml(t, "video", p) for t in tl["video"]] +
        ["      </video>", "      <audio>", f"{p}<numOutputChannels>2</numOutputChannels>", f"{p}<format>",
         f"{p}  <samplecharacteristics>", f"{p}    <depth>16</depth>", f"{p}    <samplerate>48000</samplerate>",
         f"{p}  </samplecharacteristics>", f"{p}</format>"] +
        [track_xml(t, "audio", p) for t in tl["audio"]] +
        ["      </audio>", "    </media>", "  </sequence>", "</xmeml>", ""])


def srt(cues):
    def ts(x):
        ms = int(round(float(x) * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "".join(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n\n" for i, c in enumerate(cues, 1))


# --------------------------------------------------------------------------- 剪映 / CapCut
MATERIAL_KINDS = (
    "ai_translates", "audio_balances", "audio_effects", "audio_fades", "audio_track_indexes", "audios", "beats",
    "canvases", "chromas", "color_curves", "digital_humans", "drafts", "effects", "flowers", "green_screens",
    "handwrites", "hsl", "images", "log_color_wheels", "loudnesses", "manual_deformations", "masks",
    "material_animations", "material_colors", "multi_language_refs", "placeholders", "plugin_effects",
    "primary_color_wheels", "realtime_denoises", "shapes", "smart_crops", "smart_relights", "sound_channel_mappings",
    "speeds", "stickers", "tail_leaders", "text_templates", "texts", "time_marks", "transitions", "video_effects",
    "video_trackings", "videos", "vocal_beautifys", "vocal_separations")
DRAFT_PLATFORM = dict(jianying=dict(app_id=3704, app_source="lv", app_version="5.9.0", os="windows"),
                      capcut=dict(app_id=359289, app_source="cc", app_version="5.9.0", os="windows"))
APP_FOLDER = dict(jianying="JianyingPro", capcut="CapCut")


def drafts_root(app, home=None, platform=None, local_app_data=None):
    """Where 剪映 / CapCut keeps its drafts by default (Settings > Drafts can move them): the folder when it is
    there, else None."""
    import sys
    platform = platform or sys.platform
    home = home or os.path.expanduser("~")
    if platform == "darwin":
        base = os.path.join(home, "Movies")
    elif platform == "win32":
        base = local_app_data or os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    else:
        return None
    d = os.path.join(base, APP_FOLDER[app], "User Data", "Projects", "com.lveditor.draft")
    return d if os.path.isdir(d) else None


def _hex():
    return uuid.uuid4().hex


def _r6(x):
    r = round(float(x), 6)
    return 0.0 if r == 0 else r


def jianying_draft(tl, name, folder, root, app="jianying", now=None):
    """-> (draft_info.json, draft_meta_info.json) documents for the draft folder ``folder`` in ``root``. Times in
    microseconds, each clip's edges from the plan's frames (neighbours share their cut)."""
    fps = tl["rate"]["fps"]

    def us(fr):
        return int(round(fr * 1e6 / fps))

    def span(a, b):
        return dict(start=us(a), duration=us(b) - us(a))
    files = {f["id"]: f for f in tl["files"]}
    materials = {k: [] for k in MATERIAL_KINDS}
    library, entry_of, material_of = [], {}, {}

    def register(f, kind):
        if f["path"] in entry_of:
            return entry_of[f["path"]]
        mid = str(uuid.uuid4()).upper()
        library.append(dict(ai_group_type="", create_time=-1, duration=us(f["duration"]), enter_from=0,
                            extra_info=f["name"], file_Path=f["path"], height=(f.get("video") or {}).get("h", 0), id=mid,
                            import_time=-1, import_time_ms=-1, item_source=1, material_color_tag="", md5="",
                            metetype=kind, roughcut_time_range=dict(duration=-1, start=-1),
                            sub_time_range=dict(duration=-1, start=-1), type=0, width=(f.get("video") or {}).get("w", 0)))
        entry_of[f["path"]] = mid
        return mid

    def material(f, kind):
        key = f"{kind}:{f['id']}"
        if key in material_of:
            return material_of[key]
        mid = _hex()
        if kind == "video":
            materials["videos"].append(dict(
                audio_fade=None, category_id="", category_name="local", check_flag=63487,
                crop=dict(upper_left_x=0, upper_left_y=0, upper_right_x=1, upper_right_y=0, lower_left_x=0,
                          lower_left_y=1, lower_right_x=1, lower_right_y=1),
                crop_ratio="free", crop_scale=1, duration=us(f["duration"]), height=f["video"]["h"],
                width=f["video"]["w"], id=mid, local_material_id=register(f, "video"), material_id=mid,
                material_name=f["name"], media_path="", path=f["path"], type="video"))
        else:
            materials["audios"].append(dict(
                app_id=0, category_id="", category_name="local", check_flag=3, copyright_limit_type="none",
                duration=us(f["duration"]), effect_id="", formula_id="", id=mid, local_material_id=register(f, "music"),
                music_id=mid, name=f["name"], path=f["path"], source_platform=0, type="extract_music", wave_points=[]))
        material_of[key] = mid
        return mid

    def speed_ref(v):
        mid = _hex()
        materials["speeds"].append(dict(curve_speed=None, id=mid, mode=0, speed=_r6(v), type="speed"))
        return mid

    def segment(**fields):
        base = dict(enable_adjust=True, enable_color_correct_adjust=False, enable_color_curves=True,
                    enable_color_match_adjust=False, enable_color_wheels=True, enable_lut=True,
                    enable_smart_color_adjust=False, last_nonzero_volume=1, reverse=False, track_attribute=0,
                    track_render_index=0, visible=True, id=_hex(), common_keyframes=[], keyframe_refs=[], speed=1,
                    volume=1, is_tone_modify=False)
        base.update(fields)
        return base

    def src_span(c):
        """The source part a clip plays: its timeline length times its speed (剪映 checks the two agree)."""
        d = us(c["end"]) - us(c["start"])
        return dict(start=us(c["cut_in"]), duration=int(round(d * float(c.get("speed") or 1))))
    own = {c["link"]: (c.get("gain") if c.get("gain") is not None else 1.0)
           for t in tl["audio"] for c in t["clips"] if c.get("link")}
    tracks, idx = [], 0
    for t in tl["video"]:
        segs = []
        for c in t["clips"]:
            f = files[c["file"]]
            level = own.get(c.get("link"), 0.0) if c.get("link") else 0.0
            segs.append(segment(material_id=material(f, "video"), target_timerange=span(c["start"], c["end"]),
                                source_timerange=src_span(c), visible=c.get("enabled", True), volume=_r6(level),
                                last_nonzero_volume=_r6(level) or 1, speed=_r6(c.get("speed") or 1),
                                extra_material_refs=[speed_ref(c.get("speed") or 1)],
                                clip=dict(alpha=1, flip=dict(horizontal=False, vertical=False), rotation=0,
                                          scale=dict(x=1, y=1), transform=dict(x=0, y=0)),
                                uniform_scale=dict(on=True, value=1), hdr_settings=dict(intensity=1, mode=1, nits=1000),
                                render_index=idx))
        tracks.append(dict(attribute=0, flag=0, id=_hex(), is_default_name=False, name=t["name"], type="video",
                           segments=segs))
        idx += 1
    for t in tl["audio"]:
        clips = [c for c in t["clips"] if not c.get("link")]        # footage sound plays with its picture
        if not clips:
            continue
        segs = [segment(material_id=material(files[c["file"]], "audio"), target_timerange=span(c["start"], c["end"]),
                        source_timerange=src_span(c), volume=_r6(c.get("gain") if c.get("gain") is not None else 1),
                        last_nonzero_volume=1, speed=_r6(c.get("speed") or 1),
                        extra_material_refs=[speed_ref(c.get("speed") or 1)], clip=None, hdr_settings=None,
                        render_index=idx) for c in clips]
        tracks.append(dict(attribute=0, flag=0, id=_hex(), is_default_name=False, name=t["name"], type="audio",
                           segments=segs))
        idx += 1
    if tl["cues"]:
        segs = []
        for cue in tl["cues"]:
            mid = _hex()
            text = cue["text"]
            materials["texts"].append(dict(
                id=mid, type="text", typesetting=0, alignment=1, letter_spacing=0, line_spacing=0.02, line_feed=1,
                line_max_width=0.82, force_apply_line_max_width=False, check_flag=15, global_alpha=1,
                content=json.dumps(dict(styles=[dict(
                    fill=dict(alpha=1, content=dict(render_type="solid", solid=dict(alpha=1, color=[1, 1, 1]))),
                    range=[0, len(text)], size=6, bold=False, italic=False, underline=False,
                    strokes=[dict(content=dict(render_type="solid", solid=dict(alpha=1, color=[0, 0, 0])),
                                  width=0.08)])], text=text), ensure_ascii=False)))
            a = frame(cue["start"], fps)
            b = max(a + 1, frame(cue["end"], fps))
            segs.append(segment(material_id=mid, target_timerange=span(a, b), source_timerange=None,
                                extra_material_refs=[], render_index=idx,
                                clip=dict(alpha=1, flip=dict(horizontal=False, vertical=False), rotation=0,
                                          scale=dict(x=1, y=1), transform=dict(x=0, y=-0.8)),
                                uniform_scale=dict(on=True, value=1)))
        tracks.append(dict(attribute=0, flag=0, id=_hex(), is_default_name=False, name="Subtitles", type="text",
                           segments=segs))
    plat = DRAFT_PLATFORM[app]
    duration = us(tl["duration"])
    did = str(uuid.uuid4()).upper()
    now = int(now if now is not None else time.time() * 1000)
    info = dict(
        canvas_config=dict(width=tl["width"], height=tl["height"], ratio="original"), color_space=0,
        config=dict(adjust_max_index=1, attachment_info=[], combination_max_index=1, export_range=None,
                    extract_audio_last_index=1, lyrics_recognition_id="", lyrics_sync=True, lyrics_taskinfo=[],
                    maintrack_adsorb=False, material_save_mode=0, multi_language_current="none",
                    multi_language_list=[], multi_language_main="none", multi_language_mode="none",
                    original_sound_last_index=1, record_audio_last_index=1, sticker_max_index=1,
                    subtitle_keywords_config=None, subtitle_recognition_id="", subtitle_sync=True,
                    subtitle_taskinfo=[], system_font_list=[], video_mute=False, zoom_info_params=None),
        cover=None, create_time=0, duration=duration, extra_info=None, fps=round(fps, 6),
        free_render_index_mode_on=False, group_container=None, id=did, keyframe_graph_list=[],
        keyframes=dict(adjusts=[], audios=[], effects=[], filters=[], handwrites=[], stickers=[], texts=[], videos=[]),
        last_modified_platform=plat, platform=plat, materials=materials, mutable_config=None, name=name,
        new_version="110.0.0", relationships=[], render_index_track_mode_on=False, retouch_cover=None,
        source="default", static_cover_image_path="", time_marks=None, tracks=tracks, update_time=0, version=360000)
    meta = dict(
        cloud_package_completed_time="", draft_cloud_capcut_purchase_info="", draft_cloud_last_action_download=False,
        draft_cloud_materials=[], draft_cloud_purchase_info="", draft_cloud_template_id="",
        draft_cloud_tutorial_info="", draft_cloud_videocut_purchase_info="", draft_cover="", draft_deeplink_url="",
        draft_enterprise_info=dict(draft_enterprise_extra="", draft_enterprise_id="", draft_enterprise_name="",
                                   enterprise_material=[]),
        draft_fold_path=folder, draft_id=did, draft_is_ai_packaging_used=False, draft_is_ai_shorts=False,
        draft_is_ai_translate=False, draft_is_article_video_draft=False, draft_is_from_deeplink="false",
        draft_is_invisible=False,
        draft_materials=[dict(type=k, value=library if k == 0 else []) for k in (0, 1, 2, 3, 6, 7, 8)],
        draft_materials_copied_info=[], draft_name=name, draft_new_version="", draft_removable_storage_device="",
        draft_root_path=root, draft_segment_extra_info=[], draft_type="", tm_draft_cloud_completed="",
        tm_draft_cloud_modified=0, tm_draft_create=now * 1000, tm_draft_modified=now * 1000, tm_draft_removed=0,
        tm_duration=duration)
    return info, meta


# --------------------------------------------------------------------------- OpenTimelineIO
def _rt(v, fps):
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": round(fps, 6), "value": float(v)}


def _tr(a, d, fps):
    return {"OTIO_SCHEMA": "TimeRange.1", "start_time": _rt(a, fps), "duration": _rt(d, fps)}


def otio(tl):
    """The timeline as OpenTimelineIO JSON (.otio): clips with their source ranges and a LinearTimeWarp for the
    speed, captions as markers, levels in metadata (OTIO has no level of its own)."""
    fps = tl["rate"]["fps"]
    files = {f["id"]: f for f in tl["files"]}

    def track(t, kind):
        kids, at = [], 0
        for c in t["clips"]:
            if c["start"] > at:
                kids.append({"OTIO_SCHEMA": "Gap.1", "name": "", "source_range": _tr(0, c["start"] - at, fps),
                             "effects": [], "markers": [], "metadata": {}})
            f = files[c["file"]]
            fx = []
            if abs(float(c.get("speed") or 1) - 1) > 1e-6:
                fx.append({"OTIO_SCHEMA": "LinearTimeWarp.1", "name": "speed", "effect_name": "LinearTimeWarp",
                           "time_scalar": float(c["speed"]), "metadata": {}})
            kids.append({"OTIO_SCHEMA": "Clip.1", "name": c["name"], "source_range": _tr(c["cut_in"], c["end"] - c["start"], fps),
                         "media_reference": {"OTIO_SCHEMA": "ExternalReference.1", "name": f["name"],
                                             "target_url": "file://" + quote(os.path.abspath(f["path"]).replace(os.sep, "/"),
                                                                             safe="/:"),
                                             "available_range": _tr(0, f["duration"], fps), "metadata": {}},
                         "effects": fx, "markers": [], "enabled": c.get("enabled", True),
                         "metadata": {"reelfold": {k: c[k] for k in ("gain", "link") if c.get(k) is not None}}})
            at = c["end"]
        return {"OTIO_SCHEMA": "Track.1", "name": t["name"], "kind": kind, "children": kids, "source_range": None,
                "effects": [], "markers": [], "enabled": t.get("enabled", True), "metadata": {}}
    markers = [{"OTIO_SCHEMA": "Marker.2", "name": c["text"], "comment": c["text"], "color": "PURPLE",
                "marked_range": _tr(frame(c["start"], fps), max(1, frame(c["end"], fps) - frame(c["start"], fps)), fps),
                "metadata": {"reelfold": {"kind": "caption"}}} for c in tl["cues"]]
    return {"OTIO_SCHEMA": "Timeline.1", "name": tl["name"], "global_start_time": None,
            "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "source_range": None, "effects": [],
                       "markers": markers, "enabled": True, "metadata": {},
                       "children": [track(t, "Video") for t in tl["video"]] + [track(t, "Audio") for t in tl["audio"]]},
            "metadata": {"reelfold": {"notes": tl["notes"], "source": tl["source"]}}}


# --------------------------------------------------------------------------- writing it out
def _safe(name):
    s = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "-", str(name)).strip(" .-")
    return s[:80] or "clip"


def _clone(src, dst):
    """An APFS clone when the disk can (no extra space), else a copy. Never a link, never a write of ``src``."""
    import sys
    if os.path.exists(dst):
        return dst
    if sys.platform == "darwin":
        r = subprocess.run(["/bin/cp", "-c", src, dst], capture_output=True)
        if r.returncode == 0:
            return dst
    shutil.copy2(src, dst)
    return dst


def collect_media(tl, media_dir):
    """Put every file of the plan into ``media_dir`` (clone / copy) and point the plan at the copies."""
    os.makedirs(media_dir, exist_ok=True)
    seen = {}
    for f in tl["files"]:
        base = os.path.basename(f["path"])
        dst = os.path.join(media_dir, base)
        k = 1
        while os.path.exists(dst) and seen.get(dst) != f["path"]:
            stem, ext = os.path.splitext(base)
            dst = os.path.join(media_dir, f"{stem}-{k}{ext}")
            k += 1
        seen[dst] = f["path"]
        _clone(f["path"], dst)
        f["path"] = os.path.abspath(dst)
    return tl


def write(tl, fmt, out_dir, media="link", app_root=None, name=None):
    """Write the plan in ``fmt`` under ``out_dir`` -> {format, dir, files [paths], main, media, notes, cues}.
    jianying / capcut: a draft folder (in ``app_root``, the app's drafts folder, when given - it then shows on the
    app's home screen - else in ``out_dir``)."""
    fmt = norm_format(fmt)
    name = _safe(name or tl["name"])
    os.makedirs(out_dir, exist_ok=True)
    if media == "copy":
        collect_media(tl, os.path.join(out_dir, "media"))
    files = []
    if fmt == "xmeml":
        main = os.path.join(out_dir, f"{name}.xml")
        with open(main, "w", encoding="utf-8") as f:
            f.write(xmeml(tl))
        files.append(main)
    elif fmt == "otio":
        main = os.path.join(out_dir, f"{name}.otio")
        with open(main, "w", encoding="utf-8") as f:
            json.dump(otio(tl), f, ensure_ascii=False, indent=2)
        files.append(main)
    else:
        root = app_root or out_dir
        folder = os.path.join(root, name)
        k = 2
        while os.path.exists(folder):
            folder = os.path.join(root, f"{name} {k}")
            k += 1
        os.makedirs(folder)
        info, meta = jianying_draft(tl, os.path.basename(folder), folder, root, app=fmt)
        for fn, doc in (("draft_info.json", info), ("draft_content.json", info), ("draft_meta_info.json", meta)):
            with open(os.path.join(folder, fn), "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
            files.append(os.path.join(folder, fn))
        main = folder
    if tl["cues"] and fmt in ("xmeml", "otio"):
        p = os.path.join(out_dir, f"{name}.srt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(srt(tl["cues"]))
        files.append(p)
    with open(os.path.join(out_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write(readme(fmt, name, tl))
    return dict(format=fmt, dir=os.path.abspath(out_dir), main=main, files=files, media=media,
                notes=list(tl["notes"]), cues=len(tl["cues"]), clips=sum(len(t["clips"]) for t in tl["video"]),
                duration=round(tl["duration"] / tl["rate"]["fps"], 3))


HOW = dict(xmeml="Premiere Pro: File > Import, pick the .xml. DaVinci Resolve: File > Import > Timeline. "
                 "The .srt next to it: File > Import (Premiere makes it a captions track; Resolve a subtitle track).",
           otio="Resolve: File > Import > Timeline (.otio); other editors through an OpenTimelineIO adapter. "
                "Captions are markers and the .srt next to it.",
           jianying="剪映: the draft is in its drafts folder (it shows on the home screen); if not, copy the folder "
                    "into 剪映's drafts folder (Settings > Drafts location).",
           capcut="CapCut: the draft is in its drafts folder (it shows on the home screen); if not, copy the folder "
                  "into CapCut's drafts folder (Settings > Drafts location).")


def readme(fmt, name, tl):
    lines = [f"{name}: the edit from Reelfold for an editing program", "", HOW[fmt], "",
             f"Media ({len(tl['files'])}): " + ", ".join(f["path"] for f in tl["files"]),
             "If the media moved: python -m vstudio.project output nle-relink --out <this folder> --media-dir <folder>",
             ""]
    if tl["notes"]:
        lines += ["Not carried over (made by Reelfold):"] + [f"- {n}" for n in tl["notes"]] + [""]
    return "\n".join(lines)


def relink(export_dir, media_dir):
    """Point every timeline of ``export_dir`` (xml / otio / 剪映 drafts) at files of the same name in ``media_dir``
    -> {ok, relinked [names], missing [names], files [timelines rewritten]}."""
    media_dir = os.path.abspath(media_dir)
    have = {f: os.path.join(media_dir, f) for f in os.listdir(media_dir)} if os.path.isdir(media_dir) else {}
    relinked, missing, touched = set(), set(), []

    def new_path(old):
        b = os.path.basename(old)
        if b in have:
            relinked.add(b)
            return have[b]
        missing.add(b)
        return old
    for dp, _dn, fns in os.walk(export_dir):
        for fn in fns:
            p = os.path.join(dp, fn)
            if fn.endswith(".xml"):
                txt = open(p, encoding="utf-8").read()
                out = re.sub(r"<pathurl>(.*?)</pathurl>", lambda m: "<pathurl>" + xml_escape(path_url(new_path(
                    url_path(m.group(1).replace("&amp;", "&"))))) + "</pathurl>", txt)
            elif fn.endswith(".otio"):
                doc = json.load(open(p, encoding="utf-8"))

                def walk(x):
                    if isinstance(x, dict):
                        if x.get("OTIO_SCHEMA", "").startswith("ExternalReference") and x.get("target_url"):
                            x["target_url"] = "file://" + quote(new_path(url_path(x["target_url"])), safe="/:")
                        for v in x.values():
                            walk(v)
                    elif isinstance(x, list):
                        for v in x:
                            walk(v)
                walk(doc)
                out = json.dumps(doc, ensure_ascii=False, indent=2)
                txt = None
            elif fn in ("draft_info.json", "draft_content.json", "draft_meta_info.json"):
                doc = json.load(open(p, encoding="utf-8"))
                for m in (doc.get("materials") or {}).get("videos", []) + (doc.get("materials") or {}).get("audios", []):
                    m["path"] = new_path(m["path"])
                for grp in doc.get("draft_materials") or []:
                    for e in grp.get("value") or []:
                        if e.get("file_Path"):
                            e["file_Path"] = new_path(e["file_Path"])
                out = json.dumps(doc, ensure_ascii=False)
                txt = None
            else:
                continue
            if txt is None or out != txt:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(out)
                touched.append(p)
    return dict(ok=not missing, relinked=sorted(relinked), missing=sorted(missing - relinked), files=touched)


# --------------------------------------------------------------------------- the commands
def export_output(d, output, fmt, out_dir=None, media="link", to_app=False, measure=True):
    """One output's edit -> the ``write`` result + {output, format}. ``out_dir`` default:
    <the output's edit folder>/nle/<stamp>-<format>/."""
    from . import outputs as O
    fmt = norm_format(fmt)
    if media not in ("link", "copy"):
        raise NleError("bad-param", "media: link | copy", param="media")
    rec, doc = O._load(d, output)
    st = doc.state()
    O._effective(rec, doc, st)
    tl = plan(rec, doc, st, measure=measure)
    out_dir = out_dir or os.path.join(doc.dir, "nle", time.strftime("%Y%m%d-%H%M%S") + "-" + fmt)
    root = drafts_root(fmt) if to_app and fmt in ("jianying", "capcut") else None
    res = write(tl, fmt, out_dir, media=media, app_root=root, name=tl["name"])
    res.update(ok=True, output=rec["id"], in_app=bool(root))
    return res


def export_all(d, fmt, out_dir=None, media="link", to_app=False, measure=True, outputs=None):
    """Every output of a project / work folder (or ``outputs``), each its own timeline, in one folder."""
    from . import outputs as O
    d2, _kind = O._owner(d)
    rows = O.list_outputs(d2)["outputs"]
    if outputs:
        want = set(outputs)
        rows = [r for r in rows if r["id"] in want]
    if not rows:
        raise NleError("no-outputs", "nothing finished to export yet")
    out_dir = out_dir or os.path.join(O.edits_root(d2, _kind), "nle", time.strftime("%Y%m%d-%H%M%S") + "-" + norm_format(fmt))
    done, failed = [], []
    for r in rows:
        try:
            done.append(export_output(d2, r["id"], fmt, out_dir=out_dir, media=media, to_app=to_app, measure=measure))
        except Exception as e:  # noqa: BLE001  (one clip that cannot go does not stop the others)
            failed.append(dict(output=r["id"], error=str(e)[:300]))
    return dict(ok=bool(done), format=norm_format(fmt), dir=os.path.abspath(out_dir), outputs=done, failed=failed)
