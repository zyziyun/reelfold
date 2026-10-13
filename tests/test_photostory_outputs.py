"""A photo story's made versions as every reader lists them (outputs.item_files / output list: the desk's goal summary,
Studio rows, the clip page's versions and the publish board). 2026-10-13, her DJI goal: every "Music film" showed a
striped tile, "None 原尺寸" and no post copy - the collector listed out/story.mp4 and out/bilibili/story.mp4 with no
platform, size, cover or post, and the second one (same file name) was lost. Tiny synthetic videos, no AI."""
import os
import shutil
import subprocess

import pytest

from vstudio.project import outputs as O
from vstudio.project.adapters import common as CM
from vstudio.project.adapters import photostory as PS
from vstudio.project.core import Project

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("HOME", str(tmp_path / "userhome"))


def _video(path, w, h, dur=1.5):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=30:duration={dur}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path], check=True)


def _write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _story(tmp_path, platforms, name="p", item="blue-hour-zh"):
    p = Project.create(str(tmp_path / name), recipe="photo-story", items=[dict(id=item, params=dict(title="蓝调时刻"))],
                       params=dict(platforms=platforms, mode="music"))
    p.plan()
    return p, os.path.join(p.dir, "items", item, "out")


def _job(p):
    from vstudio.batch.store import Store
    st = Store(p.state_dir)
    try:
        return st.jobs()[0]
    finally:
        st.close()


def test_each_platform_version_with_its_size_cover_and_post(tmp_path):
    """小红书 3:4 in out/, B站 16:9 in out/bilibili/: two versions, each for its platform, with its own cover / post."""
    p, out = _story(tmp_path, ["xiaohongshu:vertical", "bilibili"])
    _video(os.path.join(out, "story.mp4"), 300, 400)
    _video(os.path.join(out, "bilibili", "story.mp4"), 320, 180)
    for d in (out, os.path.join(out, "bilibili")):
        _write(os.path.join(d, "cover.png"))
        _write(os.path.join(d, "post.md"), "蓝调时刻\n\n正文\n\n#西雅图")
    _write(os.path.join(out, "subtitles.srt"))
    ents = PS.collect(p, _job(p), {})
    vids = [e for e in ents if e["kind"] == "video"]
    assert [e["platforms"] for e in vids] == [["xiaohongshu:vertical"], ["bilibili"]]
    xhs, bili = vids
    assert (xhs["w"], xhs["h"]) == (300, 400) and (bili["w"], bili["h"]) == (320, 180)
    assert xhs["duration"] > 1 and xhs["fps"] == 30
    assert xhs["cover"] == os.path.join(out, "cover.png") and bili["cover"] == os.path.join(out, "bilibili", "cover.png")
    assert bili["posts"] == {"bilibili": os.path.join(out, "bilibili", "post.md")}
    assert xhs["platform"] is None                       # the output's id still reads the file name (her edit docs)
    rest = [os.path.relpath(e["file"], out) for e in ents if e["kind"] != "video"]
    assert "subtitles.srt" in rest and "post.md" not in rest and "cover.png" not in rest
    # every reader: both files, distinct ids (they share a file name), the primary's id unchanged
    files = O.item_files(p.dir)["blue-hour-zh"]["files"]
    assert [f["platforms"] for f in files] == [["xiaohongshu:vertical"], ["bilibili"]]
    assert [o["id"] for o in O.list_outputs(p.dir)["outputs"]] == ["blue-hour-zh/story.mp4",
                                                                   "blue-hour-zh/bilibili-story.mp4"]
    # an export names them by platform, side files by their video's
    ex = p.export(out_dir=str(tmp_path / "ex"), include_unapproved=True)
    names = sorted(os.path.basename(e["file"]) for e in ex["entries"])
    assert "xiaohongshu-vertical.mp4" in names and "bilibili.mp4" in names


def test_a_platform_on_the_first_canvas_shares_the_video_and_a_missing_one_is_not_listed(tmp_path):
    p, out = _story(tmp_path, ["youtube", "bilibili", "xiaohongshu:vertical"], item="blue-hour-en")
    _video(os.path.join(out, "story.mp4"), 320, 180)
    _write(os.path.join(out, "post.md"), "Blue Hour\n\nbody")
    _write(os.path.join(out, "bilibili", "post.md"), "蓝调\n\n正文")          # B站: the same 16:9 video, its own post
    vids = [e for e in PS.collect(p, _job(p), {}) if e["kind"] == "video"]
    assert len(vids) == 1                                # 小红书 3:4 was never rendered: not made, not listed
    assert vids[0]["platforms"] == ["youtube", "bilibili"]
    assert set(vids[0]["posts"]) == {"youtube", "bilibili"}


def test_any_recipe_video_carries_its_facts_and_the_planned_platforms_on_its_canvas(tmp_path):
    """collect_files (launch kit, promo recut, slides...): frame facts, the planned platforms of its shape, the cover
    and post beside it - never a bare path the desk shows as "None 原尺寸"."""
    p, out = _story(tmp_path, ["douyin", "youtube"])
    _video(os.path.join(out, "story.mp4"), 180, 320)
    _write(os.path.join(out, "cover.png"))
    (e,) = [x for x in CM.collect_files(p, _job(p), {}) if x["kind"] == "video"]
    assert (e["w"], e["h"]) == (180, 320) and e["platforms"] == ["douyin"]
    assert e["cover"] == os.path.join(out, "cover.png") and e["post"] is None
