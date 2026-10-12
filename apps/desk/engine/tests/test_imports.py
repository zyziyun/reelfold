"""Import finished videos for second-pass editing, the desk side (desk_engine.imports) against the real engine of
this monorepo: check what was dropped, import it (the originals untouched), the clip opens in the editor with its
versions and post copy, the background transcript + shot match, other takes of a shot, a shot swap through the
editor."""
import json
import os
import queue
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
from desk_engine.caps import CliRunner  # noqa: E402
from desk_engine.common import EventBus, Registry  # noqa: E402
from desk_engine.history import History  # noqa: E402
from desk_engine.imports import Imports  # noqa: E402
from desk_engine.timeline import Strips  # noqa: E402

TESTS = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.environ.get("VSTUDIO_ENGINE_PATH") or os.path.abspath(os.path.join(TESTS, "..", "..", "..", ".."))
HAVE = os.path.isdir(os.path.join(ENGINE, "lib", "vstudio", "project")) and shutil.which("ffmpeg")


def _ff(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


@unittest.skipUnless(HAVE, "engine repo or ffmpeg not found")
class ImportApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        raw = os.path.join(cls.root, "footage")
        out = os.path.join(cls.root, "exports", "01-city")
        os.makedirs(raw)
        os.makedirs(out)
        srcs = ["mandelbrot=s=320x180:r=30",
                "mandelbrot=s=320x180:r=30:start_x=-1.25066:start_y=0.02012:start_scale=0.05:end_scale=0.00005"]
        for k, s in enumerate(srcs):
            _ff("-f", "lavfi", "-i", f"{s},format=yuv420p", "-t", "8", "-c:v", "libx264", "-preset", "ultrafast",
                "-g", "15", os.path.join(raw, f"DJI_000{k + 1}.MP4"))
        cut = os.path.join(cls.root, "cut.mp4")
        _ff("-ss", "1", "-t", "2", "-i", os.path.join(raw, "DJI_0001.MP4"), "-ss", "2", "-t", "2", "-i",
            os.path.join(raw, "DJI_0002.MP4"), "-filter_complex",
            "[0:v]setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[v]", "-map", "[v]",
            "-c:v", "libx264", "-preset", "ultrafast", cut)
        for name, vf in (("youtube.mp4", "scale=640:360"), ("douyin.mp4", "crop=101:180:30:0,scale=360:640")):
            _ff("-i", cut, "-f", "lavfi", "-t", "4", "-i", "sine=frequency=300", "-vf", vf, "-c:v", "libx264",
                "-preset", "ultrafast", "-c:a", "aac", "-shortest", os.path.join(out, name))
        with open(os.path.join(out, "post.md"), "w", encoding="utf-8") as f:
            f.write("## youtube\n\nCity at night\n\nA flight.\n\n#city\n\n## douyin\n\n夜色城市\n\n一次飞行。\n")
        cls.raw, cls.out = raw, out

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, True)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(ENGINE, "lib"), TESTS]),
                   VSTUDIO_OUTPUT_TRANSCRIBER="_fake_asr:words", VSTUDIO_LLM_PROVIDER="none",
                   VSTUDIO_HOME=os.path.join(self.tmp, "home"), VSTUDIO_CACHE=os.path.join(self.tmp, "cache"))
        for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            env.pop(k, None)
        self.patch = mock.patch.dict(os.environ, {"VSTUDIO_HOME": env["VSTUDIO_HOME"], "DESK_HISTORY_WATCH": "",
                                                  "VSTUDIO_CACHE": env["VSTUDIO_CACHE"]})
        self.patch.start()
        data = os.path.join(self.tmp, "desk")
        self.bus = EventBus()
        self.q = self.bus.subscribe()
        self.h = History(data, Registry(data))
        runner = CliRunner(sys.executable, env)
        self.o = OU.Outputs(data, self.h, runner, self.bus)
        self.s = Strips(data, self.o, self.h, self.bus)
        self.im = Imports(data, self.h, self.o, self.s, self.bus, runner)

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, True)

    def _wait(self, kind, pred, timeout=240):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                ev = self.q.get(timeout=5)
            except queue.Empty:
                continue
            if ev["type"] == kind and pred(ev):
                return ev
        self.fail(f"no {kind} event")

    def test_check_import_open_match_swap(self):
        chk = self.im.check([self.out, self.raw])
        self.assertEqual(chk["verdict"], "mixed")
        self.assertEqual(chk["counts"]["finished"], 2)
        [c] = chk["clips"]
        self.assertEqual([v["platform"] for v in c["versions"]], ["youtube", "douyin"])
        self.assertEqual(c["sources"], 2)
        before = os.stat(os.path.join(self.out, "youtube.mp4")).st_mtime_ns

        job = self.im.start([self.out], [self.raw], None)["job"]
        done = self._wait("import", lambda e: e.get("job") == job and e["state"] in ("done", "failed"))
        self.assertEqual(done["state"], "done", done)
        item, clip = done["item"], done["clip"]
        self.assertEqual(os.stat(os.path.join(self.out, "youtube.mp4")).st_mtime_ns, before)
        self.assertFalse(os.path.exists(os.path.join(self.out, ".vstudio")))

        # the Studio lists it: one clip, both versions (labels per platform), its post copy
        cl = self.o.clips(item)
        self.assertEqual(cl["kind"], "work")
        [row] = cl["clips"]
        self.assertEqual(row["id"], clip)
        self.assertEqual(row["title"], "City at night")
        self.assertEqual([f["label"] for f in row["files"]], ["YouTube", "抖音"])
        self.assertEqual(row["posts"]["douyin"]["title"], "夜色城市")

        # transcribed in the background with the engine (the editor opens on the words), then matched
        self._wait("output-transcribe", lambda e: e.get("item") == item and e["state"] in ("done", "failed"))
        m = self._wait("import-match", lambda e: e.get("item") == item and e["state"] in ("done", "failed"))
        self.assertEqual(m["state"], "done", m)
        self.assertEqual(m["matched"], 2)
        doc = self.o.show(item, clip)
        self.assertEqual(doc["engine"], "real")
        self.assertEqual([w["w"] for w in doc["words"]], ["hello", "world", "again"])
        self.assertTrue(doc["caps"]["shot_swap"])
        info = self.im.info(item)
        self.assertEqual(info["clips"][0]["match"]["state"], "done")

        tk = self.im.takes(item, clip, 0)
        self.assertTrue(tk["takes"] and tk["takes"][0]["still"] and os.path.exists(tk["takes"][0]["still"]))
        self.assertEqual(tk["original"]["name"], "DJI_0001.MP4")
        r = self.o.edit(item, clip, [{"op": "shot_swap", "shot": 0, "source": tk["takes"][0]["source"],
                                      "t": tk["takes"][0]["t"]}])
        self.assertEqual(r["step"]["describe"][0]["code"], "op-shot-swap")
        self.assertEqual(self.o.show(item, clip)["imported"]["shots"][0]["swap"]["t"], tk["takes"][0]["t"])

    def test_footage_only_is_refused(self):
        job = self.im.start([self.raw], [], None)["job"]
        done = self._wait("import", lambda e: e.get("job") == job and e["state"] in ("done", "failed"))
        self.assertEqual(done["state"], "failed")
        self.assertEqual(done["error"]["code"], "no-finished-video")


if __name__ == "__main__":
    unittest.main()
