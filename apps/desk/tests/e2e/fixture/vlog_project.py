"""Test fixture for the vertical-framing e2e: a vlog project from two tiny synthetic DJI-like landscape clips (a
moving disk on a textured ground, a DJI .SRT flight log beside each: Seattle), platforms TikTok + YouTube, run on
autopilot with the REAL engine to the end (no AI account: the post copy is written from the facts by the rules).

    python vlog_project.py ROOT   (VSTUDIO_HOME etc. from the environment) -> {dir, decisions}
"""
import json
import os
import subprocess
import sys

ROOT = sys.argv[1]
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path[:0] = [os.path.join(REPO, "lib")]

from vstudio import media  # noqa: E402
from vstudio.project import autopilot as AP  # noqa: E402
from vstudio.project.core import Project  # noqa: E402

SRT = ("1\n00:00:00,000 --> 00:00:00,033\n<font size=\"28\">FrameCnt: 1\n2026-10-10 18:55:57.457\n[latitude: 47.762948] "
       "[longitude: -122.182302] [rel_alt: 85.200 abs_alt: 105.1] </font>\n")
foot = os.path.join(ROOT, "footage")
os.makedirs(foot, exist_ok=True)
clips = []
for i in range(2):
    p = os.path.join(foot, f"DJI_2026101018555{i}_000{i}_D.MP4")
    # a red disk crossing a green, textured ground (16:9): something to follow
    vf = (f"geq=r='40+30*random(1)':g='{90 + 20 * i}+30*random(1)':b='40+20*random(1)',"
          f"drawbox=x='40+t*90':y=150:w=40:h=40:color=red@1:t=fill")
    subprocess.run([media.ffmpeg_bin(), "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=black:size=480x270:rate=30:duration=4", "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    p], check=True)
    with open(os.path.splitext(p)[0] + ".SRT", "w") as f:
        f.write(SRT)
    clips.append(p)
proj = Project.create(os.path.join(ROOT, "projects", "seattle"), recipe="vlog", name="Seattle red leaves",
                      inputs=dict(footage=clips), params=dict(platforms=["tiktok", "youtube"], preset="ultrafast",
                                                              title="Seattle in Red"))
proj.data["prompt"] = "使用这些视频帮我剪辑成一个西雅图红叶的视频，配个音乐什么的，显得高级一点"
proj.save()
out = Project(proj.dir).run(autopilot=True)
decs = {d["checkpoint"]: d.get("params") for d in AP.decisions(Project(proj.dir))}
print(json.dumps(dict(dir=proj.dir, exit=out.get("exit_code"), decisions=decs), ensure_ascii=False))
