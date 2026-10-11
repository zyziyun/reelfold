"""「Try again」 on a failed project re-runs what failed, on the real engine.

0.2.7: the Studio's Try again (``POST /api/pilot/retry`` -> ``Intake.retry_pilot``) spawned
``vstudio.project run --pilot 1`` even for a project made on autopilot, and the run replayed the old failure in the
same second with no stage started: the re-plan put the failed job back to "planned" while its failed stage row kept
the same key, so the batch ended the job as failed at once. A failed pilot of an ask-first project was paused, and
``run`` without ``--resume`` ended at once too.

Here a project's ``lint`` stage fails while a marker file exists (a test-only ``sitecustomize`` hook in the engine
subprocess); the marker goes, Try again must start the failed stage and get past it."""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _isolate  # noqa: E402,F401

from desk_engine import intake as IN  # noqa: E402
from desk_engine import pilot as P  # noqa: E402
from desk_engine.caps import CliRunner  # noqa: E402
from desk_engine.common import read_json  # noqa: E402

HOOK = '''import os
_m = os.environ.get("TRYAGAIN_FAIL_WHILE")
if _m:
    from vstudio.project.adapters import preproduction as _pp
    _lint = _pp.lint

    def lint(*a, **k):
        if os.path.exists(_m):
            raise RuntimeError("No such filter: 'nope' (test failure)")
        return _lint(*a, **k)
    _pp.lint = lint
'''


def events(d, offset=0):
    with open(os.path.join(d, P.LOG), "rb") as f:
        f.seek(offset)
        out = []
        for ln in f.read().decode("utf-8", "replace").splitlines():
            try:
                ev = json.loads(ln)
            except ValueError:
                continue
            if isinstance(ev, dict) and ev.get("event"):
                out.append(ev)
        return out


