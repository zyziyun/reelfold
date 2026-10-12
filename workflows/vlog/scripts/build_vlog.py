#!/usr/bin/env python3
"""Build a B-roll vlog master from silent or ambient clips (drone, phone, travel,
walking, nature, city).

Reads a JSON edit-decision list and produces one graded, speed-adjusted,
crossfaded master with a clean opening (NO black first frame) and a fade to
black at the end. Segments are rendered in parallel as intermediates, then
xfaded together.

    python3 build_vlog.py work/edit.json
    python3 build_vlog.py work/edit.json --dry-run      # print ffmpeg commands only

Relative paths in the config (src_dir, out) resolve against the config file's
folder. Full schema + worked example: ../references/recipes.md. Quick schema:
{
  "src_dir": "../footage",
  "clips": {"0079": "DJI_0079.MP4", "walk1": "IMG_1234.MOV"},   # id -> filename
  "res": [3840, 2160],       # master size; source res for true 4K, [1080,1920] for vertical
  "fps": 30,
  "xfade": 0.8, "fade_out": 1.5,
  "fit": "crop",             # crop | pad | blur | stretch  (how off-aspect clips fill the frame)
  "hdr": "auto",             # auto | true | false   (tone-map HLG/PQ phone/drone clips to BT.709)
  "ambient_audio": false,    # true = keep each clip's own sound (tempo-matched, crossfaded)
  "grade": {"brightness":0.0,"contrast":1.04,"saturation":1.04,"gamma":1.0},   # restrained (references/AESTHETICS.md)
  "warm": true, "sharpen": false, "stabilize": false,
  "match_exposure": 0.6,     # pull each segment's brightness toward the film's median (0 = off); no exposure jumps at cuts
  "deflicker": true,         # even out frame-to-frame exposure pumping inside a clip (drone auto-exposure)
  "qc": {"flicker": "fail"}, # vstudio.flicker on the master: fail | warn | off
  "seg_crf": 12, "final_crf": 18, "workers": 3,
  "out": "vlog_master.mp4",
  "segments": [
    {"clip":"0079","start":4,"dur":10,"kind":"empty","bright":0.08},   # establishing: faster
    {"clip":"walk1","start":6,"dur":20,"speed":1.15}
  ]
}
Per segment: clip, start, dur (SOURCE seconds), optional speed (default 1.0: aerials play in real time; any speed
gets an even frame cadence via ffmpeg_filters.retime), kind
("subject" | "empty"), bright (added to grade.brightness), stabilize, cleanup (a segment where someone
talks: true | "gentle" | "standard" | "tight" | "pauses" | {profile, approve, keep, reply} -> the shared
vstudio.cleanup 气口/filler/repeat pass before assembly; needs "ambient_audio": true; see clean_speech).

"style": "calm" (default, this script) | "fun" (beat-cut travel vlog: hands over to build_fun.py).
"platform": "youtube" / "xiaohongshu:full" / ... (vstudio.platform) - used when "res" is absent: canvas
from the profile, fps default from the profile, length check printed. --platform overrides it.
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import argparse, json, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from vstudio import ffmpeg_filters as FF, media, proctail
from vstudio.config import persona

COLORBALANCE = "colorbalance=rs=0.02:rm=0.02:bm=-0.02:bs=-0.03:rh=0.01:bh=-0.02"
UNSHARP = "unsharp=5:5:0.5:5:5:0.0"
# restrained by default: DJI / phone footage is already contrasty and saturated; a heavy lift + 1.18x saturation and a
# sharpen on a 4K -> 1080 downscale looked cheap (俗气) and made fine detail (city lights, water) shimmer
DEFAULT_GRADE = {"brightness": 0.0, "contrast": 1.04, "saturation": 1.04, "gamma": 1.0}
DEFLICKER = "deflicker=size=5:mode=am"
# xfade transitions that pass through black / white (a flash between two shots): not by default
DIP_TRANSITIONS = ("fadeblack", "fadewhite", "fadefast", "fadeslow")


class RenderError(RuntimeError):
    """One ffmpeg run of the render failed: ``what`` (segment / final) + ffmpeg's own error output."""


