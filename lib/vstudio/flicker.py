"""Flicker QC: find flashes, blinks and strobing in a rendered video from its frame-to-frame luminance.

    from vstudio import flicker
    rep = flicker.analyze("out/story.mp4")            # {ok, max_jump, flash, blink, events, ...}
    flicker.check("out/story.mp4")                    # raises FlickerError when the video flickers
    flicker.check(out, mode=flicker.mode_for(cfg))    # "fail" (default) | "warn" | "off"

    python3 -m vstudio.flicker out/story.mp4 [--json] [--profile calm|energetic]

What it measures (every frame, scaled down to an 8x8 grid of mean luma, 0-255):

  max_jump   the largest change of the whole frame's mean luma from one frame to the next. A hard cut between two
             shots of different exposure shows here; it is reported (the before/after number of a fix) but is not
             a failure on its own - a cut is one step, not a flicker.
  flash      a TRANSIENT: the picture (whole frame, or one quarter of it) goes brighter or darker than it is both
             0.35-0.6 s before and 0.35-0.6 s after, and comes back. A white flash transition, a dip through black
             between shots, a light leak, a box that pops in and out: all flashes. Value = the excursion in levels.
  blink      the same over 0.1-0.3 s on a horizontal band (a quarter of the frame's height): a subtitle that is cut
             out for a frame or two before the next one fades in, a lower third that flickers, strobing cuts.

  colour     the same as flash on the picture's mean colour cast (Cb / Cr): a warm light leak or a tinted dip that
             barely changes the brightness (DJI 06's leak: 5.7; every remade film <= 3.7).

A cut, a crossfade between two shots, a slow fade in / out (the first 0.5 s and the last 2 s are not judged) and
real motion in the picture are steps or slow changes, not transients; each excursion is also reduced by 4x the
picture's own frame-to-frame activity around it (busy water spray or a fast drone pass is not a flash). On the six
DJI test films the clean ones scored at most 7.6 (flash), 16.5 (one quarter), 4.5 (blink); the flawed ones (white
flash hits, a light-leak transition, subtitle blinks, a timeline box popping) 7.7 to 178.

Limits per profile (``LIMITS``): calm (films, vlogs, stories) and energetic (beat reels, a little more room for
fast cuts). A render recipe calls ``check`` on its final file; ``qc.flicker`` in the persona or the recipe config
(``"fail"`` | ``"warn"`` | ``"off"``) decides whether a flicker stops the render.
"""
import argparse
import json
import subprocess
import sys

import numpy as np

GRID = 8
LIMITS = {
    "calm": dict(flash=10.0, flash_region=20.0, blink=7.0, colour=5.0),
    # beat reels: cuts every beat between spray, sun glitter and dark water are content, not flicker - only a whole-frame
    # flash (white flash hits, impact frames) or gross strobing fails (the 2026-10-12 jet-ski reel: 119 / 173 / 179;
    # its clean remake: 14 / 64 / 35)
    "energetic": dict(flash=16.0, flash_region=90.0, blink=60.0, colour=8.0),
}
HEAD_S, TAIL_S = 0.5, 2.0            # the opening and the closing fade are not judged
ACT_K = 4.0                          # a transient counts above 4x the picture's own frame-to-frame activity


class FlickerError(RuntimeError):
    """A render flickers: ``report`` holds the measurements and the events (time, kind, level)."""

    def __init__(self, report):
        self.report = report
        super().__init__(describe(report))


def _ff():
    try:
        from . import media
        return media.ffmpeg_bin()
    except Exception:  # noqa: BLE001
        return "ffmpeg"


def _fps(path):
    try:
        from . import media
        f = float(media.probe(path)["fps"] or 0)
        if f > 0:
            return f
    except Exception:  # noqa: BLE001
        pass
    return 30.0


