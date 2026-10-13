"""Test fixture for the clip page's versions: one goal video made in two languages, as goal mode makes it - an English
project for YouTube / TikTok and its 中文 sibling for 小红书 / B站 - travel vlogs on tiny synthetic clips (no audio, no
speech), made to the end by the REAL engine (the vlog recipe on autopilot, no AI account), and the goal record that
links them (the desk's goal store, what goal mode writes once both are made).

    python vlog_lang_pair.py ROOT DESK_DATA_DIR   (VSTUDIO_HOME etc. from the environment) -> prints {en, zh, goal}
"""
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT, DATA = sys.argv[1], sys.argv[2]
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path[:0] = [os.path.join(REPO, "lib")]

from vstudio.project.core import Project  # noqa: E402


def footage(folder, secs=6):
    os.makedirs(folder, exist_ok=True)
    out = []
    for i in range(3):
        p = os.path.join(folder, f"DJI_000{i}_D.MP4")
        if not os.path.exists(p):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            f"testsrc=size=480x270:rate=30:duration={secs}", "-vf", f"hue=h={i * 40}", "-c:v",
                            "libx264", "-pix_fmt", "yuv420p", p], check=True)
        out.append(p)
    return out


def make(name, title, platforms, lang, clips):
    p = Project.create(os.path.join(ROOT, "projects", name), recipe="vlog", name=title, inputs=dict(footage=clips),
                       params=dict(platforms=platforms, preset="ultrafast", title=title))
    p.data["prompt"] = "Cut these into a calm red-leaves film with some music"
    p.data["autopilot"] = dict(on=True, spend_cap=0.0, judge=False, ask=[], lang=lang)
    p.save()
    r = p.run(autopilot=True)
    return p, r


def item_id(d):  # a project's history id: desk_engine.common.batch_id of its run store (<dir>/state)
    return hashlib.sha1(os.path.realpath(os.path.join(d, "state")).encode()).hexdigest()[:12]


clips = footage(os.path.join(ROOT, "media"))
out = {}
projects = []
for key, title, pfs, lang in (("en", "Red leaves (English)", ["youtube", "tiktok"], "en"),
                              ("zh", "红叶 (中文)", ["xiaohongshu", "bilibili"], "zh")):
    p, r = make(key, title, pfs, lang, clips)
    out[key] = dict(dir=p.dir, status=r["status"], item=item_id(p.dir))
    projects.append(dict(dir=p.dir, name=title, item=item_id(p.dir), lang=lang))

now = time.time()
gid = hashlib.sha1(ROOT.encode()).hexdigest()[:12]
video = dict(id="v1", title="Red leaves", title_zh="红叶", kind="vlog", length_s=15, clips=3, stories=["s1"],
             platforms=["youtube", "tiktok", "xiaohongshu", "bilibili"], request="Red leaves", state="made",
             projects=[{k: x[k] for k in ("dir", "name", "item")} for x in projects],
             versions=[dict(item=x["item"], dir=x["dir"], name=x["name"], lang=x["lang"], state="made") for x in projects],
             started=now - 60, finished=now, progress=1.0)
goal = dict(id=gid, prompt="Make videos from my card, in English and Chinese", inputs=[os.path.join(ROOT, "media")],
            platforms=video["platforms"], lang="en", mode="autopilot", state="done", created=now - 120, updated=now,
            approved=now - 100, finished=now, videos=[video])
os.makedirs(os.path.join(DATA, "goals"), exist_ok=True)
with open(os.path.join(DATA, "goals", f"{gid}.json"), "w", encoding="utf-8") as f:
    json.dump(goal, f, ensure_ascii=False)
out["goal"] = gid
print(json.dumps(out, ensure_ascii=False))
