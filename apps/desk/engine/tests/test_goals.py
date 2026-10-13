"""Goal mode in the desk (goals.py): a goal-style request -> survey -> plan card (edits) -> a group of videos, each an
ordinary autopilot request; at most N in flight; a failure is retried once, then the video is dropped with the reason;
the goal is done when every video is made or dropped; clearing the unfinished ones; the lists mark a goal's rows."""
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

from desk_engine import goals as GO  # noqa: E402
from desk_engine.common import BadRequest  # noqa: E402
from desk_engine.goals import Goals  # noqa: E402


def plan_doc(n=4, fallback=False):
    stories = [dict(id=f"s{k + 1}", place=dict(en="Seattle", zh="西雅图", km=2.0), date="2026-06-11", videos=3,
                    photos=0, panoramas=0, seconds=60.0, aerial=True, thumbs=[], sheet=None, clips=[f"/c/{k}.MP4"])
               for k in range(n)]
    vids = [dict(id=f"v{k + 1}", title=f"Video {k + 1}", kind="film" if k else "history", theme="t", why="w",
                 length_s=45, clips=3, stories=[f"s{k + 1}"], platforms=["youtube", "xiaohongshu"],
                 request=f"Make video {k + 1}", inputs=[f"/c/{k}.MP4"], recipe="photo-story" if not k else "vlog")
            for k in range(n)]
    return dict(kind="vstudio.intake.goal", version=1, id="x", goal="Many videos", prompt="p",
                survey=dict(stories=stories, totals=dict(videos=3 * n), notes=[]), videos=vids,
                planner=dict(provider="none", fallback=fallback), platforms=["youtube", "xiaohongshu"], ui_lang="en")


class FakeIntake:
    """The desk's Intake as goals.py uses it: requests that plan, get applied into project dirs, fail on demand."""

    def __init__(self):
        self.jobs, self.calls = {}, []

    def start(self, prompt, inputs, platforms=None, lang=None, mode=None, recipe=None):
        rid = f"{len(self.jobs) + 1:012x}"
        self.jobs[rid] = dict(id=rid, state="running", prompt=prompt, inputs=inputs, mode=mode, recipe=recipe)
        self.calls.append(("start", rid, prompt))
        return dict(id=rid)

    def applied(self, rid, d):
        self.jobs[rid].update(state="done", applied=[dict(dir=d, name="p", recipe="vlog")])

    def fail(self, rid, code="ai-timeout"):
        self.jobs[rid].update(state="error", error_code=code, error="the model timed out")

    def retry(self, rid):
        self.calls.append(("retry", rid))
        self.jobs[rid].update(state="running", error_code=None)

    def retry_pilot(self, d, provider=None):
        self.calls.append(("retry_pilot", d))

    def go_on(self, rid):
        self.calls.append(("go_on", rid))
        self.jobs[rid]["state"] = "running"

    def apply(self, rid, plan=None, run=True):
        self.calls.append(("apply", rid))

    def stop(self, rid, by="you"):
        self.calls.append(("stop", rid))
        self.jobs[rid].update(state="stopped", stopped_by=by)

    def delete(self, ids):
        self.calls.append(("delete", tuple(ids)))


class FakeHistory:
    def __init__(self):
        self.archived = []

    def archive(self, dirs):
        self.archived += list(dirs)

    def allow_media(self, paths):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="goals-")
        self.intake, self.history = FakeIntake(), FakeHistory()
        self.states = {}                      # project dir -> (state, detail)
        p = mock.patch.object(GO, "project_state", side_effect=lambda d: self.states.get(d, ("running", {})))
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def goals(self, doc=None, survey=None):
        doc = doc or plan_doc()
        return Goals(self.tmp, None, self.intake, self.history, ticker=False,
                     survey=survey or (lambda g, on_event: (on_event(dict(event="stage", stage="probe", i=1, n=3)), doc)[1]))

    def wait(self, G, gid, state):
        for _ in range(200):
            v = G.view(gid)
            # running: also the first videos started (approve sets the state, then its first tick starts them)
            if v["state"] == state and (state != "running" or any(x.get("intake") for x in v["videos"])):
                return G.view(gid)
            time.sleep(0.02)
        self.fail(f"goal never reached {state}: {G.view(gid)['state']} {G.view(gid).get('error')}")

    def proj(self, name):
        d = os.path.join(self.tmp, name)
        os.makedirs(d, exist_ok=True)
        return d


