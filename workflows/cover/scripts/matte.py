#!/usr/bin/env python3
"""Matte a single still (speaker photo / video frame) to a transparent RGBA PNG.

Engines (vstudio.matte)
  auto (default)       BiRefNet when downloaded, else MediaPipe.
  birefnet             BiRefNet-lite (MIT) on onnxruntime: any salient subject (people, a boat, a tower), clean hair.
                       First-run download (app asset group matte-birefnet; CLI: python -m vstudio.assets fetch
                       matte-birefnet).
  mediapipe            MediaPipe selfie segmenter (Apache-2.0, vstudio.config.model("selfie_segmenter")),
                       refined with an edge-aware guided filter so hair edges follow the photo. People only.
  rvm (optional)       Robust Video Matting via torch.hub. RVM is **GPL-3.0**: it is NOT vendored here;
                       torch.hub downloads it at runtime into your torch cache, on your machine, under its
                       own licence. Cleaner hair than the default; needs `pip install torch torchvision`.

Usage:
  python3 matte.py face_src.png face_alpha.png [--engine auto|birefnet|mediapipe|rvm] [--crop-bottom 0.1] [--trim]
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))

import argparse

import cv2
import numpy as np

from vstudio.matte import guided, mediapipe_alpha  # noqa: F401  (guided re-exported: older callers import it here)


def matte_mediapipe(bgr, lo=0.25, hi=0.75, radius=None):
    return bgr, mediapipe_alpha(bgr, lo, hi, radius)


def matte_rvm(bgr, warmup=2):
    try:
        import torch
    except ImportError:
        raise SystemExit("--engine rvm needs torch (pip install torch torchvision). RVM itself is GPL-3.0 and is "
                         "downloaded at runtime by torch.hub; it is not part of this repo.")
    print("note: Robust Video Matting (PeterL1n/RobustVideoMatting) is GPL-3.0, fetched by torch.hub at runtime.")
    dev = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    net = torch.hub.load("PeterL1n/RobustVideoMatting", "mobilenetv3").to(dev).eval()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    ten = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(dev)
    rec = [None] * 4
    with torch.no_grad():
        for _ in range(max(1, warmup)):           # RVM is recurrent: warm the state on the same frame
            fgr, pha, *rec = net(ten, *rec, 0.4)
    fg = (fgr.clamp(0, 1)[0].permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
    return cv2.cvtColor(fg, cv2.COLOR_RGB2BGR), pha.clamp(0, 1)[0, 0].cpu().numpy()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src"); ap.add_argument("out", help="RGBA png")
    ap.add_argument("--engine", choices=["auto", "birefnet", "mediapipe", "rvm"], default="auto")
    ap.add_argument("--lo", type=float, default=0.25, help="mediapipe: confidence mapped to alpha 0")
    ap.add_argument("--hi", type=float, default=0.75, help="mediapipe: confidence mapped to alpha 1")
    ap.add_argument("--crop-bottom", type=float, default=0.0,
                    help="drop this fraction of the height from the bottom (burned-in caption band)")
    ap.add_argument("--trim", action="store_true", help="crop to the alpha bounding box (+2%% margin)")
    ap.add_argument("--preview", action="store_true", help="also write <out>.check.png over a grey checker")
    a = ap.parse_args()

    bgr = cv2.imread(a.src)
    if bgr is None:
        raise SystemExit(f"cannot read {a.src}")
    if a.engine == "rvm":
        fg, alpha = matte_rvm(bgr)
    elif a.engine == "mediapipe":
        fg, alpha = matte_mediapipe(bgr, a.lo, a.hi)
    else:
        from vstudio.matte import matte
        fg, alpha, used = matte(bgr, a.engine, log=print)
        print(f"engine: {used}")
    rgba = np.dstack([fg, (alpha * 255).astype(np.uint8)])
    if a.crop_bottom > 0:
        rgba = rgba[: int(rgba.shape[0] * (1 - a.crop_bottom))]
    if a.trim:
        ys, xs = np.nonzero(rgba[..., 3] > 8)
        if len(xs):
            m = int(0.02 * max(rgba.shape[:2]))
            rgba = rgba[max(0, ys.min() - m): ys.max() + m, max(0, xs.min() - m): xs.max() + m]
    cv2.imwrite(a.out, rgba)
    h, w = rgba.shape[:2]
    print(f"{a.out}  {w}x{h}  aspect {w / h:.3f}  (size the template's .face-wrap to this aspect)")
    if a.preview:
        chk = (((np.indices((h, w)) // 24).sum(0) % 2) * 60 + 120).astype(np.float32)[..., None].repeat(3, 2)
        al = rgba[..., 3:4].astype(np.float32) / 255
        cv2.imwrite(str(pathlib.Path(a.out).with_suffix(".check.png")),
                    (rgba[..., :3] * al + chk * (1 - al)).astype(np.uint8))


if __name__ == "__main__":
    main()
