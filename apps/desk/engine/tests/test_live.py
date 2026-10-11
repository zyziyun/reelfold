"""The live pane's data (desk_engine.live): a job's transcript - the model CLIs' turns the engine captured and the
engine's own stages / log - read from a cursor, redacted on the way out, a ``live`` nudge on the event bus while it
grows; the request's planner child gets VSTUDIO_AGENT_LOG and its stderr lands in the transcript; a project run's
agent file + run log are read from where the current run started."""
import json
import os
import queue
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _isolate  # noqa: E402,F401

from desk_engine import live as L  # noqa: E402
from desk_engine import pilot as P  # noqa: E402
from desk_engine.caps import CliRunner  # noqa: E402
from desk_engine.common import EventBus, Registry, write_json  # noqa: E402
from desk_mock import MockEngine, make_api  # noqa: E402


def wait_for(fn, limit=20, step=0.05):
    t0 = time.time()
    while time.time() - t0 < limit:
        v = fn()
        if v:
            return v
        time.sleep(step)
    raise AssertionError("timed out")


def jl(path, *recs):
    with open(path, "a", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


class ReadTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="live-")

    def test_project_run_merges_agent_lines_and_run_log_in_time_order(self):
        agent = os.path.join(self.d, L.LIVE_NAME)
        log = os.path.join(self.d, P.LOG)
        jl(agent, dict(at=5.0, src="agent", kind="say", text="old run", pid=1))      # an earlier run
        with open(log, "w") as f:
            f.write('{"event": "project-end", "ts": 4.0, "exit_code": 0}\n')
        write_json(os.path.join(self.d, P.REC), dict(pid=None, offset=os.path.getsize(log),
                                                     agent_offset=os.path.getsize(agent)))
        jl(log, dict(event="run-start", ts=10.0, jobs=["s01", "s02"]), dict(event="progress", ts=10.5),
           dict(event="stage-start", ts=11.0, job="s01", stage="asr"))
        with open(log, "a") as f:
            f.write("ffmpeg: frame=  120 fps=60 key OPENAI_API_KEY=sk-proj-" "abcdefghijklmnopqrstu\n")
        jl(agent, dict(at=10.6, src="agent", kind="turn", text="segment_plan · claude-code", turn="9-1", pid=9),
           dict(at=10.7, src="agent", kind="say", text="mail me@example.com", turn="9-1", pid=9))
        r = L.read(L.project_sources(self.d))
        texts = [x["text"] for x in r["lines"]]
        self.assertNotIn("old run", texts)                                   # the current run only
        self.assertEqual(texts[0], "run-start · 2 jobs")
        self.assertEqual([x["kind"] for x in r["lines"]][:3], ["event", "turn", "say"])
        self.assertEqual(texts[-1].count("[redacted"), 1)                    # the raw log is redacted too
        self.assertIn("[email]", texts[2])
        self.assertTrue(all("pid" not in x for x in r["lines"]))
        self.assertFalse(any(x["text"].startswith("progress") for x in r["lines"]))   # counters are not log lines
        self.assertEqual(r["lines"][-2]["data"], dict(event="stage-start", job="s01", stage="asr"))
        # from the cursor: only what came after
        self.assertEqual(L.read(L.project_sources(self.d), r["cursor"])["lines"], [])
        jl(agent, dict(at=12.0, src="agent", kind="result", text="900 in · 64 out", turn="9-1"))
        more = L.read(L.project_sources(self.d), r["cursor"])
        self.assertEqual([x["text"] for x in more["lines"]], ["900 in · 64 out"])

    def test_a_half_written_line_waits_for_its_end(self):
        p = os.path.join(self.d, "r.live.jsonl")
        with open(p, "w") as f:
            f.write(json.dumps(dict(at=1, src="agent", kind="say", text="a")) + "\n" + '{"at": 2, "src": "ag')
        r = L.read([(p, "jsonl", 0)])
        self.assertEqual(len(r["lines"]), 1)
        with open(p, "a") as f:
            f.write('ent", "kind": "say", "text": "b"}\n')
        self.assertEqual([x["text"] for x in L.read([(p, "jsonl", 0)], r["cursor"])["lines"]], ["b"])

    def test_a_long_transcript_opens_at_its_end(self):
        p = os.path.join(self.d, "big.live.jsonl")
        with open(p, "w") as f:
            for i in range(6000):
                f.write(json.dumps(dict(at=i, src="agent", kind="say", text=f"line {i} " + "x" * 60)) + "\n")
        r = L.read([(p, "jsonl", 0)])
        self.assertTrue(r["lines"][-1]["text"].startswith("line 5999"))
        self.assertLess(len(r["lines"]), 6000)
        self.assertFalse(r["more"])

    def test_bad_cursor_parts_are_ignored(self):
        p = os.path.join(self.d, "c.live.jsonl")
        jl(p, dict(at=1, src="engine", kind="stage", text="scan · 3 files"))
        self.assertEqual(len(L.read([(p, "jsonl", 0)], "x:1,9:99")["lines"]), 1)

    def test_intake_stage_words(self):
        self.assertEqual(L.intake_stage_text(dict(stage="faces", file="DJI_0438.MP4", i=16, n=27)),
                         "faces · DJI_0438.MP4 · 16/27")
        self.assertEqual(L.intake_stage_text(dict(stage="transcribe", file="a.mp4", done_s=125, total_s=600)),
                         "transcribe · a.mp4 · 2:05 / 10:00")
        self.assertEqual(L.intake_stage_text(dict(stage="model", provider="claude-code")), "model · claude-code")


