"""The project page (2026-10-11, her finished "Seattle red leaves" vlog that still read "Not started"): a project whose
recipe exports under ``items/<item>/exports`` (vlog, explainer, polish, photo-story...) is made like a batch one - the
clip list, the Ready count, the cover / thumbnail and the editor all read the engine's collect (one source); the run's
pieces (stage ``wip`` files, finished previews) come in recipe order; a project-level ask (pause, the music, the cover,
cut it again) is answered at once with the real controls. A REAL vlog run on tiny synthetic clips (no audio, no AI)."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import outputs as OU  # noqa: E402
from desk_engine import projask as PA  # noqa: E402
from desk_engine.common import EventBus, Registry  # noqa: E402
from desk_engine.history import History  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg"))


def footage(d, n=3, secs=4):
    out = []
    for i in range(n):
        p = os.path.join(d, f"DJI_000{i}_D.MP4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"testsrc2=size=320x180:rate=30:duration={secs}", "-vf", f"hue=h={i * 40}", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", p], check=True)
        out.append(p)
    return out


def _stage_logs(d):
    """The tail of each stage's run.log (what a failed run says, in the assertion)."""
    out = []
    for root, _dirs, files in os.walk(os.path.join(d, "state", "jobs")):
        if "run.log" in files:
            with open(os.path.join(root, "run.log"), encoding="utf-8", errors="replace") as f:
                out.append(f"--- {os.path.relpath(root, d)}\n{f.read()[-3000:]}")
    return "\n".join(out)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not installed")
class FinishedVlogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="pp-")
        cls.env = mock.patch.dict(os.environ, {"VSTUDIO_HOME": os.path.join(cls.root, "home"),
                                               "VSTUDIO_CACHE": os.path.join(cls.root, "cache"),
                                               "VSTUDIO_MUSIC_DIRS": "", "VSTUDIO_LLM_PROVIDER": "none"})
        cls.env.start()
        cls.addClassCleanup(cls.env.stop)        # also when the run below fails (tearDownClass would not run)
        from vstudio.project.core import Project
        media = os.path.join(cls.root, "media")
        os.makedirs(media)
        clips = footage(media)
        p = Project.create(os.path.join(cls.root, "projects", "vlog"), recipe="vlog", inputs=dict(footage=clips),
                           params=dict(platforms=["youtube", "tiktok"], preset="ultrafast", title="Red leaves"))
        p.data["prompt"] = "a calm red leaves film with music"
        p.save()
        r = p.run(autopilot=True)
        assert r["exit_code"] == 0, (r, _stage_logs(p.dir))
        cls.dir = p.dir

    def setUp(self):
        data = os.path.join(self.root, f"desk-{self._testMethodName}")
        self.h = History(data, Registry(data))
        self.o = OU.Outputs(data, self.h, bus=EventBus())
        self.row = next(r for r in self.h.list()["items"] if os.path.realpath(r["dir"]) == os.path.realpath(self.dir))

    def test_exports_outside_the_batch_layout_count_as_made(self):
        # her vlog: exports live in items/main/exports (state/jobs/<id>/export has none) - it was "0 of 1 ready",
        # "Not started" in In progress, an empty tile that did not open
        self.assertFalse(os.path.exists(os.path.join(self.dir, "state", "jobs", "main", "export", "manifest.json")))
        doc = self.o.clips(self.row["id"])
        (c,) = doc["clips"]
        self.assertEqual(c["state"], "done")
        self.assertEqual(sorted(f["aspect"] for f in c["files"]), ["16:9", "9:16"])
        self.assertTrue(all(os.path.isfile(f["path"]) and f["w"] and f["h"] and f["duration"] for f in c["files"]))
        self.assertTrue(c["cover"] and os.path.isfile(c["cover"]))
        self.assertEqual(c["duration"], c["files"][0]["duration"])
        # the same files the engine's own output list / export name (one source)
        from vstudio.project import outputs as O
        eng = {os.path.realpath(x["file"]) for x in O.list_outputs(self.dir)["outputs"]}
        self.assertEqual({os.path.realpath(f["path"]) for f in c["files"]}, eng)

    def test_the_row_is_done_with_a_thumbnail(self):
        self.assertEqual(self.row["status"], "done")
        self.assertEqual((self.row["counts"]["done"], self.row["counts"]["total"]), (1, 1))
        self.assertTrue(self.row["thumb"] and os.path.isfile(self.row["thumb"]))
        self.assertIn(os.path.dirname(self.row["thumb"]), self.h.roots())

    def test_the_editor_opens_the_finished_vlog_without_words(self):
        doc = self.o.show(self.row["id"], "main")
        self.assertEqual(doc["words"], [])
        self.assertTrue(doc["file"].endswith(".mp4") and os.path.isfile(doc["file"]))
        self.assertGreater(doc["duration"], 1)

    def test_pieces_in_recipe_order_with_their_words(self):
        r = self.o.pieces(self.row["id"])
        ps = r["pieces"]
        stages = [p["stage"] for p in ps]
        self.assertEqual(stages[0], "sheets")                       # text previews (probe.txt) are not tiles
        self.assertNotIn("probe", stages)
        order = [s for i, s in enumerate(stages) if s not in stages[:i]]
        self.assertEqual(order, ["sheets", "render", "music", "cover_frames"])
        segs = [p for p in ps if p["stage"] == "render" and p["kind"] == "videos"]
        self.assertEqual([p["n"] for p in segs], list(range(1, len(segs) + 1)))
        self.assertTrue(segs and all(p["of"] == len(segs) and p["label"]["en"] == "Graded segment" for p in segs))
        self.assertTrue(all(p["label"].get("fr") for p in segs))
        self.assertEqual([p["label"]["en"] for p in ps if p["stage"] == "cover_frames"], ["Cover options"])
        self.assertTrue(all(p["job"] == "main" and p["state"] == "done" and os.path.isfile(p["path"]) for p in ps))
        self.assertTrue(all(os.path.dirname(p["path"]) in self.h.roots() for p in ps))

    def test_project_level_asks_answer_with_the_real_controls(self):
        pa = PA.ProjectAsk(self.o)

        class AP:                                       # the desk's Autopilot: the decisions the run took
            def get(self, item):
                from vstudio.project import autopilot as A
                from vstudio.project.core import Project
                return dict(decisions=A.decisions(Project(FinishedVlogTest.dir)))
        pa.autopilot = AP()
        res = pa.get(pa.start(self.row["id"], "换个音乐，太闷了")["job"])["result"]
        self.assertEqual(res["answer"], "actions")
        self.assertEqual([(a["kind"], a["checkpoint"]) for a in res["actions"]], [("reopen", "music")])
        self.assertFalse(res["model_called"])
        res = pa.get(pa.start(self.row["id"], "re-cut it, swap the second shot")["job"])["result"]
        self.assertEqual([(a["kind"], a["checkpoint"]) for a in res["actions"]], [("reopen", "edit")])
        res = pa.get(pa.start(self.row["id"], "pick another cover")["job"])["result"]
        self.assertEqual([a["checkpoint"] for a in res["actions"]], ["cover"])
        # not running: pause has nothing to stop, and says so; "go on" offers to run it on
        res = pa.get(pa.start(self.row["id"], "pause it")["job"])["result"]
        self.assertEqual((res["answer"], res["warnings"][0]["code"]), ("nothing", "pa-not-running"))
        res = pa.get(pa.start(self.row["id"], "继续")["job"])["result"]
        self.assertEqual([a["kind"] for a in res["actions"]], ["resume"])


