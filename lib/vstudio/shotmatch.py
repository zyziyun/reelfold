"""Shot matching (镜头对齐): where each shot of a finished video came from in the source footage - by its frames, never
by file names - so a second-pass edit can pull another take of a shot from the footage, or rebuild a shot at another
aspect from the full source frame.

    from vstudio import shotmatch as SM
    m = SM.match("final/youtube.mp4", ["raw/DJI_0001.MP4", ...], on_event=print)
    m["shots"][3]["match"]  # {source, t, t_end, speed, score, box [x, y, w, h] (fractions of the source frame),
                            #  fbox [x, y, w, h] (where it sits in the finished frame), grade [[gain, offset] x 3]}
    SM.alternatives(m, 3)   # unused windows of the linked footage for shot 3: [{source, t, dur, why}]
    SM.piece_filter(...)    # the ffmpeg -vf that puts a source piece on a W x H canvas

Method. The finished video is sampled at 5 fps (grey, 96 px high) and cut into shots: hard cuts where consecutive
frames differ sharply (a local peak well above the neighbourhood's median), dissolves where a frame is a mix of the
frames 0.2-0.6 s either side of it (and those two differ), dips through black / white at the middle of the flat
frames. Graded, low-contrast finals and their crossfades count, a pan or a reframe that follows the subject does
not. Every source is indexed once - its key frames (drones and
phones write one every 0.5-1 s; decoded with VideoToolbox on a Mac: a 4K HEVC minute in ~1.5 s), else 2 fps - as grey
128x72 thumbnails, cached in ``$VSTUDIO_CACHE/shotmatch/`` by the file's content hash. Three frames of each shot are
compared with every indexed frame by normalised cross-correlation over the placements a finished frame can have in
a source frame: a crop of the full height or width (a vertical cut of landscape footage, a 16:9 cut of a 4:3 one),
the same at a 1.25x punch-in, or the whole frame letter-boxed in a band. The finished frame's caption / title rows are
left out, so burned text does not count. The best source + time is refined on the source's own frame rate around it,
the speed comes from the shot's first and last sampled frames, and a per-channel gain / offset maps the source's
colours onto the finished grade (so a swapped take looks like its neighbours). Nothing is written next to the inputs.

Tests replace nothing: they make small synthetic sources + a finished cut with ffmpeg (tests/test_shotmatch.py).
"""
import hashlib
import json
import os
import re
import subprocess
import sys

import numpy as np

VERSION = 1
FIN_FPS = 5.0              # finished-video sampling rate (shot cuts, matching frames)
FIN_H = 96                 # finished frames: grey, this many rows (width keeps the aspect)
SRC_W, SRC_H = 128, 72     # source index thumbnails (16:9; other aspects keep their ratio at SRC_H rows)
KEY_GAP_MAX = 1.6          # key frames further apart than this: the source is indexed at INDEX_FPS instead
INDEX_FPS = 2.0
MIN_SHOT_S = 0.6
MATCH_MIN = 0.55           # NCC needed to call a shot matched
TOP_K = 10                 # candidates kept from the coarse pass per sampled frame
ZOOMS = (1.0, 1.12, 1.25)
MASK_TOP, MASK_BOTTOM = 0.2, 0.28     # finished rows ignored (titles, captions)
HWACCEL = os.environ.get("VSTUDIO_SHOTMATCH_HWACCEL", "1") != "0"


# --------------------------------------------------------------------------- decoding
def _ffmpeg():
    from . import media
    return media.ffmpeg_bin()


def probe(path):
    from . import media
    info = media.probe(path)
    w, h = info.get("display_w") or info["w"], info.get("display_h") or info["h"]
    return dict(w=int(w), h=int(h), duration=float(info["duration"] or 0.0), fps=float(info["fps"] or 30.0),
                has_audio=bool(info["has_audio"]), vcodec=info.get("vcodec"))


