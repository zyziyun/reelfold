"""Delete (purge.py): the plan names exactly what Reelfold made (her footage never), Move to Trash hides at once and
moves only after the Undo window (undo brings it back, nothing moved), Delete permanently removes from disk, running
ones and a changed plan are refused, and nothing is left pointing at what went (history, calendar, goals, titles,
requests)."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import history as HI  # noqa: E402
from desk_engine import outputs as OU  # noqa: E402
from desk_engine.calendar import Calendar  # noqa: E402
from desk_engine.common import BadRequest, Registry, batch_id  # noqa: E402
from desk_engine.purge import Purge, folder_sources  # noqa: E402
from test_archive import make_project, set_running  # noqa: E402
from test_history import make_batch  # noqa: E402


def touch(p, data=b"x" * 10):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    return p


class FakeIntake:
    def __init__(self):
        self.jobs = {"a" * 12: dict(id="a" * 12, prompt="two clips", inputs=["/x/rec.mp4"], mode="ask")}
        self.hidden = set()
        self.deleted = []

    def get(self, rid):
        if rid not in self.jobs:
            raise KeyError(rid)
        return self.jobs[rid]

    def delete(self, ids):
        self.deleted += ids
        for i in ids:
            self.jobs.pop(i, None)


class PurgeTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="purge-")
        self.data = os.path.join(self.root, "desk")
        self.home = os.path.join(self.root, "vhome")
        os.makedirs(self.home)
        self.env = mock.patch.dict(os.environ, {"VSTUDIO_HOME": self.home, "DESK_HISTORY_WATCH": ""})
        self.env.start()
        self.reg = Registry(self.data)
        self.h = HI.History(self.data, self.reg)
        # her recording, outside every project
        self.rec = touch(os.path.join(self.root, "recordings", "take1.mp4"), b"r" * 1000)
        # an app-made project (projects/<id>/<name>) pointing at it
        self.pp = os.path.join(self.home, "projects", "512d9d387962")
        self.p = make_project(os.path.join(self.pp, "talk"), "talk")
        with open(os.path.join(self.p, "project.yaml"), "a") as f:
            f.write(f"items:\n- id: a\n  inputs:\n    video: {self.rec}\n")
        touch(os.path.join(self.p, "final", "a", "youtube.mp4"))
        touch(os.path.join(self.pp, "intake.json"), b"{}")
        # a batch in her watched folder: her lecture beside the batch's own files, a job naming it as its input
        self.w = os.path.join(self.root, "demos")
        self.b = make_batch(os.path.join(self.w, "batch-rag"), name="rag")
        self.lecture = touch(os.path.join(self.b, "lecture.mp4"), b"l" * 500)
        touch(os.path.join(self.b, "raw", "cam.mov"))
        con = sqlite3.connect(os.path.join(self.b, "batch.db"))
        con.execute("UPDATE jobs SET params = ? WHERE id = 'ep01'", (json.dumps(dict(input=self.lecture, title="One")),))
        con.commit()
        con.close()
        touch(os.path.join(self.b, "jobs", "ep01", "export", "youtube.mp4"))
        touch(os.path.join(self.b, "review", "index.html"))
        with open(os.path.join(self.home, "projects.json"), "w") as f:
            json.dump([dict(dir=self.p, name="talk", recipe="talkinghead")], f)
        self.h.set_watch([self.w])
        self.intake = FakeIntake()
        self.cal = Calendar(self.data, self.h, None)
        self.pg = Purge(self.data, self.h, self.intake, self.cal, None, None)

    def tearDown(self):
        self.env.stop()
        from desk_engine import purge
        purge.PENDING_CLIPS.clear()

    def names(self, archived=False):
        return sorted(i["name"] for i in self.h.list(archived=archived)["items"])

    def item_id(self, name):
        return next(i["id"] for i in self.h.list()["items"] if i["name"] == name)

    def fake_trash(self, paths):
        """The desk's main process: the targets go to a Trash folder of the test (not her real Trash)."""
        trash = os.path.join(self.root, "Trash")
        os.makedirs(trash, exist_ok=True)
        for i, t in enumerate(paths):
            shutil.move(t, os.path.join(trash, f"{i}-{os.path.basename(t)}"))
        return trash

    # ------------------------------------------------------------------ the plan
    def test_plan_names_made_files_and_keeps_footage(self):
        doc = self.pg.plan(dict(dirs=[self.p, self.b]))
        proj, batch = doc["items"]
        self.assertTrue(proj["ok"])
        self.assertEqual(proj["kind"], "project")
        self.assertEqual(proj["targets"], [os.path.realpath(self.pp)])     # projects/<id> as a whole (intake note only)
        self.assertTrue(proj["whole"])
        self.assertIn(os.path.realpath(self.rec), proj["keep"])
        self.assertTrue(batch["ok"])
        self.assertEqual(batch["kind"], "batch")
        self.assertFalse(batch["whole"])
        got = sorted(os.path.basename(t) for t in batch["targets"])
        self.assertEqual(got, ["batch.db", "jobs", "review"])
        self.assertIn(os.path.realpath(self.lecture), batch["keep"])
        self.assertEqual(sorted(batch["other"]), ["raw"])                  # her other files stay (lecture listed in keep)
        self.assertGreater(doc["bytes"], 0)
        self.assertEqual(doc["files"], proj["files"] + batch["files"])
        self.assertIn(os.path.realpath(self.lecture), folder_sources(self.b))

    def test_footage_inside_a_made_name_is_kept(self):
        inside = touch(os.path.join(self.p, "work", "take.mp4"))
        with open(os.path.join(self.p, "project.yaml"), "a") as f:
            f.write(f"inputs:\n  - {inside}\n")
        it = self.pg.plan(dict(dirs=[self.p]))["items"][0]
        self.assertTrue(it["ok"])
        self.assertFalse(it["whole"])
        self.assertNotIn(os.path.realpath(os.path.join(self.p, "work")), it["targets"])
        self.assertTrue(all(not t.endswith(os.sep + "work") for t in it["targets"]))

    def test_running_and_changed_plans_refused(self):
        set_running(self.b)
        it = self.pg.plan(dict(dirs=[self.b]))["items"][0]
        self.assertEqual((it["ok"], it["reason"]), (False, "running"))
        with self.assertRaises(BadRequest):
            self.pg.hard(dict(dirs=[self.b]), "whatever")
        # something new since she looked: a new made entry in the batch
        os.remove(os.path.join(self.b, ".vstudio", "status.json"))
        b1 = self.pg.plan(dict(dirs=[self.b]))
        touch(os.path.join(self.b, "delivery", "x.zip"))
        with self.assertRaisesRegex(BadRequest, "changed"):
            self.pg.hard(dict(dirs=[self.b]), b1["sig"])
        self.assertTrue(os.path.exists(os.path.join(self.b, "batch.db")))

    def test_bad_selection(self):
        for sel in ({}, dict(dirs=["rel/path"]), dict(clips=[dict(item="x", clip="../a")]), dict(requests=["nope"])):
            with self.assertRaises(BadRequest):
                self.pg.plan(sel)

    # ------------------------------------------------------------------ Move to Trash
    def test_soft_hides_undo_brings_back_nothing_moved(self):
        doc = self.pg.plan(dict(dirs=[self.p]))
        st = self.pg.stage(dict(dirs=[self.p]), doc["sig"])
        self.assertNotIn("talk", self.names())
        self.assertNotIn("talk", self.names(archived=True))
        self.assertTrue(os.path.exists(self.p))                            # nothing moved yet
        self.assertEqual(self.pg.pending()["items"][0]["targets"], st["targets"])
        # the desk restarted while the toast was up: still hidden
        Purge(self.data, self.h, self.intake, self.cal, None, None)
        self.assertNotIn("talk", self.names())
        self.pg.undo(st["id"])
        self.assertIn("talk", self.names())
        self.assertEqual(self.pg.pending()["items"], [])

    def test_soft_to_trash_then_commit_cleans_references(self):
        pid = self.item_id("talk")
        self.h.archive([self.p])
        self.h.rename(self.p, "My talk")
        with open(self.cal.path, "w") as f:
            json.dump([dict(id="1" * 12, item=pid, clip="a", platform="youtube", at="2026-10-20T10:00", state="ready"),
                       dict(id="2" * 12, item=pid, clip="a", platform="youtube", at="2026-10-01T10:00", state="posted"),
                       dict(id="3" * 12, item="f" * 12, clip="z", platform="youtube", at="2026-10-21T10:00", state="ready")], f)
        doc = self.pg.plan(dict(dirs=[self.p]))
        self.assertEqual(doc["items"][0]["name"], "My talk")
        st = self.pg.stage(dict(dirs=[self.p]), doc["sig"])
        self.assertEqual(self.names(archived=True), [])
        trash = self.fake_trash(st["targets"])
        r = self.pg.commit(st["id"], st["targets"], [])
        self.assertEqual(r["deleted"], [f"d:{os.path.realpath(self.p)}"])
        self.assertFalse(os.path.exists(self.pp))
        self.assertTrue(os.listdir(trash))                                 # restorable from the Trash
        self.assertTrue(os.path.exists(self.rec))                          # her recording stays
        with open(os.path.join(self.data, "history.json")) as f:
            cfg = json.load(f)
        rp = os.path.realpath(self.p)
        self.assertNotIn(rp, cfg.get("hidden") or [])
        self.assertNotIn(rp, cfg.get("names") or {})
        self.assertEqual(sorted(x["id"] for x in self.cal._rows()), ["2" * 12, "3" * 12])   # posted + other stay
        self.assertEqual(self.pg.pending()["items"], [])

    def test_trash_refused_comes_back(self):
        doc = self.pg.plan(dict(dirs=[self.p]))
        st = self.pg.stage(dict(dirs=[self.p]), doc["sig"])
        r = self.pg.commit(st["id"], [], st["targets"])
        self.assertEqual(r["deleted"], [])
        self.assertEqual(r["back"][0]["name"], "talk")
        self.assertIn("talk", self.names())

    # ------------------------------------------------------------------ Delete permanently
    def test_hard_batch_removes_made_keeps_her_files(self):
        doc = self.pg.plan(dict(dirs=[self.b]))
        r = self.pg.hard(dict(dirs=[self.b]), doc["sig"])
        self.assertEqual(r["deleted"], [f"d:{os.path.realpath(self.b)}"])
        for gone in ("batch.db", "jobs", "review"):
            self.assertFalse(os.path.exists(os.path.join(self.b, gone)), gone)
        self.assertTrue(os.path.exists(self.lecture))
        self.assertTrue(os.path.exists(os.path.join(self.b, "raw", "cam.mov")))
        self.assertNotIn("rag", self.names())
        self.assertNotIn(batch_id(self.b), {b["id"] for b in self.reg.all()})

    def test_hard_one_video_of_a_batch(self):
        bid = self.item_id("rag")
        with open(self.cal.path, "w") as f:
            json.dump([dict(id="4" * 12, item=bid, clip="ep01", platform="tiktok", at="2026-10-20T10:00", state="ready"),
                       dict(id="5" * 12, item=bid, clip="ep02", platform="tiktok", at="2026-10-21T10:00", state="ready")], f)
        e = self.h.find(bid)
        self.assertEqual([c["id"] for c in OU.list_clips(e)], ["ep01", "ep02"])
        doc = self.pg.plan(dict(clips=[dict(item=bid, clip="ep01")]))
        it = doc["items"][0]
        self.assertTrue(it["ok"], it)
        self.assertEqual(it["targets"], [os.path.realpath(os.path.join(self.b, "jobs", "ep01"))])
        self.assertEqual(it["name"], "ep01")
        r = self.pg.hard(dict(clips=[dict(item=bid, clip="ep01")]), doc["sig"])
        self.assertEqual(len(r["deleted"]), 1)
        self.assertFalse(os.path.exists(os.path.join(self.b, "jobs", "ep01")))
        self.assertTrue(os.path.exists(os.path.join(self.b, "jobs", "ep02")))
        self.assertTrue(os.path.exists(self.lecture))
        self.assertEqual([c["id"] for c in OU.list_clips(self.h.find(bid))], ["ep02"])
        self.assertEqual([x["id"] for x in self.cal._rows()], ["5" * 12])

    def test_soft_one_video_hidden_while_pending(self):
        self.pg.bus = mock.Mock()
        bid = self.item_id("rag")
        doc = self.pg.plan(dict(clips=[dict(item=bid, clip="ep02")]))
        st = self.pg.stage(dict(clips=[dict(item=bid, clip="ep02")]), doc["sig"])
        self.assertEqual([c["id"] for c in OU.list_clips(self.h.find(bid))], ["ep01"])
        self.pg.bus.publish.assert_any_call("output-edit", item=bid, clip="ep02")
        self.pg.bus.reset_mock()
        self.pg.undo(st["id"])
        self.pg.bus.publish.assert_any_call("output-edit", item=bid, clip="ep02")
        self.assertEqual([c["id"] for c in OU.list_clips(self.h.find(bid))], ["ep01", "ep02"])

    def test_requests(self):
        rid = "a" * 12
        doc = self.pg.plan(dict(requests=[rid]))
        self.assertEqual(doc["items"][0]["keep"], ["/x/rec.mp4"])
        st = self.pg.stage(dict(requests=[rid]), doc["sig"])
        self.assertIn(rid, self.intake.hidden)
        self.pg.commit(st["id"], [], [])
        self.assertEqual(self.intake.deleted, [rid])
        self.assertNotIn(rid, self.intake.hidden)
        doc = self.pg.plan(dict(requests=["b" * 12]))
        self.assertEqual(doc["items"][0]["reason"], "not-found")

    def test_goal_videos_dropped(self):
        from desk_engine.goals import Goals
        g = Goals(self.data, None, self.intake, self.h, None, "real", ticker=False)
        rec = dict(id="c" * 12, state="done", prompt="p", created=1, videos=[
            dict(id="v1", state="made", projects=[dict(dir=self.p)]),
            dict(id="v2", state="made", projects=[dict(dir="/elsewhere/x")])])
        g._save(rec)
        g.forget([self.p], [])
        v1, v2 = g.view("c" * 12)["videos"]
        self.assertEqual((v1["state"], v1["reason_code"], v1["projects"]), ("dropped", "deleted", []))
        self.assertEqual(v2["state"], "made")

    def test_routes(self):
        from desk_engine.common import EventBus
        from desk_mock import MockEngine, make_api
        bus = EventBus()
        tmp = tempfile.mkdtemp(prefix="purge-api-")
        eng = MockEngine(tmp, Registry(tmp), bus, step=0.005)
        api = make_api(eng, bus, "t" * 48, [])

        def R(m, path, body=None):
            return api.route(m, path, {}, body)
        R("POST", "/api/history/config", dict(watch=[self.w]))
        doc = R("POST", "/api/delete/plan", dict(dirs=[self.b]))
        self.assertTrue(doc["items"][0]["ok"])
        with self.assertRaises(BadRequest):
            R("POST", "/api/delete/hard", dict(dirs=[self.b], sig=doc["sig"]))          # no second confirm
        st = R("POST", "/api/delete/stage", dict(dirs=[self.b], sig=doc["sig"]))
        self.assertEqual(R("GET", f"/api/delete/pending/{st['id']}")["targets"], st["targets"])
        self.assertNotIn("rag", [i["name"] for i in R("GET", "/api/history")["items"]])
        R("POST", f"/api/delete/pending/{st['id']}/undo")
        self.assertIn("rag", [i["name"] for i in R("GET", "/api/history")["items"]])
        doc = R("POST", "/api/delete/plan", dict(dirs=[self.b]))
        r = R("POST", "/api/delete/hard", dict(dirs=[self.b], sig=doc["sig"], confirm=True))
        self.assertEqual(len(r["deleted"]), 1)
        self.assertTrue(os.path.exists(self.lecture))
        with self.assertRaises(KeyError):
            R("POST", "/api/delete/pending/" + "0" * 12 + "/commit", dict(trashed=[], failed=[]))


