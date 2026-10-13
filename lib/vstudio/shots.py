"""Shots inside a clip and the best moments in each, so a planner picks real moments instead of a clip's first seconds.

    from vstudio import shots
    a = shots.analyze("DJI_0081.MP4")      # cached; one low-res decode (VideoToolbox on a Mac) for everything below
    a["shots"]      # [{i, start, end, moments: [{i, start, end, score, sharp, steady, exposure, best: [a, b]}]}]
    a["best"]       # the clip's top moments [{shot, moment, start, end, score}]
    a["flashes"]    # flash frames / glitches (s) - never cut onto them
    a["secs"]       # per second {t, sharp, motion, bright} (the reel scorer's inputs, from the same decode)
    shots.sheet("DJI_0081.MP4", "work/sheets/0081.jpg")   # one labelled tile per moment (its best second)
    shots.line(a)   # "shots: S1 0-12.4 s (best 3.0-7.0, .81); ..." for a planner prompt

Cuts: TransNet V2 (``vstudio.transnet``, MIT weights, numpy / MLX) when its weights are downloaded, else an adaptive
content detector (the PySceneDetect AdaptiveDetector method, BSD-3, re-done in numpy so the runtime needs no new
package): frame-to-frame HSV change over its rolling average, cut at >= 3x and >= 15 change.
Moments: a shot longer than ~10 s (a drone take, a walk) is split where the view has drifted to something new (colour
histogram vs the moment's first frame) or every 12 s, so a 2-minute flight becomes a handful of choosable moments.
Scores (0-1) per moment: sharpness (Laplacian variance), steadiness (gyro-like: high-frequency jitter of the camera
path from phase correlation, whip pans penalised), exposure (mid-grey, few clipped pixels, stable). There is no
aesthetic model in the engine yet; when one lands it slots into ``_score``.
Decode: frames at <= 30 fps, 320 px on the long side, decoded on the GPU with VideoToolbox + scale_vt for 4K HEVC
when that ffmpeg has it (software decode otherwise); thumbnails every 0.5 s are kept (JPEG) for the sheets.
"""
import hashlib
import json
import os
import subprocess

import numpy as np

VERSION = 1
LONG = 320                  # decode size, long side
SMALL = 160                 # metric size, long side (the reel scorer's 160-px grey)
THUMB_EVERY = 0.5           # s between kept thumbnails
MOMENT_SPLIT = 10.0         # shots longer than this are split into moments
MOMENT_MAX = 12.0
MOMENT_MIN = 3.0
BEST_LEN = 4.0              # best window inside a moment
MAX_TILES = 20


def _cache_root():
    from .config import cache_dir
    return cache_dir("shots")


def _key(src, backend):
    st = os.stat(src)
    return hashlib.sha1(json.dumps([os.path.abspath(src), st.st_size, int(st.st_mtime), VERSION, backend]).encode()
                        ).hexdigest()[:16]


# ------------------------------------------------------------------ decode
def _vt_ok(info):
    """VideoToolbox decode + GPU scaling: macOS, an ffmpeg with scale_vt, no rotation (autorotate is CPU-only)."""
    import sys
    from . import media
    if sys.platform != "darwin" or int(info.get("rotation") or 0) % 360:
        return False
    try:
        return media.has_filter("scale_vt")
    except Exception:  # noqa: BLE001
        return False


def _decode_cmd(src, info, fps, w, h, vt):
    from . import media
    ff = media.ffmpeg_bin()
    rate = [f"fps={fps:g}"] if fps else []
    if vt:
        sw = "p010le" if "10" in str(info.get("pix_fmt") or "") or "12" in str(info.get("pix_fmt") or "") else "nv12"
        vf = ",".join(rate + [f"scale_vt=w={w}:h={h}", "hwdownload", f"format={sw}"])
        pre = ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"]
    else:
        vf = ",".join(rate + [f"scale={w}:{h}:flags=area"])
        pre = []
    return [ff, "-v", "error", "-nostdin", *pre, "-i", os.fspath(src), "-an", "-sn", "-dn", "-vf", vf,
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]


