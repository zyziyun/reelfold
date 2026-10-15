"""Per-task AI in the desk engine (aichoice.py): the composer's AI rides on the request (its planning runs with
VSTUDIO_LLM_PROJECT_AI), is written into each project it becomes (project.yaml ``ai``, through the real
``vstudio.project model``), a project / request / goal can switch it (running ones from their next AI step), and the
lists show it."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import aichoice as AC  # noqa: E402
from desk_engine import goals as GO  # noqa: E402
from desk_engine import intake as IN  # noqa: E402
from desk_engine.caps import CliRunner  # noqa: E402
from desk_engine.common import BadRequest  # noqa: E402
from desk_engine.history import summarize_project  # noqa: E402

ENGINE = os.environ.get("VSTUDIO_ENGINE_PATH") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
KIMI = {"provider": "kimi", "model": "kimi-k2-0905-preview"}


def make_project(root, name="p"):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "project.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"version": 1, "name": name, "recipe": "talkinghead", "items": [], "answers": {}}, f)
    return d


def real_runner(tmp):
    env = dict(os.environ, PYTHONPATH=os.path.join(ENGINE, "lib"), VSTUDIO_HOME=os.path.join(tmp, "vhome"),
               VSTUDIO_DEFAULT_PERSONA="1")
    for k in [k for k in env if k.startswith("VSTUDIO_LLM_")] + ["VSTUDIO_PROJECT_DIR"]:
        env.pop(k, None)
    return CliRunner(sys.executable, env)


class Clean(unittest.TestCase):
    def test_review_request_is_not_autopilot(self):
        from desk_engine.intake import review_first
        for prompt in ("保留原声，先给选段方案；另建项目", "Plan first, wait for my approval"):
            self.assertTrue(review_first(prompt))
        self.assertFalse(review_first("现在直接制作这条视频"))

    def test_clean(self):
        self.assertEqual(AC.clean(KIMI), KIMI)
        self.assertEqual(AC.clean({"provider": "kimi"}), {"provider": "kimi"})
        self.assertIsNone(AC.clean(None))
        self.assertIsNone(AC.clean({"provider": "default"}))
        for bad in ({"provider": "Kimi!"}, {"provider": "kimi", "model": "a b"}, "kimi", {"provider": 3}):
            with self.assertRaises(BadRequest):
                AC.clean(bad)
        self.assertEqual(json.loads(AC.env(KIMI)[AC.ENV]), KIMI)
        self.assertEqual(AC.env(None), {})


class RealProjectSwitch(unittest.TestCase):
    """The real ``vstudio.project model``: written into project.yaml, resolved by the engine as the project's AI,
    said in the live pane, recorded in the decisions log, shown in the lists."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aichoice-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.runner = real_runner(self.tmp)

    def test_set_and_clear(self):
        d = make_project(self.tmp)
        r = AC.set_project(self.runner, d, KIMI, by="you")
        self.assertEqual(r["ai"], KIMI)
        self.assertEqual((r["resolved"]["provider"], r["resolved"]["model"], r["resolved"]["source"]),
                         ("kimi", "kimi-k2-0905-preview", "project ai"))
        with open(os.path.join(d, "project.yaml"), encoding="utf-8") as f:
            self.assertEqual(yaml.safe_load(f)["ai"], KIMI)
        self.assertEqual(AC.read_project(d), KIMI)
        self.assertEqual(summarize_project(d)["ai"], KIMI)
        with open(os.path.join(d, "desk-agent.jsonl"), encoding="utf-8") as f:
            line = json.loads(f.readlines()[-1])
        self.assertEqual((line["kind"], line["data"]["ai"]), ("ai", KIMI))
        with open(os.path.join(d, "state", "autopilot.jsonl"), encoding="utf-8") as f:
            ev = [json.loads(x) for x in f if '"ai"' in x]
        self.assertEqual((ev[-1]["event"], ev[-1]["provider"], ev[-1]["by"]), ("ai", "kimi", "you"))
        r = AC.set_project(self.runner, d, None, by="chat")
        self.assertIsNone(r["ai"])
        self.assertIsNone(AC.read_project(d))
        self.assertNotIn("ai", summarize_project(d))

    def test_refuses_a_folder_without_a_project(self):
        with self.assertRaises(BadRequest):
            AC.set_project(self.runner, self.tmp, KIMI)


class FakeCli:
    def __init__(self, rec, module, dirs):
        self.rec, self.module, self.dirs = rec, module, dirs

    def text(self, args):
        return "plan apply revise --json-events"

    def events(self, args, on_event, timeout=None, track=None, env_extra=None, on_log=None):
        self.rec.append(("events", self.module, list(args), dict(env_extra or {})))
        return {"plan": {"kind": "vstudio.intake.plan", "projects": [{"name": "talk", "recipe": "talkinghead"}]}}

    def json(self, args, timeout=None, track=None, env_extra=None):
        self.rec.append(("json", self.module, list(args), dict(env_extra or {})))
        if args[0] == "apply":
            return {"projects": [{"dir": d, "name": "talk", "recipe": "talkinghead"} for d in self.dirs]}
        if args[0] == "model":
            ai = None if "--clear" in args else {"provider": args[args.index("--provider") + 1]}
            return {"ok": True, "ai": ai, "resolved": {}}
        return {}


class FakeRunner:
    python = sys.executable
    env = {}

    def __init__(self, dirs):
        self.rec, self.dirs = [], dirs

    def sibling(self, module):
        return FakeCli(self.rec, module, self.dirs)