class PlanToGroup(Base):
    def test_survey_plan_card_edits_and_approve(self):
        G = self.goals()
        with self.assertRaises(BadRequest):
            G.start("several videos", [], mode="ask")              # nothing to survey
        gid = G.start("make several videos", ["/Volumes/card"], ["youtube"], "en", "ask")["id"]
        v = self.wait(G, gid, "planned")
        self.assertEqual(v["goal"], "Many videos")
        self.assertEqual(v["counts"]["total"], 4)
        self.assertEqual([x["state"] for x in v["videos"]], ["planned"] * 4)
        self.assertEqual(len(v["survey"]["stories"]), 4)
        self.assertEqual(G.inbox_items()[0]["code"], "goal.inbox")
        # the plan card: rename + drop (the engine's edit_goal rebuilds the requests)
        v = G.edit(gid, [{"op": "rename", "video": "v1", "title": "Space Needle"}, {"op": "drop", "video": "v4"}])
        self.assertEqual(v["videos"][0]["title"], "Space Needle")
        self.assertTrue(v["videos"][3]["planned_out"])
        self.assertEqual(v["counts"]["total"], 3)
        with self.assertRaises(BadRequest):
            G.edit(gid, [{"op": "kind", "video": "v1", "kind": "opera"}])
        v = G.approve(gid)
        self.assertEqual(v["state"], "running")
        self.assertEqual([x["state"] for x in v["videos"]], ["planning", "planning", "planning", "skipped"])
        self.assertEqual(G.inbox_items(), [])
        with self.assertRaises(BadRequest):
            G.edit(gid, [{"op": "drop", "video": "v1"}])       # being made: the plan is fixed

    def test_stock_goal_line_is_marked_for_the_ui_language(self):
        """The rule planner's stock line was shown in the language it was planned in after the UI language changed:
        the view marks it so the UI renders it in its own language; the AI's own line is shown as written."""
        from vstudio.intake.goal import GOAL_LINE
        G = self.goals(dict(plan_doc(), goal=GOAL_LINE["zh"]))
        gid = G.start("make several videos", ["/Volumes/card"], None, "zh", "ask")["id"]
        self.assertEqual(self.wait(G, gid, "planned")["goal_code"], "default")
        G = self.goals()
        gid = G.start("make several videos", ["/Volumes/card"], None, "en", "ask")["id"]
        self.assertIsNone(self.wait(G, gid, "planned")["goal_code"])

    def test_autopilot_approves_and_limits_videos_in_flight(self):
        G = self.goals(plan_doc(5))
        gid = G.start("make several videos", ["/Volumes/card"], None, "en", "autopilot")["id"]
        v = self.wait(G, gid, "running")
        self.assertEqual(v["counts"]["making"], GO.PARALLEL)
        self.assertEqual(v["counts"]["waiting"], 5 - GO.PARALLEL)
        self.assertEqual([c[2] for c in self.intake.calls if c[0] == "start"], [f"Make video {k + 1}" for k in range(3)])
        # the survey's plan came from a model: each video's own planner picks its recipe
        self.assertEqual({j.get("recipe") for j in self.intake.jobs.values()}, {None})
        # one video's request becomes a project: still in flight, so nothing new starts
        rid = v["videos"][0]["intake"]
        d1 = self.proj("p1")
        self.intake.applied(rid, d1)
        v = G.view(G.tick(gid)["id"])
        self.assertEqual(v["videos"][0]["state"], "making")
        self.assertEqual(v["videos"][0]["projects"][0]["dir"], d1)
        self.assertEqual(v["counts"]["waiting"], 2)
        # made: a slot frees up and the next video starts
        self.states[d1] = ("made", {})
        G.tick(gid)
        v = G.view(gid)
        self.assertEqual(v["videos"][0]["state"], "made")
        self.assertEqual(v["videos"][3]["state"], "planning")
        self.assertEqual(v["counts"]["made"], 1)


