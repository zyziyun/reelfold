#!/usr/bin/env python3
"""Upscale cheap draft takes (e.g. Seedance 480p 样片) to the delivery size locally instead of paying for an upgrade.

    python3 upscale.py takes/u02_v1.mp4 takes/u02_v1_1080.mp4                         # ffmpeg lanczos + grain
    python3 upscale.py takes/u02_v1.mp4 out.mp4 --weights ~/models/realesr-general-x4v3.pth   # Real-ESRGAN mix

Sessions: upgrading drafts in the web UI cost ~7x the draft price (~64 vs ~9 credits/s), so the drafts were
upscaled locally. Pure ESRGAN gives plastic skin; the kept recipe blends 60 % ESRGAN with 40 % bicubic and adds
light temporal grain (keeps pores/freckles). Weights: Real-ESRGAN realesr-general-x4v3 (BSD-3-Clause; the app's asset group upscale-esrgan, or
`python -m vstudio.assets fetch upscale-esrgan`). --weights runs on MLX (Apple silicon) or torch via vstudio.upscale;
without it the ffmpeg path runs anywhere.
"""
import argparse
import os
import subprocess
import sys

import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))

from vstudio import media  # noqa: E402


def ffmpeg_upscale(src, dst, w=1080, h=1920, fps=30, grain=4):
    vf = (f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},"
          f"unsharp=5:5:0.4:5:5:0.0,noise=alls={grain}:allf=t,setsar=1")
    media.run(["ffmpeg", "-y", "-i", src, "-vf", vf, "-map", "0:v", "-map", "0:a?", "-c:v", "libx264", "-crf", "14",
               "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy", dst])
    return dst


def esrgan_upscale(src, dst, weights, w=1080, h=1920, fps=30, mix=0.6, grain=4):
    """Real-ESRGAN x4 per frame (``vstudio.upscale``: the same network as the cover upscaler; MLX on Apple silicon,
    torch elsewhere, no torch needed to read the weights), resized to w x h and blended ``mix`` with bicubic."""
    import numpy as np
    from PIL import Image

    from vstudio import upscale as U
    info = media.probe(src)
    wi, hi = info["w"], info["h"]
    tmp = dst + ".video.mp4"
    dec = subprocess.Popen([media.ffmpeg_bin(), "-v", "error", "-i", src, "-vf", f"fps={fps}", "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen([media.ffmpeg_bin(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-vf", f"noise=alls={grain}:allf=t",
                            "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p", tmp],
                           stdin=subprocess.PIPE)
    fb = wi * hi * 3
    path = os.path.expanduser(weights)
    while True:
        buf = dec.stdout.read(fb)
        if len(buf) < fb:
            break
        x = np.frombuffer(buf, np.uint8).reshape(hi, wi, 3)
        sr = Image.fromarray((U.esrgan_x4(x, path) * 255 + 0.5).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        base = Image.fromarray(x).resize((w, h), Image.BICUBIC)   # aspect: caller passes matching w/h
        enc.stdin.write(Image.blend(base, sr, mix).tobytes())
    enc.stdin.close()
    enc.wait()
    dec.wait()
    media.run(["ffmpeg", "-y", "-i", tmp, "-i", src, "-map", "0:v", "-map", "1:a?", "-c:v", "copy", "-c:a", "copy",
               "-shortest", dst])
    os.remove(tmp)
    return dst


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--size", default="1080x1920")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--weights", help="realesr-general-x4v3.pth (optional; MLX or torch)")
    ap.add_argument("--mix", type=float, default=0.6, help="ESRGAN share (rest bicubic) - lower = less plastic")
    ap.add_argument("--grain", type=int, default=4)
    a = ap.parse_args(argv)
    w, h = map(int, a.size.lower().split("x"))
    if a.weights:
        esrgan_upscale(a.src, a.dst, a.weights, w, h, a.fps, a.mix, a.grain)
    else:
        ffmpeg_upscale(a.src, a.dst, w, h, a.fps, a.grain)
    print(a.dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
