"""Chat editing against the real engine (this monorepo's lib/): the capability probe sees the extended output
commands, and ``ask`` -> ``show`` returns the new turn (the desk must read the engine's transcript, P0-2)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import outputs as OU  # noqa: E402
from desk_engine.caps import CliRunner  # noqa: E402
from desk_engine.common import Registry  # noqa: E402
from desk_engine.history import History  # noqa: E402

TESTS = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.environ.get("VSTUDIO_ENGINE_PATH") or os.path.abspath(os.path.join(TESTS, "..", "..", "..", ".."))
HAVE = os.path.isdir(os.path.join(ENGINE, "lib", "vstudio", "project")) and shutil.which("ffmpeg")


class ProbeTest(unittest.TestCase):
    def test_has_word(self):
        txt = "{list,show,edit,render,undo,redo,revert,ai,chat,effects}  [--context CONTEXT] [--chat-x]"
        for w in ("show", "chat", "--context", "revert"):
            self.assertTrue(OU._has_word(txt, w), w)
        self.assertFalse(OU._has_word("[--contexts X] chat-x", "--context"))
        self.assertFalse(OU._has_word("chat-x", "chat"))


@unittest.skipUnless(HAVE, "engine repo or ffmpeg not found")
class RealChatTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        watch = os.path.join(self.root, "demos")
        self.work = os.path.join(watch, "talk")
        os.makedirs(os.path.join(self.work, "final"))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x568:d=3:r=30",
                        "-f", "lavfi", "-i", "sine=f=220:d=3", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", os.path.join(self.work, "final", "clip.mp4")], check=True)
        with open(os.path.join(self.work, "REPORT.md"), "w") as f:
            f.write("# clip\n")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(ENGINE, "lib"), TESTS]),
                   VSTUDIO_OUTPUT_TRANSCRIBER="_fake_asr:words", VSTUDIO_LLM_OUTPUT_EDIT_PROVIDER="none",
                   VSTUDIO_HOME=os.path.join(self.root, "home"))
        for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VSTUDIO_LLM_PROVIDER"):
            env.pop(k, None)
        self.patch = mock.patch.dict(os.environ, {"DESK_HISTORY_WATCH": watch, "VSTUDIO_HOME": env["VSTUDIO_HOME"]})
        self.patch.start()
        subprocess.run([sys.executable, "-c", f"from vstudio.project import works; works.adopt({self.work!r})"],
                       env=env, check=True)
        data = os.path.join(self.root, "desk")
        self.h = History(data, Registry(data))
        self.env = env
        self.o = OU.Outputs(data, self.h, CliRunner(sys.executable, env))
        self.item = next(r["id"] for r in self.h.list()["items"] if r["dir"] == self.work)

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.root, True)

    def fake_cli(self):
        """Run the Python CLI fixtures directly, including on Windows without POSIX shebang support."""
        fake = os.path.join(ENGINE, "tests", "fixtures", "fake_cli")
        hook = os.path.join(self.root, "hook")
        os.makedirs(hook, exist_ok=True)
        with open(os.path.join(hook, "sitecustomize.py"), "w", encoding="utf-8") as f:
            f.write("import os, sys\nfrom vstudio import llm\n"
                    f"_fakes = {{name: os.path.join({fake!r}, name) for name in ('claude', 'codex')}}\n"
                    "_find, _argv = llm.find_cli, llm.cli_argv\n"
                    "llm.find_cli = lambda name, opts=None: _fakes.get(name) or _find(name, opts)\n"
                    "llm.cli_argv = lambda exe, windows=None: [sys.executable, exe] if exe in _fakes.values() else _argv(exe, windows)\n")
        self.env["PYTHONPATH"] = hook + os.pathsep + self.env["PYTHONPATH"]

    def test_probe_sees_the_extended_commands(self):
        self.assertTrue(self.o.real())
        self.assertTrue(self.o._ext, "the engine has revert / chat / --context: the probe must see them")

    def test_ask_then_show_returns_the_new_turn(self):
        clip = self.o.clips(self.item)["clips"][0]["id"]
        before = self.o.show(self.item, clip)
        self.assertEqual(before["engine"], "real")
        r = self.o.ask(self.item, clip, "1.1倍速")
        self.assertTrue(r.get("turn"))
        after = self.o.show(self.item, clip)
        self.assertIn(r["turn"], [t["id"] for t in after["chat"]])
        self.assertEqual(len(after["chat"]), len(before["chat"]) + 1)

    def test_model_failure_rules_turn_is_shown(self):
        """A model that fails -> the desk rules answer; that turn must land in the transcript ``show`` reads."""
        self.env.update(VSTUDIO_LLM_OUTPUT_EDIT_PROVIDER="anthropic", VSTUDIO_LLM_FALLBACK="")
        clip = self.o.clips(self.item)["clips"][0]["id"]
        before = self.o.show(self.item, clip)
        r = self.o.ask(self.item, clip, "去掉开头 1 秒")
        self.assertEqual(r.get("provider"), "rules")
        self.assertIn(r["turn"], [t["id"] for t in self.o.show(self.item, clip)["chat"]])
        self.assertEqual(len(self.o.show(self.item, clip)["chat"]), len(before["chat"]) + 1)

    def test_ask_with_a_live_id_writes_its_steps_and_the_model_stream(self):
        """The chat bubble's progress: /ask {live} -> the engine's steps (start, read, think, ..., done) and the model
        CLI's own stream-json lines (thinking, tool call, result) in the request's transcript, redacted; a model answer
        that is not {ops} falls back to the rules (a step of its own), never a silent stop."""
        from desk_engine import live as L
        self.fake_cli()
        self.env.update(VSTUDIO_LLM_OUTPUT_EDIT_PROVIDER="claude-code", VSTUDIO_LLM_FALLBACK="")
        clip = self.o.clips(self.item)["clips"][0]["id"]
        r = self.o.ask(self.item, clip, "1.1倍速", live="abcdef012345")
        self.assertTrue(r.get("turn"))
        self.assertFalse(self.o.asking("abcdef012345"))
        lines = L.read([(self.o.live_path("abcdef012345"), "jsonl", 0)])["lines"]
        stages = [x["data"]["stage"] for x in lines if x["src"] == "engine" and x["kind"] == "stage"]
        self.assertEqual(stages[:3], ["start", "read", "think"])
        self.assertEqual(stages[-1], "done")
        kinds = {(x["src"], x["kind"]) for x in lines}
        for k in (("agent", "turn"), ("agent", "thinking"), ("agent", "tool"), ("agent", "result")):
            self.assertIn(k, kinds)
        self.assertNotIn("SECRETSECRET", json.dumps(lines))
        with self.assertRaises(Exception):
            self.o.ask(self.item, clip, "1.1倍速", live="../etc")
        self.assertIsNone(self.o.live_path("nope"))

    def test_a_fallback_is_said_in_the_log_and_kept_with_the_turn(self):
        """The AI she picked (Claude Code) fails, the route's fallback (Codex) answers: the live transcript says
        "claude-code failed (...) -> trying codex", the reply and its turn carry {from, to, code} (the footer words
        it) - never a silent switch."""
        from desk_engine import live as L
        self.fake_cli()
        self.env.update(VSTUDIO_LLM_OUTPUT_EDIT_PROVIDER="claude-code", VSTUDIO_LLM_OUTPUT_EDIT_FALLBACK="codex",
                        FAKE_CLI_FAIL="1", FAKE_CLI_REPLY=json.dumps({"ops": [{"op": "speed", "value": 1.1}],
                                                                      "summary": "faster"}))
        clip = self.o.clips(self.item)["clips"][0]["id"]
        r = self.o.ask(self.item, clip, "1.1倍速", live="abcdef012346")
        self.assertEqual(r["provider"], "codex")
        self.assertEqual((r["fallback"]["from"], r["fallback"]["to"]), ("claude-code", "codex"))
        turn = next(t for t in self.o.show(self.item, clip)["chat"] if t["id"] == r["turn"])
        self.assertEqual((turn["provider"], turn["fallback"]["from"], turn["fallback"]["to"]), ("codex", "claude-code", "codex"))
        self.assertTrue(turn["fallback"]["code"])
        lines = L.read([(self.o.live_path("abcdef012346"), "jsonl", 0)])["lines"]
        fb = [x for x in lines if x["kind"] == "fallback"]
        self.assertEqual(len(fb), 1)
        self.assertEqual((fb[0]["src"], fb[0]["data"]["from"], fb[0]["data"]["to"]), ("engine", "claude-code", "codex"))
        self.assertIn("claude-code failed", fb[0]["text"])


if __name__ == "__main__":
    unittest.main()