if __name__ == "__main__":
    unittest.main()

class SeriesPurgeTest(unittest.TestCase):
    setUp = PurgeTest.setUp
    tearDown = PurgeTest.tearDown
    def series(self):
        class Goals:
            hidden = set()
            def __init__(self, goal):
                self.goal = goal
            def _get(self, gid):
                if gid != self.goal['id']:
                    raise KeyError(gid)
                return self.goal
            def _all(self):
                return [self.goal]
            def forget(self, dirs, reqs):
                pass
            def dismiss(self, gid):
                self._get(gid)['dismissed_at'] = 1
        g = Goals(dict(id='f'*12, goal='Series', state='stopped', inputs=[self.rec], videos=[dict(projects=[dict(dir=self.p)], intake='a'*12)]))
        self.pg.goals = g
        return g, dict(goals=['f'*12])

    def test_series_undo_preserves_every_file(self):
        g, sel = self.series()
        plan = self.pg.plan(sel)
        self.assertTrue(plan['items'][0]['ok'])
        self.assertIn(self.rec, plan['keep'])
        staged = self.pg.stage(sel, plan['sig'])
        self.assertIn(g.goal['id'], g.hidden)
        self.assertTrue(os.path.exists(self.p))
        self.pg.undo(staged['id'])
        self.assertFalse(g.hidden)
        self.assertTrue(os.path.exists(self.p))
        self.assertTrue(os.path.exists(self.rec))

    def test_series_hard_preserves_source_and_removes_group(self):
        g, sel = self.series()
        result = self.pg.hard(sel, self.pg.plan(sel)['sig'])
        self.assertEqual(len(result['deleted']), 1)
        self.assertFalse(os.path.exists(self.p))
        self.assertTrue(os.path.exists(self.rec))
        self.assertEqual(g.goal['dismissed_at'], 1)

    def test_series_rechecks_running_state(self):
        g, sel = self.series()
        plan = self.pg.plan(sel)
        g.goal['state'] = 'running'
        with self.assertRaises(BadRequest):
            self.pg.stage(sel, plan['sig'])
        self.assertTrue(os.path.exists(self.p))

    def test_series_failed_trash_keeps_group(self):
        g, sel = self.series()
        staged = self.pg.stage(sel, self.pg.plan(sel)['sig'])
        result = self.pg.commit(staged['id'], [], staged['targets'])
        self.assertEqual(len(result['back']), 1)
        self.assertNotIn('dismissed_at', g.goal)
        self.assertFalse(g.hidden)

    def test_series_shared_source_target_refused(self):
        g, sel = self.series()
        g.goal['inputs'].append(os.path.join(self.p, 'final', 'a', 'youtube.mp4'))
        self.assertEqual(self.pg.plan(sel)['items'][0]['reason'], 'unsafe')

    def test_series_shared_project_refused(self):
        g, sel = self.series()
        g._all = lambda: [g.goal, dict(id='e'*12, videos=[dict(projects=[dict(dir=self.p)])])]
        self.assertEqual(self.pg.plan(sel)['items'][0]['reason'], 'unsafe')

    def test_series_changed_membership_invalidates_confirmation(self):
        g, sel = self.series()
        plan = self.pg.plan(sel)
        g.goal['videos'].append(dict(projects=[dict(dir=self.b)]))
        with self.assertRaises(BadRequest):
            self.pg.stage(sel, plan['sig'])

    def test_series_soft_commit_removes_group_after_targets_move(self):
        g, sel = self.series()
        staged = self.pg.stage(sel, self.pg.plan(sel)['sig'])
        for i, target in enumerate(staged['targets']):
            shutil.move(target, os.path.join(self.root, f'trash-{i}'))
        result = self.pg.commit(staged['id'], staged['targets'], [])
        self.assertFalse(result['back'])
        self.assertEqual(g.goal['dismissed_at'], 1)
        self.assertTrue(os.path.exists(self.rec))
