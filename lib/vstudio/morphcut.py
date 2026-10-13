"""Morph cuts: bridge a talking-head jump cut with a few RIFE frames when the face barely moved across it.

    from vstudio import morphcut
    rep = morphcut.smooth("body.mp4", "body.smooth.mp4", joints=[12.4, 30.1, 41.0])
    rep["joints"]   # [{t, frame, action: morph|cut, frames, delta, bg, why}, ...]

Per joint (the first frame after a cut, in output seconds) the last frame before and the first frame after it are
measured (``measure``): MediaPipe's face mesh on both gives the face's shift and scale change and the residual of
the rigid landmarks after a similarity fit (head turn / nod), all relative to the eye distance; the background
outside the face and body is compared on a small grey thumbnail. ``decide``:

  - no face in one of the frames, or a different background (a camera / angle / scene change): ``cut`` - a morph
    across a shot change is never made;
  - face delta <= ``small`` (the speaker barely moved): ``morph`` with 3-6 frames at 30 fps (more for a larger
    delta, scaled with the frame rate), centred on the cut: ``frames // 2`` before it and the rest after it are
    replaced by RIFE in-betweens of the two untouched frames around them - length-neutral, so the time map, the
    captions and the audio stay exactly as they were;
  - larger: ``cut`` (the recipe's clean cut / punch-in stays).

Every bridge is checked before it is kept: each in-between must stay close to the plain blend of its two anchors
(no warped-face artefact) and its brightness must stay between theirs (no flicker); a failing bridge falls back
to the cut. Without RIFE (``rife.available()`` False: Intel / Windows, or the model not downloaded) nothing is
morphed and ``smooth`` returns the input unchanged with every joint ``cut`` / why ``no-rife``.
"""
import json
import os
import shutil
import subprocess
import tempfile

import numpy as np

from . import rife

SMALL = 0.06          # face delta (eye distances) up to which a joint is morphed
BG_SHOT = 14.0        # mean background difference (0-255 grey levels) above which the two frames are other shots
MIN_FRAMES, MAX_FRAMES = 3, 6      # at 30 fps
QC_BLEND = 14.0       # an in-between may differ from the anchors' blend by this much (mean, grey levels, 1/4 res)
QC_LUMA = 3.0         # ... and its mean brightness may leave the anchors' range by this much
RIGID = [33, 133, 362, 263, 1, 4, 6, 168, 10, 151, 9, 8, 70, 300, 234, 454, 127, 356]
THUMB = (96, 54)


# ------------------------------------------------------------------ colour (yuv420p <-> rgb, the source's matrix)
def _k(matrix):
    return (0.2126, 0.0722) if matrix == "bt709" else (0.299, 0.114)


