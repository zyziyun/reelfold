"""Shared bits of the story-vlog passes (facecam / textfx / finish / own_voice): the spec's timeline, ffmpeg.

Every pass reads the same spec as render.py and rebuilds the same Timeline, so overlays land on the exact unit
starts. Unit names: spec ``UNITS`` (one per SCRIPT item, e.g. ["c1", "u00", "u02", ...]); without it, the index.
"""
import subprocess

from photostory.ctx import Ctx, load_spec
from photostory.timeline import Timeline, load_timing

FPS = 30
ENC = ["-c:v", "libx264", "-profile:v", "high", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p",
       "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]


def timeline(spec_path):
    """-> (spec, Ctx, Timeline, {unit name: timeline unit dict})."""
    spec = load_spec(spec_path)
    C = Ctx(spec)
    timing, _ = load_timing(C)
    T = Timeline(C, timing)
    names = list(getattr(spec, "UNITS", None) or [str(i) for i in range(len(spec.SCRIPT))])
    return spec, C, T, {names[u["i"]]: u for u in T.units}


def lang_of(spec, C=None):
    """The version's language: spec LANG, else what the captions show (zh / en)."""
    v = getattr(spec, "LANG", None)
    if v:
        return v
    return "en" if (C is not None and getattr(C, "SUBS", "") == "en") else "zh"


def cue_rows(spec, unit):
    """[(start, end, 中文, English)] of a unit: spec VO (voice units) or RAW (clip-sound / music-only units)."""
    vo = getattr(spec, "VO", {}) or {}
    raw = getattr(spec, "RAW", {}) or {}
    if unit in vo:
        return vo[unit]
    return raw[unit][1] if unit in raw else []


def dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout
    return float(out.strip())


def ff(args):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + list(args), capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-800:])