class FailureAndCompletion(Base):
    def _running(self, n=2):
        G = self.goals(plan_doc(n))
        gid = G.start("make several videos", ["/Volumes/card"], None, "en", "autopilot")["id"]
        self.wait(G, gid, "running")
        return G, gid

    def test_without_a_model_each_video_is_planned_for_its_kinds_recipe(self):
        G = self.goals(plan_doc(2, fallback=True))
        gid = G.start("make several videos", ["/Volumes/card"], None, "en", "autopilot")["id"]
        self.wait(G, gid, "running")
        self.assertEqual([j["recipe"] for j in self.intake.jobs.values()], ["photo-story", "vlog"])

    def test_a_failed_plan_is_retried_once_then_dropped(self):
        G, gid = self._running()
        rid = G.view(gid)["videos"][0]["intake"]
        self.intake.fail(rid)
        v = G.view(G.tick(gid)["id"])["videos"][0]
        self.assertEqual((v["state"], v["attempts"], v["retried"]), ("planning", 2, "ai-timeout"))
        self.assertIn(("retry", rid), self.intake.calls)
        self.intake.fail(rid, "ai-quota")
        v = G.view(G.tick(gid)["id"])["videos"][0]
        self.assertEqual((v["state"], v["reason_code"]), ("dropped", "ai-quota"))

    def test_a_failed_run_is_retried_then_dropped_and_the_goal_finishes(self):
        G, gid = self._running()
        a, b = (x["intake"] for x in G.view(gid)["videos"])
        da, db = self.proj("a"), self.proj("b")
        self.intake.applied(a, da)
        self.intake.applied(b, db)
        G.tick(gid)
        self.states[da] = ("failed", dict(code="tool-ffmpeg"))
        G.tick(gid)
        self.assertIn(("retry_pilot", da), self.intake.calls)
        self.assertEqual(G.view(gid)["videos"][0]["state"], "making")
        G.tick(gid)                                         # still failed after its retry: dropped
        v = G.view(gid)
        self.assertEqual((v["videos"][0]["state"], v["videos"][0]["reason_code"]), ("dropped", "tool-ffmpeg"))
        self.assertEqual(v["state"], "running")
        self.states[db] = ("made", {})
        G.tick(gid)
        v = G.view(gid)
        self.assertEqual(v["state"], "done")
        self.assertEqual((v["counts"]["made"], v["counts"]["dropped"]), (1, 1))
        self.assertTrue(v["finished"])
        # clear the unfinished: its project is archived (files kept), never the made one
        r = G.clear(gid)
        self.assertEqual(self.history.archived, [da])
        self.assertEqual(r["cleared"], dict(requests=0, projects=1))
        self.assertTrue(r["videos"][0]["cleared"])

    def test_a_stalled_video_is_stopped_and_retried(self):
        G, gid = self._running(1)
        rid = G.view(gid)["videos"][0]["intake"]
        G.tick(gid, now=time.time() + GO.STALL_S + 60)
        self.assertIn(("stop", rid), self.intake.calls)
        self.assertEqual(self.intake.jobs[rid]["stopped_by"], "stall")      # the app stopped it, never "by you"
        v = G.view(gid)["videos"][0]
        self.assertEqual((v["state"], v["attempts"]), ("planning", 2))     # a fresh request, its second try
        self.assertNotEqual(v["intake"], rid)

    def test_she_drops_a_video_and_stops_the_goal(self):
        G, gid = self._running(3)
        v = G.video(gid, "v1", "drop")
        self.assertEqual((v["videos"][0]["state"], v["videos"][0]["reason_code"]), ("dropped", "by-you"))
        v = G.stop(gid)
        self.assertEqual(v["state"], "stopped")
        self.assertEqual({x["state"] for x in v["videos"]}, {"dropped"})
        v = G.video(gid, "v2", "retry")                       # a dropped one, once more
        self.assertEqual(v["state"], "running")
        self.assertEqual(v["videos"][1]["state"], "planning")
        # requests that never became projects are deleted when she clears them
        G.video(gid, "v2", "drop")
        G.tick(gid)
        r = G.clear(gid)
        self.assertEqual(r["cleared"]["requests"], 4)          # v2's first request (left behind by Try again) too

    def test_a_video_waiting_for_her_holds_the_goal_and_frees_its_slot(self):
        G, gid = self._running(1)
        rid = G.view(gid)["videos"][0]["intake"]
        d = self.proj("w")
        self.intake.applied(rid, d)
        G.tick(gid)
        self.states[d] = ("you", {})
        G.tick(gid)
        v = G.view(gid)
        self.assertEqual((v["videos"][0]["state"], v["state"], v["counts"]["making"]), ("you", "running", 0))


    def test_a_step_autopilot_could_not_draft_is_retried_then_dropped_but_her_questions_wait(self):
        G, gid = self._running(2)
        a, b = (x["intake"] for x in G.view(gid)["videos"])
        da, db = self.proj("na"), self.proj("nb")
        self.intake.applied(a, da)
        self.intake.applied(b, db)
        G.tick(gid)
        self.states[da] = ("you", dict(blocker="needs-input"))
        self.states[db] = ("you", dict(blocker="consent"))
        G.tick(gid)
        self.assertIn(("retry_pilot", da), self.intake.calls)
        self.assertNotIn(("retry_pilot", db), self.intake.calls)
        G.tick(gid)
        v = G.view(gid)["videos"]
        self.assertEqual((v[0]["state"], v[0]["reason_code"]), ("dropped", "needs-input"))
        self.assertEqual(v[1]["state"], "you")