def _decode(path, w, h, fps=None, keyframes=False, start=None, dur=None, frames=None, color=False):
    """-> (times [N] seconds on the file's timeline, frames uint8 [N, h, w] grey or [N, h, w, 3] RGB)."""
    for hw in ((True, False) if (HWACCEL and sys.platform == "darwin") else (False,)):
        cmd = [_ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "info"]
        if hw:
            cmd += ["-hwaccel", "videotoolbox"]
        if keyframes:
            cmd += ["-skip_frame", "nokey"]
        if start:
            cmd += ["-ss", f"{max(0.0, start):.3f}"]
        cmd += ["-i", path, "-an", "-sn", "-dn"]
        if dur:
            cmd += ["-t", f"{dur:.3f}"]
        if frames:
            cmd += ["-frames:v", str(int(frames))]
        # big frames: a fast pre-shrink, then an area average (a 4K key frame -> 128 px: ~4x faster than area alone)
        vf = ([f"fps={fps:g}"] if fps else []) + [f"scale='min(iw,{w * 4})':-2:flags=fast_bilinear",
                                                   f"scale={w}:{h}:flags=area", "showinfo"]
        cmd += ["-vf", ",".join(vf), "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt",
                "rgb24" if color else "gray", "-"]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            if hw:
                continue
            raise RuntimeError(f"ffmpeg could not read {os.path.basename(path)}: "
                               f"{r.stderr.decode('utf-8', 'replace')[-400:]}")
        ch = 3 if color else 1
        n = len(r.stdout) // (w * h * ch)
        if n == 0 and hw:
            continue
        arr = np.frombuffer(r.stdout[: n * w * h * ch], np.uint8)
        arr = arr.reshape((n, h, w, 3) if color else (n, h, w))
        ts = [float(x) for x in re.findall(rb"pts_time:\s*(-?[\d.]+)", r.stderr)]
        if len(ts) != n:
            step = 1.0 / fps if fps else 0.5
            ts = [i * step for i in range(n)]
        t = np.asarray(ts[:n], np.float64) + float(start or 0.0)
        return t, arr
    return np.zeros(0), np.zeros((0, h, w) if not color else (0, h, w, 3), np.uint8)


def _even(x):
    return max(2, int(round(x / 2.0)) * 2)


def _fin_size(w, h):
    return _even(FIN_H * w / max(1, h)), FIN_H


def _src_size(w, h):
    if abs(w / max(1, h) - 16 / 9) < 0.02:
        return SRC_W, SRC_H
    return _even(SRC_H * w / max(1, h)), SRC_H