class TryAgainArgsTest(unittest.TestCase):
    """Which command Try again starts (no run)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tryargs-")
        self.spawned = []
        self._spawn = P.spawn
        P.spawn = lambda python, env, d, provider=None, bus=None, args=None: self.spawned.append((d, args)) or {}
        self.it = IN.Intake(os.path.join(self.tmp, "desk"), None, CliRunner(sys.executable, dict(os.environ)), "real")
        self.it._need_engine = lambda: None

    def tearDown(self):
        P.spawn = self._spawn

    def project(self, autopilot, rec_args=None):
        d = os.path.join(self.tmp, f"p{len(os.listdir(self.tmp))}")
        os.makedirs(d)
        with open(os.path.join(d, "project.yaml"), "w", encoding="utf-8") as f:
            f.write("name: p\nrecipe: vlog\n" + ("autopilot:\n  'on': true\n" if autopilot else ""))
        if rec_args:
            with open(os.path.join(d, P.REC), "w", encoding="utf-8") as f:
                json.dump(dict(pid=None, exit=1, args=rec_args), f)
        return d

    def test_retry_of_an_autopilot_project_runs_on_autopilot_and_resumes(self):
        d = self.project(True, rec_args=["-m", "vstudio.project", "run", "--dir", "x", "--pilot", "1", "--json-events"])
        self.it.retry_pilot(d)
        (_d, args), = self.spawned
        self.assertIn("--autopilot", args)
        self.assertNotIn("--pilot", args)
        self.assertIn("--resume", args)

    def test_retry_of_an_ask_first_project_is_a_resumed_pilot(self):
        d = self.project(False)
        self.it.retry_pilot(d, "codex")
        (_d, args), = self.spawned
        self.assertEqual(args[args.index("--pilot") + 1], "1")
        self.assertIn("--resume", args)
        self.assertNotIn("--autopilot", args)

    def test_resume_never_replays_a_pilot_on_an_autopilot_project(self):
        # her 0.2.7 project: made on autopilot, the record says `run --pilot 1` (left by the old Try again)
        d = self.project(True, rec_args=["-m", "vstudio.project", "run", "--dir", "x", "--pilot", "1", "--json-events"])
        self.it.resume_pilot(d)
        (_d, args), = self.spawned
        self.assertIn("--autopilot", args)
        self.assertNotIn("--pilot", args)
        self.assertIn("--resume", args)

    def test_resume_keeps_the_recorded_command_and_resumes_it(self):
        rec = ["-m", "vstudio.project", "run", "--dir", "x", "--pilot", "1", "--json-events"]
        d = self.project(False, rec_args=rec)
        self.it.resume_pilot(d)
        (_d, args), = self.spawned
        self.assertEqual(args[1:], rec + ["--resume"])
        self.spawned.clear()
        rec2 = ["-m", "vstudio.project", "resume", "--dir", "x", "--json-events", "--confirm-pilot"]
        d2 = self.project(False, rec_args=rec2)
        self.it.resume_pilot(d2)
        (_d, args), = self.spawned
        self.assertEqual(args[1:], rec2)


@unittest.skipIf(os.name == "nt", "the hook path is POSIX-only in this test")
class TryAgainRealEngineTest(unittest.TestCase):
    """A failed render-like stage, then Try again through ``Intake.retry_pilot`` with the real spawn + engine."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tryagain-")
        hook = os.path.join(self.tmp, "hook")
        os.makedirs(hook)
        with open(os.path.join(hook, "sitecustomize.py"), "w", encoding="utf-8") as f:
            f.write(HOOK)
        self.marker = os.path.join(self.tmp, "FAIL")
        open(self.marker, "w").close()
        self.env = dict(os.environ, PYTHONPATH=os.pathsep.join([hook, os.environ.get("PYTHONPATH", "")]),
                        TRYAGAIN_FAIL_WHILE=self.marker)
        for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            self.env.pop(k, None)
        self.runner = CliRunner(sys.executable, self.env)
        self.it = IN.Intake(os.path.join(self.tmp, "desk"), None, self.runner, "real")

    def new(self, name, autopilot):
        d = os.path.join(self.tmp, name)
        cli = self.runner.sibling("vstudio.project")
        cli.json(["new", "--recipe", "preproduction", "--dir", d, "--json"], timeout=120)
        if autopilot:
            cli.json(["autopilot", "--dir", d, "--on", "--no-judge", "--json"], timeout=120)
        return d

    def wait_run(self, d):
        for _ in range(1200):
            rec = read_json(os.path.join(d, P.REC), None) or {}
            if rec.get("pid") and rec.get("exit") is not None:
                return rec
            time.sleep(0.05)
        self.fail("the run never ended")

    def status(self, d):
        return self.runner.sibling("vstudio.project").json(["status", "--dir", d, "--json"], timeout=120)

    def check(self, d, autopilot):
        self.it._spawn_pilot(d, autopilot=autopilot)                          # the project's first run
        rec = self.wait_run(d)
        first = events(d)
        self.assertIn("stage-start", [e["event"] for e in first])
        fail = [e for e in first if e["event"] == "job-done"]
        self.assertEqual(fail[-1]["state"], "failed")
        self.assertEqual([i["state"] for i in self.status(d)["items"]], ["failed"])
        os.remove(self.marker)                                                # she fixed it (a new build)
        self.it.retry_pilot(d)                                                # Studio: Try again
        time.sleep(0.05)
        rec2 = self.wait_run(d)
        self.assertNotEqual(rec2["pid"], rec["pid"])
        self.assertEqual("--autopilot" in rec2["args"], autopilot)
        self.assertEqual("--pilot" in rec2["args"], not autopilot)
        again = events(d, rec2["offset"])
        started = [e["stage"] for e in again if e["event"] == "stage-start"]
        self.assertIn("lint", started)                                        # the failed stage ran again
        self.assertNotIn("draft", started)                                    # the done one is a cache hit
        self.assertNotIn("failed", [e["state"] for e in again if e["event"] == "job-done"])
        self.assertNotEqual([i["state"] for i in self.status(d)["items"]], ["failed"])

    def test_autopilot_project(self):
        self.check(self.new("auto", True), True)

    def test_ask_first_project_whose_failed_pilot_paused_the_batch(self):
        self.check(self.new("ask", False), False)


if __name__ == "__main__":
    unittest.main()
