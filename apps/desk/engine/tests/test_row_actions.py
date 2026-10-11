"""The Studio's row menu on the engine side: requests archived / restored / deleted (never her files), a stopped
request stays listed and can be tried again, Delete's trash plan for project folders (her footage never inside what
goes, her own folders and running projects refused), forget after the Trash (posts waiting to go out go too), and a
project run stopped by her is "stopped", not a failure."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import history as HI  # noqa: E402
from desk_engine import pilot as PI  # noqa: E402
from desk_engine.common import BadRequest, Registry  # noqa: E402
from test_archive import make_project, set_running  # noqa: E402
from test_history import make_batch  # noqa: E402


class RequestRowTest(unittest.TestCase):
    def setUp(self):
        from desk_mock.intake import MockIntake
        self.tmp = tempfile.mkdtemp(prefix="rowreq-")
        self.env = mock.patch.dict(os.environ, {"DESK_MOCK_STEP": "0.01", "VSTUDIO_HOME": os.path.join(self.tmp, "vh")})
        self.env.start()
        self.video = os.path.join(self.tmp, "her.mp4")
        with open(self.video, "w", encoding="utf-8") as f:
            f.write("x")
        self.it = MockIntake(os.path.join(self.tmp, "desk"), None, None, "mock")

    def tearDown(self):
        self.env.stop()

    def failed(self):
        pid = self.it.start("剪 2 条切片", [self.video], mode="ask")["id"]
        for _ in range(200):
            if self.it.get(pid)["state"] != "running":
                break
            time.sleep(0.02)
        self.it._set(pid, state="error", error="boom", error_code="plan-empty")
        return pid

    def test_archive_restore_and_counts(self):
        pid = self.failed()
        self.assertEqual([x["id"] for x in self.it.open()["items"]], [pid])
        self.assertEqual(len(self.it.inbox_items()), 1)
        self.it.archive([pid])
        self.assertEqual(self.it.open()["items"], [])
        self.assertEqual(self.it.open()["archived"], 1)                   # the Studio's Archived filter count
        self.assertEqual(self.it.inbox_items(), [])                       # archived: not in the Inbox / badges
        arch = self.it.open(archived=True)["items"]
        self.assertEqual([x["id"] for x in arch], [pid])
        self.assertTrue(arch[0]["archived"] and arch[0]["archived_at"])
        # survives a restart
        from desk_mock.intake import MockIntake
        again = MockIntake(os.path.join(self.tmp, "desk"), None, None, "mock")
        self.assertEqual([x["id"] for x in again.open(archived=True)["items"]], [pid])
        self.it.restore([pid])
        self.assertEqual([x["id"] for x in self.it.open()["items"]], [pid])
        self.assertEqual(self.it.open(archived=True)["items"], [])

    def test_delete_is_for_good_and_never_her_files(self):
        pid = self.failed()
        job = os.path.join(self.tmp, "desk", "intake", f"{pid}.job.json")
        self.assertTrue(os.path.exists(job))
        self.it.delete([pid])
        self.assertFalse(os.path.exists(job))
        self.assertEqual(self.it.open()["items"], [])
        self.assertEqual(self.it.open(archived=True)["items"], [])
        with self.assertRaises(KeyError):
            self.it.get(pid)
        self.assertTrue(os.path.exists(self.video))                       # her file stays

    def test_delete_refuses_a_request_already_made(self):
        pid = self.failed()
        self.it._set(pid, applied=[dict(dir="/x", name="x")])
        with self.assertRaises(BadRequest):
            self.it.delete([pid])

    def test_stopped_stays_listed_and_tries_again(self):
        pid = self.it.start("剪 2 条切片", [self.video], mode="ask")["id"]
        self.it.stop(pid)
        self.assertEqual([(x["id"], x["state"]) for x in self.it.open()["items"]], [(pid, "stopped")])
        self.it.retry(pid)
        self.assertIn(self.it.get(pid)["state"], ("running", "done"))


class TrashPlanTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rowtrash-")
        self.data = os.path.join(self.root, "desk")
        self.home = os.path.join(self.root, "vh")
        self.env = mock.patch.dict(os.environ, {"VSTUDIO_HOME": self.home, "DESK_HISTORY_WATCH": ""})
        self.env.start()
        self.h = HI.History(self.data, Registry(self.data))
        self.rec = os.path.join(self.root, "recordings", "take1", "assembled.mp4")
        os.makedirs(os.path.dirname(self.rec))
        with open(self.rec, "wb") as f:
            f.write(b"\0" * 10)
        # an app-made project: <home>/projects/<id>/<name> with its intake note beside it
        self.p = make_project(os.path.join(self.home, "projects", "512d9d387962", "01-talkinghead-1"), "talkinghead-1")
        with open(os.path.join(self.p, "project.yaml"), "a", encoding="utf-8") as f:
            f.write(f"items:\n- id: assembled\n  inputs:\n    video: {self.rec}\n")
        with open(os.path.join(os.path.dirname(self.p), "intake.json"), "w") as f:
            f.write("{}")
        # a project that keeps her footage inside its own folder
        self.q = make_project(os.path.join(self.root, "work", "q"), "Q")
        own = os.path.join(self.q, "footage.mp4")
        with open(own, "wb") as f:
            f.write(b"\0")
        with open(os.path.join(self.q, "project.yaml"), "a", encoding="utf-8") as f:
            f.write(f"inputs:\n  video: {own}\n")
        self.b = make_batch(os.path.join(self.root, "work", "batch-b"), name="b")
        with open(os.path.join(self.home, "projects.json"), "w") as f:
            json.dump([dict(dir=self.p, name="talkinghead-1"), dict(dir=self.q, name="Q")], f)
        self.h.set_watch([os.path.join(self.root, "work")])

    def tearDown(self):
        self.env.stop()

    def plan(self, d):
        return self.h.trash_plan([d])["items"][0]

    def test_app_project_goes_with_its_folder_her_take_stays(self):
        x = self.plan(self.p)
        self.assertTrue(x["ok"], x)
        self.assertEqual(x["target"], os.path.realpath(os.path.dirname(self.p)))   # projects/<id> as a whole
        self.assertEqual(x["keep"], [self.rec])
        self.assertGreaterEqual(x["files"], 2)
        self.assertEqual(x["name"], "talkinghead-1")
        # another project in the same projects/<id>: only this one's folder
        os.makedirs(os.path.join(os.path.dirname(self.p), "02-other"))
        self.assertEqual(self.plan(self.p)["target"], os.path.realpath(self.p))

    def test_refusals(self):
        self.assertEqual(self.plan(self.q)["reason"], "footage-inside")
        self.assertEqual(self.plan(self.q)["inside"], [os.path.join(self.q, "footage.mp4")])
        self.assertEqual(self.plan(self.b)["reason"], "own-folder")
        self.assertEqual(self.plan(os.path.join(self.root, "nope"))["reason"], "not-in-list")
        set_running(self.p)
        self.assertEqual(self.plan(self.p)["reason"], "running")
        home = os.path.realpath(os.path.expanduser("~"))
        self.assertFalse(HI._trashable(os.path.join(home, "Desktop"), home))
        self.assertFalse(HI._trashable("/Users", "/Users/me"))

    def test_forget_after_the_trash(self):
        self.h.archive([self.p])
        self.h.rename(self.p, "mine")
        shutil.rmtree(os.path.dirname(self.p))                          # what the desk's main process moved away
        self.h.forget([self.p])
        cfg = json.load(open(self.h.path))
        self.assertNotIn(os.path.realpath(self.p), cfg.get("hidden") or [])
        self.assertNotIn(os.path.realpath(self.p), cfg.get("names") or {})
        self.assertEqual(sorted(i["name"] for i in self.h.list()["items"]), ["Q", "b"])


class StopRunTest(unittest.TestCase):
    def test_stop_is_not_a_failure_and_shows_stopped(self):
        root = tempfile.mkdtemp(prefix="rowstop-")
        d = make_project(os.path.join(root, "p"), "P")
        with open(os.path.join(d, PI.LOG), "w") as f:
            f.write('{"event": "stage-fail", "ok": false, "error": "KeyboardInterrupt", "stage": "render"}\n')
        # a run the desk started that is going: a long sleep in its own session
        import subprocess
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        try:
            with open(os.path.join(d, PI.REC), "w") as f:
                json.dump(dict(pid=p.pid, started=time.time(), offset=0, exit=None, args=["-m", "vstudio.project"]), f)
            self.assertIsNotNone(PI.running(d))
            r = PI.stop(d)
            self.assertEqual(r["stopped"], "running")
            p.wait(timeout=10)
            rec = json.load(open(os.path.join(d, PI.REC)))
            rec["exit"] = p.returncode
            json.dump(rec, open(os.path.join(d, PI.REC), "w"))
            self.assertIsNone(PI.failure(d))                             # she stopped it: no failure card
            self.assertTrue(PI.stopped(d))
            with mock.patch.dict(os.environ, {"VSTUDIO_HOME": os.path.join(root, "vh"), "DESK_HISTORY_WATCH": root}):
                h = HI.History(os.path.join(root, "desk"), Registry(os.path.join(root, "desk")))
                row = next(i for i in h.list()["items"] if i["name"] == "P")
                self.assertTrue(row.get("stopped"))
                self.assertNotIn("failure", row)
        finally:
            if p.poll() is None:
                p.kill()

    def test_stop_a_queued_run(self):
        root = tempfile.mkdtemp(prefix="rowq-")
        d = make_project(os.path.join(root, "p"), "P")
        saved = PI.QUEUE
        PI.QUEUE = PI.RunQueue()
        try:
            PI.QUEUE.active = {"/a", "/b", "/c"}
            with mock.patch.dict(os.environ, {"DESK_MAX_RUNS": "1"}):
                PI.spawn(sys.executable, dict(os.environ), d)
                self.assertEqual(PI.queued(d), 1)
                self.assertEqual(PI.stop(d)["stopped"], "queued")
                self.assertIsNone(PI.queued(d))
                self.assertTrue(PI.stopped(d))
        finally:
            PI.QUEUE = saved


if __name__ == "__main__":
    unittest.main()