def qhash(path, win=1 << 20):
    """Content hash that stays fast on multi-GB files (size + head / middle / tail windows)."""
    st = os.stat(path)
    h = hashlib.sha1(str(st.st_size).encode())
    with open(path, "rb") as f:
        if st.st_size <= 3 * win:
            h.update(f.read())
        else:
            for off in (0, st.st_size // 2 - win // 2, st.st_size - win):
                f.seek(off)
                h.update(f.read(win))
    return h.hexdigest()


def _cache_dir():
    from .config import cache_dir
    return cache_dir("shotmatch")


# --------------------------------------------------------------------------- the source index
def index(path, on_event=None):
    """A source's thumbnails (cached): {path, w, h, duration, fps, t [N], frames uint8 [N, rows, cols]}."""
    key = f"{qhash(path)}-v{VERSION}"
    cp = os.path.join(_cache_dir(), key + ".npz")
    if os.path.exists(cp):
        try:
            z = np.load(cp, allow_pickle=False)
            meta = json.loads(str(z["meta"]))
            return dict(meta, path=os.path.abspath(path), t=z["t"], frames=z["frames"], cached=True)
        except (OSError, ValueError, KeyError):
            pass
    info = probe(path)
    sw, sh = _src_size(info["w"], info["h"])
    t, fr = _decode(path, sw, sh, keyframes=True)
    gap = float(np.median(np.diff(t))) if len(t) > 2 else 99.0
    if len(t) < 3 or gap > KEY_GAP_MAX:
        t, fr = _decode(path, sw, sh, fps=INDEX_FPS)
    meta = dict(w=info["w"], h=info["h"], duration=info["duration"], fps=info["fps"], cols=sw, rows=sh)
    try:
        tmp = cp + ".part.npz"
        np.savez_compressed(tmp, t=t, frames=fr, meta=np.asarray(json.dumps(meta)))
        os.replace(tmp, cp)
    except OSError:
        pass
    return dict(meta, path=os.path.abspath(path), t=t, frames=fr, cached=False)


# --------------------------------------------------------------------------- shots of the finished video
def _hard_cuts(t, d):
    """Sample gaps that are a sharp, isolated peak of frame change -> cut times."""
    cuts = []
    for i in range(len(d)):
        lo, hi = max(0, i - 10), min(len(d), i + 11)
        med = float(np.median(d[lo:hi]))
        left = d[i - 1] if i > 0 else 0.0
        right = d[i + 1] if i + 1 < len(d) else 0.0
        # well above the neighbourhood and a clear peak over the frames either side (a pan is not); the floor is low
        # enough for a cut between two shots of one grade (golden-hour aerials differ by ~8 grey levels)
        if d[i] >= max(8.0, 2.0 * med) and d[i] >= max(left, right) and \
                d[i] - min(left, right) >= max(5.0, 1.2 * med):
            cuts.append(float((t[i] + t[i + 1]) / 2.0))
    return cuts


def _flat(f):
    """Near-uniform frames (black, white, a fade's darkest point)."""
    return f.std(axis=1) < 4.0


def _mix_cuts(t, f, d, flat):
    """Dissolves: a sample that is a mix (a * before + (1 - a) * after, a in .25-.75) of the samples 1-3 steps either
    side, which differ clearly from each other. A pan, a zoom or a reframe is a shifted picture, not a mix, so it does
    not fit. One cut per run of mixed samples, at the best fit."""
    n = len(f)
    hits = []
    for i in range(1, n - 1):
        lo, hi = max(0, i - 15), min(len(d), i + 16)
        base = float(np.percentile(d[lo:hi], 25))
        best = None
        for k in (1, 2, 3):
            if i - k < 0 or i + k >= n or flat[i - k] or flat[i + k]:
                continue
            a, b, m = f[i - k], f[i + k], f[i]
            ab = a - b
            span = float(np.abs(ab).mean())
            if span < max(8.0, 3.0 * base):
                continue
            # the change is concentrated in the transition (steady motion - a pan, a reframe that follows the subject -
            # changes about as much just before and after it); needs ~1.5 s of picture on each side
            before, after = d[max(0, i - k - 9):max(0, i - k - 1)], d[i + k + 1:i + k + 9]
            if len(before) < 4 or len(after) < 4:
                continue
            if float(d[i - k:i + k].mean()) < 1.15 * max(float(np.median(before)), float(np.median(after))):
                continue
            al = float(((m - b) * ab).sum() / max(1e-6, float((ab * ab).sum())))
            if not 0.25 <= al <= 0.75:
                continue
            res = float(np.abs(m - (al * a + (1.0 - al) * b)).mean())
            near = min(float(np.abs(m - a).mean()), float(np.abs(m - b).mean()))
            r = res / max(near, 1e-3)
            if r < 0.6 and (best is None or r < best):
                best = r
        if best is not None:
            hits.append((i, best))
    cuts, run = [], []
    for i, r in hits + [(n + 10, 0.0)]:
        if run and i - run[-1][0] > 2:
            j = min(run, key=lambda x: x[1])[0]
            cuts.append(float(t[j]))
            run = []
        run.append((i, r))
    return cuts


def _dip_cuts(t, f):
    """A dip to black / white (lifted by a grade or not): a sample whose contrast falls to a local minimum far below
    the pictures ~0.5-1.6 s either side of it -> that sample."""
    sd = f.std(axis=1)
    cuts = []
    for i in range(len(sd)):
        before, after = sd[max(0, i - 8):max(0, i - 2)], sd[i + 3:i + 9]
        if len(before) < 3 or len(after) < 3 or sd[i] > sd[max(0, i - 3):i + 4].min():
            continue
        if sd[i] < 0.35 * min(float(np.median(before)), float(np.median(after))):
            cuts.append(float(t[i]))
    return cuts


def _merge(cuts, gap):
    """[(time, rank)] -> times; cuts of different detectors closer than ``gap`` are one transition, placed by the
    best-ranked one (a dip's darkest frame, then a dissolve's middle, then a hard cut). Hard cuts in a row stay."""
    out = []
    for c, r in sorted(cuts):
        if out and c - out[-1][0] < gap and r != out[-1][1]:
            if r < out[-1][1]:
                out[-1] = (c, r)
            continue
        out.append((c, r))
    return [c for c, _ in out]


def detect_shots(t, frames, duration):
    """Cut points of a sampled video -> [[start, end], ...] covering [0, duration]."""
    n = len(frames)
    if n < 3:
        return [[0.0, round(duration, 3)]]
    f = frames.astype(np.float32).reshape(n, -1)
    d = np.abs(np.diff(f, axis=0)).mean(axis=1)       # d[i] between frame i and i+1
    cuts = _merge([(c, 0) for c in _dip_cuts(t, f)] + [(c, 1) for c in _mix_cuts(t, f, d, _flat(f))] +
                  [(c, 2) for c in _hard_cuts(t, d)], 0.9)
    bounds = [0.0]
    for c in cuts:
        if c - bounds[-1] >= MIN_SHOT_S and duration - c >= MIN_SHOT_S:
            bounds.append(round(c, 3))
    bounds.append(round(duration, 3))
    return [[bounds[i], bounds[i + 1]] for i in range(len(bounds) - 1)]


# --------------------------------------------------------------------------- correlation
def _resize(img, w, h):
    from PIL import Image
    a = Image.fromarray(np.asarray(img, np.float32), mode="F") if img.dtype != np.uint8 else Image.fromarray(img)
    return np.asarray(a.resize((max(1, int(w)), max(1, int(h))), Image.BILINEAR), np.float32)


def _down(frames, k):
    n, h, w = frames.shape
    h2, w2 = h // k, w // k
    return frames[:, : h2 * k, : w2 * k].reshape(n, h2, k, w2, k).mean(axis=(2, 4)).astype(np.float32)


def _mask(ph, pw, top=MASK_TOP, bottom=MASK_BOTTOM):
    m = np.ones((ph, pw), np.float32)
    a, b = int(round(ph * top)), int(round(ph * (1 - bottom)))
    if b - a >= 2:
        m[:a] = 0
        m[b:] = 0
    return m


def _integral(S):
    """Zero-padded integral images of a stack (N, h, w) -> (N, h + 1, w + 1) float64."""
    I = np.zeros((S.shape[0], S.shape[1] + 1, S.shape[2] + 1), np.float64)
    I[:, 1:, 1:] = S.cumsum(axis=1).cumsum(axis=2)
    return I


def _box(I, r0, r1, pw, ny, nx):
    """Sums of rows [y + r0, y + r1) x columns [x, x + pw) for every placement (y < ny, x < nx) -> (N, ny, nx)."""
    return (I[:, r1:r1 + ny, pw:pw + nx] - I[:, r0:r0 + ny, pw:pw + nx]
            - I[:, r1:r1 + ny, 0:nx] + I[:, r0:r0 + ny, 0:nx])


def _ncc(S, P, M, I=None, I2=None):
    """Masked NCC of patch P (mask M: a band of whole rows) over every placement in every frame of S -> (N, ny, nx).
    The window sums come from integral images (``I`` / ``I2``: of S and S*S, made here when not given); only the
    patch product is a tensor contraction."""
    from numpy.lib.stride_tricks import sliding_window_view as swv
    ph, pw = P.shape
    if ph > S.shape[1] or pw > S.shape[2]:
        return None
    rows = np.where(M[:, 0] > 0)[0]
    if len(rows) < 2:
        return None
    r0, r1 = int(rows[0]), int(rows[-1]) + 1
    m = float((r1 - r0) * pw)
    pz = (P - float(P[r0:r1].mean())) * M
    pn = float(np.sqrt((pz * pz).sum()))
    if pn < 1e-3:
        return None
    ny, nx = S.shape[1] - ph + 1, S.shape[2] - pw + 1
    I = _integral(S) if I is None else I
    I2 = _integral(S * S) if I2 is None else I2
    s1 = _box(I, r0, r1, pw, ny, nx)
    s2 = _box(I2, r0, r1, pw, ny, nx)
    W = swv(S[:, r0:, :], (r1 - r0, pw), axis=(1, 2))[:, :ny]
    num = np.tensordot(W, pz[r0:r1], axes=([3, 4], [0, 1]))
    var = np.maximum(s2 - s1 * s1 / m, 1e-3)
    return num / (np.sqrt(var) * pn)


def placements(fw, fh, sw, sh):
    """How a finished frame (fw x fh) can sit in a source frame (sw x sh): [{kind, zoom, fbox, pw, ph}] - ``fbox``
    the part of the finished frame that shows source pixels, ``pw x ph`` its size in source pixels."""
    af, as_ = fw / fh, sw / sh
    out = []
    for z in ZOOMS:
        if af <= as_:
            ph = sh / z
            pw = ph * af
        else:
            pw = sw / z
            ph = pw / af
        out.append(dict(kind="crop", zoom=z, fbox=[0.0, 0.0, 1.0, 1.0], pw=pw, ph=ph))
    if af < as_ * 0.8:                       # landscape footage letter-boxed in a vertical frame (a band layout)
        bh = (fw / as_) / fh
        out.append(dict(kind="band", zoom=1.0, fbox=[0.0, (1 - bh) / 2, 1.0, bh], pw=sw, ph=sh))
    elif af > as_ * 1.25:                    # portrait footage pillar-boxed in a landscape frame
        bw = (fh * as_) / fw
        out.append(dict(kind="band", zoom=1.0, fbox=[(1 - bw) / 2, 0.0, bw, 1.0], pw=sw, ph=sh))
    return out


def _patch(F, pl, scale_w, scale_h):
    """The finished frame's region for a placement, resized to (pw, ph) * scale -> (patch, mask)."""
    fh, fw = F.shape
    x, y, w, h = pl["fbox"]
    reg = F[int(round(y * fh)): int(round((y + h) * fh)), int(round(x * fw)): int(round((x + w) * fw))]
    pw, ph = max(2, int(round(pl["pw"] * scale_w))), max(2, int(round(pl["ph"] * scale_h)))
    P = _resize(reg, pw, ph)
    M = _mask(ph, pw) if pl["kind"] == "crop" else np.ones((ph, pw), np.float32)
    return P, M


def _best_in(S, F, pls, scale, I=None, I2=None, frames_idx=None, around=None):
    """Best (score, frame index, placement index, y, x) per frame of S for finished frame F. ``around``: {placement
    index: (y, x)} - only placements within 3 px of that position (the fine pass after a coarse one)."""
    rows = []
    for k, pl in enumerate(pls):
        if around is not None and k not in around:
            continue
        P, M = _patch(F, pl, scale, scale)
        if float(P[M > 0].std()) < 2.5:              # a flat frame (sky, black): nothing to match on
            continue
        y0 = x0 = 0
        S_, I_, I2_ = S, I, I2
        if around is not None:
            cy, cx = around[k]
            ph, pw = P.shape
            y0, x0 = max(0, cy - 3), max(0, cx - 3)
            y1, x1 = min(S.shape[1], cy + 3 + ph), min(S.shape[2], cx + 3 + pw)
            S_, I_, I2_ = S[:, y0:y1, x0:x1], None, None
        r = _ncc(S_, P, M, I_, I2_)
        if r is None:
            continue
        flat = r.reshape(r.shape[0], -1)
        j = flat.argmax(axis=1)
        sc = flat[np.arange(len(j)), j]
        nx = r.shape[2]
        for i in range(len(j)):
            rows.append((float(sc[i]), int(frames_idx[i] if frames_idx is not None else i), k,
                         y0 + int(j[i] // nx), x0 + int(j[i] % nx)))
    return rows


# --------------------------------------------------------------------------- matching
def _sample_times(a, b):
    d = b - a
    if d < 1.2:
        return [a + d / 2]
    return [a + d * 0.2, a + d * 0.5, a + d * 0.8]


def _nearest(t, ts):
    return int(np.abs(ts - t).argmin())


COARSE = 4                 # the coarse pass runs on thumbnails this many times smaller (32 x 18)


class _Src:
    def __init__(self, ix):
        self.ix = ix
        self.fine = ix["frames"].astype(np.float32)
        self.coarse = _down(self.fine, COARSE)
        self.I, self.I2 = _integral(self.coarse), _integral(self.coarse * self.coarse)
        self.rows, self.cols = self.fine.shape[1], self.fine.shape[2]


def _coarse(srcs, F, fw, fh):
    """Every source's top candidates for one finished frame: [(score, src index, frame index, placement, y, x)]
    (y, x in coarse pixels)."""
    out = []
    for si, s in enumerate(srcs):
        pls = placements(fw, fh, s.cols, s.rows)
        rows = _best_in(s.coarse, F, pls, 1.0 / COARSE, s.I, s.I2)
        rows.sort(reverse=True)
        seen = set()
        for sc, fi, k, y, x in rows:
            if fi in seen:
                continue
            seen.add(fi)
            out.append((sc, si, fi, k, y, x))
            if len(seen) >= TOP_K:
                break
    out.sort(reverse=True)
    return out


def _fine(s, F, fw, fh, cand):
    """Re-score coarse candidates [(frame, placement, y, x)] (+ the frames next to them) at the index's full size,
    near their coarse position."""
    pls = placements(fw, fh, s.cols, s.rows)
    rows = []
    for fi, k, y, x in cand:
        idx = [j for j in (fi - 1, fi, fi + 1) if 0 <= j < len(s.fine)]
        rows += _best_in(s.fine[idx], F, pls, 1.0, frames_idx=idx, around={k: (y * COARSE, x * COARSE)})
    rows.sort(reverse=True)
    return rows


def _refine_time(path, s, F, fw, fh, pl_i, t0, span):
    """Decode the source around t0 at its own rate (small) and find the best-matching instant."""
    try:
        t, fr = _decode(path, s.cols, s.rows, start=max(0.0, t0 - span), dur=2 * span, fps=min(30.0, s.ix["fps"] or 30))
    except RuntimeError:
        return None
    if not len(fr):
        return None
    f = fr.astype(np.float32)
    pl = placements(fw, fh, s.cols, s.rows)[pl_i]
    P, M = _patch(F, pl, 1.0, 1.0)
    r = _ncc(f, P, M)
    if r is None:
        return None
    flat = r.reshape(r.shape[0], -1)
    j = int(flat.max(axis=1).argmax())
    k = int(flat[j].argmax())
    return float(t[j]), float(flat[j, k]), k // r.shape[2], k % r.shape[2]


def _grade(fin_rgb, src_rgb):
    """Per-channel [gain, offset] mapping the source's colours onto the finished frame's (8-bit values)."""
    out = []
    for c in range(3):
        a, b = src_rgb[..., c].astype(np.float64), fin_rgb[..., c].astype(np.float64)
        sa, sb = a.std(), b.std()
        g = float(np.clip(sb / sa, 0.5, 2.0)) if sa > 2 else 1.0
        o = float(np.clip(b.mean() - g * a.mean(), -80, 80))
        out.append([round(g, 3), round(o, 1)])
    return out


def _frame_rgb(path, t, w, h):
    try:
        _ts, fr = _decode(path, w, h, start=t, frames=1, color=True)
    except RuntimeError:
        return None
    return fr[0] if len(fr) else None


def match(video, sources, on_event=None, refine=True, grade=True):
    """Shots of ``video`` matched to ``sources`` -> {version, video, duration, fps, canvas, shots [{i, start, end,
    match}], sources [{path, duration, w, h}], coverage}. ``match`` is None for a shot found in no source (a title
    card, footage that is not linked)."""
    emit = on_event or (lambda ev: None)
    info = probe(video)
    fw, fh = _fin_size(info["w"], info["h"])
    emit(dict(event="stage", stage="read", file=os.path.basename(video)))
    ft, ff = _decode(video, fw, fh, fps=FIN_FPS)
    shots = detect_shots(ft, ff, info["duration"] or (float(ft[-1]) if len(ft) else 0.0))
    srcs, metas = [], []
    for n, p in enumerate(sources):
        emit(dict(event="stage", stage="index", file=os.path.basename(p), i=n + 1, n=len(sources)))
        try:
            ix = index(p)
        except (RuntimeError, OSError) as e:
            emit(dict(event="warning", code="source-unreadable", file=os.path.basename(p), error=str(e)[:200]))
            continue
        if not len(ix["frames"]):
            continue
        srcs.append(_Src(ix))
        metas.append(dict(path=ix["path"], duration=round(ix["duration"], 3), w=ix["w"], h=ix["h"],
                          fps=round(ix["fps"], 3)))
    ffl = ff.astype(np.float32)
    out = []
    for i, (a, b) in enumerate(shots):
        emit(dict(event="progress", stage="match", i=i + 1, n=len(shots)))
        row = dict(i=i, start=a, end=b, match=None)
        out.append(row)
        if not srcs:
            continue
        samples = []
        for ts in _sample_times(a, b):
            j = _nearest(ts, ft)
            if a - 0.05 <= ft[j] <= b + 0.05:
                samples.append((float(ft[j]), ffl[j]))
        per_src = {}
        for ts, F in samples:
            cands = _coarse(srcs, F, fw, fh)
            by = {}
            for sc, si, fi, k, y, x in cands:
                by.setdefault(si, []).append((sc, fi, k, y, x))
            # the fine pass for the sources that came out best (all of them would cost seconds per frame)
            keep = sorted(by, key=lambda q: -max(c[0] for c in by[q]))[:4]
            for si in keep:
                rows = _fine(srcs[si], F, fw, fh, [c[1:] for c in by[si][:5]])
                if rows:
                    per_src.setdefault(si, []).append((ts, rows[0]))
        if not per_src:
            continue
        # the source whose best frames agree most (mean of the best score per sample; missing samples count 0)
        si = max(per_src, key=lambda k: sum(r[1][0] for r in per_src[k]) / max(1, len(samples)))
        hits = sorted(per_src[si])
        s = srcs[si]
        mid = min(hits, key=lambda h: abs(h[0] - (a + b) / 2))
        sc, fi, k, y, x = mid[1]
        t_src = float(s.ix["t"][fi])
        speed = 1.0
        good = [h for h in hits if h[1][0] >= MATCH_MIN and h[1][2] == k]
        if len(good) >= 2 and good[-1][0] - good[0][0] > 0.6:
            dt = float(s.ix["t"][good[-1][1][1]] - s.ix["t"][good[0][1][1]])
            sp = dt / (good[-1][0] - good[0][0])
            if 0.2 <= sp <= 5.0:
                speed = 1.0 if abs(sp - 1.0) < 0.2 else round(sp, 2)
        ts_mid = mid[0]
        if refine:
            gap = float(np.median(np.diff(s.ix["t"]))) if len(s.ix["t"]) > 2 else 0.5
            F = next(F_ for t_, F_ in samples if t_ == ts_mid)
            r = _refine_time(s.ix["path"], s, F, fw, fh, k, t_src, max(0.4, gap * 0.75))
            if r and r[1] >= sc - 0.02:
                t_src, sc, y, x = r
        if sc < MATCH_MIN:
            continue
        pl = placements(fw, fh, s.cols, s.rows)[k]
        pw, ph = pl["pw"], pl["ph"]
        box = [round(x / s.cols, 4), round(y / s.rows, 4), round(min(1.0, pw / s.cols), 4),
               round(min(1.0, ph / s.rows), 4)]
        start_src = max(0.0, t_src - (ts_mid - a) * speed)
        end_src = min(s.ix["duration"], start_src + (b - a) * speed)
        m = dict(source=s.ix["path"], t=round(start_src, 3), t_end=round(end_src, 3), speed=speed,
                 score=round(float(sc), 3), placement=pl["kind"], zoom=pl["zoom"], box=box,
                 fbox=[round(v, 4) for v in pl["fbox"]], grade=None)
        if grade:
            fin = _frame_rgb(video, ts_mid, 160, int(round(160 * info["h"] / max(1, info["w"]))) or 90)
            src = _frame_rgb(s.ix["path"], t_src, s.cols * 2, s.rows * 2)
            if fin is not None and src is not None:
                fx, fy, fwb, fhb = m["fbox"]
                H, W = fin.shape[:2]
                fin_r = fin[int(fy * H): int((fy + fhb) * H), int(fx * W): int((fx + fwb) * W)]
                Hs, Ws = src.shape[:2]
                src_r = src[int(box[1] * Hs): int((box[1] + box[3]) * Hs), int(box[0] * Ws): int((box[0] + box[2]) * Ws)]
                if fin_r.size and src_r.size:
                    from PIL import Image
                    src_r = np.asarray(Image.fromarray(src_r).resize((fin_r.shape[1], fin_r.shape[0])))
                    a0, b0 = int(fin_r.shape[0] * MASK_TOP), int(fin_r.shape[0] * (1 - MASK_BOTTOM))
                    m["grade"] = _grade(fin_r[a0:b0], src_r[a0:b0])
        row["match"] = m
    covered = sum(r["end"] - r["start"] for r in out if r["match"])
    total = sum(r["end"] - r["start"] for r in out) or 1.0
    emit(dict(event="stage", stage="done", shots=len(out), matched=sum(1 for r in out if r["match"])))
    return dict(version=VERSION, video=os.path.abspath(video), duration=round(info["duration"], 3),
                fps=info["fps"], canvas=[info["w"], info["h"]], shots=out, sources=metas,
                coverage=round(covered / total, 3))


# --------------------------------------------------------------------------- using a match
def used_ranges(m):
    """{source: [[a, b], ...]} the finished video uses (sorted, merged)."""
    out = {}
    for s in m.get("shots") or []:
        x = s.get("match")
        if x:
            out.setdefault(x["source"], []).append([x["t"], x["t_end"]])
    for k, v in out.items():
        v.sort()
        merged = []
        for a, b in v:
            if merged and a <= merged[-1][1] + 0.2:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        out[k] = merged
    return out


def alternatives(m, i, n=4):
    """Other takes for shot ``i``: windows of the linked footage the video does not use, as long as the shot (at
    its speed). The same source near the used moment first (the same subject, a little earlier / later), then the
    other sources' unused stretches. -> [{source, t, dur, why same-source-after | same-source-before | other-source}]"""
    shots = m.get("shots") or []
    if not (0 <= i < len(shots)):
        return []
    sh = shots[i]
    x = sh.get("match")
    need = (sh["end"] - sh["start"]) * (x["speed"] if x else 1.0)
    used = used_ranges(m)
    srcs = {s["path"]: s for s in m.get("sources") or []}

    def free(src, a, b):
        return all(b <= u0 - 0.05 or a >= u1 + 0.05 for u0, u1 in used.get(src, []))

    out = []
    if x:
        dur = srcs.get(x["source"], {}).get("duration") or x["t_end"]
        for k in range(1, 30):
            t = round(x["t_end"] + 0.25 + (k - 1) * need, 3)
            if t + need > dur:
                break
            if free(x["source"], t, t + need):
                out.append(dict(source=x["source"], t=t, dur=round(need, 3), why="same-source-after"))
                break
        for k in range(1, 30):
            t = round(x["t"] - 0.25 - k * need, 3)
            if t < 0:
                break
            if free(x["source"], t, t + need):
                out.append(dict(source=x["source"], t=t, dur=round(need, 3), why="same-source-before"))
                break
    for p, s in srcs.items():
        if x and p == x["source"]:
            continue
        dur = s.get("duration") or 0.0
        best = None
        t = 0.0
        while t + need <= dur:
            if free(p, t, t + need):
                best = t
                break
            t += max(0.5, need / 2)
        if best is not None:
            mid = min(max(0.0, dur / 2 - need / 2), dur - need)
            if free(p, mid, mid + need):
                best = mid
            out.append(dict(source=p, t=round(best, 3), dur=round(need, 3), why="other-source"))
    return out[:n]


def fit_box(box, src_wh, aspect, widest=False):
    """A crop of the source with ``aspect`` (w / h) centred on ``box``'s centre, inside the frame. ``widest``: as
    large as the frame allows (a new version at another aspect: the most of the footage), else the size of ``box``
    (the same framing as the finished video). -> [x, y, w, h] fractions."""
    sw, sh = src_wh
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    if widest:
        if aspect <= sw / sh:
            h = 1.0
            w = h * sh * aspect / sw
        else:
            w = 1.0
            h = w * sw / aspect / sh
    else:
        w, h = box[2], box[3]
        cur = (w * sw) / max(1e-6, h * sh)
        if abs(cur - aspect) > 0.01:
            if aspect < cur:
                w = h * sh * aspect / sw
            else:
                h = w * sw / aspect / sh
    w, h = min(1.0, w), min(1.0, h)
    x = min(max(0.0, cx - w / 2), 1.0 - w)
    y = min(max(0.0, cy - h / 2), 1.0 - h)
    return [round(x, 4), round(y, 4), round(w, 4), round(h, 4)]


def _blur():
    from .ffmpeg_filters import blur
    return blur(sigma=24)                       # gblur: the app's LGPL ffmpeg has no boxblur


def piece_filter(box, W, H, fps, speed=1.0, grade=None, fbox=None):
    """The -vf for a source piece: crop ``box`` (fractions), scale onto W x H (``fbox``: only that part of the canvas,
    over a blurred fill of the same picture), the finished grade, the speed, the canvas frame rate."""
    x, y, w, h = box
    crop = f"crop=trunc(iw*{w:.5f}/2)*2:trunc(ih*{h:.5f}/2)*2:trunc(iw*{x:.5f}):trunc(ih*{y:.5f})"
    g = ""
    if grade:
        exprs = [f"clip(val*{gn:.4f}+{off:.2f}\\,0\\,255)" for gn, off in grade]
        g = f",format=rgb24,lutrgb=r='{exprs[0]}':g='{exprs[1]}':b='{exprs[2]}'"
    sp = f",setpts=(PTS-STARTPTS)/{speed:.4f}" if abs(speed - 1.0) > 1e-3 else ",setpts=PTS-STARTPTS"
    tail = f",fps={fps:g},format=yuv420p,setsar=1"
    if not fbox or fbox == [0.0, 0.0, 1.0, 1.0]:
        return f"{crop},scale={W}:{H}:flags=lanczos{g}{sp}{tail}"
    fx, fy, fw_, fh_ = fbox
    pw, ph = _even(W * fw_), _even(H * fh_)
    return (f"{crop}{g}{sp},split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"{_blur()}[bg];[b]scale={pw}:{ph}:flags=lanczos[fg];[bg][fg]overlay={int(round(W * fx))}:"
            f"{int(round(H * fy))}{tail}")
