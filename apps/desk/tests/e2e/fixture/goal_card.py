"""A small DJI-like SD card for goal mode's real-engine e2e (goalReal.spec.ts): three stories - an evening by the Space
Needle, a bright noon at Kirkland, the same spot after dark - two short clips each, every clip with its DJI .SRT flight
log (time + GPS), plus a panorama tile folder. Prints {"card": <DCIM path>}.

    python3 goal_card.py <tmp>
"""
import json
import os
import subprocess
import sys

SEATTLE = (47.62050, -122.34930)
KIRKLAND = (47.68150, -122.20870)
# testsrc2 is not used: its colour cycle swings the picture's cast every ~4 s, a "colour flash" the render's flicker
# QC rightly refuses; a hue-turned testsrc is as distinct and moves too
SHOTS = [("20260611200000", "0001", SEATTLE, "testsrc,hue=h=180"), ("20260611200500", "0002", SEATTLE, "smptebars"),
         ("20260612120000", "0003", KIRKLAND, "testsrc"), ("20260612121000", "0004", KIRKLAND, "smptebars"),
         ("20260612124500", "0005", KIRKLAND, "black"), ("20260612125000", "0006", KIRKLAND, "black")]


def srt(path, stamp, lat, lon, n=4):
    out = []
    for k in range(n):
        out.append(f"{k + 1}\n00:00:0{k},000 --> 00:00:0{k},033\n<font size=\"28\">FrameCnt: {k + 1}\n{stamp}.{k:03d}\n"
                   f"[iso: 100] [latitude: {lat + k * 1e-4:.5f}] [longitude: {lon:.5f}] [rel_alt: 80.000 abs_alt: 120.0] </font>\n")
    with open(path, "w") as f:
        f.write("\n".join(out))


def clip(path, src, secs=10):
    src, _, vf = src.partition(",")
    v = f"color=c=black:s=320x180:r=24:d={secs}" if src == "black" else f"{src}=s=320x180:r=24:d={secs}"
    v += f",{vf}" if vf else ""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", v, "-f", "lavfi", "-i",
                    f"anullsrc=r=48000:cl=stereo:d={secs}", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", path], check=True)


def main(tmp):
    card = os.path.join(tmp, "card", "DCIM")
    d = os.path.join(card, "DJI_001")
    os.makedirs(d, exist_ok=True)
    for ts, n, (lat, lon), src in SHOTS:
        stem = os.path.join(d, f"DJI_{ts}_{n}_D")
        clip(stem + ".MP4", src)
        srt(stem + ".SRT", f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}", lat, lon)
    pano = os.path.join(card, "PANORAMA", "001_0007")
    os.makedirs(pano, exist_ok=True)
    from PIL import Image
    for k in range(3):
        Image.new("RGB", (64, 48), (90, 120, 200)).save(os.path.join(pano, f"PANO_{k + 1:04d}.JPG"))
    print(json.dumps(dict(card=card)))


if __name__ == "__main__":
    main(sys.argv[1])