class Survey(Base):
    def test_a_failed_survey_can_be_tried_again(self):
        calls = []

        def survey(g, on_event):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("ffprobe not found")
            return plan_doc(2)
        G = self.goals(survey=survey)
        gid = G.start("make several videos", ["/Volumes/card"], None, "en", "ask")["id"]
        v = self.wait(G, gid, "failed")
        self.assertEqual(v["error_code"], "tool-ffmpeg")
        self.assertEqual(G.inbox_items()[0]["kind"], "failed")
        G.retry(gid)
        self.wait(G, gid, "planned")

    def test_a_restart_turns_a_survey_in_flight_into_a_failure_and_keeps_running_goals(self):
        G, gid = self.goals(), None
        gid = G.start("make several videos", ["/Volumes/card"], None, "en", "autopilot")["id"]
        self.wait(G, gid, "running")
        other = Goals(self.tmp, None, self.intake, self.history, ticker=False)
        self.assertEqual(other.view(gid)["state"], "running")
        rec = other.goals[gid]
        rec["state"] = "surveying"
        other._save(rec)
        again = Goals(self.tmp, None, self.intake, self.history, ticker=False)
        self.assertEqual((again.view(gid)["state"], again.view(gid)["error_code"]), ("failed", "stopped"))

    def test_rows_of_the_lists_are_marked_with_their_goal(self):
        G = self.goals(plan_doc(1))
        gid = G.start("make several videos", ["/Volumes/card"], None, "en", "autopilot")["id"]
        self.wait(G, gid, "running")
        rid = G.view(gid)["videos"][0]["intake"]
        d = self.proj("m")
        self.intake.applied(rid, d)
        G.tick(gid)
        rows = G.mark([dict(id=rid), dict(id="ffffffffffff")], "id")
        self.assertEqual((rows[0]["goal"], rows[0]["goal_video"]), (gid, "v1"))
        self.assertNotIn("goal", rows[1])
        self.assertEqual(G.mark([dict(dir=d)], "dir")[0]["goal"], gid)
        items = [dict(key=f"plan-{rid}-error"), dict(key="plan-ffffffffffff-error")]
        self.assertEqual([x["key"] for x in G.without_owned(items)], ["plan-ffffffffffff-error"])
        self.assertEqual(len(G.list()["goals"]), 1)
        G.stop(gid)
        G.dismiss(gid)
        self.assertEqual(G.list()["goals"], [])


