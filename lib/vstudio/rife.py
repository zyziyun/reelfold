"""Frame interpolation with RIFE 4.25 on Apple silicon (MLX, no torch): morph-cut bridges and smooth slow motion.

    from vstudio import rife
    if rife.available():
        mids = rife.inbetweens(a_rgb, b_rgb, 4)          # 4 frames between two HxWx3 uint8 frames
        rife.slowmo("drone.mp4", "slow.mp4", 12.0, 15.0, speed=0.25, fps=30)

The network is Practical-RIFE 4.25's IFNet (MIT, (c) hzwer, https://github.com/hzwer/Practical-RIFE), written here
in MLX after the rife-mlx port (MIT, https://github.com/xocialize/rife-mlx). The weights are the official 4.25
release converted to safetensors by mlx-community (``mlx-community/RIFE-4.25``, MIT, 22.7 MB fp32 - RIFE's
coarse-to-fine flow is fp16-sensitive, so it stays fp32).

Where the model comes from: env ``VSTUDIO_RIFE_MODEL`` (the desk app's first-run asset group ``rife-mlx``, sha256
pinned in apps/desk/packaging/assets.json), else ``<cache>/models/rife-4.25-mlx`` (``python -m vstudio.rife fetch``
downloads the same pinned file for skill users). The engine never downloads it on its own: without the model (or
without MLX - Intel Macs, Windows) ``available()`` is False and callers keep their fallback (a clean cut / punch-in
for jump cuts, ffmpeg ``minterpolate`` for slow motion).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.request

import numpy as np

MODEL_ENV = "VSTUDIO_RIFE_MODEL"
MODEL_NAME = "rife-4.25-mlx"
REPO = "mlx-community/RIFE-4.25"
REV = "6b650eaa5664aab280119511fe944861491aa15e"
FILES = {   # name -> (sha256, size): the same pins as apps/desk/packaging/assets.json group rife-mlx
    "config.json": ("ea2ed44511141528db10b78461073ec2106a64bd7439849b01b56cd83296fa2e", 403),
    "model.safetensors": ("40bd5bdc9b41d22ad2fad79da325dcd68988a90d8b8e8fb7b67ed5eedebccf5f", 22674262),
}
LICENCE = "RIFE 4.25 (Practical-RIFE, MIT, hzwer); MLX weights by mlx-community (MIT)"
SCALES = (16, 8, 4, 2, 1)
PAD = 64


class ModelMissing(RuntimeError):
    """RIFE is not installed here (no MLX, or the weights are not downloaded)."""


def model_dir():
    """The folder with model.safetensors, or None."""
    from .config import MODEL_DIR
    for d in (os.environ.get(MODEL_ENV), os.path.join(MODEL_DIR, MODEL_NAME)):
        if d and os.path.isfile(os.path.join(os.path.expanduser(d), "model.safetensors")):
            return os.path.expanduser(d)
    return None


def _has_mlx():
    if sys.platform != "darwin":
        return False
    try:
        import mlx.core  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def available():
    """True when RIFE can run here (MLX + downloaded weights). ``VSTUDIO_RIFE=0`` turns it off."""
    if os.environ.get("VSTUDIO_RIFE", "1").strip().lower() in ("0", "off", "false", "no"):
        return False
    return model_dir() is not None and _has_mlx()


# ------------------------------------------------------------------ the network (NHWC)
def _build():
    import mlx.core as mx
    import mlx.nn as nn

    def lrelu(x):
        return nn.leaky_relu(x, 0.2)

    def resize(x, f):
        """F.interpolate(bilinear, align_corners=False) by factor f (sizes are exact: inputs padded to 64)."""
        if f == 1:
            return x
        for axis in (1, 2):
            n_in = x.shape[axis]
            n_out = int(round(n_in * f))
            src = (mx.arange(n_out, dtype=mx.float32) + 0.5) * (n_in / n_out) - 0.5
            src = mx.maximum(src, 0.0)
            i0 = mx.floor(src)
            w1 = src - i0
            i0 = mx.clip(i0, 0, n_in - 1).astype(mx.int32)
            i1 = mx.clip(i0 + 1, 0, n_in - 1)
            shape = [1, 1, 1, 1]
            shape[axis] = n_out
            w1 = w1.reshape(shape)
            x = mx.take(x, i0, axis=axis) * (1 - w1) + mx.take(x, i1, axis=axis) * w1
        return x

    grids = {}

    def warp(img, flow):
        """Backward warp (grid_sample bilinear, border, align_corners=True) by a pixel flow [N,H,W,2]."""
        N, H, W, C = img.shape
        if (H, W) not in grids:
            grids[(H, W)] = (mx.arange(W, dtype=mx.float32).reshape(1, 1, W), mx.arange(H, dtype=mx.float32).reshape(1, H, 1))
        gx, gy = grids[(H, W)]
        ix = mx.clip(gx + flow[..., 0], 0, W - 1)
        iy = mx.clip(gy + flow[..., 1], 0, H - 1)
        x0, y0 = mx.floor(ix), mx.floor(iy)
        wx, wy = (ix - x0)[..., None], (iy - y0)[..., None]
        x0i, y0i = x0.astype(mx.int32), y0.astype(mx.int32)
        x1i, y1i = mx.minimum(x0i + 1, W - 1), mx.minimum(y0i + 1, H - 1)
        flat = img.reshape(N, H * W, C)

        def g(yy, xx):
            idx = mx.broadcast_to((yy * W + xx).reshape(N, H * W, 1), (N, H * W, C))
            return mx.take_along_axis(flat, idx, axis=1).reshape(N, H, W, C)
        top = g(y0i, x0i) * (1 - wx) + g(y0i, x1i) * wx
        bot = g(y1i, x0i) * (1 - wx) + g(y1i, x1i) * wx
        return top * (1 - wy) + bot * wy

    def shuffle(x, r=2):
        n, h, w, c = x.shape
        c //= r * r
        x = x.reshape(n, h, w, c, r, r).transpose(0, 1, 4, 2, 5, 3)
        return x.reshape(n, h * r, w * r, c)

    class Conv(nn.Module):
        def __init__(self, i, o, s=1):
            super().__init__()
            self.conv = nn.Conv2d(i, o, 3, stride=s, padding=1)

        def __call__(self, x):
            return lrelu(self.conv(x))

    class ResConv(nn.Module):
        def __init__(self, c):
            super().__init__()
            self.conv = nn.Conv2d(c, c, 3, padding=1)
            self.beta = mx.ones((1, 1, 1, c))

        def __call__(self, x):
            return lrelu(self.conv(x) * self.beta + x)

    class Head(nn.Module):
        def __init__(self):
            super().__init__()
            self.cnn0 = nn.Conv2d(3, 16, 3, stride=2, padding=1)
            self.cnn1 = nn.Conv2d(16, 16, 3, padding=1)
            self.cnn2 = nn.Conv2d(16, 16, 3, padding=1)
            self.cnn3 = nn.ConvTranspose2d(16, 4, 4, stride=2, padding=1)

        def __call__(self, x):
            x = lrelu(self.cnn0(x))
            x = lrelu(self.cnn1(x))
            x = lrelu(self.cnn2(x))
            return self.cnn3(x)

    class IFBlock(nn.Module):
        def __init__(self, i, c):
            super().__init__()
            self.conv0 = [Conv(i, c // 2, 2), Conv(c // 2, c, 2)]
            self.convblock = [ResConv(c) for _ in range(8)]
            self.lastconv = nn.ConvTranspose2d(c, 4 * 13, 4, stride=2, padding=1)

        def __call__(self, x, flow, scale):
            x = resize(x, 1.0 / scale)
            if flow is not None:
                x = mx.concatenate([x, resize(flow, 1.0 / scale) * (1.0 / scale)], axis=-1)
            f = self.conv0[1](self.conv0[0](x))
            for b in self.convblock:
                f = b(f)
            t = resize(shuffle(self.lastconv(f)), scale)
            return t[..., :4] * scale, t[..., 4:5], t[..., 5:]

    class IFNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.block0 = IFBlock(7 + 8, 192)
            self.block1 = IFBlock(28, 128)
            self.block2 = IFBlock(28, 96)
            self.block3 = IFBlock(28, 64)
            self.block4 = IFBlock(28, 32)
            self.encode = Head()

        def __call__(self, img0, img1, t, scales):
            """img0/img1 [N,H,W,3] in 0..1, t [N,1,1,1] -> the frame at t."""
            N, H, W, _ = img0.shape
            ts = mx.broadcast_to(t, (N, H, W, 1))
            f0, f1 = self.encode(img0), self.encode(img1)
            blocks = [self.block0, self.block1, self.block2, self.block3, self.block4]
            flow = mask = feat = None
            w0, w1 = img0, img1
            for i, blk in enumerate(blocks):
                if flow is None:
                    flow, mask, feat = blk(mx.concatenate([img0, img1, f0, f1, ts], axis=-1), None, scales[i])
                else:
                    wf0, wf1 = warp(f0, flow[..., :2]), warp(f1, flow[..., 2:4])
                    fd, mask, feat = blk(mx.concatenate([w0, w1, wf0, wf1, ts, mask, feat], axis=-1), flow, scales[i])
                    flow = flow + fd
                w0, w1 = warp(img0, flow[..., :2]), warp(img1, flow[..., 2:4])
            m = mx.sigmoid(mask)
            return w0 * m + w1 * (1 - m)

    return mx, IFNet


_NET = {}
_LOCK = threading.Lock()       # one MLX graph at a time (segment renders run in threads)


def _net():
    if "net" not in _NET:
        d = model_dir()
        if d is None or not _has_mlx():
            raise ModelMissing("RIFE is not available (needs Apple silicon + the rife-mlx download)")
        mx, IFNet = _build()
        net = IFNet()
        net.load_weights(os.path.join(d, "model.safetensors"), strict=True)
        net.eval()
        mx.eval(net.parameters())
        _NET["net"], _NET["mx"] = net, mx
    return _NET["mx"], _NET["net"]


def auto_scale(h, w):
    """RIFE's pyramid scale: 1.0 up to 1080p, 0.5 above (4K: flow is estimated at half resolution)."""
    return 1.0 if max(h, w) <= 2160 and min(h, w) <= 1200 else 0.5


