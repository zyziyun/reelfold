"""A finished video made "elsewhere" + the footage it was cut from, for the import e2e (importReal.spec.ts): two
synthetic camera clips (DJI_0001 / DJI_0002, 8 s each) and exports/01-city/{youtube,douyin}.mp4 with a cover and a
post.md - all made with ffmpeg. Prints {out, raw} as JSON on the last line."""
import json
import os
import subprocess
import sys


def ff(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


root = os.path.abspath(sys.argv[1])
raw = os.path.join(root, "footage")
out = os.path.join(root, "exports", "01-city")
os.makedirs(raw, exist_ok=True)
os.makedirs(out, exist_ok=True)
srcs = ["mandelbrot=s=640x360:r=30",
        "mandelbrot=s=640x360:r=30:start_x=-1.25066:start_y=0.02012:start_scale=0.05:end_scale=0.00005"]
for k, s in enumerate(srcs):
    ff("-f", "lavfi", "-i", f"{s},format=yuv420p", "-t", "8", "-c:v", "libx264", "-preset", "ultrafast", "-g", "15",
       os.path.join(raw, f"DJI_000{k + 1}.MP4"))
cut = os.path.join(root, "cut.mp4")
ff("-ss", "1", "-t", "3", "-i", os.path.join(raw, "DJI_0001.MP4"), "-ss", "2", "-t", "3", "-i",
   os.path.join(raw, "DJI_0002.MP4"), "-filter_complex",
   "[0:v]setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[v]", "-map", "[v]",
   "-c:v", "libx264", "-preset", "ultrafast", cut)
for name, vf in (("youtube.mp4", "scale=1280:720"), ("douyin.mp4", "crop=203:360:60:0,scale=540:960")):
    ff("-i", cut, "-f", "lavfi", "-t", "6", "-i", "sine=frequency=300:sample_rate=48000", "-vf", vf, "-c:v", "libx264",
       "-preset", "ultrafast", "-c:a", "aac", "-shortest", os.path.join(out, name))
ff("-ss", "1", "-i", os.path.join(out, "youtube.mp4"), "-frames:v", "1", "-vf", "scale=640:-2",
   os.path.join(out, "youtube.cover.jpg"))
with open(os.path.join(out, "post.md"), "w", encoding="utf-8") as f:
    f.write("## youtube\n\nCity lights from above\n\nA night flight.\n\n#city #drone\n\n"
            "## douyin\n\n城市夜景航拍\n\n一次夜航。\n\n#城市 #航拍\n")
print(json.dumps(dict(out=out, raw=raw)))
