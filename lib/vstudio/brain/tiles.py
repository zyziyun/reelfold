"""Shot tiles: the moments of each clip with the numbers the treatment planner reads.

    from vstudio.brain import tiles
    ts = tiles.for_clips(["DJI_0081.MP4", ...])   # [{id, clip, file, start, end, best, t, score, sharp, steady,
                                                  #   exposure, jitter_px, pan_px_s, motion, bright, faces, face_area,
                                                  #   subject_frac, subject_xy, speech, src_fps, w, h, thumb, recorded,
                                                  #   lab}]

Source of the moments: ``vstudio.shots`` (TransNet V2 / adaptive cuts, per-moment sharpness, steadiness, exposure)
when the engine has it; otherwise one tile per clip from five sampled frames (sharpness, brightness, frame-to-frame
change; steadiness unknown = 0.6) so the planner still works, more cautiously. Faces (MediaPipe, when installed)
and the subject (``vstudio.saliency``) are read from the tile's best second. ``words``: {clip path: [{start, end}]}
(a transcript) marks the tiles where someone speaks.
"""
import os
import subprocess

import numpy as np


def _shots():
    try:
        from vstudio import shots
        return shots
    except Exception:  # noqa: BLE001  (shot detection not in this engine yet)
        return None


def _ffmpeg():
    from vstudio import media
    try:
        return media.ffmpeg_bin() or "ffmpeg"
    except Exception:  # noqa: BLE001
        return "ffmpeg"


def _grab(src, t, width=320):
    """One frame (BGR uint8) at ``t`` s, or None."""
    cmd = [_ffmpeg(), "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", src, "-frames:v", "1", "-vf",
           f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    if not out:
        return None
    import cv2
    return cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)


def _read(path):
    if not path or not os.path.exists(path):
        return None
    import cv2
    return cv2.imread(path, cv2.IMREAD_COLOR)


_SAL = {}


def look(img):
    """A frame -> {faces, face_area, subject_frac, subject_xy, bright, lab}: who / what is in it, where."""
    import cv2
    out = dict(faces=None, face_area=None, subject_frac=None, subject_xy=None, subject_spread=None, bright=None,
               lab=None)
    if img is None:
        return out
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    out["bright"] = round(float(g.mean()) / 255.0, 3)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    out["lab"] = [round(float(x), 1) for x in lab.mean(axis=0)]
    try:
        from vstudio.intake import inventory as I
        areas = I._face_areas(img)
        out["faces"] = len([a for a in areas if a >= 0.002])
        out["face_area"] = round(areas[0], 4) if areas else 0.0
    except Exception:  # noqa: BLE001  (no MediaPipe / model: faces unknown)
        pass
    try:
        from vstudio import saliency as S
        if "an" not in _SAL:
            _SAL["an"] = S.Analyzer(person=None)
        an = _SAL["an"]
        an.reset()
        small = cv2.resize(img, (S.GRID_W, max(1, int(round(img.shape[0] * S.GRID_W / img.shape[1])))))
        m = an(small)["map"]
        thr = m >= max(0.5, float(np.percentile(m, 90)))
        if thr.any():
            ys, xs = np.nonzero(thr)
            out["subject_frac"] = round(float(thr.mean()), 3)
            out["subject_xy"] = [round(float(xs.mean()) / m.shape[1], 2), round(float(ys.mean()) / m.shape[0], 2)]
            # how gathered the interest is: one compact subject (a boat, a person) vs interest all over a wide view
            out["subject_spread"] = round(float(np.hypot(xs.std() / m.shape[1], ys.std() / m.shape[0])), 3)
    except Exception:  # noqa: BLE001  (saliency needs opencv; without it the subject is unknown)
        pass
    return out


def _speech(words, a, b):
    if not words:
        return 0.0
    cov = 0.0
    for w in words:
        lo, hi = max(a, float(w.get("start", 0))), min(b, float(w.get("end", 0)))
        if hi > lo:
            cov += hi - lo
    return round(min(1.0, cov / max(0.1, b - a)), 2)


