"""Test fixture for the goal summary of photo stories (2026-10-13, her DJI goal: every "Music film" showed a striped tile,
"None 原尺寸" and no post copy). Two goal videos, each made as goal mode makes a photo story - an English project for
YouTube and its 中文 sibling for 小红书 3:4 + B站 16:9 - laid out as the photo-story recipe leaves them (out/story.mp4 is
the first platform's, out/<platform>/ each other one's, each with its cover and post.md), and the goal record that
links them. The second video's 中文 project has no B站 version (its platforms stage never made it): the summary says
"not made" and offers Make. Tiny synthetic videos; nothing is rendered by the recipe (no AI writes a spec here).

    python photo_story_pair.py ROOT DESK_DATA_DIR   (VSTUDIO_HOME etc. from the environment) -> prints {goal, videos}
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

from vstudio.batch.store import Store  # noqa: E402
from vstudio.project.core import Project  # noqa: E402


def video(path, w, h, hue=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=30:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-vf", f"hue=h={hue}", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path], check=True)


def cover(path, w, h, hue=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}", "-vf",
                    f"hue=h={hue}", "-frames:v", "1", path], check=True)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def project(name, title, item, platforms, versions, hue):
    p = Project.create(os.path.join(ROOT, "projects", name), recipe="photo-story", name=title,
                       items=[dict(id=item, params=dict(title=title))], params=dict(platforms=platforms, mode="music"))
    p.plan()
    out = os.path.join(p.dir, "items", item, "out")
    for sub, (w, h), post in versions:
        d = os.path.join(out, sub) if sub else out
        video(os.path.join(d, "story.mp4"), w, h, hue)
        cover(os.path.join(d, "cover.png"), w, h, hue)
        write(os.path.join(d, "post.md"), post)
    write(os.path.join(out, "subtitles.srt"), "1\n00:00:00,000 --> 00:00:02,000\nBlue hour\n")
    st = Store(p.state_dir)
    try:
        for j in st.jobs():
            st.set_job(j["id"], state="done")
    finally:
        st.close()
    return p


def item_id(d):  # a project's history id: desk_engine.common.batch_id of its run store (<dir>/state)
    return hashlib.sha1(os.path.realpath(os.path.join(d, "state")).encode()).hexdigest()[:12]


EN_POST = "{t} — a quiet drone film over Seattle\n\nSunset to blue hour over the water, a slow music bed.\n\n#seattle #drone"
ZH_POST = "{t}｜西雅图航拍\n\n日落之后的半小时，跟着光线走。\n\n#西雅图 #航拍"
BILI_POST = "{t}｜西雅图航拍\n\n日落之后的半小时（B站版）。\n\n标签：西雅图，航拍"
now = time.time()
vids, out = [], {}
for k, (vid, en_t, zh_t, bili) in enumerate((("v1", "Blue Hour at Shilshole Bay", "蓝调时刻的希尔斯霍尔湾", True),
                                              ("v2", "Trains by the Bay", "海湾边的火车", False))):
    en = project(f"{vid}-en", f"{en_t} (English)", f"{vid}-en", ["youtube"],
                 [(None, (1920, 1080), EN_POST.format(t=en_t))], k * 60)
    zh_versions = [(None, (1080, 1440), ZH_POST.format(t=zh_t))]
    if bili:
        zh_versions.append(("bilibili", (1920, 1080), BILI_POST.format(t=zh_t)))
    zh = project(f"{vid}-zh", f"{zh_t} (中文)", f"{vid}-zh", ["xiaohongshu:vertical", "bilibili"], zh_versions, k * 60)
    ps = [dict(dir=en.dir, name=f"{en_t} (English)", item=item_id(en.dir), lang="en"),
          dict(dir=zh.dir, name=f"{zh_t} (中文)", item=item_id(zh.dir), lang="zh")]
    vids.append(dict(id=vid, title=en_t, title_zh=zh_t, kind="film", length_s=60, clips=3, stories=["s1"],
                     platforms=["youtube", "xiaohongshu", "bilibili"], request=en_t, state="made",
                     projects=[{x: p[x] for x in ("dir", "name", "item")} for p in ps],
                     versions=[dict(item=p["item"], dir=p["dir"], name=p["name"], lang=p["lang"], state="made")
                               for p in ps],
                     started=now - 60, finished=now, progress=1.0))
    out[vid] = dict(en=ps[0]["item"], zh=ps[1]["item"])

gid = hashlib.sha1(ROOT.encode()).hexdigest()[:12]
goal = dict(id=gid, prompt="Make videos from my DJI card for YouTube, 小红书 and B站", inputs=[os.path.join(ROOT, "media")],
            platforms=["youtube", "xiaohongshu", "bilibili"], lang="en", mode="autopilot", state="done",
            created=now - 120, updated=now, approved=now - 100, finished=now, videos=vids)
os.makedirs(os.path.join(DATA, "goals"), exist_ok=True)
with open(os.path.join(DATA, "goals", f"{gid}.json"), "w", encoding="utf-8") as f:
    json.dump(goal, f, ensure_ascii=False)
print(json.dumps(dict(goal=gid, videos=out), ensure_ascii=False))