class HubTest(unittest.TestCase):
    def test_a_watched_file_that_grows_is_announced(self):
        d = tempfile.mkdtemp(prefix="livehub-")
        p = os.path.join(d, "x.live.jsonl")
        bus = EventBus()
        q = bus.subscribe()
        hub = L.LiveHub(bus)
        hub.watch("request:abcdefabcdef", [(p, "jsonl", 0)])
        jl(p, dict(at=1, src="agent", kind="say", text="hi"))
        ev = q.get(timeout=5)
        self.assertEqual((ev["type"], ev["key"]), ("live", "request:abcdefabcdef"))
        with self.assertRaises(queue.Empty):                                 # quiet while nothing changes
            q.get(timeout=1)


class ChildEnvTest(unittest.TestCase):
    def test_the_planner_child_gets_the_transcript_path_and_its_stderr_is_kept(self):
        d = tempfile.mkdtemp(prefix="livechild-")
        mod = os.path.join(d, "fake_planner.py")
        with open(mod, "w") as f:
            f.write("import json, os, sys\n"
                    "from vstudio import agentlog\n"
                    "agentlog.emit('say', 'hello from the child')\n"
                    "print('reading 3 files', file=sys.stderr, flush=True)\n"
                    "print(json.dumps({'event': 'stage', 'stage': 'scan'}), flush=True)\n"
                    "print(json.dumps({'event': 'done', 'plan': {}}), flush=True)\n")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([d, os.environ.get("PYTHONPATH", "")]))
        r = CliRunner(sys.executable, env, module="fake_planner")
        path = os.path.join(d, "r.live.jsonl")
        logs, evs = [], []
        r.events([], evs.append, timeout=60, env_extra={L.AGENT_ENV: path}, on_log=logs.append)
        self.assertEqual(logs, ["reading 3 files"])
        self.assertEqual(evs, [dict(event="stage", stage="scan")])
        self.assertEqual([x["text"] for x in L.read([(path, "jsonl", 0)])["lines"]], ["hello from the child"])
        self.assertNotIn(L.AGENT_ENV, r.env)                                  # per call, not the runner's env


class RouteTest(unittest.TestCase):
    """GET /api/live/request/<id> while the (test) planner plans: stage lines + the streamed model turn, redacted."""

    def test_request_transcript_streams_while_it_plans(self):
        tmp = tempfile.mkdtemp(prefix="liveroute-")
        bus = EventBus()
        q = bus.subscribe()
        engine = MockEngine(tmp, Registry(tmp), bus, step=0.05)
        api = make_api(engine, bus, "t" * 48, ["app://desk"])
        video = os.path.join(tmp, "talk.mp4")
        with open(video, "wb") as f:
            f.write(b"\0" * 64)
        os.environ["DESK_MOCK_SECRET"] = "1"
        try:
            pid = api.intake.start("把这条剪成 2 条切片", [video], mode="ask")["id"]
            first = api.route("GET", f"/api/live/request/{pid}", {}, None)
            self.assertEqual(first["key"], f"request:{pid}")
            wait_for(lambda: (api.intake.jobs.get(pid) or {}).get("state") == "done")
            seen_nudge = False
            for _ in range(5000):
                if q.empty():
                    break
                if q.get_nowait()["type"] == "live":
                    seen_nudge = True
                    break
            self.assertTrue(seen_nudge)
            r = api.route("GET", f"/api/live/request/{pid}", {"cursor": [first["cursor"]]}, None)
            all_lines = first["lines"] + r["lines"]
            kinds = [(x["src"], x["kind"]) for x in all_lines]
            for k in (("engine", "stage"), ("agent", "turn"), ("agent", "prompt"), ("agent", "thinking"),
                      ("agent", "tool"), ("agent", "tool-result"), ("agent", "say"), ("agent", "result"),
                      ("engine", "done")):
                self.assertIn(k, kinds)
            blob = json.dumps(all_lines)
            self.assertNotIn("PLANTEDSECRET", blob)
            self.assertFalse(r["running"])
        finally:
            os.environ.pop("DESK_MOCK_SECRET", None)
            engine.shutdown()

    def test_bad_ids_and_cursors_are_refused(self):
        tmp = tempfile.mkdtemp(prefix="liveroute2-")
        bus = EventBus()
        engine = MockEngine(tmp, Registry(tmp), bus, step=0.01)
        api = make_api(engine, bus, "t" * 48, ["app://desk"])
        from desk_engine.common import BadRequest
        for path, q in (("/api/live/request/../x", {}), ("/api/live/nope/abcdefabcdef", {}),
                        ("/api/live/request/abcdefabcdef", {"cursor": ["; rm"]})):
            with self.assertRaises(BadRequest):
                api.route("GET", path, q, None)
        engine.shutdown()


if __name__ == "__main__":
    unittest.main()
