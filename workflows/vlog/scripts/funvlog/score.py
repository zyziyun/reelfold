"""Per-second clip scores and best-window picking (auto windows when the edit list gives none).

score = 0.35 sharpness + 0.30 motion (moderate motion preferred, a frozen or whipping frame scores low)
      + 0.20 brightness (mid-grey best, crushed or blown frames low) + 0.15 face (a face in frame).
Samples are grey 160-px frames at 4 fps from vstudio.shots' single low-res decode (faces: its 320-px thumbnails, one
a second, vstudio.face when MediaPipe works).
Results are cached in <cache>/scores_<hash>.json keyed by path, size and mtime.
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "lib"))
import hashlib
import json
import os

import numpy as np

from vstudio import media

W_SHARP, W_MOTION, W_BRIGHT, W_FACE = 0.35, 0.30, 0.20, 0.15
MOTION_BEST = 8.0          # mean abs grey diff (0-255) between samples 0.25 s apart that reads as "lively"


def _faces_per_sec(a):
    """{second: 1/0} on the kept 320-px thumbnails (vstudio.shots, one per second) via vstudio.face; {} when
    MediaPipe is unavailable. No second decode of the clip."""
    try:
        from vstudio import face as F
        lm = F.landmarker(num_faces=1)
    except Exception:
        return {}
    import cv2
    from vstudio import shots as S
    out = {}
    try:
        for s in a["secs"]:
            k = s["t"]
            img = cv2.imread(S.thumb(a, k + 0.5))
            if img is None:
                continue
            try:
                out[k] = 1.0 if F.detect(lm, np.ascontiguousarray(img)) else 0.0
            except Exception:
                out[k] = 0.0
    finally:
        try:
            lm.close()
        except Exception:
            pass
    return out


def clip_scores(src, cache_dir=None, faces=True):
    """Per-second scores for ``src``: dict(duration, fps, secs=[{t, score, sharp, motion, bright, face}]).

    The inputs come from ``vstudio.shots.analyze`` (cached): ONE low-res decode of the clip (VideoToolbox + scale_vt
    on a Mac), not two full-resolution software decodes - a 4K HEVC reel on an SD card went from ~an hour to
    minutes."""
    st = os.stat(src)
    key = hashlib.sha1(f"{os.path.abspath(src)}|{st.st_size}|{st.st_mtime}|{faces}|v2".encode()).hexdigest()[:16]
    cp = os.path.join(cache_dir, f"scores_{key}.json") if cache_dir else None
    if cp and os.path.exists(cp):
        with open(cp) as f:
            return json.load(f)
    from vstudio import shots as S
    a = S.analyze(os.fspath(src))
    info = media.probe(src)
    dur = info["duration"] or a["dur"]
    fc = _faces_per_sec(a) if faces else {}
    secs = []
    for r in a["secs"]:
        k = r["t"]
        sharp, bright, motion = r["sharp"], r["bright"], r["motion"]
        s_sharp = float(np.clip(np.log10(sharp + 1.0) / 3.0, 0, 1))
        s_motion = float(np.exp(-((motion - MOTION_BEST) / MOTION_BEST) ** 2))
        s_bright = float(1 - np.clip(abs(bright - 125.0) / 125.0, 0, 1) ** 1.5)
        s_face = float(fc.get(k, 0.0))
        score = W_SHARP * s_sharp + W_MOTION * s_motion + W_BRIGHT * s_bright + W_FACE * s_face
        secs.append(dict(t=k, score=round(score, 4), sharp=sharp, motion=motion, bright=bright, face=s_face))
    flash = {int(t) for t in a.get("flashes") or []}
    for r in secs:                                   # never pick a window around a flash frame
        if r["t"] in flash:
            r["score"] = 0.0
    if not secs:
        secs = [dict(t=0, score=0.0, sharp=0.0, motion=0.0, bright=0.0, face=0.0)]
    res = dict(src=os.fspath(src), duration=dur, fps=info["fps"], secs=secs)
    if cp:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cp, "w") as f:
            json.dump(res, f)
    return res


def _curve(scores, step=0.25):
    secs = scores["secs"]
    dur = scores["duration"]
    ts = np.arange(0.0, max(step, dur), step)
    vals = np.array([secs[min(len(secs) - 1, int(t))]["score"] for t in ts]) if secs else np.zeros(len(ts))
    return ts, vals


def window_score(scores, start, length):
    ts, vals = _curve(scores)
    m = (ts >= start - 1e-6) & (ts < start + length - 1e-6)
    return float(vals[m].mean()) if m.any() else 0.0


def pick_window(scores, length, avoid=(), edge=0.3, step=0.25):
    """Start time of the best ``length``-second window (sliding mean of the per-second score), keeping
    ``edge`` s clear of the clip ends (dead heads/tails) when possible and penalising overlap with
    ``avoid`` [(a, b)] spans already used. Returns (start, mean score)."""
    dur = float(scores["duration"])
    if length >= dur - 1e-3:
        return 0.0, window_score(scores, 0.0, dur)
    lo = min(edge, max(0.0, dur - length) / 2)
    hi = max(lo, dur - length - lo)
    best = (lo, -1e9)
    ts, vals = _curve(scores, step)
    for s in np.arange(lo, hi + 1e-6, step):
        m = (ts >= s - 1e-6) & (ts < s + length - 1e-6)
        v = float(vals[m].mean()) if m.any() else 0.0
        ov = sum(max(0.0, min(s + length, b) - max(s, a)) for a, b in avoid) / max(length, 1e-6)
        v_eff = v - 0.6 * ov
        if v_eff > best[1] + 1e-9:
            best = (float(s), v_eff)
    return round(best[0], 3), round(window_score(scores, best[0], length), 4)


def best_second(scores):
    secs = scores["secs"] or [dict(t=0, score=0.0)]
    s = max(secs, key=lambda r: r["score"])
    return s["t"], s["score"]
