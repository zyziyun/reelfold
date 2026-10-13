"""Reframe a video to another canvas: face-tracked virtual camera, centre crop, blurred-fill or letterbox.

    from vstudio import reframe as R
    plan = R.plan("talk-16x9.mp4", 1080, 1440, mode="face", safe=(48, 60, 1032, 1290))
    R.render("talk-16x9.mp4", "talk-3x4.mp4", plan)            # rawvideo pipe: decode -> warp -> encode
    R.reframe("talk-16x9.mp4", "talk-9x16.mp4", 1080, 1920)     # plan + render + <dst>.crop.json
    pl = R.plan(None, 1080, 1920, frames=frames, fps=30)        # frames already in memory: decode once
    R.render(src, dst, pl, frames=frames)                       # HDR sources are tone-mapped (hdr="auto")

    python -m vstudio.reframe talk.mp4 out.mp4 --size 1080x1920 --mode face [--platform douyin]

Modes
  face       the main face is kept inside the target ``safe`` box (target px; e.g. platform.safe_box) with
             the eye line ~1/3 down it (headroom rule). Faces are detected every ``every`` frames
             (MediaPipe via vstudio.face, or any ``detector(bgr) -> [(x0, y0, x1, y1[, talk])]``), the target
             is One-Euro filtered (vstudio.filters), then followed by a virtual camera with a dead zone (small
             moves never drift the crop), an acceleration-limited eased pan and a max pan speed. Shot cuts
             (frame-difference spikes) reset the camera: a hard cut never becomes a pan. Several faces: the
             largest / most-talking (mouth-movement energy, as face.talk_activity) is followed; switching
             needs a sustained lead (``switch_hold`` s) and is done as an eased pan.
             No face found (hit rate < ``min_hit``) -> ``fallback`` mode ("pad-blur" by default).
  subject    "Follow the subject" for footage without a talking head (travel / vlog / drone): per shot, faces
             when there is a sizeable one, else where the eye goes (vstudio.saliency: spectral residual + colour
             contrast + motion that is not the drone's own + MediaPipe person mask) -> a globally smooth window path
             (dynamic programming over the shot), placed at the target's safe-box centre above the caption band,
             then the same damped virtual camera. Shot-aware: hard cuts reset, ``transitions`` ([t0, t1] s, e.g.
             a crossfade) ease from one framing to the next inside the dissolve; a shot whose target barely moves
             (or is short) holds still. A shot that cannot be cropped meaningfully - two subjects too far apart
             for one window, or a panorama with nothing standing out - is shown whole on a blurred fill (only that
             shot); ``shots`` in the plan says what each shot got and why.
  center     fixed centre crop.  pad-blur  fit inside, blurred+dimmed fill behind.  letterbox  fit on black.

The plan is plain JSON: per-frame crop rects [x, y, w, h] in source pixels (float, sub-pixel; render uses
cv2.warpAffine so slow pans don't step); a ``null`` rect (subject mode) = that frame is shown whole on a blurred
fill. Subject renders let ffmpeg scale the source to the crop's scale first (a 4K drone master is decoded once and
never warped at 4K).
"""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np

from . import media

MODES = ("face", "subject", "center", "pad-blur", "letterbox")

DEFAULTS = dict(
    every=None,            # detect every N frames (default ~6 Hz)
    analysis_w=960,        # detection frame width
    max_faces=3,
    zoom=1.0,              # >1 = tighter crop than the largest box of the target aspect
    headroom=1 / 3,        # eye line at this fraction down the safe box
    dead_zone=0.06,        # fraction of the crop size the target may move before the camera follows
    settle=0.015,          # once moving, stop when within this fraction (hysteresis)
    gain=3.0,              # 1/s: camera speed per unit of error beyond the dead zone
    max_speed=0.45,        # crop widths (or heights) per second
    max_accel=1.2,         # crop widths per second^2 (eases pans in and out)
    min_cutoff=0.6, beta=0.6,   # One Euro on the normalised target
    cut_thresh=28.0,       # mean abs diff (0-255) of 64x36 grey thumbnails that counts as a shot cut
    switch_margin=0.20,    # challenger score lead needed to switch subject
    switch_hold=1.5,       # ... held for this many seconds
    lost_hold=1.0,         # keep framing the last face position this long after it disappears
    talk_weight=0.5,       # weight of mouth-movement energy vs face size in the subject score
    min_hit=0.15,          # below this face hit rate -> fallback
    fallback="pad-blur",
    blur_dim=0.72,
)

# subject mode (overrides DEFAULTS where the names match: a calmer camera than a talking head's)
SUBJECT = dict(
    analysis_w=640,        # decode width of the analysis pass
    sample_hz=4.0,         # interest maps per second
    face_min=0.025,        # a face narrower than this share of the source width is no subject (aerial crowds)
    face_hit=0.35,         # a shot is framed by its faces when this share of its samples has one
    move_cost=0.8,         # path cost of moving the window across the whole frame between two samples
    center_bias=0.05,      # a slight pull to the middle when nothing stands out
    peak=1.6,              # a column with > peak x the shot's median interest is "subject"
    split=0.55,            # a subject peak outside the window >= split x the one inside -> that sample cannot be cropped
    split_share=0.5,       # ... in this share of a shot's samples -> the shot is shown whole (blurred fill)
    panorama=4.0,          # the crop keeps < 1/panorama of the width and nothing stands out -> shown whole
    shot_pad=True,         # False: such shots are cropped on their strongest interest too (no blurred bands)
    hold=0.06,             # the shot's target moves less than this share of the crop -> the camera holds still
    min_shot=1.2,          # shots shorter than this (s) hold still
    lead=0.4,              # s the camera looks ahead on the (offline) target path: it arrives with the subject
    dead_zone=0.08, settle=0.02, gain=3.0, max_speed=0.50, max_accel=0.8,
    min_cutoff=0.4, beta=0.3,
)