def luma_grid(path, grid=GRID, fps=None, chroma=False):
    """-> (frames (n, grid, grid) float32 mean luma per cell, fps) [, chroma (n, 2) mean Cb / Cr - 128 per frame].
    One ffmpeg decode, area-scaled."""
    fps = fps or _fps(path)
    s = grid * 4
    out = subprocess.run([_ff(), "-v", "error", "-i", path, "-map", "0:v:0", "-vf",
                          f"scale={s}:{s}:flags=area,format=yuv444p", "-f", "rawvideo", "-"],
                         capture_output=True, timeout=3600)
    if out.returncode != 0:
        raise RuntimeError(f"flicker: cannot decode {path}: {out.stderr.decode(errors='replace')[-300:]}")
    a = np.frombuffer(out.stdout, np.uint8)
    n = len(a) // (3 * s * s)
    P = a[:n * 3 * s * s].reshape(n, 3, s, s).astype(np.float32)
    F = P[:, 0].reshape(n, grid, 4, grid, 4).mean((2, 4))
    if chroma:
        return F, fps, P[:, 1:].mean((2, 3)) - 128.0
    return F, fps


def transients(Y, fps, near=0.35, far=0.6):
    """Excursion of every frame from its surroundings: ``Y`` (n, ...) -> (n, ...) levels, > 0 only where the frame
    is brighter (or darker) than BOTH the median of [-far, -near] s and of [+near, +far] s around it."""
    Y = np.asarray(Y, np.float32)
    n = len(Y)
    k0 = max(1, int(round(near * fps)))
    k1 = max(k0 + 1, int(round(far * fps)))
    amp = np.zeros_like(Y)
    if n <= 2 * k1:
        return amp
    from numpy.lib.stride_tricks import sliding_window_view as win
    w = k1 - k0
    med = np.median(win(Y, w, axis=0), axis=-1)          # med[j] = median(Y[j:j+w])
    idx = np.arange(k1, n - k1)
    before = med[idx - k1]
    after = med[idx + k0]
    d1, d2 = Y[idx] - before, Y[idx] - after
    same = np.sign(d1) == np.sign(d2)
    amp[idx] = np.where(same, np.minimum(np.abs(d1), np.abs(d2)), 0.0)
    return amp


def activity(Y, fps, half=0.5):
    """How much the picture moves around each frame: the median frame-to-frame change over +-``half`` s."""
    Y = np.asarray(Y, np.float32)
    d = np.abs(np.diff(Y, axis=0, prepend=Y[:1]))
    k = max(1, int(round(half * fps)))
    from numpy.lib.stride_tricks import sliding_window_view as win
    pad = np.concatenate([np.repeat(d[:1], k, 0), d, np.repeat(d[-1:], k, 0)])
    return np.median(win(pad, 2 * k + 1, axis=0), axis=-1)


def score(Y, fps, near=0.35, far=0.6, k=ACT_K):
    """Transient excursion minus ``k`` x the local activity: fast real motion (spray, a drone crossing bright rocks)
    is busy all around its transient; a flash or a blinking subtitle on a calm shot is not."""
    return np.maximum(0.0, transients(Y, fps, near, far) - k * activity(Y, fps))


def _events(series, fps, limit, kind, start, merge=0.3):
    """Runs of ``series`` (judged frames) above ``limit`` -> [{t, end, kind, level}]."""
    out = []
    for i in np.nonzero(series > limit)[0]:
        t = (i + start) / fps
        if out and t - out[-1]["end"] <= merge:
            out[-1]["end"] = round(t, 2)
            out[-1]["level"] = round(max(out[-1]["level"], float(series[i])), 1)
        else:
            out.append(dict(t=round(t, 2), end=round(t, 2), kind=kind, level=round(float(series[i]), 1)))
    return out