def yuv_to_rgb(buf, w, h, matrix="bt709"):
    """One raw yuv420p (limited range) frame -> HxWx3 uint8 RGB."""
    kr, kb = _k(matrix)
    kg = 1 - kr - kb
    y = (np.frombuffer(buf, np.uint8, w * h).reshape(h, w).astype(np.float32) - 16) / 219
    c = np.frombuffer(buf, np.uint8, w * h // 2, w * h).astype(np.float32)
    u = (c[:w * h // 4].reshape(h // 2, w // 2) - 128) / 224
    v = (c[w * h // 4:].reshape(h // 2, w // 2) - 128) / 224
    u = u.repeat(2, 0).repeat(2, 1)
    v = v.repeat(2, 0).repeat(2, 1)
    r = y + 2 * (1 - kr) * v
    b = y + 2 * (1 - kb) * u
    g = (y - kr * r - kb * b) / kg
    return np.clip(np.stack([r, g, b], -1) * 255 + 0.5, 0, 255).astype(np.uint8)


def rgb_to_yuv(rgb, matrix="bt709"):
    """HxWx3 uint8 RGB -> raw yuv420p bytes (limited range)."""
    kr, kb = _k(matrix)
    kg = 1 - kr - kb
    x = rgb.astype(np.float32) / 255
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    y = kr * r + kg * g + kb * b
    u = (b - y) / (2 * (1 - kb))
    v = (r - y) / (2 * (1 - kr))
    h, w = y.shape

    def sub(c):
        return c.reshape(h // 2, 2, w // 2, 2).mean((1, 3))
    Y = np.clip(y * 219 + 16 + 0.5, 0, 255).astype(np.uint8)
    U = np.clip(sub(u) * 224 + 128 + 0.5, 0, 255).astype(np.uint8)
    V = np.clip(sub(v) * 224 + 128 + 0.5, 0, 255).astype(np.uint8)
    return Y.tobytes() + U.tobytes() + V.tobytes()


def _matrix(info):
    cs = str(info.get("colorspace") or info.get("color_space") or "")
    if "709" in cs:
        return "bt709"
    if "601" in cs or "470" in cs or "170" in cs:
        return "bt601"
    return "bt709" if min(info["w"], info["h"]) >= 720 else "bt601"


# ------------------------------------------------------------------ measuring a joint
_LM = {}


def _landmarker():
    if "lm" not in _LM:
        try:
            from . import face
            _LM["lm"] = face.landmarker(num_faces=1)
        except Exception:  # noqa: BLE001  (no mediapipe / model: every joint stays a cut)
            _LM["lm"] = None
    return _LM["lm"]


def _face(rgb):
    lm = _landmarker()
    if lm is None:
        return None
    from . import face
    faces = face.detect(lm, np.ascontiguousarray(rgb[..., ::-1]))
    f = face.main_face(faces)
    return None if f is None else f["pts"]


def _similarity(src, dst):
    """Least-squares similarity (scale, rotation, shift) mapping src -> dst points; returns the mapped src."""
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    cov = b.T @ a / len(src)
    U, S, Vt = np.linalg.svd(cov)
    d = np.sign(np.linalg.det(U @ Vt))
    D = np.diag([1, d])
    R = U @ D @ Vt
    s = np.trace(np.diag(S) @ D) / max(1e-9, (a ** 2).sum() / len(src))
    return (s * (R @ a.T)).T + md


def _bg_diff(a, b, pa, pb):
    """Mean grey difference of two frames outside the face + body (the speaker), on a small blurred thumbnail."""
    import cv2
    h, w = a.shape[:2]
    ga = cv2.resize(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), THUMB, interpolation=cv2.INTER_AREA).astype(np.float32)
    gb = cv2.resize(cv2.cvtColor(b, cv2.COLOR_RGB2GRAY), THUMB, interpolation=cv2.INTER_AREA).astype(np.float32)
    ga, gb = cv2.GaussianBlur(ga, (3, 3), 0), cv2.GaussianBlur(gb, (3, 3), 0)
    mask = np.ones((THUMB[1], THUMB[0]), bool)
    sx, sy = THUMB[0] / w, THUMB[1] / h
    for p in (pa, pb):
        if p is None:
            continue
        x0, y0 = p.min(0)
        x1, y1 = p.max(0)
        fw = x1 - x0
        # the head with hair and the torso below it
        X0, X1 = int((x0 - 0.9 * fw) * sx), int(np.ceil((x1 + 0.9 * fw) * sx))
        Y0 = int((y0 - 0.8 * (y1 - y0)) * sy)
        mask[max(0, Y0):, max(0, X0):max(0, X1)] = False
    if mask.mean() < 0.15:                      # the speaker fills the frame: compare the whole picture
        mask[:] = True
    # exposure drift is not a shot change: compare after matching the means
    da = ga[mask] - ga[mask].mean()
    db = gb[mask] - gb[mask].mean()
    return float(np.abs(da - db).mean() + 0.5 * abs(ga[mask].mean() - gb[mask].mean()))


def measure(a, b):
    """Two RGB frames (the last before a cut, the first after) -> {face, shift, scale, pose, delta, bg}."""
    pa, pb = _face(a), _face(b)
    out = dict(face=pa is not None and pb is not None, bg=round(_bg_diff(a, b, pa, pb), 2))
    if not out["face"]:
        return out
    iod = float(np.linalg.norm(pa[33] - pa[263]) + np.linalg.norm(pb[33] - pb[263])) / 2 or 1.0
    ra, rb = pa[RIGID], pb[RIGID]
    shift = float(np.linalg.norm(ra.mean(0) - rb.mean(0))) / iod
    scale = abs(float(np.log((np.linalg.norm(pb[33] - pb[263]) + 1e-6) / (np.linalg.norm(pa[33] - pa[263]) + 1e-6))))
    pose = float(np.sqrt(((_similarity(ra, rb) - rb) ** 2).sum(1).mean())) / iod
    out.update(shift=round(shift, 4), scale=round(scale, 4), pose=round(pose, 4),
               delta=round(max(shift, 2.0 * scale, 2.0 * pose), 4))
    return out


def decide(m, fps=30.0, small=SMALL, bg_shot=BG_SHOT):
    """A measurement -> {action: morph|cut, frames, why}."""
    if m.get("bg", 0) > bg_shot:
        return dict(action="cut", frames=0, why="shot-change")
    if not m.get("face"):
        return dict(action="cut", frames=0, why="no-face")
    d = m["delta"]
    if d > small:
        return dict(action="cut", frames=0, why="moved")
    n = MIN_FRAMES + (MAX_FRAMES - MIN_FRAMES) * d / small
    n = int(round(n * float(fps) / 30.0))
    return dict(action="morph", frames=max(2, n), why="small")


# ------------------------------------------------------------------ video io
def _ff():
    from . import media
    return media._resolve(["ffmpeg"])[0]


def _grab(video, frames, width=640):
    """{frame index: RGB uint8 (width wide)} for the given frame indices, one decode pass."""
    from . import media
    info = media.probe(video)
    W, H = rife.frame_size(info)
    w = min(width, W) // 2 * 2
    h = int(round(H * w / W)) // 2 * 2
    idx = sorted(set(int(i) for i in frames if i >= 0))
    if not idx:
        return {}
    sel = "+".join(f"eq(n\\,{i})" for i in idx)
    cmd = [_ff(), "-v", "error", "-nostdin", "-i", video, "-an", "-vf", f"select='{sel}',scale={w}:{h}",
           "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    arr = np.frombuffer(raw[:n * w * h * 3], np.uint8).reshape(n, h, w, 3)
    return {i: arr[k] for k, i in enumerate(idx[:n])}


def plan(video, joints, fps=None, small=SMALL, bg_shot=BG_SHOT):
    """Decisions for the joints (output seconds of the first frame after each cut) of ``video``."""
    from . import media
    info = media.probe(video)
    F = float(fps or info["fps"] or 30)
    total = int(round(info["duration"] * F))
    J = sorted({int(round(float(t) * F)) for t in joints})
    J = [j for j in J if 1 <= j < total - 1]
    frames = _grab(video, [j - 1 for j in J] + J)
    out, last_end = [], -1
    for j in J:
        d = dict(t=round(j / F, 4), frame=j)
        a, b = frames.get(j - 1), frames.get(j)
        if a is None or b is None:
            d.update(action="cut", frames=0, why="no-frame")
            out.append(d)
            continue
        m = measure(a, b)
        d.update(m)
        d.update(decide(m, F, small, bg_shot))
        if d["action"] == "morph":
            n = d["frames"]
            lo, hi = j - n // 2 - 1, j + (n - n // 2)       # untouched anchors
            if lo <= last_end or lo < 0 or hi >= total:
                d.update(action="cut", frames=0, why="too-close")
            else:
                last_end = hi
        out.append(d)
    return out


def _qc(a, b, mids, times):
    """In-betweens of anchors a, b at ``times`` look like a morph (no artefact, no flicker)? -> (ok, why)."""
    sa, sb = a[::4, ::4].astype(np.float32).mean(-1), b[::4, ::4].astype(np.float32).mean(-1)
    la, lb = sa.mean(), sb.mean()
    for m, t in zip(mids, times):
        sm = m[::4, ::4].astype(np.float32).mean(-1)
        if np.abs(sm - ((1 - t) * sa + t * sb)).mean() > QC_BLEND:
            return False, "qc-artefact"
        lm = sm.mean()
        if lm < min(la, lb) - QC_LUMA or lm > max(la, lb) + QC_LUMA:
            return False, "qc-flicker"
    return True, ""


def bridge(video, out, decisions, crf=14, preset="fast", scale=None, log=None):
    """Re-encode ``video`` -> ``out`` with every ``morph`` decision's frames replaced by RIFE in-betweens (audio
    stream-copied). Decisions that fail the QC become cuts (updated in place). Returns the number morphed."""
    from . import media
    info = media.probe(video)
    W, H = rife.frame_size(info)
    F = info["fps_q"] or info["fps"] or 30
    mat = _matrix(info)
    fsz = W * H * 3 // 2
    jobs = {}
    for d in decisions:
        if d.get("action") != "morph":
            continue
        n, j = d["frames"], d["frame"]
        lo, hi = j - n // 2 - 1, j + (n - n // 2)
        jobs[lo] = (hi, d)
    rd = subprocess.Popen([_ff(), "-v", "error", "-nostdin", "-i", video, "-an", "-f", "rawvideo", "-pix_fmt",
                           "yuv420p", "-"], stdout=subprocess.PIPE)
    tags = []
    if "709" in mat:
        tags = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
    wcmd = [_ff(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{W}x{H}", "-r", str(F),
            "-i", "-"]
    if info.get("has_audio"):
        wcmd += ["-i", video, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "copy"]
    wcmd += ["-c:v", "libx264", "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p", *tags,
             "-movflags", "+faststart", out]
    wr = subprocess.Popen(wcmd, stdin=subprocess.PIPE)
    done, i, buf, pend = 0, 0, [], None
    try:
        while True:
            fr = rd.stdout.read(fsz)
            if len(fr) < fsz:
                break
            if pend is None and i in jobs:
                pend = (jobs[i][0], jobs[i][1])
                buf = []
            if pend is None:
                wr.stdin.write(fr)
            else:
                buf.append(fr)
                if i == pend[0]:
                    hi, d = pend
                    n = len(buf) - 2
                    a, b = yuv_to_rgb(buf[0], W, H, mat), yuv_to_rgb(buf[-1], W, H, mat)
                    times = [(k + 1) / (n + 1) for k in range(n)]
                    mids = rife.interpolate(a, b, times, scale)
                    ok, why = _qc(a, b, mids, times)
                    if ok:
                        buf[1:-1] = [rgb_to_yuv(m, mat) for m in mids]
                        done += 1
                    else:
                        d.update(action="cut", frames=0, why=why)
                        if log:
                            log(f"morphcut: {d['t']:.2f}s {why} -> cut")
                    for x in buf:
                        wr.stdin.write(x)
                    pend, buf = None, []
            i += 1
        for x in buf:
            wr.stdin.write(x)
    finally:
        wr.stdin.close()
        rd.stdout.close()
        rd.wait()
    if wr.wait():
        raise RuntimeError(f"morphcut: ffmpeg failed writing {out}")
    return done


def smooth(video, out, joints, fps=None, small=SMALL, bg_shot=BG_SHOT, crf=14, log=print, report=None):
    """Plan + bridge: ``video`` -> ``out`` with the small-delta joints morphed. When nothing is morphed (or RIFE is
    not available) ``out`` is a copy of ``video``. Returns {out, joints, morphed, available}; ``report``: also
    write it as JSON there."""
    avail = rife.available()
    if not joints:
        dec = []
    elif not avail:
        dec = [dict(t=round(float(t), 4), action="cut", frames=0, why="no-rife") for t in joints]
    else:
        dec = plan(video, joints, fps, small, bg_shot)
    n = 0
    if any(d["action"] == "morph" for d in dec):
        tmp = out + ".part" + os.path.splitext(out)[1]
        n = bridge(video, tmp, dec, crf=crf, log=log)
        os.replace(tmp, out)
    elif os.path.abspath(video) != os.path.abspath(out):
        shutil.copyfile(video, out)
    rep = dict(out=out, available=avail, morphed=n, joints=dec)
    if log and dec:
        why = {}
        for d in dec:
            if d["action"] != "morph":
                why[d["why"]] = why.get(d["why"], 0) + 1
        log(f"morphcut: {n}/{len(dec)} jump cuts morphed" + "".join(f", {v} {k}" for k, v in sorted(why.items())))
    if report:
        with open(report, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=1)
    return rep


def smooth_inplace(video, joints, **kw):
    """``smooth`` writing back over ``video`` (via a temp file). Returns the report."""
    d = tempfile.mkdtemp(prefix="vstudio_morph_", dir=os.path.dirname(os.path.abspath(video)))
    try:
        tmp = os.path.join(d, "m" + os.path.splitext(video)[1])
        rep = smooth(video, tmp, joints, **kw)
        if rep["morphed"]:
            os.replace(tmp, video)
        rep["out"] = video
        return rep
    finally:
        shutil.rmtree(d, ignore_errors=True)


def joints_of(timemap, tol=1e-3):
    """Output seconds of the first frame after every cut of a ``cut.TimeMap`` (or its ``to_list()`` items): where
    the next kept span does not start where the previous one ended in the source."""
    items = timemap.to_list() if hasattr(timemap, "to_list") else list(timemap)
    clips = [x for x in items if isinstance(x, dict) and "src0" in x]
    out = []
    for x, y in zip(clips, clips[1:]):
        if x.get("source", 0) != y.get("source", 0) or abs(float(y["src0"]) - float(x["src1"])) > tol:
            out.append(float(y["dst0"]))
    return out


def _cli(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m vstudio.morphcut", description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--joints", required=True, help="comma-separated output seconds of the cuts, or a cleanup sidecar")
    ap.add_argument("--small", type=float, default=SMALL)
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    if os.path.isfile(a.joints):
        with open(a.joints, encoding="utf-8") as f:
            J = joints_of(json.load(f)["timemap"])
    else:
        J = [float(x) for x in a.joints.split(",") if x.strip()]
    rep = smooth(a.video, a.out, J, small=a.small, report=a.report)
    print(json.dumps({k: rep[k] for k in ("out", "available", "morphed")}))


if __name__ == "__main__":
    _cli()


def find_cuts(video, min_diff=0.3, ratio=3.0, peak=1.8, win=6, band=0.75):
    """Output seconds of the hard cuts already baked into ``video`` (a finished talking-head body): frames whose
    grey 64x36 difference to the previous frame (the top ``band`` of the picture: burned captions below it change
    on their own) is a lone spike - ``ratio`` x the median and ``peak`` x the largest of the ``win`` frames on each
    side, and at least ``min_diff`` levels. Speech and gestures change gradually; a cut changes in one frame."""
    from . import media
    info = media.probe(video)
    F = float(info["fps"] or 30)
    w, h = 64, 36
    raw = subprocess.run([_ff(), "-v", "error", "-nostdin", "-i", video, "-an", "-vf", f"scale={w}:{h}:flags=area",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    n = len(raw) // (w * h)
    if n < 3:
        return []
    Y = np.frombuffer(raw[:n * w * h], np.uint8).reshape(n, h, w)[:, :max(1, int(h * band))].astype(np.float32)
    d = np.r_[0.0, np.abs(np.diff(Y, axis=0)).mean((1, 2))]
    out = []
    for i in range(1, n):
        nb = np.r_[d[max(1, i - win):i], d[i + 1:i + 1 + win]]
        if len(nb) and d[i] >= min_diff and d[i] >= ratio * max(0.05, float(np.median(nb))) \
                and d[i] >= peak * float(nb.max()):
            out.append(round(i / F, 4))
    return out
