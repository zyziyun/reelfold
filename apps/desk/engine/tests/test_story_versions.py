"""A project's made versions as the desk lists them (goal summary, Studio rows, clip page versions, publish board).
2026-10-13, her DJI goal: each photo-story "Music film" showed a striped tile, "None 原尺寸" and no post copy, and its
B站 16:9 version was dropped - the engine listed out/story.mp4 and out/bilibili/story.mp4 with no size or platform."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import outputs as OU  # noqa: E402
from desk_engine import works as WK  # noqa: E402


def _touch(p, text="x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class StoryVersions(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "state", "jobs", "blue-hour-zh"))
        _touch(os.path.join(self.d, "project.yaml"),
               "recipe: photo-story\nparams:\n  platforms: [xiaohongshu:vertical, bilibili]\nitems:\n- id: blue-hour-zh\n")
        out = os.path.join(self.d, "items", "blue-hour-zh", "out")
        self.xhs, self.bili = _touch(os.path.join(out, "story.mp4")), _touch(os.path.join(out, "bilibili", "story.mp4"))
        cov = _touch(os.path.join(out, "cover.png"))
        post = _touch(os.path.join(out, "post.md"), "蓝调时刻｜西雅图\n\n正文\n\n#西雅图 #航拍")
        bpost = _touch(os.path.join(out, "bilibili", "post.md"), "蓝调时刻｜西雅图\n\nB站正文\n\n标签：西雅图，航拍")
        self.eng = {"blue-hour-zh": dict(state="done", files=[
            dict(file=self.xhs, platform=None, orientation=None, w=1080, h=1440, duration=56.2, cover=cov, post=post,
                 platforms=["xiaohongshu:vertical"], posts={"xiaohongshu": post}),
            dict(file=self.bili, platform=None, orientation=None, w=1920, h=1080, duration=56.2,
                 cover=os.path.join(out, "bilibili", "cover.png"), post=bpost, platforms=["bilibili"],
                 posts={"bilibili": bpost})])}

    def clips(self):
        with mock.patch.object(OU, "_engine_item_files", return_value=self.eng):
            return OU.list_clips(dict(kind="project", dir=self.d))

    def test_each_version_has_its_platform_size_cover_and_post(self):
        (c,) = self.clips()
        self.assertEqual([(f["aspect"], f["w"], f["h"], f["platform"], f["platforms"]) for f in c["files"]],
                         [("3:4", 1080, 1440, "xiaohongshu:vertical", ["xiaohongshu:vertical"]),
                          ("16:9", 1920, 1080, "bilibili", ["bilibili"])])
        self.assertTrue(c["cover"].endswith("cover.png"))
        self.assertEqual(c["post"]["title"], "蓝调时刻｜西雅图")
        self.assertEqual(c["duration"], 56.2)
        self.assertEqual(c["posts"]["bilibili"]["body"], "B站正文")
        self.assertEqual(c["posts"]["bilibili"]["tags"], ["西雅图", "航拍"])        # B站's 标签： line
        self.assertEqual(OU._targets(self.d, c["id"]), ["xiaohongshu", "bilibili"])

    def test_a_file_without_platform_facts_never_reads_none(self):
        self.eng["blue-hour-zh"]["files"] = [dict(file=self.xhs, platform=None, orientation=None)]
        (c,) = self.clips()
        self.assertIsNone(c["files"][0]["platform"])
        self.assertEqual(OU._file_row(self.xhs, dict(platform="youtube"))["platform"], "youtube")

    def test_two_files_of_one_canvas_keep_both_platforms(self):
        self.eng["blue-hour-zh"]["files"][1].update(w=1080, h=1440, platforms=["douyin"])
        (c,) = self.clips()
        self.assertEqual(len(c["files"]), 1)
        self.assertEqual(c["files"][0]["platforms"], ["xiaohongshu:vertical", "douyin"])

    def test_tag_line(self):
        self.assertEqual(WK.parse_post_single("T\n\nbody\n\n标签：a，b、c")["tags"], ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