class RequestAi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aichoice-req-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.d = make_project(self.tmp, "proj")
        self.runner = FakeRunner([self.d])
        self.it = IN.Intake(os.path.join(self.tmp, "desk"), None, self.runner, "real")

    def wait(self, pid):
        import time
        for _ in range(300):
            j = self.it.get(pid)
            if j["state"] != "running":
                return j
            time.sleep(0.02)
        self.fail("never planned")

    def test_plan_runs_with_the_request_ai_and_projects_keep_it(self):
        pid = self.it.start("cut my talk", [], mode="ask", ai=KIMI)["id"]
        j = self.wait(pid)
        self.assertEqual(j["ai"], KIMI)
        plans = [r for r in self.runner.rec if r[0] == "events" and r[2][0] == "plan"]
        self.assertEqual(json.loads(plans[-1][3][AC.ENV]), KIMI)
        self.assertEqual([x["ai"] for x in self.it.open()["items"] if x["id"] == pid], [KIMI])
        self.it.apply(pid, run=False)
        sets = [r[2] for r in self.runner.rec if r[0] == "json" and r[2][0] == "model"]
        self.assertEqual(sets[-1][:3], ["model", "--dir", self.d])
        self.assertIn("kimi", sets[-1])
        # switched after it became a project: the project switches
        self.it.set_ai(pid, {"provider": "deepseek"})
        sets = [r[2] for r in self.runner.rec if r[0] == "json" and r[2][0] == "model"]
        self.assertIn("deepseek", sets[-1])

    def test_plan_first_words_override_autopilot(self):
        pid = self.it.start("先给选段方案", [], mode="autopilot", ai=KIMI)["id"]
        j = self.wait(pid)
        self.assertEqual(j["mode"], "ask")
        self.assertFalse(j.get("applied"))

    def test_no_ai_no_env_and_switch_while_planning(self):
        pid = self.it.start("cut my talk", [], mode="ask")["id"]
        self.wait(pid)
        plans = [r for r in self.runner.rec if r[0] == "events" and r[2][0] == "plan"]
        self.assertNotIn(AC.ENV, plans[-1][3])
        self.it.set_ai(pid, KIMI)
        self.it.revise(pid, "only TikTok")
        self.wait(pid)
        revs = [r for r in self.runner.rec if r[0] == "events" and r[2][0] == "revise"]
        self.assertEqual(json.loads(revs[-1][3][AC.ENV]), KIMI)


class GoalAi(unittest.TestCase):
    def setUp(self):
        from test_goals import FakeHistory, FakeIntake, plan_doc
        self.tmp = tempfile.mkdtemp(prefix="aichoice-goal-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

        class Intake(FakeIntake):
            runner = None

            def start(self, prompt, inputs, platforms=None, lang=None, mode=None, recipe=None, ai=None, group=None):
                r = super().start(prompt, inputs, platforms, lang, mode, recipe, group)
                self.jobs[r["id"]]["ai"] = ai
                return r

            def set_ai(self, rid, ai, by="you"):
                self.calls.append(("set_ai", rid, ai, by))
                self.jobs[rid]["ai"] = ai
        self.intake = Intake()
        p = mock.patch.object(GO, "project_state", side_effect=lambda d: ("running", {}))
        p.start()
        self.addCleanup(p.stop)
        self.G = GO.Goals(self.tmp, None, self.intake, FakeHistory(), ticker=False,
                          survey=lambda g, on_event: plan_doc())

    def running(self, ai):
        import time
        gid = self.G.start("make several videos", ["/Volumes/card"], ["youtube"], "en", "ask", ai=ai)["id"]
        for _ in range(200):
            if self.G.view(gid)["state"] == "planned":
                break
            time.sleep(0.02)
        self.G.approve(gid)
        return gid

    def test_group_ai_reaches_every_video_and_switches(self):
        gid = self.running(KIMI)
        v = self.G.view(gid)
        self.assertEqual(v["ai"], KIMI)
        self.assertTrue(all(x["ai"] == KIMI for x in v["videos"]))
        self.assertTrue(all(j["ai"] == KIMI for j in self.intake.jobs.values()))
        # one video is being made already: its project switches from its next step
        d = make_project(self.tmp, "v1proj")
        g = self.G._get(gid)
        g["videos"][0].update(state="making", projects=[{"dir": d}])
        self.G._save(g)
        with mock.patch.object(AC, "set_project") as sp:
            v = self.G.set_ai(gid, {"provider": "deepseek"})
        self.assertEqual(v["ai"], {"provider": "deepseek"})
        sp.assert_called_once()
        self.assertEqual((sp.call_args[0][1], sp.call_args[0][2], sp.call_args[1]["by"]), (d, {"provider": "deepseek"}, "group"))
        planning = [c for c in self.intake.calls if c[0] == "set_ai"]
        self.assertEqual(len(planning), 2)                                  # v2, v3 still planning
        self.assertTrue(all(c[2] == {"provider": "deepseek"} for c in planning))

    def test_one_video_switches_alone(self):
        gid = self.running(None)
        v = self.G.set_ai(gid, KIMI, video="v2")
        own = {x["id"]: (x["ai"], x["own_ai"]) for x in v["videos"]}
        self.assertEqual(own["v2"], (KIMI, True))
        self.assertEqual(own["v1"], (None, False))
        self.assertIsNone(v["ai"])
        with self.assertRaises(BadRequest):
            self.G.set_ai(gid, KIMI, video="v99")


if __name__ == "__main__":
    unittest.main()