# ----------------------------------------------------------------------------------- geometry
def crop_size(sw, sh, tw, th, zoom=1.0):
    """Largest (w, h) of the target aspect inside a sw x sh source, divided by zoom."""
    ta = tw / th
    if sw / sh > ta:
        ch, cw = sh, sh * ta
    else:
        cw, ch = sw, sw / ta
    return cw / zoom, ch / zoom


def _fit(sw, sh, tw, th):
    s = min(tw / sw, th / sh)
    w, h = max(2, int(round(sw * s / 2)) * 2), max(2, int(round(sh * s / 2)) * 2)
    return w, h, (tw - w) // 2, (th - h) // 2


def _desired(face_box, cw, ch, sw, sh, tw, safe, headroom):
    """Crop top-left (x, y) that puts a face box inside the safe box with the eye line at headroom."""
    fx0, fy0, fx1, fy1 = face_box
    s = tw / cw
    sx0, sy0, sx1, sy1 = (v / s for v in safe)
    fcx = (fx0 + fx1) / 2
    eye = fy0 + 0.42 * (fy1 - fy0)                         # landmark box: forehead..chin, eyes ~0.42
    x = fcx - (sx0 + sx1) / 2
    y = eye - (sy0 + (sy1 - sy0) * headroom)
    lo, hi = fx1 - sx1, fx0 - sx0                          # keep the whole face inside the safe box
    if lo <= hi:
        x = min(max(x, lo), hi)
    lo, hi = fy1 - sy1, fy0 - sy0
    if lo <= hi:
        y = min(max(y, lo), hi)
    return min(max(x, 0.0), sw - cw), min(max(y, 0.0), sh - ch)


# ----------------------------------------------------------------------------------- detection
def _face_detector(max_faces, analysis_w):
    from . import face
    lm = face.landmarker(max_faces, video=True)

    def det(bgr, ts_ms):
        import cv2
        h, w = bgr.shape[:2]
        k = min(1.0, analysis_w / w)
        small = cv2.resize(bgr, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else bgr
        out = []
        for f in face.detect(lm, np.ascontiguousarray(small), ts_ms):
            p = f["pts"] / k
            out.append((float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max()),
                        face.mouth_gap(f["pts"])))
        return out
    det.close = lm.close
    return det


def _scan(src, start, dur, every, detector, cut_thresh=None, frames=None, fps=None, region=None):
    """One decode pass: per-frame thumbnail differences + detections at sample frames (and right after a
    cut). frames: already-decoded BGR frames (sequence or iterator) of the window instead of decoding
    ``src``; region: (x, y, w, h) sub-rectangle analysed instead of the whole frame.
    Returns fps, n, sw, sh, diffs[n], samples {i: [(x0, y0, x1, y1, talk|None)]}."""
    import cv2
    cap = None
    if frames is None:
        cap = cv2.VideoCapture(str(src))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if start:
            cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
        it = None
    else:
        fps = fps or 30.0
        it = iter(frames)
    n_max = int(round(dur * fps)) if dur else None
    diffs, samples, prev, i, sw, sh, force = [], {}, None, 0, 0, 0, False
    try:
        while n_max is None or i < n_max:
            if it is None:
                ok, fr = cap.read()
            else:
                fr = next(it, None)
                ok = fr is not None
            if not ok:
                break
            if region is not None:
                rx, ry, rw, rh = (int(round(v)) for v in region)
                fr = fr[ry:ry + rh, rx:rx + rw]
            sh, sw = fr.shape[:2]
            th = cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
            d = float(np.abs(th - prev).mean()) if prev is not None else 0.0
            diffs.append(d)
            prev = th
            if d > 0 and i > 0 and _is_cut(diffs, i, cut_thresh):
                force = True
            if i % every == 0 or force:
                res = detector(fr, int(round(i / fps * 1000))) if _takes_ts(detector) else detector(fr)
                samples[i] = [tuple(b) + (None,) * (5 - len(b)) for b in (res or [])]
                force = False
            i += 1
    finally:
        if cap is not None:
            cap.release()
    return fps, i, sw, sh, diffs, samples


def _takes_ts(fn):
    try:
        import inspect
        return len(inspect.signature(fn).parameters) >= 2
    except (TypeError, ValueError):
        return False


def _is_cut(diffs, i, thresh=None):
    t = thresh if thresh is not None else DEFAULTS["cut_thresh"]
    d = diffs[i]
    if d < t:
        return False
    recent = diffs[max(1, i - 15):i]
    base = float(np.median(recent)) if recent else 0.0
    return d > 3.0 * base + 4.0


def shot_cuts(diffs, thresh=None):
    """Frame indices that start a new shot (frame-difference spikes)."""
    return [i for i in range(1, len(diffs)) if _is_cut(diffs, i, thresh)]