def _frames(src, info, fps, w, h):
    """Yield (index, rgb uint8 (h, w, 3)); VideoToolbox first, software if that fails before the first frame."""
    for vt in ([True, False] if _vt_ok(info) else [False]):
        p = subprocess.Popen(_decode_cmd(src, info, fps, w, h, vt), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        n, size = 0, w * h * 3
        try:
            while True:
                buf = p.stdout.read(size)
                if len(buf) < size:
                    break
                yield n, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
                n += 1
        finally:
            p.stdout.close()
            err = p.stderr.read().decode("utf-8", "replace")[-300:]
            p.stderr.close()
            rc = p.wait()
        if n:
            return
        if not vt:
            raise RuntimeError(f"could not decode {os.path.basename(src)}: {err or rc}")


def _sizes(info):
    dw, dh = int(info.get("display_w") or 16), int(info.get("display_h") or 9)
    if dw >= dh:
        w, h = LONG, max(2, int(round(LONG * dh / dw / 2)) * 2)
        sw, sh = SMALL, max(2, int(round(SMALL * dh / dw / 2)) * 2)
    else:
        w, h = max(2, int(round(LONG * dw / dh / 2)) * 2), LONG
        sw, sh = max(2, int(round(SMALL * dw / dh / 2)) * 2), SMALL
    return w, h, sw, sh


def _hist512(rgb_small):
    f = rgb_small.astype(np.int32)
    b = ((f[..., 0] >> 5) << 6) + ((f[..., 1] >> 5) << 3) + (f[..., 2] >> 5)
    hst = np.bincount(b.ravel(), minlength=512).astype(np.float32)
    return hst / max(float(np.linalg.norm(hst)), 1e-9)


def _scan(src, info, thumb_dir):
    """One pass over the clip -> per-frame arrays + TransNet input + thumbnails on disk."""
    import cv2
    fps_src = float(info.get("fps") or 30.0)
    fps = 30.0 if fps_src > 31 else 0.0
    afps = fps or fps_src or 30.0
    w, h, sw, sh = _sizes(info)
    lag = max(1, int(round(0.25 * afps)))                  # the reel scorer's "0.25 s apart" motion
    tn, sharp, luma, clip, cv, dx, dy, hist, motion = [], [], [], [], [], [], [], [], []
    prev_hsv = prev_g = None
    greys = []
    win = None
    next_thumb = 0.0
    os.makedirs(thumb_dir, exist_ok=True)
    thumbs = []
    for i, rgb in _frames(src, info, fps, w, h):
        t = i / afps
        tn.append(cv2.resize(rgb, (48, 27), interpolation=cv2.INTER_AREA))
        small = cv2.resize(rgb, (sw, sh), interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
        sharp.append(float(cv2.Laplacian(g, cv2.CV_32F).var()))
        luma.append(float(g.mean()))
        clip.append(float(((g <= 8) | (g >= 247)).mean()))
        hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV).astype(np.int16)
        cv.append(float(np.abs(hsv - prev_hsv).mean(axis=(0, 1)).mean()) if prev_hsv is not None else 0.0)
        prev_hsv = hsv
        gf = g.astype(np.float32)
        if win is None:
            win = cv2.createHanningWindow((sw, sh), cv2.CV_32F)
        if prev_g is not None:
            (ddx, ddy), _resp = cv2.phaseCorrelate(prev_g, gf, win)
        else:
            ddx = ddy = 0.0
        dx.append(float(ddx))
        dy.append(float(ddy))
        prev_g = gf
        greys.append(g)
        motion.append(float(np.abs(g.astype(np.int16) - greys[i - lag]).mean()) if i >= lag else np.nan)
        if len(greys) > lag + 1:
            greys[i - lag - 1] = None
        hist.append(_hist512(tn[-1]))
        if t + 1e-6 >= next_thumb:
            fn = os.path.join(thumb_dir, f"t{len(thumbs):05d}.jpg")
            cv2.imwrite(fn, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 82])
            thumbs.append(round(t, 3))
            next_thumb += THUMB_EVERY
    if not tn:
        raise RuntimeError(f"no frames from {os.path.basename(src)}")
    A = lambda v: np.asarray(v, np.float32)  # noqa: E731
    return dict(fps=afps, tn=np.stack(tn), sharp=A(sharp), luma=A(luma), clip=A(clip), cv=A(cv), dx=A(dx), dy=A(dy),
                hist=np.stack(hist), motion=A(motion), thumbs=thumbs, size=(w, h))