def _fallback(src, info):
    """No ``shots``: one tile per clip from five frames."""
    import cv2
    dur = float(info.get("duration") or 0)
    ts = [dur * k / 6 for k in range(1, 6)] if dur > 0 else [0.0]
    frames = [f for f in (_grab(src, t, 160) for t in ts) if f is not None]
    if not frames:
        return []
    greys = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32) for f in frames]
    sharp = np.mean([np.clip((np.log10(cv2.Laplacian(g, cv2.CV_32F).var() + 1.0) - 1.5) / 2.0, 0, 1) for g in greys])
    lum = np.array([g.mean() for g in greys])
    expo = float(np.mean(1 - np.clip(np.abs(lum - 118.0) / 118.0, 0, 1) ** 1.5))
    mot = float(np.mean([np.abs(a - b).mean() for a, b in zip(greys, greys[1:])])) if len(greys) > 1 else 0.0
    steady = 0.6
    score = 0.40 * sharp + 0.35 * steady + 0.25 * expo
    mid = dur / 2
    return [dict(id="S1", start=0.0, end=round(dur, 2), best=[round(max(0, mid - 2), 2), round(min(dur, mid + 2), 2)],
                 t=round(mid, 2), score=round(float(score), 3), sharp=round(float(sharp), 3), steady=steady,
                 exposure=round(expo, 3), jitter_px=None, pan_px_s=None, motion=round(mot, 2), approx=True)]


def for_clip(src, words=None, faces=True):
    from vstudio import media
    info = media.probe(src)
    S = _shots()
    rows, thumb_of = [], None
    if S is not None:
        a = S.analyze(src)
        secs = a.get("secs") or []
        for m in S.moments(a):
            ss = [x for x in secs if m["start"] <= x["t"] < m["end"]] or secs[:1]
            rows.append(dict({k: m.get(k) for k in ("id", "start", "end", "best", "t", "score", "sharp", "steady",
                                                     "exposure", "jitter_px", "pan_px_s")},
                             motion=round(float(np.mean([x["motion"] for x in ss])), 2) if ss else None))
        thumb_of = lambda t: S.thumb(a, t)  # noqa: E731
    else:
        rows = _fallback(src, info)
    try:
        from vstudio import footage
        f = footage.facts(src)
    except Exception:  # noqa: BLE001
        f = {}
    w, h = f.get("w") or info.get("w"), f.get("h") or info.get("h")
    out = []
    for r in rows:
        th = thumb_of(r["t"]) if thumb_of else None
        img = _read(th) if th else _grab(src, r["t"])
        lk = look(img) if faces else dict(look(None))
        out.append(dict(r, clip=os.path.abspath(src), file=os.path.basename(src), src_fps=round(float(info.get("fps") or 0), 2),
                        w=w, h=h, recorded=f.get("recorded"), time_of_day=f.get("time_of_day"), aerial=bool(f.get("gps")),
                        city=(f.get("city") or {}).get("en"), thumb=th, speech=_speech((words or {}).get(src), r["start"], r["end"]),
                        **lk))
    return out


def for_clips(paths, words=None, faces=True, echo=None):
    """Tiles of every clip, clips in recording order (else name order); tile ids ``<clip#>.<moment id>``."""
    from vstudio import footage
    vids = [p for p in paths if footage.is_video(p)]

    def when(p):
        try:
            return footage.facts(p).get("recorded") or os.path.basename(p)
        except Exception:  # noqa: BLE001
            return os.path.basename(p)
    vids.sort(key=when)
    out = []
    for k, p in enumerate(vids):
        if echo:
            echo(f"tiles: {os.path.basename(p)} ({k + 1}/{len(vids)})")
        for t in for_clip(p, words, faces):
            t["id"] = f"C{k + 1}.{t['id']}"
            t["clip_no"] = k + 1
            out.append(t)
    return out