def run_ffmpeg(cmd, what):
    """media.run (stderr captured, LGPL filter / H.264 encoder rewrites for this ffmpeg) -> RenderError that names
    the step and leads with ffmpeg's reason ("No such filter: 'eq'", "<file>: No such file or directory")."""
    try:
        media.run(cmd, quiet=False)
    except media.FFmpegError as e:
        why = proctail.cause(str(e)) or "ffmpeg failed"
        raise RenderError(f"{what}: {why}\n{e}") from None


def vlog_persona():
    return persona().get("vlog", {}) or {}


@lru_cache(maxsize=None)
def clip_info(path):
    """Cached media.probe (each source is asked once per segment, possibly several times)."""
    return media.probe(path)


def hdr_chain(cfg, src):
    """media.hdr_to_sdr_args per the config "hdr" mode, with a trailing comma (or "")."""
    mode = cfg.get("hdr", "auto")
    if mode is False or mode == "false":
        return ""
    chain = media.hdr_to_sdr_args(src, transfer=clip_info(src)["transfer"],
                                  force=mode is True or mode == "true")
    return chain + "," if chain else ""


def fit_chain(cfg):
    W, H = cfg["res"]
    fit = cfg.get("fit", "crop")
    if fit == "stretch":
        return f"scale={W}:{H}:flags=lanczos"
    if fit == "pad":
        return (f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    if fit == "blur":
        return (f"split=2[bg][fg];[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},gblur=sigma=40,{FF.dim(-0.08)}[bgb];"
                f"[fg]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
                f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1")
    return (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={W}:{H},setsar=1")


def grade_chain(cfg, extra_bright):
    g = {**DEFAULT_GRADE, **(vlog_persona().get("grade") or {}), **(cfg.get("grade") or {})}
    # LGPL (the desk's bundled ffmpeg has no eq): the same look as eq=brightness:contrast:saturation:gamma
    parts = [FF.grade(brightness=round(g['brightness'] + extra_bright, 3), contrast=g['contrast'],
                      saturation=g['saturation'], gamma=g['gamma'])]
    if cfg.get("warm", True):
        parts.append(COLORBALANCE)
    if cfg.get("sharpen", False):
        parts.append(UNSHARP)
    return ",".join(parts)


def stab_prefix(cfg, seg):
    """Optional in-pass stabilization (built-in `deshake`; no libvidstab needed).
    Runs on native frames BEFORE scale/speed; a small zoom-crop hides edge jitter.
    Top-level "stabilize": true or per-segment override. "stab_rx"/"stab_ry"
    (search range, multiple of 16, max 64) and "stab_zoom" (keep fraction)."""
    if not seg.get("stabilize", cfg.get("stabilize", False)):
        return ""
    snap = lambda v: max(16, min(64, round(v / 16) * 16))
    keep = cfg.get("stab_zoom", 0.93)
    return (f"deshake=rx={snap(cfg.get('stab_rx', 32))}:ry={snap(cfg.get('stab_ry', 32))}"
            f":edge=clamp,crop=iw*{keep}:ih*{keep},")


def seg_speed(cfg, seg):
    if "speed" in seg:
        return float(seg["speed"])
    vp = vlog_persona()
    if seg.get("kind") == "empty":
        return float(cfg.get("empty_speed", vp.get("speed_empty", 1.0)))
    # "deer_speed" accepted for configs written with the original drone skill
    return float(cfg.get("default_speed", cfg.get("deer_speed", vp.get("speed_subject", 1.0))))


def render_seg(args):
    i, cfg, seg, segdir, dry = args
    src = seg.get("_src") or os.path.join(cfg["_src_dir"], cfg["clips"][seg["clip"]])
    speed = seg_speed(cfg, seg)
    eb = seg.get("bright", 0.0) + seg.get("_match", 0.0)
    eff = seg["dur"] / speed
    vf = (stab_prefix(cfg, seg) + hdr_chain(cfg, src) + fit_chain(cfg) + "," + grade_chain(cfg, eb)
          + ("," + DEFLICKER if cfg.get("deflicker", True) else "")
          + "," + FF.retime(clip_info(src)["fps"], speed, cfg.get("fps", 30)))
    dst = os.path.join(segdir, f"seg_{i:02d}.mp4")
    # -t BEFORE -i limits how much SOURCE is read, so the output length is dur/speed for
    # speed-ups AND slow-mo. After -i it would cap the OUTPUT and truncate slow-mo.
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-ss", str(seg["start"]), "-t", str(seg["dur"]), "-i", src]
    if cfg.get("ambient_audio"):
        if clip_info(src)["has_audio"]:
            fc = (f"[0:v]{vf}[v];[0:a]aresample=48000,aformat=channel_layouts=stereo,"
                  f"{media.atempo_chain(speed)},apad,atrim=0:{eff:.3f}[a]")
            cmd += ["-filter_complex", fc]
        else:
            cmd += ["-f", "lavfi", "-t", f"{eff:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
                    "-filter_complex", f"[0:v]{vf}[v];[1:a]anull[a]"]
        cmd += ["-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        if ";" in vf or "[" in vf:   # blur fit uses labelled pads
            cmd += ["-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]"]
        else:
            cmd += ["-vf", vf]
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(cfg.get("seg_crf", 12)),
            "-pix_fmt", "yuv420p", dst]
    print(f"[seg {i:02d}] {seg['clip']} {seg['start']}-{seg['start'] + seg['dur']}s "
          f"x{speed:g} +b{eb} -> {os.path.basename(dst)} ({eff:.2f}s)", flush=True)
    if dry:
        print("  " + " ".join(cmd))
    else:
        run_ffmpeg(cmd, f"segment {i:02d} ({os.path.basename(src)})")
    return dst, eff


def seg_luma(src, start, dur, n=5):
    """Mean luma (0-1) of a segment from ``n`` frames across it (the exposure-match input)."""
    import subprocess
    vals = []
    for k in range(n):
        t = start + dur * (k + 0.5) / n
        r = subprocess.run([media.ffmpeg_bin(), "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
                            "-vf", "scale=64:36,format=gray", "-f", "rawvideo", "-"], capture_output=True)
        if r.stdout:
            vals.append(sum(r.stdout) / len(r.stdout) / 255.0)
    return sum(vals) / len(vals) if vals else None


def match_exposure(cfg, strength=None, cap=0.06):
    """Even out exposure jumps at the cuts: each segment's brightness moves ``strength`` of the way toward the
    median segment's mean luma, at most +-``cap`` (a night shot next to a day shot stays a night shot, only the
    step between them gets smaller). Sets seg["_match"]; returns [(clip, luma, offset)]."""
    k = float(cfg.get("match_exposure", 0.6) if strength is None else strength)
    if k <= 0 or len(cfg["segments"]) < 2:
        return []
    lum = []
    for seg in cfg["segments"]:
        src = seg.get("_src") or os.path.join(cfg["_src_dir"], cfg["clips"][seg["clip"]])
        lum.append(seg_luma(src, float(seg["start"]), float(seg["dur"])))
    known = sorted(v for v in lum if v is not None)
    if not known:
        return []
    med = known[len(known) // 2]
    out = []
    for seg, v in zip(cfg["segments"], lum):
        off = 0.0 if v is None else max(-cap, min(cap, (med - v) * k))
        seg["_match"] = round(off, 3)
        out.append((seg["clip"], v, seg["_match"]))
    return out


def clean_speech(cfg, segdir, dry=False):
    """Segments with speech get the shared 气口 / filler / repeat cleanup (vstudio.cleanup, references/CLEANUP.md)
    BEFORE assembly: ``analyze --ranges start-(start+dur)`` -> ``apply`` (auto edits + the creator's approve /
    keep / reply) -> the segment then plays the cleaned clip (start 0, dur = its length). Opt-in per segment
    (``"cleanup": true | "gentle" | {...}``, or ``"speech": true`` with a top-level ``"cleanup"``); needs
    ``ambient_audio`` (a calm master without sound has nothing to clean). Transcript: segment ``words``,
    ``<clip>.words.json`` or ASR. EDL + review sheet: <out dir>/clips/cleanup/."""
    from funvlog import speechclean as SPC
    warnings = []
    for i, seg in enumerate(cfg["segments"]):
        if "cleanup" not in seg and not (seg.get("speech") and cfg.get("cleanup")):
            continue
        o = SPC.options(cfg, seg, default=bool(seg.get("speech")))
        if not o["enabled"]:
            continue
        src = os.path.join(cfg["_src_dir"], cfg["clips"][seg["clip"]])
        if not cfg.get("ambient_audio"):
            print(f"[seg {i:02d}] cleanup skipped: the master has no sound (set \"ambient_audio\": true)", flush=True)
            continue
        if not clip_info(src)["has_audio"]:
            print(f"[seg {i:02d}] cleanup skipped: {seg['clip']} has no audio", flush=True)
            continue
        a0, a1 = float(seg["start"]), min(float(seg["start"]) + float(seg["dur"]), clip_info(src)["duration"])
        if dry:
            print(f"[seg {i:02d}] cleanup ({o['profile']}) {a0:.2f}-{a1:.2f}s (dry run: not analysed)", flush=True)
            continue
        out, dur, lg = SPC.clean_file(src, SPC.words_sidecar(src, seg.get("words")), a0, a1, o,
                                      os.path.join(segdir, "cleanup"), warnings)
        print(f"[seg {i:02d}] cleanup ({o['profile']}): {lg['source_s']:.2f}s -> {dur:.2f}s, "
              f"{len(lg['applied'])} edits cut, {len(lg['confirm_pending'])} to confirm -> {lg['review']}", flush=True)
        seg.update(_src=out, start=0.0, dur=round(dur, 3), _cleanup=lg)
    for w in warnings:
        print("[warn]", w, flush=True)


def main():
    ap = argparse.ArgumentParser(description="Grade + speed + crossfade B-roll clips into one master.")
    ap.add_argument("config", help="edit.json")
    ap.add_argument("--dry-run", action="store_true", help="print commands, render nothing")
    ap.add_argument("--workers", type=int, help="override parallel segment encodes")
    ap.add_argument("--platform", help="platform[:orientation] canvas when the config has no res (see vstudio.platform)")
    a, rest = ap.parse_known_args()

    base = os.path.dirname(os.path.abspath(a.config))
    with open(a.config) as f:
        cfg = json.load(f)
    if cfg.get("style", "calm") == "fun":
        import build_fun
        return build_fun.main([a.config] + (["--dry-run"] if a.dry_run else [])
                              + (["--platform", a.platform] if a.platform else []) + rest)
    if rest:
        ap.error(f"unrecognized arguments: {' '.join(rest)}")
    prof = None
    if (a.platform or cfg.get("platform")) and not cfg.get("res"):
        from vstudio import platform as P
        prof = P.profile(a.platform or cfg["platform"])
        cfg["res"] = [prof.w, prof.h]
        cfg.setdefault("fps", prof.fps.get("default", 30))
        print(f"platform {prof.key}: {prof.w}x{prof.h} @ {cfg['fps']} fps "
              f"(loudness {prof.loudness['lufs']} LUFS via add_music.py --platform {prof.key})", flush=True)
    cfg["_src_dir"] = os.path.join(base, os.path.expanduser(cfg.get("src_dir", ".")))
    out = os.path.join(base, os.path.expanduser(cfg["out"]))
    segdir = os.path.join(os.path.dirname(out), "clips")
    os.makedirs(segdir, exist_ok=True)

    try:
        return render(cfg, out, segdir, prof, a)
    except RenderError as e:
        # the whole ffmpeg output first, the reason last: the desk's stage error keeps the last lines
        head, _, rest = str(e).partition("\n")
        print(rest, file=sys.stderr, flush=True)
        sys.exit(f"!! render failed - {head}")


def render(cfg, out, segdir, prof, a):
    clean_speech(cfg, segdir, a.dry_run)
    if not a.dry_run:
        for clip, v, off in match_exposure(cfg):
            if off:
                print(f"[exposure] {clip}: luma {v:.2f} -> brightness {off:+.3f}", flush=True)
    tasks = [(i, cfg, s, segdir, a.dry_run) for i, s in enumerate(cfg["segments"])]
    with ThreadPoolExecutor(max_workers=a.workers or cfg.get("workers", 3)) as ex:
        results = list(ex.map(render_seg, tasks))
    segs, durs = [r[0] for r in results], [r[1] for r in results]
    print("intermediates done", flush=True)

    D = cfg.get("xfade", 0.8)
    if D > 0 and min(durs) <= D:
        sys.exit(f"a segment is shorter on screen ({min(durs):.2f}s) than the crossfade ({D}s)")
    inputs = []
    for s in segs:
        inputs += ["-i", s]
    audio = bool(cfg.get("ambient_audio"))
    # Kept local (not cut.xfade_assemble): segments are pre-rendered with per-segment HDR/fit/grade/
    # stabilize chains, joins use the configurable "transition", and silent masters have no audio
    # streams; xfade_assemble has one global vf, fixed "fade" and always maps [i:a]. See PORT_NOTES.
    fc, prev, aprev, L = [], "0:v", "0:a", durs[0]
    joins = []
    tr = cfg.get("transition", "fade")
    if tr in DIP_TRANSITIONS and not cfg.get("allow_dips"):
        print(f"[note] transition {tr!r} flashes through black / white between shots: using a plain crossfade "
              "(set \"allow_dips\": true to keep it)", flush=True)
        tr = "fade"
    for k in range(1, len(segs)):
        joins.append([round(L - D, 3), round(L, 3)])
        fc.append(f"[{prev}][{k}:v]xfade=transition={tr}"
                  f":duration={D}:offset={L - D:.3f}[x{k}]")
        prev = f"x{k}"
        if audio:
            fc.append(f"[{aprev}][{k}:a]acrossfade=d={D}[ax{k}]")
            aprev = f"ax{k}"
        L = L + durs[k] - D
    fo = cfg.get("fade_out", 1.5)
    # no fade-in on purpose (no black first frame); only fade out at the end
    fc.append(f"[{prev}]fade=t=out:st={L - fo:.3f}:d={fo}[vout]")
    maps = ["-map", "[vout]"]
    if audio:
        fc.append(f"[{aprev}]afade=t=out:st={L - fo:.3f}:d={fo}[aout]")
        maps += ["-map", "[aout]", "-c:a", "aac", "-b:a", str(persona().get("export", {}).get("audio_bitrate", "192k"))]

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
           *inputs, "-filter_complex", ";".join(fc), *maps,
           "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.get("final_crf", 18)),
           "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
           "-color_trc", "bt709", "-movflags", "+faststart", out]
    print(f"total timeline ~ {L:.1f}s; rendering final -> {out}", flush=True)
    if a.dry_run:
        print("  " + " ".join(cmd))
        return
    run_ffmpeg(cmd, "final crossfade render")
    # the shot changes are crossfades a frame difference cannot see: the export's subject reframe reads them here
    with open(os.path.splitext(out)[0] + ".shots.json", "w") as f:
        json.dump(dict(transitions=joins, duration=round(L, 3), segments=len(segs)), f)
    from vstudio import flicker
    try:
        flicker.check(out, "calm", flicker.mode_for(cfg))
    except flicker.FlickerError as e:
        raise RenderError(f"flicker QC: {e}") from None
    print(f"DONE -> {out}", flush=True)
    if prof is not None:
        from vstudio import platform as P
        for w in P.check_length(prof, L):
            print("[warn]", w)


if __name__ == "__main__":
    main()
