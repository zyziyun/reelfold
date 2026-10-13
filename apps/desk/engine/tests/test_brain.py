"""The editor brain on the desk's side (``Brain``) over the real ``vstudio.brain`` CLI: computed in the background on
the first GET, then cached; her template / shot / proposal answers go through the engine (a template of another recipe
and a wrong confirm code are refused); nothing is spent."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _isolate  # noqa: E402,F401

from desk_engine.brain import Brain  # noqa: E402
from desk_engine.caps import CliRunner  # noqa: E402
from desk_engine.common import BadRequest  # noqa: E402

ENGINE = os.environ.get("VSTUDIO_ENGINE_PATH") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
ITEM = "abcdefabcdef"


class FakeHistory:
    def __init__(self, d):
        self.d = d

    def find(self, item, **_kw):
        return dict(id=item, dir=self.d, kind="project")


class Bus:
    def __init__(self):
        self.events = []

    def publish(self, kind, **kw):
        self.events.append(dict(kind=kind, **kw))


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class BrainRealEngineTest(unittest.TestCase):
    def test_compute_change_and_decide(self):
        tmp = tempfile.mkdtemp(prefix="brain-")
        env = dict(os.environ, PYTHONPATH=os.path.join(ENGINE, "lib"), VSTUDIO_HOME=os.path.join(tmp, "vhome"),
                   VSTUDIO_CACHE=os.path.join(tmp, "cache"), VSTUDIO_LLM_PROVIDER="none")
        clips = []
        for k, src in enumerate(("testsrc2=size=320x180:rate=30", "mandelbrot=size=320x180:rate=30")):
            c = os.path.join(tmp, f"clip{k}.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", src, "-t", "6", "-pix_fmt", "yuv420p", c],
                           check=True)
            clips.append(c)
        d = os.path.join(tmp, "proj")
        cli = [sys.executable, "-m", "vstudio.project"]
        subprocess.run(cli + ["new", "--recipe", "vlog", "--dir", d, "--json", "--input", f"footage={clips[0]}",
                              "--input", f"footage={clips[1]}"], env=env, check=True, capture_output=True)
        bus = Bus()
        b = Brain(FakeHistory(d), CliRunner(sys.executable, env), bus)
        first = b.get(ITEM)
        self.assertTrue(first["supported"])
        self.assertIn(first["state"], ("computing", "ready"))
        t0 = time.time()
        doc = first
        while doc["state"] == "computing" and time.time() - t0 < 300:
            time.sleep(0.5)
            doc = b.get(ITEM)
        self.assertEqual(doc["state"], "ready", doc.get("error"))
        self.assertTrue(any(e["kind"] == "brain" and e["state"] == "ready" for e in bus.events))
        brain = doc["doc"]
        self.assertEqual(brain["template"]["recipe"], "vlog")
        self.assertTrue(brain["plan"]["shots"])
        self.assertTrue(all("reason" in x for x in brain["decisions"]))
        out = b.template(ITEM, "beat-short")
        self.assertEqual(out["doc"]["template"]["template"], "beat-short")
        self.assertEqual(out["doc"]["template"]["by"], "her")
        with self.assertRaises(BadRequest):
            b.template(ITEM, "th-refined")                 # another recipe: refused by the engine
        sid = next(r["id"] for r in out["doc"]["plan"]["shots"] if not r["skip"])
        out = b.shot(ITEM, sid, {"transition": "cut"})
        self.assertEqual(next(r for r in out["doc"]["plan"]["shots"] if r["id"] == sid)["by"], "her")
        with self.assertRaises(BadRequest):
            b.shot(ITEM, sid, {"look": "glitch"})
        props = out["doc"]["proposals"]
        if props:
            g = props[0]
            with self.assertRaises(BadRequest):
                b.gen(ITEM, g["id"], "approve", "000000" if g["code"] != "000000" else "111111")
            got = b.gen(ITEM, g["id"], "skip")
            self.assertEqual(next(x for x in got["doc"]["proposals"] if x["id"] == g["id"])["status"], "skipped")
        with self.assertRaises(BadRequest):
            b.gen(ITEM, "g12345678", "approve")             # approve needs the code

    def test_generation_goes_through_the_spend_gate(self):
        """Pricing sends nothing; without the service's key the real Kling adapter is refused by the gate (her click
        gets the Create code back, nothing starts); a take that does not exist cannot be placed; the clip timeline's
        shots answer even before the first render."""
        import yaml
        tmp = tempfile.mkdtemp(prefix="brain-gate-")
        env = {k: v for k, v in os.environ.items() if k not in ("KLING_MCP_TOKEN", "MINIMAX_API_KEY", "GEMINI_API_KEY")}
        env.update(PYTHONPATH=os.path.join(ENGINE, "lib"), VSTUDIO_HOME=os.path.join(tmp, "vhome"),
                   VSTUDIO_CACHE=os.path.join(tmp, "cache"), VSTUDIO_LLM_PROVIDER="none")
        clips = []
        for k, src in enumerate(("testsrc2=size=320x180:rate=30", "mandelbrot=size=320x180:rate=30")):
            c = os.path.join(tmp, f"clip{k}.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", src, "-t", "6", "-pix_fmt", "yuv420p", c],
                           check=True)
            clips.append(c)
        d = os.path.join(tmp, "proj")
        subprocess.run([sys.executable, "-m", "vstudio.project", "new", "--recipe", "vlog", "--dir", d, "--json",
                        "--input", f"footage={clips[0]}", "--input", f"footage={clips[1]}"], env=env, check=True,
                       capture_output=True)
        py = os.path.join(d, "project.yaml")
        with open(py) as f:
            data = yaml.safe_load(f)
        data["prompt"] = "Make a 90-second calm film from these clips."   # far more than 12 s: "more shots"
        with open(py, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True)
        spawned = []
        b = Brain(FakeHistory(d), CliRunner(sys.executable, env), Bus(), spawn=lambda *a, **k: spawned.append(a))
        doc = b.get(ITEM)
        t0 = time.time()
        while doc["state"] == "computing" and time.time() - t0 < 300:
            time.sleep(0.5)
            doc = b.get(ITEM)
        props = [p for p in doc["doc"]["proposals"] if p["kind"] != "cover"]
        self.assertTrue(props, doc["doc"]["proposals"])
        g = props[0]
        est = b.estimate(ITEM, g["id"])
        self.assertEqual([c["code"] for c in est["codes"]], ["create.provider-not-ready"])
        self.assertEqual(est["lines"][0]["provider"], "kling-mcp")
        self.assertEqual(len(est["confirm_code"]), 8)
        from desk_engine.create import Refused
        with self.assertRaises(Refused) as e:
            b.generate(ITEM, g["id"], est["id"], est["confirm_code"], est["max_cny"], g["code"])
        self.assertEqual(e.exception.doc["code"], "create.provider-not-ready")
        self.assertEqual(b.get(ITEM)["generating"], {})
        self.assertFalse(os.path.exists(os.path.join(d, "state", "brain", "gen", "spend.jsonl")))
        with self.assertRaises(BadRequest):
            b.place(ITEM, g["id"])                          # nothing generated: nothing to place
        self.assertEqual(spawned, [])
        shots = b.shots(ITEM, "")
        self.assertTrue(shots["supported"])
        self.assertEqual(shots["shots"], [])

    def test_not_a_project(self):
        tmp = tempfile.mkdtemp(prefix="brain-")
        self.assertFalse(Brain(FakeHistory(tmp), None).get(ITEM)["supported"])


if __name__ == "__main__":
    unittest.main()