def _compiled(scales):
    """The network compiled for one pyramid (mx.compile fuses the warps' elementwise work: ~1.6x faster; it retraces
    per input shape, a few seconds once per clip size)."""
    mx, net = _net()
    key = ("c",) + tuple(scales)
    if key not in _NET:
        _NET[key] = mx.compile(lambda A, B, T: net(A, B, T, scales))
    return _NET[key]


def interpolate(a, b, times, scale=None, batch=1):
    """Frames between ``a`` and ``b`` (HxWx3 uint8, same size) at each t in ``times`` (0..1) -> [uint8 frames]."""
    with _LOCK:
        return _interpolate(a, b, times, scale, batch)


def _interpolate(a, b, times, scale, batch):
    mx, _ = _net()
    a, b = np.ascontiguousarray(a), np.ascontiguousarray(b)
    H, W = a.shape[:2]
    s = float(scale or auto_scale(H, W))
    pad = max(PAD, int(round(PAD / s)))
    ph, pw = -(-H // pad) * pad, -(-W // pad) * pad
    P = ((0, 0), (0, ph - H), (0, pw - W), (0, 0))
    A = mx.pad(mx.array(a[None].astype(np.float32) / 255.0), P)
    B = mx.pad(mx.array(b[None].astype(np.float32) / 255.0), P)
    run = _compiled(tuple(x / s for x in SCALES))
    times = [float(t) for t in times]
    out = []
    for k in range(0, len(times), batch):
        tt = times[k:k + batch]
        n = len(tt)
        y = run(mx.broadcast_to(A, (n, ph, pw, 3)) if n > 1 else A, mx.broadcast_to(B, (n, ph, pw, 3)) if n > 1 else B,
                mx.array(np.array(tt, np.float32).reshape(n, 1, 1, 1)))
        y = mx.clip(y[:, :H, :W, :] * 255.0 + 0.5, 0, 255).astype(mx.uint8)
        mx.eval(y)
        out += list(np.array(y))
    return out


def inbetweens(a, b, n, scale=None):
    """``n`` evenly spaced frames strictly between a and b (t = 1/(n+1) .. n/(n+1))."""
    return interpolate(a, b, [(i + 1) / (n + 1) for i in range(n)], scale) if n > 0 else []


# ------------------------------------------------------------------ video helpers
def _ffmpeg():
    from . import media
    return media._resolve(["ffmpeg"])[0]


def frame_size(info):
    """(w, h) of the decoded frames (ffmpeg applies the rotation tag)."""
    w, h = info["w"], info["h"]
    return (h, w) if abs(int(info.get("rotation") or 0)) % 180 == 90 else (w, h)


def read_frames(path, start=None, dur=None, size=None):
    """Decode ``path`` (optionally [start, start+dur)) to RGB uint8 frames. size = (w, h) of the stream."""
    from . import media
    info = media.probe(path)
    w, h = size or frame_size(info)
    cmd = [_ffmpeg(), "-v", "error"] + (["-ss", f"{start:.4f}"] if start else []) + ["-i", path] + \
        (["-t", f"{dur:.4f}"] if dur else []) + ["-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    return list(np.frombuffer(raw[:n * w * h * 3], np.uint8).reshape(n, h, w, 3))


def iter_frames(path, start=None, dur=None):
    """Stream RGB uint8 frames of ``path`` (optionally [start, start+dur)) without holding them all."""
    from . import media
    w, h = frame_size(media.probe(path))
    cmd = [_ffmpeg(), "-v", "error", "-nostdin"] + (["-ss", f"{start:.4f}"] if start else []) + ["-i", path] + \
        (["-t", f"{dur:.4f}"] if dur else []) + ["-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * 3
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.kill()
        p.wait()


def slow_frames(frames, speed, scale=None):
    """Frames (any iterable) played at ``speed`` (< 1) with RIFE in-betweens: output frame k sits at source position
    k * speed (a generator; only two source frames are held). Positions on a source frame reuse it."""
    speed = float(speed)
    if not 0 < speed < 1:
        raise ValueError("slow_frames needs 0 < speed < 1")
    it = iter(frames)
    try:
        f0 = next(it)
    except StopIteration:
        return
    i, k = 0, 0
    for f1 in it:                                    # the interval [i, i + 1)
        ts = []
        while k * speed < i + 1 - 1e-6:
            ts.append(k * speed - i)
            k += 1
        mids = [t for t in ts if t > 1e-4]
        made = iter(interpolate(f0, f1, mids, scale)) if mids else iter(())
        for t in ts:
            yield f0 if t <= 1e-4 else next(made)
        f0, i = f1, i + 1
    if abs(k * speed - i) < 1e-4:
        yield f0


def write_frames(frames, out, fps, crf=14, preset="fast"):
    """Encode RGB uint8 frames (any iterable) to an H.264 yuv420p file (no audio). Returns the frame count."""
    p, n = None, 0
    try:
        for f in frames:
            if p is None:
                h, w = f.shape[:2]
                p = subprocess.Popen([_ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                      "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-", "-c:v", "libx264", "-crf", str(crf),
                                      "-preset", preset, "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
            p.stdin.write(np.ascontiguousarray(f).tobytes())
            n += 1
    finally:
        if p is not None:
            p.stdin.close()
    if p is None or p.wait():
        raise RuntimeError(f"rife: ffmpeg failed writing {out}")
    return n


def needs_interp(src_fps, speed, fps, tol=0.02):
    """True when ``speed`` asks for more frames than the source has at the output rate (30p at 0.5x into 30 fps,
    60p at 0.25x): slow motion that needs in-betweens. 60p at 0.5x into 30 fps does not (every source frame)."""
    return float(src_fps or 0) * float(speed or 1) < float(fps) * (1 - tol)


def _exactly(frames, n):
    """The first ``n`` frames, the last one repeated when there are fewer."""
    last, k = None, 0
    for f in frames:
        if k >= n:
            return
        last, k = f, k + 1
        yield f
    while last is not None and k < n:
        k += 1
        yield last


def slowmo(src, out, start=0.0, end=None, speed=0.5, fps=None, scale=None, crf=14, frames=None):
    """``src`` [start, end) slowed to ``speed`` with RIFE in-betweens, written at ``fps`` (default the source rate) ->
    out (video only; the caller owns audio). Streams: memory stays at a few frames. ``frames``: exactly this many
    output frames (default: the span's length / speed at ``fps``). Returns out."""
    from . import media
    info = media.probe(src)
    sf = float(info.get("fps") or 30)
    of = float(fps or sf)
    step = float(speed) * sf / of                     # source frames per output frame
    dur = (end - start) if end is not None else None
    if step >= 1 - 1e-6:
        raise ValueError(f"rife.slowmo: {speed}x of {sf:g}p at {of:g} fps needs no in-betweens")
    span = dur if dur is not None else max(0.0, float(info["duration"] or 0) - (start or 0.0))
    n = int(frames) if frames else max(1, int(round(span / float(speed) * of)))
    write_frames(_exactly(slow_frames(iter_frames(src, start, dur), step, scale), n), out, of, crf=crf)
    return out


# ------------------------------------------------------------------ fetch (skill users; the desk app downloads itself)
def fetch(dest=None, log=print):
    """Download the pinned weights into ``dest`` (default <cache>/models/rife-4.25-mlx), sha256-checked."""
    from .config import MODEL_DIR
    dest = dest or os.path.join(MODEL_DIR, MODEL_NAME)
    os.makedirs(dest, exist_ok=True)
    for name, (sha, size) in FILES.items():
        p = os.path.join(dest, name)
        if os.path.isfile(p) and os.path.getsize(p) == size and _sha256(p) == sha:
            continue
        url = f"https://huggingface.co/{REPO}/resolve/{REV}/{name}"
        log(f"rife: downloading {url} ({size / 1e6:.1f} MB)")
        tmp = p + ".part"
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        got = _sha256(tmp)
        if got != sha:
            os.remove(tmp)
            raise RuntimeError(f"rife: {name} sha256 {got} != pinned {sha}")
        os.replace(tmp, p)
    return dest


def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _cli(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m vstudio.rife", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="download the pinned RIFE 4.25 MLX weights")
    sub.add_parser("status", help="is RIFE available here")
    s = sub.add_parser("slowmo", help="slow a span with RIFE in-betweens")
    s.add_argument("src")
    s.add_argument("out")
    s.add_argument("--start", type=float, default=0.0)
    s.add_argument("--end", type=float, required=True)
    s.add_argument("--speed", type=float, default=0.5)
    s.add_argument("--fps", type=float)
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        print(fetch())
    elif a.cmd == "status":
        print(json.dumps(dict(available=available(), model=model_dir(), mlx=_has_mlx(), licence=LICENCE)))
    else:
        slowmo(a.src, a.out, a.start, a.end, a.speed, a.fps)
        print(a.out)


if __name__ == "__main__":
    _cli()
