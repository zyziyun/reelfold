"""Test fixture for 「Edit the collection」 (goalEdit.spec.ts): the made group of photo_story_pair.py (two videos, each an
English + a 中文 project) turned into what her DJI goal looks like after it was made - the survey's plan document
(three stories of real tiny clips, each clip with its survey frame), her words asking for about 4 videos (at least 3)
so the group is short, Ask-me-first, and the first video's cut playing two clips of its story (its edit list).

    python goal_edit.py ROOT DESK_DATA_DIR   (VSTUDIO_HOME / VSTUDIO_CACHE from the environment) -> {goal, videos}
"""
import json
import os
import subprocess
import sys

ROOT, DATA = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
sys.path[:0] = [os.path.join(REPO, "lib")]

from vstudio.intake import goal as G  # noqa: E402

fx = json.loads(subprocess.run([sys.executable, os.path.join(HERE, "photo_story_pair.py"), ROOT, DATA], check=True,
                               capture_output=True, text=True).stdout.strip().splitlines()[-1])
card = os.path.join(ROOT, "card", "DCIM", "DJI_001")
os.makedirs(card, exist_ok=True)


def clip(path, hue):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=2",
                    "-vf", f"hue=h={hue}", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path],
                   check=True)
    frame = G._frame_cache(path)                 # the survey's frame of the clip (what the re-cut shows)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-frames:v", "1", frame], check=True)


stories, k = [], 0
for sid, place, n, day in (("s1", "Shilshole Bay", 4, "2026-06-22"), ("s2", "Elliott Bay", 3, "2026-06-23"),
                           ("s3", "Coeur d'Alene", 3, "2026-06-24")):
    paths = []
    for j in range(n):
        p = os.path.join(card, f"DJI_{day.replace('-', '')}20{j:02d}00_{k:04d}_D.MP4")
        clip(p, k * 35)
        paths.append(p)
        k += 1
    stories.append(dict(id=sid, place=dict(en=place, zh=place, km=1.0), date=day, start=f"{day} 20:00:00",
                        end=f"{day} 20:30:00", time_of_day="evening", videos=n, photos=0, panoramas=0,
                        seconds=30.0 * n, aerial=True, vertical=0, light=0.4, geo=None, clips=paths,
                        clip_secs=[30.0] * n, stills=[], panorama_dirs=[], thumbs=[G._frame_cache(paths[0])],
                        folder="DJI_001", short_clips=0, sheet=None))
by = {s["id"]: s for s in stories}

gpath = os.path.join(DATA, "goals", f"{fx['goal']}.json")
with open(gpath, encoding="utf-8") as f:
    goal = json.load(f)
vids = []
for v, sid in zip(goal["videos"], ("s1", "s2")):
    d = G._finish_video(dict(id=v["id"], title=v["title"], title_zh=v["title_zh"], kind="film", stories=[sid],
                             brief="b", theme="Music and a few short lines", why="w",
                             platforms=["youtube", "xiaohongshu", "bilibili"]), by, ["youtube", "xiaohongshu", "bilibili"])
    v.update(stories=[sid], inputs=d["inputs"], request=d["request"])
    vids.append(d)
# the first video's English cut plays clips 1 and 2 of its story (its builder's edit list)
s1 = by["s1"]["clips"]
edl = os.path.join(goal["videos"][0]["projects"][0]["dir"], "items", "v1-en", "work", "story.edl.json")
os.makedirs(os.path.dirname(edl), exist_ok=True)
with open(edl, "w") as f:
    json.dump(dict(version=1, builder="photo-story", duration=6.0, shots=[
        dict(i=0, t0=0, t1=2, src=s1[0], kind="video", src_in=0.2, src_out=1.8),
        dict(i=1, t0=2, t1=4, src=s1[1], kind="video", src_in=0.1, src_out=1.9)]), f)
goal.update(prompt="用 DJI 卡里的素材做 4 条左右，最少 3 条，YouTube、小红书和 B站", mode="ask", count=None)
with open(gpath, "w", encoding="utf-8") as f:
    json.dump(goal, f, ensure_ascii=False)
doc = dict(kind=G.KIND, version=1, id=fx["goal"], prompt=goal["prompt"], inputs=[os.path.dirname(card)], ui_lang="en",
           platforms=["youtube", "xiaohongshu", "bilibili"], survey=dict(stories=stories, totals={}, unused={}),
           videos=vids, planner=dict(provider="none", fallback=True))
with open(os.path.join(DATA, "goals", f"{fx['goal']}.plan.json"), "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False)
print(json.dumps(dict(fx, card=card), ensure_ascii=False))
