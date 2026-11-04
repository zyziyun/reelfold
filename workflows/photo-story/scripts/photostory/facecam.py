"""Narrator face over a rendered photo story: a small card or a cutout sticker that changes form and place.

    python3 facecam.py spec.py film.mp4 out.mp4

Spec keys
  FACECAM = {unit: (style, [slot, slot, ...]), ...}
      style  circle | round | polaroid | sticker (head-and-shoulders cutout, white outline, grows 85-105 %)
      slots  BR (bottom-right above the captions) | TR | TL | ML; several = it glides between them through the unit
  FACECAM_CROP = (x, y, size)          face square in the recording, default (100, 380, 920) on 1080x1920
  FACECAM_STICKER = (x, y, w, h, height_px)   cutout region and on-screen height, default (100, 380, 880, 1260, 640)

The face video of a voice unit is the clip its narration came from: the unit's voice path with ``.mp4``
(``vo/u07c.wav`` -> ``vo/u07c.mp4``, as own_voice.py writes them), so lips and voice stay in sync.
Show it on opinion beats, not everywhere; scenery stays clean.
"""
import math
import os
import subprocess
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np                                        # noqa: E402

from vstudio import storyfx as S                          # noqa: E402
from photostory.storyrun import ENC, FPS, ff, timeline    # noqa: E402

BOX = 720
CROP = (100, 380, 920)
STICK = (100, 380, 880, 1260, 640)


def frames(path, n, vf, w, h, fmt):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", vf + f",fps={FPS}", "-f", "rawvideo",
                          "-pix_fmt", fmt, "-"], stdout=subprocess.PIPE)
    last = None
    for _ in range(n):
        buf = p.stdout.read(w * h * 3)
        if len(buf) == w * h * 3:
            last = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        yield last
    p.stdout.close()
    p.wait()


def plan(spec_path):
    spec, C, T, units = timeline(spec_path)
    want = dict(getattr(spec, "FACECAM", {}) or {})
    ivs = []
    for name, (style, slots) in want.items():
        u = units.get(name)
        if not u or not u["path"]:
            continue
        face = os.path.splitext(C.path(u["path"]))[0] + ".mp4"
        ivs.append(dict(a=u["start"], b=u["start"] + u["dur"], face=face, style=style, slots=slots, unit=name))
    return spec, C, T.total, sorted(ivs, key=lambda v: v["a"])


def main(spec_path, video, out):
    spec, C, total, ivs = plan(spec_path)
    cx, cy, cs = getattr(spec, "FACECAM_CROP", CROP)
    sx, sy, sw, sh, sth = getattr(spec, "FACECAM_STICKER", STICK)
    stw = int(round(sth * sw / sh))
    slots = S.slots(C.W, C.H, C.SUB_Y0, BOX, top_safe=max(200, C.SAFE[1] + 40))
    track = os.path.splitext(out)[0] + ".track.mov"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{BOX}x{BOX}",
                            "-r", str(FPS), "-i", "-", "-c:v", "qtrle", track], stdin=subprocess.PIPE)
    empty = np.zeros((BOX, BOX, 4), np.uint8).tobytes()
    cmds, fi = [], 0
    for iv in ivs:
        f0, f1 = int(round(iv["a"] * FPS)), int(round(iv["b"] * FPS))
        while fi < f0:
            enc.stdin.write(empty)
            fi += 1
        pts = [slots[s] for s in iv["slots"]]
        span = (f1 - f0) / FPS
        sticker = iv["style"] == "sticker"
        if sticker:
            cut = S.Sticker()
            src = frames(iv["face"], f1 - f0, f"crop={sw}:{sh}:{sx}:{sy},scale={stw}:{sth}:flags=lanczos", stw, sth, "bgr24")
        else:
            src = frames(iv["face"], f1 - f0, f"crop={cs}:{cs}:{cx}:{cy},scale={S.D}:{S.D}:flags=lanczos", S.D, S.D, "rgb24")
        tilt = {"polaroid": -5.0, "round": 2.5, "circle": 0.0, "sticker": -2.0}[iv["style"]]
        for k, fr in enumerate(src):
            t, rem = k / FPS, (f1 - f0 - k) / FPS
            x, y = S.glide(pts, t, span)
            cmds.append((fi / FPS, int(round(x)), int(round(y))))
            sc, al = S.pop(t, rem, grow=(0.85, 1.05) if sticker else None, dur=span)
            canvas = np.zeros((BOX, BOX, 4), np.float32)
            if fr is not None and al > 0.01:
                card = cut(fr) if sticker else S.face_card(fr, iv["style"])
                sway = tilt + 1.2 * math.sin(2 * math.pi * t / 5.0)
                b = S.bob(t)
                S.place(canvas, S.shadow_of(card), BOX / 2 + 3, BOX / 2 + 10 + b, sc, sway)
                S.place(canvas, card, BOX / 2, BOX / 2 + b, sc, sway)
                canvas[..., 3] *= al
            enc.stdin.write(np.clip(canvas, 0, 255).astype(np.uint8).tobytes())
            fi += 1
    while fi < int(math.ceil(total * FPS)):
        enc.stdin.write(empty)
        fi += 1
    enc.stdin.close()
    enc.wait()
    pos = os.path.splitext(out)[0] + ".pos.txt"
    with open(pos, "w") as f:
        last = None
        for t, x, y in cmds:
            if (x, y) != last:
                f.write(f"{t:.4f} [enter] overlay@ov x {x}, [enter] overlay@ov y {y};\n")
                last = (x, y)
    ff(["-i", video, "-i", track, "-filter_complex",
        f"[0:v]sendcmd=f='{pos}'[b];[b][1:v]overlay@ov=x=0:y=0:eval=frame:format=auto:eof_action=pass,format=yuv420p[v]",
        "-map", "[v]", "-map", "0:a?"] + ENC + ["-c:a", "copy", "-movflags", "+faststart", out])
    os.remove(track)
    os.remove(pos)
    print(f"facecam: {len(ivs)} units -> {out}")
    for iv in ivs:
        print(f"  {iv['a']:7.2f}-{iv['b']:7.2f}  {iv['unit']:6s} {iv['style']:8s} {' > '.join(iv['slots'])}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:4])