class Detect(unittest.TestCase):
    def test_her_request_is_a_goal_and_a_single_edit_is_not(self):
        card = tempfile.mkdtemp(prefix="dcim-")
        self.addCleanup(shutil.rmtree, card, True)
        hers = (f"在尝试帮我做多个dji航拍视频的剪辑吧，在{card}，可以先归纳一下，然后几个类似的做视频，可以尝试并行做多个视频，"
                "每个视频的主题可以不同，我可以发视频（youtube和小红书以及B站）")
        self.assertTrue(GO.detect(hers))
        self.assertEqual(GO.paths_in(hers), [card])
        self.assertFalse(GO.detect("把这条剪成小红书竖屏", [card]))


class ProjectState(unittest.TestCase):
    def test_a_project_folder_reads_as_made_failed_or_running(self):
        from desk_mock import record_pilot
        d = tempfile.mkdtemp(prefix="gp-")
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, "project.yaml"), "w") as f:
            f.write("name: x\nrecipe: vlog\n")
        self.assertEqual(GO.project_state(d)[0], "running")          # planned, its first run not started yet
        record_pilot(d, False, "render failed (exit 5): ffmpeg not found")
        st, detail = GO.project_state(d)
        self.assertEqual((st, detail["code"]), ("failed", "tool-ffmpeg"))
        self.assertEqual(GO.project_state(os.path.join(d, "nope"))[0], "failed")


class Api(unittest.TestCase):
    def test_intake_routes_a_goal_request_to_goals(self):
        import server
        from desk_engine.app import Api as A
        from desk_engine.common import EventBus
        card = tempfile.mkdtemp(prefix="dcim-")
        self.addCleanup(shutil.rmtree, card, True)
        with mock.patch.dict(os.environ, {"DESK_ENGINE_MOCK": "1"}):
            eng, _ = server.make_engine(tempfile.mkdtemp(prefix="goal-api-"), EventBus())
        api = A(eng, None, "t", [])
        r = api.route("POST", "/api/intake", {}, dict(prompt=f"make several videos from {card}, each a different theme",
                                                       inputs=[], lang="en"))
        self.assertTrue(r["goal"])
        g = api.route("GET", f"/api/goals/{r['id']}", {}, None)
        self.assertEqual(g["inputs"], [card])
        for _ in range(100):                             # mock mode: no engine survey, a plain failure she can see
            if api.route("GET", f"/api/goals/{r['id']}", {}, None)["state"] == "failed":
                break
            time.sleep(0.02)
        self.assertEqual(api.route("GET", "/api/goals", {}, None)["goals"][0]["state"], "failed")
        one = api.route("POST", "/api/intake", {}, dict(prompt="cut this into a short", inputs=[card], lang="en"))
        self.assertNotIn("goal", one)


if __name__ == "__main__":
    unittest.main()


