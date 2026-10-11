"""Test fixture for the vertical-framing e2e: a vlog project from two tiny synthetic DJI-like landscape clips (a
moving disk on a textured ground, a DJI .SRT flight log beside each: Seattle), platforms TikTok + YouTube, run on
autopilot with the REAL engine to the end (no AI account: the post copy is written from the facts by the rules).

    python vlog_project.py ROOT [--old]   (VSTUDIO_HOME etc. from the environment) -> {dir, decisions}

--old: then made to look like a vlog finished before the framing / copy steps existed (her Seattle project, app
0.2.6): no framing / copy answer, payload or stage row, no shots.json, the exports on a blurred fill with the title as
the whole post.
"""
import json
import os
import subprocess
import sys

ROOT = sys.argv[1]
OLD = "--old" in sys.argv[2:]
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
if OLD:
    import sqlite3
    from vstudio import export as EX
    p = Project(proj.dir)
    for cid in ("framing", "copy"):
        p.data["answers"].pop(cid, None)
        f = os.path.join(p.state_dir, "checkpoints", "main", f"{cid}.json")
        if os.path.exists(f):
            os.remove(f)
    for k in ("reframe", "copy_pick"):
        p.data["overrides"].get("main", {}).pop(k, None)
    p.data["auto"] = ["hook", "filler", "cover"]
    p.save()
    db = sqlite3.connect(os.path.join(p.state_dir, "batch.db"))
    db.execute("DELETE FROM stages WHERE stage IN ('copy', 'cp_framing', 'cp_copy')")
    db.commit()
    db.close()
    work = os.path.join(proj.dir, "items", "main", "work")
    for f in os.listdir(work):
        if f.endswith(".shots.json"):
            os.remove(os.path.join(work, f))
    ex = os.path.join(proj.dir, "items", "main", "exports")
    with open(os.path.join(ex, "manifest.json"), encoding="utf-8") as f:
        master = json.load(f)["master"]
    for f in os.listdir(ex):
        os.remove(os.path.join(ex, f))
    EX.export(master, ["tiktok", "youtube"], ex, post=dict(title="Seattle in Red"), mode="pad-blur", preset="ultrafast")
    decs = {d["checkpoint"]: d.get("params") for d in AP.decisions(Project(proj.dir))}
print(json.dumps(dict(dir=proj.dir, exit=out.get("exit_code"), decisions=decs), ensure_ascii=False))