class IntentTest(unittest.TestCase):
    def test_project_asks_and_clip_edits(self):
        for text, want in (("暂停一下", "pause"), ("pause it", "pause"), ("mets en pause", "pause"),
                           ("继续", "resume"), ("keep going", "resume"),
                           ("换个音乐", "music"), ("change the music", "music"), ("changer la musique", "music"),
                           ("换封面", "cover"), ("pick another cover", "cover"),
                           ("重新剪", "recut"), ("swap the third shot", "recut"), ("调色再暖一点", "recut"),
                           ("去掉标题", None), ("音乐小一点", None), ("把开头剪掉", None), ("1.2倍速", None),
                           ("remove the title from all clips", None)):
            self.assertEqual(PA.project_intent(text), want, text)

    def test_controls_follow_the_run(self):
        running = dict(live=dict(state="running"))
        acts, note = PA.project_actions(running, "pause", [])
        self.assertEqual([a["kind"] for a in acts], ["stop"])
        acts, note = PA.project_actions(running, "resume", [])
        self.assertEqual((acts, note["code"]), ([], "pa-running"))
        acts, note = PA.project_actions(dict(stopped=1.0), "resume", [])
        self.assertEqual([a["kind"] for a in acts], ["resume"])
        acts, note = PA.project_actions({}, "music", [dict(checkpoint="cover", kind="cover-pick", item="a")])
        self.assertEqual((acts, note["code"]), ([], "pa-no-music"))
        decs = [dict(checkpoint="music", kind="music-pick", item="a"), dict(checkpoint="music", kind="music-pick", item="a"),
                dict(checkpoint="music", kind="music-pick", item="b")]
        acts, _ = PA.project_actions({}, "music", decs)
        self.assertEqual([(a["checkpoint"], a["item"]) for a in acts], [("music", "a"), ("music", "b")])


class NothingMadeYetTest(unittest.TestCase):
    def test_a_project_still_being_made_answers_instead_of_refusing(self):
        root = tempfile.mkdtemp()
        d = os.path.join(root, "p")
        os.makedirs(os.path.join(d, "state"))
        with open(os.path.join(d, "project.yaml"), "w") as f:
            f.write("name: p\nrecipe: vlog\n")

        class H:
            def find(self, item, **_kw):
                return dict(kind="project", dir=d, live=dict(state="running"))

            def allow_media(self, paths):
                pass
        o = OU.Outputs(os.path.join(root, "desk"), H())
        pa = PA.ProjectAsk(o)
        t0 = time.time()
        r = pa.get(pa.start("abc123abc123", "make the intro shorter")["job"])
        self.assertLess(time.time() - t0, 1.0)
        self.assertEqual((r["state"], r["result"]["answer"], r["result"]["warnings"][0]["code"]),
                         ("done", "nothing", "pa-nothing-made"))
        r = pa.get(pa.start("abc123abc123", "暂停")["job"])
        self.assertEqual([a["kind"] for a in r["result"]["actions"]], ["stop"])


if __name__ == "__main__":
    unittest.main()