def measure(F, fps, profile="calm", C=None):
    """Measurements of a luma grid (see the module doc) [+ ``C`` (n, 2) mean chroma per frame: a colour flash -
    a warm light leak, a tinted dip - is a transient of the picture's colour cast] -> report dict."""
    lim = LIMITS.get(profile) or LIMITS["calm"]
    n = len(F)
    full = F.reshape(n, -1).mean(1) if n else np.zeros(0)
    jumps = np.abs(np.diff(full)) if n > 1 else np.zeros(1)
    s0, s1 = int(round(HEAD_S * fps)), max(0, n - int(round(TAIL_S * fps)))
    rep = dict(frames=n, fps=round(float(fps), 3), profile=profile, limits=lim,
               max_jump=round(float(jumps.max()) if len(jumps) else 0.0, 1),
               p99_jump=round(float(np.percentile(jumps, 99)) if len(jumps) else 0.0, 2),
               flash=0.0, flash_region=0.0, blink=0.0, colour=0.0, events=[])
    if s1 - s0 < 3:
        rep["ok"] = True
        return rep
    g = F.shape[1]
    quads = F.reshape(n, 2, g // 2, 2, g // 2).mean((2, 4)).reshape(n, 4)
    bands = F.reshape(n, 4, g // 4, g).mean((2, 3))
    fl = score(full, fps)[s0:s1]
    fq = score(quads, fps).max(1)[s0:s1]
    bl = score(bands, fps, 0.1, 0.3).max(1)[s0:s1]
    rep.update(flash=round(float(fl.max()), 1), flash_region=round(float(fq.max()), 1), blink=round(float(bl.max()), 1))
    ev = (_events(fl, fps, lim["flash"], "flash", s0) + _events(fq, fps, lim["flash_region"], "flash_region", s0)
          + _events(bl, fps, lim["blink"], "blink", s0))
    if C is not None and len(C) == n:
        fc = score(np.asarray(C, np.float32), fps).max(1)[s0:s1]
        rep["colour"] = round(float(fc.max()), 1)
        ev += _events(fc, fps, lim["colour"], "colour", s0)
    rep["events"] = sorted(ev, key=lambda e: e["t"])
    rep["ok"] = not rep["events"]
    return rep


def analyze(path, profile="calm"):
    """Measure a video file (see the module doc)."""
    F, fps, C = luma_grid(path, chroma=True)
    rep = measure(F, fps, profile, C)
    rep["file"] = str(path)
    return rep


WHAT = dict(flash="the whole picture flashes", flash_region="part of the picture flashes",
            colour="the picture's colour flashes (a light leak / tinted dip)",
            blink="a band of the picture blinks (subtitle / title popping, strobing cuts)")


def describe(rep, n=6):
    """One plain-English line per kind of problem."""
    if rep.get("ok"):
        return (f"no flicker (largest frame-to-frame luma change {rep['max_jump']}, flash {rep['flash']}, "
                f"blink {rep['blink']})")
    parts = []
    for kind in ("flash", "flash_region", "blink", "colour"):
        ev = [e for e in rep["events"] if e["kind"] == kind]
        if ev:
            at = ", ".join(f"{e['t']:.1f}s" for e in ev[:n]) + (" ..." if len(ev) > n else "")
            parts.append(f"{WHAT[kind]} at {at} (up to {max(e['level'] for e in ev):.0f} levels, "
                         f"limit {rep['limits'][kind]:.0f})")
    return "flicker: " + "; ".join(parts)


def mode_for(cfg=None):
    """$VSTUDIO_FLICKER_QC, else ``qc.flicker`` of the recipe config, else the persona's, else "fail"."""
    import os
    env = os.environ.get("VSTUDIO_FLICKER_QC")
    if env:
        return env.lower()
    for src in (cfg or {}, _persona()):
        q = src.get("qc") if isinstance(src, dict) else None
        v = q.get("flicker") if isinstance(q, dict) else None
        if v is not None:
            v = str(v).lower()
            return {"false": "off", "no": "off", "true": "fail"}.get(v, v)
    return "fail"


def _persona():
    try:
        from .config import persona
        return persona() or {}
    except Exception:  # noqa: BLE001
        return {}


def check(path, profile="calm", mode=None, report_path=None, log=print):
    """Analyze ``path``; write the report next to it (``<out>.flicker.json``); raise FlickerError when it flickers
    and ``mode`` is "fail". Returns the report (None when mode is "off")."""
    mode = mode or mode_for()
    if mode == "off":
        return None
    rep = analyze(path, profile)
    rp = report_path or (str(path).rsplit(".", 1)[0] + ".flicker.json")
    try:
        with open(rp, "w") as f:
            json.dump(rep, f, indent=1)
    except OSError:
        pass
    if log:
        log(f"flicker QC ({profile}): {describe(rep)}")
    if not rep["ok"] and mode == "fail":
        raise FlickerError(rep)
    return rep


def _cli(argv=None):
    ap = argparse.ArgumentParser(description="Flicker QC of a rendered video (flashes, blinks, strobing).")
    ap.add_argument("video", nargs="+")
    ap.add_argument("--profile", default="calm", choices=sorted(LIMITS))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    bad = 0
    for v in a.video:
        rep = analyze(v, a.profile)
        bad += not rep["ok"]
        print(json.dumps(rep) if a.json else f"{v}: {describe(rep)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_cli())