# ------------------------------------------------------------------ cuts
def _adaptive_cuts(cv, fps, threshold=3.0, min_content=15.0, window=2, min_len=None):
    """PySceneDetect's AdaptiveDetector method: a cut where the frame's HSV change is >= ``threshold`` x the mean
    change of the ``window`` frames on each side (and >= ``min_content``), at least ``min_len`` frames apart."""
    min_len = int(min_len or max(1, round(0.5 * fps)))
    cuts, last = [], 0
    n = len(cv)
    for i in range(window, n - window):
        nb = np.concatenate([cv[i - window:i], cv[i + 1:i + 1 + window]])
        avg = float(nb.mean())
        ratio = cv[i] / avg if avg > 1e-6 else (255.0 if cv[i] >= min_content else 0.0)
        if ratio >= threshold and cv[i] >= min_content and i - last >= min_len:
            cuts.append(i)
            last = i
    return cuts


def _flashes(luma, fps, jump=28.0, max_len=3):
    """Frames brighter (or darker) than both sides by ``jump`` for at most ``max_len`` frames -> frame indices."""
    out = []
    n = len(luma)
    for i in range(1, n - 1):
        for L in range(1, max_len + 1):
            if i + L >= n:
                break
            seg = luma[i:i + L]
            a, b = luma[i - 1], luma[i + L]
            if abs(a - b) < jump / 2 and (np.all(seg - max(a, b) >= jump) or np.all(min(a, b) - seg >= jump)):
                out.extend(range(i, i + L))
                break
    return sorted(set(out))


def _shot_ranges(S, backend):
    n = len(S["tn"])
    fps = S["fps"]
    used = "adaptive"
    if backend in ("auto", "transnetv2"):
        from . import transnet
        if transnet.available():
            try:
                p = transnet.predict(S["tn"])
                rng = transnet.scenes(p)
                used = "transnetv2"
            except Exception:  # noqa: BLE001 - weights broken / partial: content detector
                if backend == "transnetv2":
                    raise
        elif backend == "transnetv2":
            raise FileNotFoundError("TransNet V2 weights are not downloaded")
    if used == "adaptive":
        cuts = _adaptive_cuts(S["cv"], fps)
        edges = [0] + cuts + [n]
        rng = [(a, b - 1) for a, b in zip(edges[:-1], edges[1:]) if b > a]
    # a "shot" shorter than 0.4 s is a flash / glitch / dissolve sliver: fold it into its neighbour
    min_f = max(1, int(round(0.4 * fps)))
    merged = []
    for a, b in rng:
        if merged and (b - a + 1 < min_f):
            merged[-1] = (merged[-1][0], b)
        elif merged and merged[-1][1] - merged[-1][0] + 1 < min_f:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged, used


# ------------------------------------------------------------------ moments + scores
def _moments(S, a, b):
    """Split frame range [a, b] at view drift / every MOMENT_MAX s when the shot is long."""
    fps = S["fps"]
    if (b - a + 1) / fps <= MOMENT_SPLIT:
        return [(a, b)]
    out, s = [], a
    anchor = S["hist"][a]
    for i in range(a + 1, b + 1):
        long_enough = (i - s) / fps >= MOMENT_MIN and (b - i) / fps >= MOMENT_MIN
        drift = float(S["hist"][i] @ anchor) < 0.55
        if long_enough and (drift or (i - s) / fps >= MOMENT_MAX):
            out.append((s, i - 1))
            s, anchor = i, S["hist"][i]
    out.append((s, b))
    return out


