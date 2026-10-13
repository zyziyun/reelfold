"""Real-ESRGAN (compact ``realesr-general-x4v3``, BSD-3-Clause) for stills: a cover frame / crop smaller than the
cover canvas is upscaled x4 and blended with a bicubic resize (60 % ESRGAN / 40 % bicubic: pure ESRGAN reads as
plastic skin - the kept recipe of ``workflows/ai-video/scripts/upscale.py``, which shares this network).

    from vstudio import upscale as U
    U.upscale_to(pil_img, (1280, 720))      # -> (PIL, "esrgan-mlx" | "esrgan-torch" | "lanczos")

Backends, no torch needed: MLX on Apple silicon (the bundled runtime), torch when installed; otherwise a Lanczos
resize (said in the returned label). Weights: ``VSTUDIO_ESRGAN_WEIGHTS`` (app asset group ``upscale-esrgan``) or
``<cache>/models/realesrgan/realesr-general-x4v3.pth``; read with ``vstudio.ptload`` (no torch, no pickle code).
"""
from functools import lru_cache

import numpy as np

ESRGAN_ENV = "VSTUDIO_ESRGAN_WEIGHTS"
ESRGAN_DIR = "realesrgan"
ESRGAN_FILE = "realesr-general-x4v3.pth"
MIX = 0.6
SCALE = 4
TILE = 384               # input tile (px) with a 16 px overlap: bounded memory for big frames


def weights_path():
    import os

    from .config import optional_asset
    p = optional_asset(ESRGAN_ENV, ESRGAN_DIR, names=(ESRGAN_FILE,))
    return p if p and os.path.isfile(p) else None


@lru_cache(maxsize=1)
def _weights(path):
    from .ptload import load_state_dict
    sd = load_state_dict(path)
    sd = sd.get("params", sd)
    n = sum(1 for k in sd if k.endswith(".weight") and sd[k].ndim == 4)
    return sd, n


def _backend():
    import importlib.util
    import platform
    if platform.system() == "Darwin" and platform.machine() == "arm64" and importlib.util.find_spec("mlx"):
        return "mlx"
    if importlib.util.find_spec("torch"):
        return "torch"
    return None


def _run_mlx(x, sd, n_conv):
    """x: HxWx3 float32 0..1 -> (4H)x(4W)x3. SRVGGNetCompact: conv-PReLU x (n-1), conv, pixel shuffle + nearest."""
    import mlx.core as mx
    h = mx.array(x[None])
    keys = sorted({int(k.split(".")[1]) for k in sd}, key=int)
    for i in keys:
        w, b = sd.get(f"body.{i}.weight"), sd.get(f"body.{i}.bias")
        if w is not None and w.ndim == 4:                       # conv: OIHW -> OHWI
            h = mx.conv2d(h, mx.array(w.transpose(0, 2, 3, 1)), padding=1) + mx.array(b)
        elif w is not None:                                     # PReLU (per channel)
            a = mx.array(w.reshape(1, 1, 1, -1))
            h = mx.maximum(h, 0) + a * mx.minimum(h, 0)
    _, H, W, C = h.shape
    r = SCALE
    h = h.reshape(1, H, W, C // (r * r), r, r).transpose(0, 1, 4, 2, 5, 3).reshape(1, H * r, W * r, C // (r * r))
    base = mx.repeat(mx.repeat(mx.array(x[None]), r, axis=1), r, axis=2)
    out = h + base
    mx.eval(out)
    return np.array(out[0])


def _run_torch(x, sd, n_conv):
    import torch
    import torch.nn.functional as F
    t = torch.from_numpy(x.transpose(2, 0, 1)[None].copy())
    keys = sorted({int(k.split(".")[1]) for k in sd}, key=int)
    with torch.no_grad():
        h = t
        for i in keys:
            w, b = sd.get(f"body.{i}.weight"), sd.get(f"body.{i}.bias")
            if w is not None and w.ndim == 4:
                h = F.conv2d(h, torch.from_numpy(w), torch.from_numpy(b), padding=1)
            elif w is not None:
                h = F.prelu(h, torch.from_numpy(w))
        h = F.pixel_shuffle(h, SCALE) + F.interpolate(t, scale_factor=SCALE, mode="nearest")
    return h[0].numpy().transpose(1, 2, 0)


def esrgan_x4(rgb, path=None, backend=None):
    """uint8 RGB HxWx3 -> float32 RGB (4H)x(4W)x3 0..1, tiled. Raises when no weights / backend."""
    path = path or weights_path()
    if not path:
        raise FileNotFoundError("Real-ESRGAN weights are not downloaded (asset group upscale-esrgan)")
    be = backend or _backend()
    if be is None:
        raise RuntimeError("Real-ESRGAN needs MLX (Apple silicon) or torch")
    sd, n = _weights(path)
    run = _run_mlx if be == "mlx" else _run_torch
    x = rgb.astype(np.float32) / 255.0
    H, W = x.shape[:2]
    out = np.zeros((H * SCALE, W * SCALE, 3), np.float32)
    pad = 16
    for y0 in range(0, H, TILE):
        for x0 in range(0, W, TILE):
            ya, xa = max(0, y0 - pad), max(0, x0 - pad)
            yb, xb = min(H, y0 + TILE + pad), min(W, x0 + TILE + pad)
            o = run(x[ya:yb, xa:xb], sd, n)
            oy, ox = (y0 - ya) * SCALE, (x0 - xa) * SCALE
            th, tw = (min(H, y0 + TILE) - y0) * SCALE, (min(W, x0 + TILE) - x0) * SCALE
            out[y0 * SCALE:y0 * SCALE + th, x0 * SCALE:x0 * SCALE + tw] = o[oy:oy + th, ox:ox + tw]
    return np.clip(out, 0, 1)


def upscale_to(img, size, mix=MIX, log=None):
    """PIL image -> (PIL RGB at least ``size`` (w, h) on both axes, keeping the aspect; label of what ran).
    Real-ESRGAN x4 (blended ``mix`` with bicubic) when the image is smaller than ``size``; Lanczos otherwise or
    when ESRGAN cannot run here."""
    from PIL import Image
    im = img.convert("RGB")
    s = max(size[0] / im.width, size[1] / im.height)
    if s <= 1.0:
        return im, "none"
    tw, th = int(round(im.width * s)), int(round(im.height * s))
    try:
        be = _backend()
        y = esrgan_x4(np.asarray(im), backend=be)
        sr = Image.fromarray((y * 255 + 0.5).astype(np.uint8)).resize((tw, th), Image.LANCZOS)
        bic = im.resize((tw, th), Image.BICUBIC)
        out = Image.blend(bic, sr, mix)
        return out, f"esrgan-{be}"
    except Exception as e:  # noqa: BLE001  (no weights / backend: a clean resize, said in the label)
        if log:
            log(f"upscale: Real-ESRGAN unavailable ({str(e)[:100]}); Lanczos")
        return im.resize((tw, th), Image.LANCZOS), "lanczos"