# ----------------------------------------------------------------------------------- subject choice
def _choose_subjects(samples, n, fps, cuts, sw, sh, o):
    """Per-sample chosen face box (or None), tracking identities by proximity; switches need a sustained
    lead. Returns {i: box}, number of switches."""
    order = sorted(samples)
    cutset = sorted(cuts)
    tracks, cur, chosen, switches = [], None, {}, 0
    lead_since = {}
    hist_n = max(3, int(round(0.8 * fps / max(1, o["every"]))))
    seg_of = lambda i: sum(1 for c in cutset if c <= i)
    last_seg = None
    for i in order:
        seg = seg_of(i)
        if seg != last_seg:                           # new shot: forget everything
            tracks, cur, lead_since, last_seg = [], None, {}, seg
        faces = samples[i]
        # associate
        used = set()
        for tr in tracks:
            bx = tr["box"]; cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2; sz = max(bx[2] - bx[0], 1)
            best, bd = None, 0.6 * sz
            for k, f in enumerate(faces):
                if k in used:
                    continue
                d = math.hypot((f[0] + f[2]) / 2 - cx, (f[1] + f[3]) / 2 - cy)
                if d < bd:
                    best, bd = k, d
            if best is not None:
                used.add(best); f = faces[best]
                tr.update(box=f[:4], seen=i)
                if f[4] is not None:
                    tr["talk"].append(f[4]); tr["talk"] = tr["talk"][-hist_n:]
        for k, f in enumerate(faces):
            if k not in used:
                tracks.append(dict(id=len(tracks) + 1000 * seg, box=f[:4], seen=i,
                                   talk=[f[4]] if f[4] is not None else []))
        lost_frames = o["lost_hold"] * fps
        tracks = [t for t in tracks if i - t["seen"] <= lost_frames]
        live = [t for t in tracks if t["seen"] == i]
        if not live:
            chosen[i] = next((t["box"] for t in tracks if cur is not None and t["id"] == cur), None)
            continue
        areas = {t["id"]: (t["box"][2] - t["box"][0]) * (t["box"][3] - t["box"][1]) for t in live}
        energy = {t["id"]: float(np.std(t["talk"])) if len(t["talk"]) >= 3 else 0.0 for t in live}
        amax, emax = max(areas.values()) or 1.0, max(energy.values())
        tw = o["talk_weight"] if emax > 0.004 else 0.0
        score = {k: (1 - tw) * areas[k] / amax + tw * (energy[k] / emax if emax else 0) for k in areas}
        best = max(score, key=score.get)
        if cur is not None and cur not in score:
            held = next((t for t in tracks if t["id"] == cur), None)
            if held is not None:                       # briefly lost (within lost_hold): hold its position
                chosen[i] = held["box"]
                continue
            cur = None
        if cur is None:
            cur, lead_since = best, {}
        elif best != cur and score[best] > score[cur] + o["switch_margin"]:
            t0 = lead_since.setdefault(best, i)
            if (i - t0) / fps >= o["switch_hold"]:
                cur, lead_since, switches = best, {}, switches + 1
        else:
            lead_since = {}
        chosen[i] = next(t["box"] for t in live if t["id"] == cur)
    return chosen, switches


# ----------------------------------------------------------------------------------- camera
def follow(targets, fps, size, o, start=None):
    """Virtual camera over one shot: dead zone + One Euro + accel/speed limits. targets in source px
    (1-D, crop top-left along one axis); size = crop extent along that axis (normaliser)."""
    from .filters import OneEuro
    f = OneEuro(o["min_cutoff"], o["beta"])
    dt = 1.0 / fps
    p = targets[0] if start is None else start
    v, moving, out = 0.0, False, []
    for k, t in enumerate(targets):
        tn = float(f(t / size, k * dt)) * size
        e = tn - p
        a = o["max_accel"] * size * dt
        if moving:
            if abs(e) <= o["settle"] * size and abs(v) <= a * 2:
                moving = False
        elif abs(e) > o["dead_zone"] * size:
            moving = True
        if moving:
            mag = min(abs(e) * o["gain"], o["max_speed"] * size,
                      math.sqrt(2 * o["max_accel"] * size * abs(e)))      # brake in time: eased stop
            want = math.copysign(mag, e)
        else:
            want = 0.0
        v += min(max(want - v, -a), a)
        p += v * dt
        out.append(p)
    return out


def _interp_targets(points, n):
    """{i: value} -> per-frame list (linear between samples, held at the ends)."""
    if not points:
        return None
    xs = sorted(points)
    return list(np.interp(np.arange(n), xs, [points[i] for i in xs]))


interp_targets = _interp_targets   # public name (longform-to-short ``_vertical``)