def _per_frame_quality(S):
    """Per-frame 0-1 sharpness, steadiness, exposure (arrays) - shared by the moment scores and best windows."""
    fps = S["fps"]
    sharp = np.clip((np.log10(S["sharp"] + 1.0) - 1.5) / 2.0, 0, 1)          # var 30 -> 0, 3000 -> 1 at 160 px
    # camera path (px at 160 px wide); jitter = what a 0.5 s moving average does not explain
    k = max(3, int(round(0.5 * fps)) | 1)
    ker = np.ones(k, np.float32) / k
    jit = np.zeros(len(S["dx"]), np.float32)
    speed = np.zeros(len(S["dx"]), np.float32)
    for d in (S["dx"], S["dy"]):
        path = np.cumsum(d)
        pp = np.pad(path, (k // 2, k // 2), mode="edge")
        sm = np.convolve(pp, ker, mode="valid")
        jit += (path - sm) ** 2
        sp = np.pad(d, (k // 2, k // 2), mode="edge")
        speed += np.convolve(sp, ker, mode="valid") ** 2
    jit = np.sqrt(np.convolve(np.pad(jit, (k // 2, k // 2), mode="edge"), ker, mode="valid"))
    speed = np.sqrt(speed) * fps                                               # px / s at 160 px
    steady = np.exp(-(jit / 0.8) ** 2) * np.exp(-np.maximum(0.0, speed - 60.0) / 120.0)
    lum = S["luma"]
    expo = (1 - np.clip(np.abs(lum - 118.0) / 118.0, 0, 1) ** 1.5) * (1 - np.clip(S["clip"] * 3.0, 0, 1))
    return sharp.astype(np.float32), steady.astype(np.float32), expo.astype(np.float32), jit, speed


def _score(sh, st, ex):
    return 0.40 * sh + 0.35 * st + 0.25 * ex


def _best_window(q, a, b, fps, length=BEST_LEN):
    n = b - a + 1
    L = max(1, min(n, int(round(length * fps))))
    if L >= n:
        return a, b
    c = np.cumsum(np.concatenate([[0.0], q[a:b + 1]]))
    m = (c[L:] - c[:-L]) / L
    edge = min(int(round(0.3 * fps)), max(0, (n - L) // 2))                    # keep clear of the moment's edges
    lo, hi = edge, len(m) - 1 - edge
    j = lo + int(np.argmax(m[lo:hi + 1])) if hi >= lo else int(np.argmax(m))
    return a + j, a + j + L - 1


# ------------------------------------------------------------------ public
def analyze(src, backend="auto", cache=True, echo=None):
    """Shots + moments + scores of one clip (module doc). Cached in <cache>/shots/<key>.json (+ thumbnails)."""
    import time
    from . import media
    from . import transnet
    key = _key(src, backend if backend != "auto" else f"auto-{int(transnet.available())}")
    root = _cache_root()
    jp = os.path.join(root, f"{key}.json")
    if cache and os.path.exists(jp):
        try:
            with open(jp, encoding="utf-8") as f:
                a = json.load(f)
            if all(os.path.exists(os.path.join(a["thumb_dir"], f"t{i:05d}.jpg")) for i in (0, len(a["thumbs"]) - 1)):
                return a
        except (OSError, ValueError, KeyError, IndexError):
            pass
    t0 = time.time()
    info = media.probe(src)
    thumb_dir = os.path.join(root, key)
    S = _scan(src, info, thumb_dir)
    t_dec = time.time() - t0
    rng, used = _shot_ranges(S, backend)
    t_cut = time.time() - t0 - t_dec
    fps = S["fps"]
    n = len(S["tn"])
    sh, st, ex, jit, speed = _per_frame_quality(S)
    q = _score(sh, st, ex)
    fl = _flashes(S["luma"], fps)
    q[fl] = 0.0
    shots, allm = [], []
    for si, (a, b) in enumerate(rng):
        moms = []
        for mi, (ma, mb) in enumerate(_moments(S, a, b)):
            ba, bb = _best_window(q, ma, mb, fps)
            sl = slice(ma, mb + 1)
            lum_std = float(np.std(S["luma"][sl]))
            expo = float(np.mean(ex[sl])) * float(np.exp(-max(0.0, lum_std - 12.0) / 20.0))
            m = dict(i=mi + 1, start=round(ma / fps, 2), end=round((mb + 1) / fps, 2),
                     score=round(float(_score(np.mean(sh[sl]), np.mean(st[sl]), expo)), 3),
                     sharp=round(float(np.mean(sh[sl])), 3), steady=round(float(np.mean(st[sl])), 3),
                     exposure=round(expo, 3), jitter_px=round(float(np.median(jit[sl])), 2),
                     pan_px_s=round(float(np.median(speed[sl])), 1),
                     best=[round(ba / fps, 2), round((bb + 1) / fps, 2)],
                     t=round((ba + bb + 1) / 2 / fps, 2))
            moms.append(m)
            allm.append(dict(shot=si + 1, moment=mi + 1, start=m["best"][0], end=m["best"][1], score=m["score"]))
        shots.append(dict(i=si + 1, start=round(a / fps, 2), end=round((b + 1) / fps, 2), moments=moms))
    best = sorted(allm, key=lambda m: -m["score"])[:3]
    # per-second inputs of the vlog reel scorer (vlog/scripts/funvlog/score.py), same definitions: 160-px grey,
    # Laplacian variance, mean grey, mean |diff| vs 0.25 s earlier, sampled 4x a second
    secs = []
    dur = n / fps
    for k in range(int(np.ceil(dur - 1e-6))):
        idx = [int(round((k + j / 4) * fps)) for j in range(4)]
        idx = [i for i in idx if i < n]
        if not idx:
            continue
        mo = [float(S["motion"][i]) for i in idx if not np.isnan(S["motion"][i])]
        secs.append(dict(t=k, sharp=round(float(np.mean(S["sharp"][idx])), 1),
                         bright=round(float(np.mean(S["luma"][idx])), 1),
                         motion=round(float(np.mean(mo)), 2) if mo else 0.0))
    a = dict(v=VERSION, file=os.path.basename(src), src=os.path.abspath(src), dur=round(dur, 2),
             src_fps=round(float(info.get("fps") or 0), 3), fps=round(fps, 3), frames=n, backend=used,
             decode_s=round(t_dec, 1), cut_s=round(t_cut, 1), total_s=round(time.time() - t0, 1),
             shots=shots, best=best, flashes=[round(i / fps, 2) for i in fl], secs=secs,
             thumbs=S["thumbs"], thumb_dir=thumb_dir, thumb_size=list(S["size"]))
    if echo:
        echo(f"shots: {a['file']}: {len(shots)} shot(s), {len(allm)} moment(s), {used}, {a['total_s']} s")
    with open(jp + ".tmp", "w", encoding="utf-8") as f:
        json.dump(a, f)
    os.replace(jp + ".tmp", jp)
    return a


def thumb(a, t):
    """Path of the kept thumbnail nearest to ``t`` s."""
    th = a["thumbs"]
    i = int(np.argmin(np.abs(np.asarray(th) - float(t)))) if th else 0
    return os.path.join(a["thumb_dir"], f"t{i:05d}.jpg")


def moments(a):
    """Flat list of moments [{id 'S1.2', shot, moment, start, end, best, score, ...}] in clip order."""
    out = []
    for s in a["shots"]:
        for m in s["moments"]:
            mid = f"S{s['i']}" + (f".{m['i']}" if len(s["moments"]) > 1 else "")
            out.append(dict(m, id=mid, shot=s["i"], moment=m["i"]))
    return out


def line(a, limit=10):
    """Shots + moments as a compact line for a planner prompt."""
    ms = moments(a)
    if len(ms) > limit:
        keep = {id(m) for m in sorted(ms, key=lambda m: -m["score"])[:limit]}
        ms = [m for m in ms if id(m) in keep]
    bits = [f"{m['id']} {m['start']:.1f}-{m['end']:.1f}s best {m['best'][0]:.1f}-{m['best'][1]:.1f} "
            f"({m['score']:.2f})" for m in ms]
    n = len(a["shots"])
    head = f"{n} shot{'s' if n != 1 else ''}"
    if a.get("flashes"):
        head += f", flash frames at {', '.join(f'{t:.1f}' for t in a['flashes'][:4])}s (never cut onto them)"
    return f"{head}; moments (id start-end, best window, quality 0-1): " + "; ".join(bits)


def sheet(src, out, a=None, cols=5, tile_w=320):
    """A contact sheet with one tile per moment (its best second), labelled 'S2.1 14.0s ★.82' and the moment's span."""
    from PIL import Image, ImageDraw, ImageFont
    a = a or analyze(src)
    ms = moments(a)
    if len(ms) > MAX_TILES:
        keep = {id(m) for m in sorted(ms, key=lambda m: -m["score"])[:MAX_TILES]}
        ms = [m for m in ms if id(m) in keep]
    key = hashlib.sha1(json.dumps([a["src"], a["frames"], a["v"], [m["t"] for m in ms], cols, tile_w]).encode()
                       ).hexdigest()[:12]
    side = out + ".key"
    if os.path.exists(out) and os.path.exists(side):
        with open(side) as fh:
            if fh.read().strip() == key:
                return out
    ims = []
    for m in ms:
        try:
            im = Image.open(thumb(a, m["t"])).convert("RGB")
        except OSError:
            continue
        ims.append((m, im))
    if not ims:
        raise RuntimeError(f"no thumbnails for {os.path.basename(src)}")
    w0, h0 = ims[0][1].size
    tw, th = tile_w, max(2, int(round(tile_w * h0 / w0)))
    lab = 42
    cols = min(cols, len(ims))
    rows = (len(ims) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tw, rows * (th + lab)), "black")
    d = ImageDraw.Draw(canvas)
    try:
        from .config import font
        f1 = ImageFont.truetype(font("mono-bold"), 17)
        f2 = ImageFont.truetype(font("mono"), 14)
    except Exception:  # noqa: BLE001
        f1 = f2 = ImageFont.load_default()
    for k, (m, im) in enumerate(ims):
        x, y = (k % cols) * tw, (k // cols) * (th + lab)
        canvas.paste(im.resize((tw, th)), (x, y))
        d.text((x + 6, y + th + 2), f"{m['id']} {m['t']:.1f}s  q{m['score']:.2f}", fill="white", font=f1)
        d.text((x + 6, y + th + 22), f"{m['start']:.1f}-{m['end']:.1f}s best {m['best'][0]:.1f}-{m['best'][1]:.1f}",
               fill=(170, 170, 170), font=f2)
        bar = int((tw - 12) * max(0.0, min(1.0, m["score"])))
        d.rectangle([x + 6, y + th - 5, x + 6 + bar, y + th - 2], fill=(90, 200, 120))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    canvas.save(out, quality=82)
    with open(side, "w") as f:
        f.write(key)
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m vstudio.shots", description="Shots, moments and scores of clips.")
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--backend", default="auto", choices=["auto", "transnetv2", "adaptive"])
    ap.add_argument("--sheets", help="write a contact sheet per clip into this folder")
    ap.add_argument("--json", action="store_true", help="print the analyses as JSON")
    args = ap.parse_args(argv)
    res = []
    for c in args.clips:
        a = analyze(c, backend=args.backend)
        res.append(a)
        if args.sheets:
            sheet(c, os.path.join(args.sheets, os.path.splitext(os.path.basename(c))[0] + ".jpg"), a)
        if not args.json:
            print(f"{a['file']}  {a['dur']} s  {a['backend']}  ({a['total_s']} s)\n  {line(a)}")
    if args.json:
        print(json.dumps([{k: v for k, v in a.items() if k not in ("thumbs", "secs")} for a in res], indent=1))


if __name__ == "__main__":
    main()
