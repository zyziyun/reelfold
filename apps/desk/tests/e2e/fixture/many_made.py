"""Test fixture for All projects' bulk Schedule at scale (real engine): ONE talking-head project made to the end by the
real engine (real_project.py --autopilot: one made clip), then copied N times as past projects - each copy its own
folder (paths in its text files pointed at the copy), registered in VSTUDIO_HOME/projects.json the way the engine
registers its own - so the Studio lists N made videos, Ready to post.

    python many_made.py ROOT N   (VSTUDIO_HOME etc. from the environment) -> prints {n, src, dirs: [first, last]}
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

ROOT, N = sys.argv[1], int(sys.argv[2])
HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = (".mp4", ".mov", ".wav", ".m4a", ".mp3", ".jpg", ".jpeg", ".png", ".webp")
TEXT_EXT = (".json", ".yaml", ".yml", ".md", ".txt", ".srt", ".vtt", ".ass", ".jsonl")
NAMES = ["Weekly tips", "Office hours", "Studio notes", "Q&A", "Behind the edit", "Five-minute lesson"]

out = subprocess.run([sys.executable, os.path.join(HERE, "real_project.py"), os.path.join(ROOT, "src"), "--autopilot",
                      "--name", "Weekly tips"], check=True, capture_output=True, text=True, env=os.environ).stdout
src = json.loads(out.strip().splitlines()[-1])["dir"]
home = os.environ["VSTUDIO_HOME"]
reg_path = os.path.join(home, "projects.json")
reg = json.load(open(reg_path)) if os.path.exists(reg_path) else []
day = datetime.datetime.now() - datetime.timedelta(hours=1)
dirs = []
for k in range(N):
    dst = os.path.join(ROOT, "made", f"m{k:03d}")
    # media hard-linked (never written: 210 copies stay ~30 MB); everything else copied (the run store is written to,
    # the text files' paths are rewritten below)
    shutil.copytree(src, dst, symlinks=True,
                    copy_function=lambda a, b: os.link(a, b) if a.lower().endswith(MEDIA) else shutil.copy2(a, b))
    for dp, _, fs in os.walk(dst):
        for f in fs:
            p = os.path.join(dp, f)
            if f.endswith(TEXT_EXT) and not os.path.islink(p):
                s = open(p, encoding="utf-8", errors="surrogateescape").read()
                if src in s or os.path.realpath(src) in s:
                    s = s.replace(os.path.realpath(src), dst).replace(src, dst)
                    open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
    name = f"{NAMES[k % len(NAMES)]} · ep. {k // len(NAMES) + 1}"
    py = os.path.join(dst, "project.yaml")
    y = open(py, encoding="utf-8").read()
    y = re.sub(r"^name: .*$", lambda m: "name: " + json.dumps(name, ensure_ascii=False), y, count=1, flags=re.M)
    open(py, "w", encoding="utf-8").write(y)
    reg.append(dict(dir=dst, name=name, recipe="talkinghead", series=None, client=None,
                    created=(day - datetime.timedelta(minutes=k)).strftime("%Y-%m-%dT%H:%M:%S")))
    dirs.append(dst)
reg = [r for r in reg if os.path.realpath(r.get("dir", "")) != os.path.realpath(src)]   # only the copies are listed
json.dump(reg, open(reg_path, "w"), ensure_ascii=False, indent=1)
print(json.dumps(dict(n=len(dirs), src=src, dirs=[dirs[0], dirs[-1]])))