class OneGroupOneTruth(Base):
    """The group is the one place its videos are followed: what a retry left behind stays the group's (never a loose
    row), rows carry the video's title (never the request's words), a stop the app made is a failure tried again,
    each video's language versions are listed, and only a video the group says waits for her reaches the Inbox."""

    def _running(self, n=2):
        G = self.goals(plan_doc(n))
        gid = G.start("make several videos", ["/Volumes/card"], None, "en", "autopilot")["id"]
        self.wait(G, gid, "running")
        return G, gid

    def test_a_retry_keeps_what_it_left_behind_in_the_group(self):
        G, gid = self._running(1)
        first = G.view(gid)["videos"][0]["intake"]
        self.intake.fail(first, "ai-timeout")
        self.intake.retry = lambda rid: (_ for _ in ()).throw(RuntimeError("cannot"))   # a fresh request instead
        G.tick(gid)
        v = G.view(gid)["videos"][0]
        self.assertNotEqual(v["intake"], first)
        reqs, _dirs = G.owned()
        self.assertEqual(reqs[first], (gid, "v1"))                # the old request is still the group's
        rows = G.mark([dict(id=first, prompt="Title: \"Video 1\". Make a 45-second film")], "id")
        self.assertEqual((rows[0]["goal"], rows[0]["goal_title"]), (gid, "Video 1"))

    def test_a_stop_the_app_made_is_tried_again(self):
        G, gid = self._running(1)
        rid = G.view(gid)["videos"][0]["intake"]
        self.intake.stop(rid, by="stall")
        G.tick(gid)
        v = G.view(gid)["videos"][0]
        self.assertEqual((v["state"], v["attempts"], v["retried"]), ("planning", 2, "stalled"))
        # one she stopped (the request's own Stop) is hers: dropped, Try again brings it back
        rid = v["intake"]
        self.intake.stop(rid)
        G.tick(gid)
        self.assertEqual(G.view(gid)["videos"][0]["reason_code"], "stopped")

    def test_language_versions_and_the_inbox(self):
        G, gid = self._running(1)
        rid = G.view(gid)["videos"][0]["intake"]
        en, zh = self.proj("en"), self.proj("zh")
        self.intake.jobs[rid].update(state="done", applied=[dict(dir=en, name="Video 1 (English)"),
                                                            dict(dir=zh, name="Video 1 (中文)")])
        G.tick(gid)
        self.states[en] = ("running", dict(live=dict(progress=0.5)))
        self.states[zh] = ("you", dict(blocker=None))
        G.tick(gid)
        v = G.view(gid)["videos"][0]
        self.assertEqual([(x["lang"], x["state"]) for x in v["versions"]], [("en", "running"), ("zh", "you")])
        self.assertEqual(v["state"], "making")                     # one version still being made: not hers yet
        hist = [dict(id="a1", dir=en), dict(id="a2", dir=zh), dict(id="o", dir=self.proj("other"))]
        items = [dict(key="k1", project=dict(id="a2"), engine=dict(dir=zh)), dict(key="k2", project=dict(id="a1")),
                 dict(key="k3", project=dict(id="o"))]
        self.assertEqual([x["key"] for x in G.filter_inbox(items, hist)], ["k3"])
        self.states[en] = ("made", {})
        G.tick(gid)
        self.assertEqual(G.view(gid)["videos"][0]["state"], "you")
        self.assertEqual([x["key"] for x in G.filter_inbox(items, hist)], ["k1", "k3"])   # now it waits for her


class SafeToUpdate(Base):
    """She updates the app while her goal runs: a video whose planning the quit cut short is planned again (no try
    used up, never "stopped by you"), and a request an older version left behind is adopted by its video."""

    def test_a_planning_cut_short_by_a_restart_is_planned_again(self):
        G = self.goals(plan_doc(1))
        gid = G.start("make several videos", ["/Volumes/card"], None, "en", "autopilot")["id"]
        self.wait(G, gid, "running")
        rid = G.view(gid)["videos"][0]["intake"]
        self.intake.jobs[rid].update(state="error", error_code="stopped", error="the app was closed while this was being planned")
        G.tick(gid)
        v = G.view(gid)["videos"][0]
        self.assertIn(("retry", rid), self.intake.calls)
        self.assertEqual((v["state"], v["attempts"], v["intake"]), ("planning", 1, rid))

    def test_a_request_left_behind_by_an_older_version_is_adopted(self):
        G = self.goals(plan_doc(1))
        gid = G.start("make several videos", ["/Volumes/card"], None, "en", "autopilot")["id"]
        self.wait(G, gid, "running")
        old = "0" * 11 + "f"
        self.intake.jobs[old] = dict(id=old, state="stopped", prompt="Make video 1", started=time.time(), mode="autopilot")
        again = Goals(self.tmp, None, self.intake, self.history, ticker=False)
        self.assertEqual(again.owned()[0][old], (gid, "v1"))