# ----------------------------------------------------------------------------------- subject mode
def _small_frames(src, start, dur, aw, ah, frames=None, region=None, hdr_vf=""):
    """Analysis-size BGR frames of the window: ffmpeg decodes + scales (LGPL ``crop`` / ``scale`` only), or the
    given in-memory frames are resized."""
    import cv2
    if frames is not None:
        for fr in frames:
            if region is not None:
                rx, ry, rw, rh = region
                fr = fr[ry:ry + rh, rx:rx + rw]
            yield cv2.resize(fr, (aw, ah), interpolation=cv2.INTER_AREA)
        return
    vf = [hdr_vf] if hdr_vf else []
    if region is not None:
        rx, ry, rw, rh = region
        vf.append(f"crop={rw}:{rh}:{rx}:{ry}")
    vf.append(f"scale={aw}:{ah}:flags=area")
    win = (["-ss", f"{start:.3f}"] if start else []) + (["-t", f"{dur:.3f}"] if dur else [])
    cmd = [media.ffmpeg_bin(), "-v", "error", *win, "-i", os.fspath(src), "-map", "0:v:0", "-vf", ",".join(vf),
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = aw * ah * 3
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(ah, aw, 3)
    finally:
        p.stdout.close()
        p.kill()
        p.wait()


def _scan_subject(src, start, dur, fps, sw, sh, o, det, an, frames=None, region=None, hdr_vf="", hint_frames=()):
    """One analysis pass: thumbnail differences (cuts) + per-sample interest columns / rows and faces (source px)."""
    import cv2
    aw = int(min(o["analysis_w"], sw)) // 2 * 2
    ah = max(2, int(round(sh * aw / sw)) // 2 * 2)
    k = sw / aw
    every = max(1, int(round(fps / o["sample_hz"])))
    hints = set(hint_frames)
    diffs, samples, prev, i, force = [], {}, None, 0, False
    n_max = int(round(dur * fps)) if dur else None
    for fr in _small_frames(src, start, dur, aw, ah, frames=frames, region=region, hdr_vf=hdr_vf):
        if n_max is not None and i >= n_max:
            break
        th = cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
        d = float(np.abs(th - prev).mean()) if prev is not None else 0.0
        diffs.append(d)
        prev = th
        if (d > 0 and i > 0 and _is_cut(diffs, i, o["cut_thresh"])) or i in hints:
            force = True
            an.reset()
        if i % every == 0 or force:
            m = an(fr)
            mp = m["map"]
            faces = []
            if det is not None:
                res = det(fr, int(round(i / fps * 1000))) if _takes_ts(det) else det(fr)
                for b in res or []:
                    x0, y0, x1, y1 = (float(v) * k for v in b[:4])
                    if x1 - x0 >= o["face_min"] * sw:
                        faces.append((x0, y0, x1, y1, b[4] if len(b) > 4 else None))
            samples[i] = dict(col=mp.sum(0).astype(np.float64), row=mp.sum(1).astype(np.float64), faces=faces,
                              motion=m["motion"], gm=m["gm"])
            force = False
        i += 1
    return i, diffs, samples


def _window_path(cols, k, move_cost, center_bias):
    """Best window start per sample: maximise the window's share of each sample's interest, minus a move cost
    between samples and a slight centre pull (Viterbi over every start; deterministic, globally smooth)."""
    C = np.asarray(cols, np.float64)
    m, G = C.shape
    C = C / np.maximum(C.sum(1, keepdims=True), 1e-9)
    cs = np.concatenate([np.zeros((m, 1)), np.cumsum(C, 1)], 1)
    P = G - k + 1
    share = cs[:, k:k + P] - cs[:, :P]
    # what is in the window counts most near its middle (a box window is happy with the subject on its edge)
    ker = np.sin(np.pi * (np.arange(k) + 0.5) / k) ** 2
    ker /= ker.sum() / k
    weighted = np.stack([np.convolve(c, ker[::-1], mode="valid") for c in C])
    pos = np.arange(P)
    score = 0.5 * (share + weighted) - center_bias * np.abs(pos + k / 2 - G / 2) / (G / 2)
    trans = move_cost * np.abs(pos[:, None] - pos[None, :]) / G           # [from, to]
    cost = -score[0]
    back = np.zeros((m, P), np.int64)
    for s in range(1, m):
        tot = cost[:, None] + trans
        back[s] = np.argmin(tot, 0)
        cost = tot[back[s], pos] - score[s]
    path = np.zeros(m, np.int64)
    path[-1] = int(np.argmin(cost))
    for s in range(m - 1, 0, -1):
        path[s - 1] = back[s][path[s]]
    return path, share[np.arange(m), path]


def _split(cols, path, k, o):
    """Share of samples whose subject mass outside the chosen window rivals the inside (two subjects too far
    apart for one crop)."""
    import cv2
    C = np.asarray(cols, np.float64)
    med = float(np.median(C.mean(0))) or 1e-9
    n = 0
    for c, p in zip(C, path):
        c = cv2.GaussianBlur(c.reshape(1, -1), (0, 0), 1.5).ravel()
        hot = c > o["peak"] * med
        if not hot.any():
            continue
        inside = np.zeros_like(hot)
        inside[p:p + k] = True
        out = hot & ~inside
        if out.sum() < max(2, 0.03 * len(c)) or not (hot & inside).any():
            continue
        if c[out].max() >= o["split"] * c[hot & inside].max():
            n += 1
    return n / max(1, len(C))


def _place(center, extent, size, safe_c, s):
    """Crop origin that puts a source coordinate ``center`` at the target coordinate ``safe_c``, clamped."""
    return min(max(center - safe_c / s, 0.0), max(0.0, size - extent))


def _plan_subject(src, tw, th, safe, caption, start, dur, sw, sh, fps, o, det, an, frames, region, hdr_vf,
                  transitions):
    cw, ch = crop_size(sw, sh, tw, th, o["zoom"])
    s = tw / cw
    G = an.grid_w
    k = max(1, min(G, int(round(G * cw / sw))))
    hint_win = []
    for t0, t1 in transitions or []:
        f0, f1 = int(round((t0 - (start or 0)) * fps)), int(round((t1 - (start or 0)) * fps))
        if f1 > 0:
            hint_win.append((max(0, f0), max(f0 + 1, f1)))
    hint_frames = [(a + b) // 2 for a, b in hint_win]
    n, diffs, samples = _scan_subject(src, start, dur, fps, sw, sh, o, det, an, frames=frames, region=region,
                                      hdr_vf=hdr_vf, hint_frames=hint_frames)
    if n == 0:
        raise RuntimeError(f"no frames decoded from {src}")
    hard = shot_cuts(diffs, o["cut_thresh"])
    bounds = sorted(set([0, n] + [c for c in hard if 0 < c < n] + [h for h in hint_frames if 0 < h < n]))
    safe_cx = (safe[0] + safe[2]) / 2
    cap_top = caption[1] if caption else safe[3]
    safe_cy = (safe[1] + min(safe[3], cap_top)) / 2
    cam = dict(o)
    xs, ys, shots = [], [], []
    for a, b in zip(bounds, bounds[1:]):
        ids = [i for i in sorted(samples) if a <= i < b]
        m = b - a
        kind, why = "follow", ""
        tx, ty = {}, {}
        face_ids = [i for i in ids if samples[i]["faces"]]
        if ids and len(face_ids) / len(ids) >= o["face_hit"]:
            chosen, _sw = _choose_subjects({i: samples[i]["faces"] for i in ids}, n, fps, [], sw, sh, o)
            for i, box in chosen.items():
                if box is not None:
                    tx[i - a], ty[i - a] = _desired(box, cw, ch, sw, sh, tw, safe, o["headroom"])
            kind, why = "face", f"faces in {len(face_ids)}/{len(ids)} samples"
        elif ids:
            cols = [samples[i]["col"] for i in ids]
            path, share = _window_path(cols, k, o["move_cost"], o["center_bias"])
            split = _split(cols, path, k, o)
            flat = float(np.mean(share)) < 1.5 * k / G
            if not o.get("shot_pad", True):
                split, flat = 0.0, False                     # premium: crop the strongest interest, no blurred fill
            if split >= o["split_share"]:
                kind, why = "pad-blur", f"two subjects too far apart for one crop in {split:.0%} of the shot"
            elif sw / cw > o["panorama"] and flat:
                kind, why = "pad-blur", f"a panorama ({sw / sh:.1f}:1) with nothing standing out"
            else:
                why = f"interest share {float(np.mean(share)):.2f} (whole-frame average {k / G:.2f})"
                for i, p in zip(ids, path):
                    tx[i - a] = _place((p + k / 2) / G * sw, cw, sw, safe_cx, s)
                if ch < sh - 1:
                    for i in ids:
                        r = samples[i]["row"]
                        cy = float((np.arange(len(r)) + 0.5) @ r / max(r.sum(), 1e-9)) / len(r) * sh
                        ty[i - a] = _place(cy, ch, sh, safe_cy, s)
        if kind == "pad-blur":
            xs += [None] * m
            ys += [None] * m
            shots.append(dict(start=a, end=b, kind=kind, reason=why))
            continue
        x_t = _interp_targets(tx, m) or [(sw - cw) / 2] * m
        y_t = _interp_targets(ty, m) or [(sh - ch) / 2] * m
        rng = max(x_t) - min(x_t)
        if m / fps < o["min_shot"] or (rng < o["hold"] * cw and max(y_t) - min(y_t) < o["hold"] * ch):
            x_t, y_t = [float(np.median(x_t))] * m, [float(np.median(y_t))] * m
            kind, why = "hold", (why + "; " if why else "") + ("short shot" if m / fps < o["min_shot"] else
                                                              f"the subject stays put ({rng / cw:.0%} of the crop)")
        else:                                         # offline: the camera anticipates (its own lag is ~lead)
            lead = int(round(o["lead"] * fps))
            x_t = x_t[lead:] + [x_t[-1]] * min(lead, m)
            y_t = y_t[lead:] + [y_t[-1]] * min(lead, m)
        xs += follow(x_t, fps, cw, cam)
        ys += follow(y_t, fps, ch, cam)
        shots.append(dict(start=a, end=b, kind=kind, reason=why))
    for f0, f1 in hint_win:                               # a crossfade: ease from one framing to the next inside it
        f0, f1 = min(f0, n - 1), min(f1, n - 1)
        if f1 <= f0 or xs[f0] is None or xs[f1] is None:
            continue
        for arr in (xs, ys):
            pa, pb = arr[f0], arr[f1]
            for f in range(f0, f1 + 1):
                u = (f - f0) / (f1 - f0)
                arr[f] = pa + (pb - pa) * u * u * (3 - 2 * u)
    rects = [None if x is None else [round(min(max(x, 0.0), sw - cw), 2), round(min(max(y, 0.0), sh - ch), 2),
                                     round(cw, 2), round(ch, 2)] for x, y in zip(xs, ys)]
    return dict(n_frames=n, cuts=hard, transitions=[list(w) for w in hint_win], shots=shots, rects=rects,
                crop_w=cw, crop_h=ch, samples=len(samples), scale=round(s, 4),
                hit_rate=round(sum(1 for v in samples.values() if v["faces"]) / max(1, len(samples)), 4))


# ----------------------------------------------------------------------------------- plan
def plan(src, target_w, target_h, mode="face", safe=None, start=0.0, dur=None, detector=None, frames=None,
         fps=None, region=None, caption=None, transitions=None, analyzer=None, **opts):
    """Per-frame crop rects for ``src`` -> target_w x target_h. safe: (x0, y0, x1, y1) in TARGET px
    (default: whole canvas inset 6 %). Returns a JSON-able dict (see module doc); ``mode_used`` says
    what actually ran (face may fall back); ``scale`` = target px per source px (> 1 = upscaled).

    frames: already-decoded BGR frames of the [start, start+dur) window (a list, array or iterator) so
    a caller that also renders from memory decodes once; src may then be None (pass ``fps``; size
    comes from the first frame). region: (x, y, w, h) in source px -> plan inside that sub-rectangle
    (e.g. a camera tile); rects are in region coordinates and ``render``/``frame_fn`` crop it first.
    Subject mode (or face with ``fallback="subject"``): caption = the target's caption box (x0, y0, x1, y1; the
    subject is kept above it), transitions = [[t0, t1], ...] source seconds of crossfades (known shot changes a
    frame difference cannot see), analyzer = a vstudio.saliency.Analyzer stand-in (tests)."""
    base = dict(DEFAULTS, **SUBJECT) if mode == "subject" else DEFAULTS
    o = dict(base, **{k: v for k, v in opts.items() if v is not None})
    if mode not in MODES:
        raise ValueError(f"mode={mode!r} (one of {MODES})")
    tw, th = int(target_w), int(target_h)
    safe = tuple(safe) if safe else (tw * 0.06, th * 0.06, tw * 0.94, th * 0.94)
    if frames is not None and not hasattr(frames, "__len__"):
        frames = iter(frames)
    if src is not None:
        info = media.probe(src)
        fps = fps or info["fps"] or 30.0
        sw, sh = info["display_w"], info["display_h"]
        total = info["duration"] - (start or 0)
    else:
        if frames is None:
            raise ValueError("plan needs src or frames")
        if hasattr(frames, "__len__"):
            first = frames[0]
        else:
            first = next(frames)
            import itertools
            frames = itertools.chain([first], frames)
        fps = float(fps or 30.0)
        sh, sw = first.shape[:2]
        total = len(frames) / fps if hasattr(frames, "__len__") else (dur or 0.0)
    full_w, full_h = sw, sh
    if region is not None:
        region = [int(round(v)) for v in region]
        rx, ry = max(0, region[0]), max(0, region[1])
        region = [rx, ry, min(region[2], sw - rx), min(region[3], sh - ry)]
        sw, sh = region[2], region[3]
    dur = min(dur, total) if dur else total
    n_est = int(round(dur * fps))
    out = dict(src=os.fspath(src) if src is not None else None, src_w=sw, src_h=sh, fps=fps,
               start=float(start or 0), dur=dur, target=[tw, th], safe=[round(v, 1) for v in safe], mode=mode,
               mode_used=mode, hit_rate=None, cuts=[], switches=0)
    if region is not None:
        out.update(region=region, full_w=full_w, full_h=full_h)
    cw, ch = crop_size(sw, sh, tw, th, o["zoom"])
    fit_scale = min(tw / sw, th / sh)
    if mode in ("pad-blur", "letterbox"):
        out.update(crop_w=sw, crop_h=sh, n_frames=n_est, rects=None, scale=round(fit_scale, 4))
        return out
    cx0, cy0 = (sw - cw) / 2, (sh - ch) / 2
    out["scale"] = round(tw / cw, 4)
    if mode == "center":
        out.update(crop_w=cw, crop_h=ch, n_frames=n_est, rects=None, fixed=[cx0, cy0, cw, ch])
        return out
    if mode == "subject":
        return _subject_out(out, src, tw, th, safe, caption, start, dur, sw, sh, fps, o, detector, analyzer,
                            frames, region, transitions, fit_scale)

    o["every"] = int(o["every"] or max(1, round(fps / 6)))
    own = detector is None
    try:
        det = _face_detector(o["max_faces"], o["analysis_w"]) if own else detector
    except Exception as e:                            # no mediapipe / model: same as "no face found"
        det = lambda fr: []
        det.close = lambda: None
        out["detector_error"] = f"{type(e).__name__}: {e}"
    try:
        fps, n, sw2, sh2, diffs, samples = _scan(src, start, dur, o["every"], det, o["cut_thresh"],
                                                 frames=frames, fps=fps, region=region)
    finally:
        if own:
            det.close()
    if n == 0:
        raise RuntimeError(f"no frames decoded from {src}")
    cuts = shot_cuts(diffs, o["cut_thresh"])
    hits = sum(1 for v in samples.values() if v)
    hit_rate = hits / max(1, len(samples))
    out.update(n_frames=n, cuts=cuts, hit_rate=round(hit_rate, 4), samples=len(samples))
    if hit_rate < o["min_hit"] and o["fallback"] == "subject" and (src is not None or hasattr(frames, "__len__")):
        so = dict(DEFAULTS, **SUBJECT, **{k: v for k, v in opts.items() if v is not None})
        sub = _subject_out(dict(out, mode_used="subject"), src, tw, th, safe, caption, start, dur, sw, sh, fps, so,
                           detector, analyzer, frames, region, transitions, fit_scale)
        sub["fallback_reason"] = f"face hit rate {hit_rate:.2f} < {o['min_hit']}"
        return sub
    if hit_rate < o["min_hit"]:
        fb = o["fallback"]
        out["mode_used"] = fb
        out["fallback_reason"] = f"face hit rate {hit_rate:.2f} < {o['min_hit']}"
        if fb == "center":
            out.update(crop_w=cw, crop_h=ch, rects=None, fixed=[cx0, cy0, cw, ch])
        else:
            out.update(crop_w=sw, crop_h=sh, rects=None, scale=round(fit_scale, 4))
        return out

    chosen, switches = _choose_subjects(samples, n, fps, cuts, sw, sh, o)
    bounds = [0] + cuts + [n]
    xs, ys = [], []
    for a, b in zip(bounds, bounds[1:]):
        px, py = {}, {}
        for i, box in chosen.items():
            if a <= i < b and box is not None:
                x, y = _desired(box, cw, ch, sw, sh, tw, safe, o["headroom"])
                px[i - a], py[i - a] = x, y
        m = b - a
        tx = _interp_targets(px, m) or [cx0] * m
        ty = _interp_targets(py, m) or [cy0] * m
        xs += follow(tx, fps, cw, o)
        ys += follow(ty, fps, ch, o)
    rects = [[round(min(max(x, 0.0), sw - cw), 2), round(min(max(y, 0.0), sh - ch), 2), round(cw, 2), round(ch, 2)]
             for x, y in zip(xs, ys)]
    out.update(crop_w=cw, crop_h=ch, rects=rects, switches=switches, stats=path_stats(rects, fps, cuts))
    return out


def _subject_out(out, src, tw, th, safe, caption, start, dur, sw, sh, fps, o, detector, analyzer, frames, region,
                 transitions, fit_scale):
    from . import saliency
    o = dict(o)
    o["every"] = max(1, int(round(fps / o["sample_hz"])))
    hdr_vf = ""
    if src is not None and frames is None:
        info = media.probe(src)
        if info.get("hdr"):
            hdr_vf = media.hdr_to_sdr_args(src, info.get("transfer"))
    own_det = detector is None
    det = None
    if own_det:
        try:
            det = _face_detector(o["max_faces"], o["analysis_w"])
        except Exception as e:  # noqa: BLE001  (no mediapipe / model: interest maps only)
            out["detector_error"] = f"{type(e).__name__}: {e}"
    else:
        det = detector
    an = analyzer if analyzer is not None else saliency.Analyzer()
    try:
        r = _plan_subject(src, tw, th, safe, caption, start, dur, sw, sh, fps, o, det, an, frames, region, hdr_vf,
                          transitions)
    finally:
        if own_det and det is not None:
            det.close()
        if analyzer is None:
            an.close()
    out.update(r)
    crop = [x for x in r["shots"] if x["kind"] != "pad-blur"]
    if not crop:
        out.update(mode_used="pad-blur", rects=None, crop_w=sw, crop_h=sh, scale=round(fit_scale, 4),
                   fallback_reason="; ".join(dict.fromkeys(x["reason"] for x in r["shots"])) or "nothing to follow")
        return out
    out["mode_used"] = "subject"
    out["stats"] = path_stats(r["rects"], fps, r["cuts"] + [b for a, b in r["transitions"]])
    return out


def rect_at(pl, i):
    """The crop rect [x, y, w, h] of frame ``i`` (None: shown whole on the blurred fill / letterboxed)."""
    if pl["mode_used"] in ("pad-blur", "letterbox"):
        return None
    rects = pl.get("rects")
    if rects is None:
        return pl.get("fixed")
    return rects[min(i, len(rects) - 1)] if rects else None


def plan_region(src, region, target_w, target_h, mode="face", **kw):
    """``plan`` constrained to ``region`` = (x, y, w, h) of the source (a camera tile in a screen
    recording): faces are searched and the crop moves only inside it; no temp clip is encoded."""
    return plan(src, target_w, target_h, mode=mode, region=region, **kw)


def path_stats(rects, fps, cuts=()):
    """Smoothness numbers for a crop path: max / p95 pan speed (crop widths per s) and mean |accel|,
    excluding the frames at shot cuts."""
    if not rects or len([r for r in rects if r is not None]) < 3:
        return dict(max_speed=0.0, p95_speed=0.0, mean_abs_accel=0.0)
    gap = np.array([r is None for r in rects])
    ref = next(r for r in rects if r is not None)
    a = np.array([ref if r is None else r for r in rects], dtype=float)
    cw = a[0, 2]
    pos = a[:, :2] / cw
    v = np.linalg.norm(np.diff(pos, axis=0), axis=1) * fps
    keep = ~(gap[1:] | gap[:-1])
    for c in cuts:
        if 0 < c <= len(v):
            keep[c - 1] = False
    acc = np.abs(np.diff(v)) * fps
    keep_a = keep[1:] & keep[:-1]
    return dict(max_speed=round(float(v[keep].max() if keep.any() else 0), 4),
                p95_speed=round(float(np.percentile(v[keep], 95)) if keep.any() else 0, 4),
                mean_abs_accel=round(float(acc[keep_a].mean()) if keep_a.any() else 0, 4))


# ----------------------------------------------------------------------------------- render
def frame_fn(pl, blur_dim=None):
    """Callable(i, bgr) -> target-size bgr frame for a plan."""
    import cv2
    tw, th = pl["target"]
    sw, sh = pl["src_w"], pl["src_h"]
    mode = pl["mode_used"]
    region = pl.get("region")
    if mode in ("pad-blur", "letterbox"):
        fw, fh, ox, oy = _fit(sw, sh, tw, th)
        dim = DEFAULTS["blur_dim"] if blur_dim is None else blur_dim
        bw, bh = max(8, tw // 12), max(8, th // 12)
        canvas = np.zeros((th, tw, 3), np.uint8)

        def fn(i, fr):
            if region is not None:
                fr = fr[region[1]:region[1] + region[3], region[0]:region[0] + region[2]]
            interp = cv2.INTER_AREA if fw < sw else cv2.INTER_CUBIC
            fg = cv2.resize(fr, (fw, fh), interpolation=interp)
            if mode == "letterbox":
                img = canvas.copy()
            else:
                s = max(bw / sw, bh / sh)
                small = cv2.resize(fr, (max(1, int(sw * s)), max(1, int(sh * s))), interpolation=cv2.INTER_AREA)
                yy, xx = (small.shape[0] - bh) // 2, (small.shape[1] - bw) // 2
                small = cv2.GaussianBlur(small[yy:yy + bh, xx:xx + bw], (0, 0), 2.2)
                img = cv2.resize(small, (tw, th), interpolation=cv2.INTER_LINEAR)
                img = (img.astype(np.float32) * dim).astype(np.uint8)
            img[oy:oy + fh, ox:ox + fw] = fg
            return img
        return fn
    rects = pl.get("rects")
    fixed = pl.get("fixed")
    pad = frame_fn(dict(pl, mode_used="pad-blur"), blur_dim) if rects and any(r is None for r in rects) else None

    def fn(i, fr):
        r = fixed if rects is None else rects[min(i, len(rects) - 1)]
        if r is None:
            return pad(i, fr)
        x, y, cw, ch = r
        if region is not None:
            x, y = x + region[0], y + region[1]
        s = tw / cw
        if abs(s - 1.0) < 1e-6 and float(x).is_integer() and float(y).is_integer():
            return np.ascontiguousarray(fr[int(y):int(y) + th, int(x):int(x) + tw])
        M = np.float32([[s, 0, -x * s], [0, s, -y * s]])
        return cv2.warpAffine(fr, M, (tw, th), flags=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA,
                              borderMode=cv2.BORDER_REPLICATE)
    return fn


def render(src, dst, pl, overlay=None, encode_args=None, audio=True, fps=None, frames=None, hdr="auto"):
    """Decode ``src`` (from plan start/dur) as raw BGR, apply the plan (+ ``overlay(i, t, img)`` that
    may draw on the target frame in place), encode to ``dst``. encode_args default
    ``media.delivery_args()`` (H.264 + AAC). audio: map the source audio (same window) if present.
    frames: already-decoded BGR frames (sequence / iterator) used instead of decoding ``src`` (src then
    only supplies the audio; may be None). hdr: "auto" tone-maps an HLG/PQ source to SDR bt709 in the
    decoder (``media.hdr_to_sdr_args``; for avconvert quality pre-convert with ``media.to_sdr``),
    False/"keep" leaves it. Returns dst."""
    info = media.probe(src) if src is not None else dict(fps_q=None, has_audio=False, hdr=False, transfer="")
    sw, sh = pl.get("full_w") or pl["src_w"], pl.get("full_h") or pl["src_h"]
    tw, th = pl["target"]
    start, dur = pl.get("start") or 0.0, pl.get("dur")
    rate = str(info["fps_q"]) if info["fps_q"] else f"{pl['fps']:.6g}"
    ff = media.ffmpeg_bin()
    win = (["-ss", f"{start:.3f}"] if start else []) + (["-t", f"{dur:.3f}"] if dur else [])
    vf = media.hdr_to_sdr_args(src, info.get("transfer")) if (hdr == "auto" and info.get("hdr")) else ""
    pl, (sw, sh), pre = prescaled(pl, sw, sh, decode=frames is None)
    if pre:                       # ffmpeg scales the source to the crop's scale: no 4K frame crosses the pipe
        vf = ",".join(x for x in (vf, pre) if x)
    dec = [ff, "-v", "error", *win, "-i", os.fspath(src or ""), "-map", "0:v:0", *(["-vf", vf] if vf else []),
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    has_a = audio and info["has_audio"]
    enc = [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{tw}x{th}", "-r", rate, "-i", "-"]
    if has_a:
        enc += [*win, "-i", os.fspath(src), "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
    else:
        enc += ["-map", "0:v:0"]
    args = list(encode_args) if encode_args is not None else media.delivery_args(audio=bool(has_a))
    if not has_a:
        args = _strip_audio(args)
    if fps:
        args += ["-r", str(fps)]
    enc += args + [os.fspath(dst)]
    fn = frame_fn(pl)
    fsize = sw * sh * 3
    p_dec = None if frames is not None else subprocess.Popen(dec, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    it = iter(frames) if frames is not None else None
    p_enc = subprocess.Popen(enc, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    i = 0
    try:
        while True:
            if it is not None:
                fr = next(it, None)
                if fr is None:
                    break
            else:
                buf = p_dec.stdout.read(fsize)
                if len(buf) < fsize:
                    break
                fr = np.frombuffer(buf, np.uint8).reshape(sh, sw, 3)
            img = fn(i, fr)
            if overlay is not None:
                img = np.ascontiguousarray(img)
                r = overlay(i, i / pl["fps"], img)
                img = img if r is None else r
            p_enc.stdin.write(np.ascontiguousarray(img).tobytes())
            i += 1
    except BrokenPipeError:
        pass
    finally:
        try:
            p_enc.stdin.close()
        except BrokenPipeError:
            pass
        if p_dec is not None:
            p_dec.stdout.close()
            p_dec.wait()
        err = p_enc.stderr.read().decode("utf-8", "replace")
        rc = p_enc.wait()
    if rc != 0 or i == 0:
        raise media.FFmpegError(f"reframe render failed (frames={i}, rc={rc}):\n{err[-1500:]}")
    return dst


def prescaled(pl, sw, sh, decode=True):
    """A subject plan that downscales (4K -> 1080 wide): the plan rescaled to a source pre-scaled by ffmpeg to the
    crop's own scale, + that ``scale`` filter -> (plan, (w, h), vf). Other plans (or in-memory frames) as they are."""
    rects = pl.get("rects")
    s = pl.get("scale") or 1.0
    if not decode or pl.get("mode_used") != "subject" or not rects or pl.get("region") or s > 0.98:
        return pl, (sw, sh), ""
    tw, th = pl["target"]
    W = max(tw, int(round(sw * s / 2)) * 2)
    H = max(th, int(round(sh * s / 2)) * 2)
    kx, ky = W / sw, H / sh
    r2 = [None if r is None else [r[0] * kx, r[1] * ky, r[2] * kx, r[3] * ky] for r in rects]
    return dict(pl, rects=r2, src_w=W, src_h=H, scale=1.0), (W, H), f"scale={W}:{H}:flags=lanczos"


def _strip_audio(args):
    out, skip = [], 0
    for k, a in enumerate(args):
        if skip:
            skip -= 1
            continue
        if a in ("-c:a", "-b:a", "-ar", "-ac"):
            skip = 1
            continue
        out.append(a)
    return out


def reframe(src, dst, target_w, target_h, mode="face", safe=None, start=0.0, dur=None, plan_json=True,
            overlay=None, encode_args=None, detector=None, **opts):
    """plan() + render(). Writes ``<dst stem>.crop.json`` (plan_json=True) or to the given path.
    Returns the plan dict."""
    pl = plan(src, target_w, target_h, mode=mode, safe=safe, start=start, dur=dur, detector=detector, **opts)
    render(src, dst, pl, overlay=overlay, encode_args=encode_args)
    if plan_json:
        path = plan_json if isinstance(plan_json, (str, os.PathLike)) else os.path.splitext(os.fspath(dst))[0] + ".crop.json"
        with open(path, "w") as f:
            json.dump(pl, f)
        pl["plan_json"] = os.fspath(path)
    return pl


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m vstudio.reframe", description=__doc__.split("\n\n")[0])
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--size", help="WxH (default from --platform)")
    ap.add_argument("--platform", help="e.g. douyin or xiaohongshu:vertical (size + safe box)")
    ap.add_argument("--mode", default="face", choices=MODES)
    ap.add_argument("--fallback", default=None, choices=MODES[1:])
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=None)
    ap.add_argument("--zoom", type=float, default=None)
    ap.add_argument("--every", type=int, default=None, help="detect every N frames")
    a = ap.parse_args(argv)
    safe = None
    if a.platform:
        from . import platform as P
        prof = P.profile(a.platform)
        tw, th = prof.w, prof.h
        safe = P.safe_box(prof)
    if a.size:
        tw, th = (int(v) for v in a.size.lower().split("x"))
    elif not a.platform:
        ap.error("--size or --platform is required")
    pl = reframe(a.src, a.dst, tw, th, mode=a.mode, safe=safe, start=a.start, dur=a.dur,
                 fallback=a.fallback, zoom=a.zoom, every=a.every)
    print(json.dumps({k: pl.get(k) for k in ("mode_used", "hit_rate", "cuts", "switches", "stats", "plan_json")}))


if __name__ == "__main__":
    sys.exit(main())
