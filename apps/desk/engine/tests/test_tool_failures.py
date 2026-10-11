"""A render that fails on a missing / broken external tool (Node.js for HyperFrames, ffmpeg) gets its own failure
code + fix key instead of "Part of Reelfold didn't start"; the capabilities document reports tool health."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import caps as CP  # noqa: E402
from desk_engine import pilot as PI  # noqa: E402
from desk_engine.common import write_json  # noqa: E402

DYLD = ("RuntimeError: export.py exit 1: dyld[8123]: Library not loaded: /opt/homebrew/opt/simdjson/lib/"
        "libsimdjson.29.dylib  Referenced from: <0A1B> /opt/homebrew/Cellar/node/25.6.1/bin/node")
NODE_ERR = ("RuntimeError: export.py exit 1:\nerror: node unavailable: the Node.js at /opt/homebrew/bin/node is "
            "broken (dyld[1]: Library not loaded: libsimdjson.29.dylib). Run `brew reinstall node` in Terminal")
OLD_NODE = "error: node unavailable: the Node.js at /usr/local/bin/node is v16.20.2; HyperFrames needs 18+"
NO_NODE = "RuntimeError: npx (Node) not found: HyperFrames needs Node 18+"
FF_MISSING = "FFmpegError: VSTUDIO_FFMPEG=/Applications/Reelfold.app/Contents/Resources/runtime/ffmpeg/bin/ffmpeg does not exist"
FF_BSF = "export.py exit 1: [vost#0:0] Unknown bitstream filter h264_metadata"
FF_DYLD = "dyld: Library not loaded: libx264.164.dylib\n  Referenced from: /opt/homebrew/bin/ffmpeg"
B_TRACEBACK = ("RuntimeError: export.py exit 1: Traceback (most recent call last):\n  File \"export.py\"\n"
               "vstudio.media.FFmpegError: command failed (254): ffmpeg -nostdin ...\n"
               "Error opening output /x/out/promo.loud.mp4: No such file or directory")


class ClassifyTools(unittest.TestCase):
    def test_node(self):
        for t in (DYLD, NODE_ERR, OLD_NODE, NO_NODE):
            self.assertEqual(PI.classify(t), "tool-node", t)
        self.assertEqual(PI.tool_fix("tool-node", DYLD), dict(tool="node", fix="brew-reinstall-node"))
        self.assertEqual(PI.tool_fix("tool-node", OLD_NODE)["fix"], "install-node")
        self.assertEqual(PI.tool_fix("tool-node", NO_NODE)["fix"], "install-node")

    def test_ffmpeg(self):
        for t in (FF_MISSING, FF_BSF, FF_DYLD):
            self.assertEqual(PI.classify(t), "tool-ffmpeg", t)
        self.assertEqual(PI.tool_fix("tool-ffmpeg", FF_MISSING), dict(tool="ffmpeg", fix="reinstall-app"))
        self.assertEqual(PI.tool_fix("tool-ffmpeg", FF_DYLD)["fix"], "install-ffmpeg")

    def test_existing_codes_unchanged_and_traceback_is_not_engine_when_it_says_more(self):
        self.assertEqual(PI.classify("codex: 429 rate limit"), "ai-quota")
        self.assertEqual(PI.classify("ModuleNotFoundError: No module named 'vstudio.llm'"), "engine")
        self.assertEqual(PI.classify("Traceback (most recent call last):\n  ValueError: x"), "engine")
        self.assertEqual(PI.classify(B_TRACEBACK), "media")
        self.assertEqual(PI.tool_fix("media", B_TRACEBACK), {})

    def test_ffmpeg_errors_the_app_caused_are_a_bug_not_an_unreadable_file(self):
        """0.2.6: the bundled LGPL ffmpeg has no eq -> "No such filter: 'eq'" was worded as "a file couldn't be
        read" (the line merely said ffmpeg). Now: app-bug; only real open / read errors are media."""
        nofilter = ("RuntimeError: build_vlog.py exit 1: [AVFilterGraph @ 0x1] No such filter: 'eq'\n"
                    "!! render failed - segment 00 (DJI_0079.MP4): No such filter: 'eq'")
        for t in (nofilter, "[vost#0:0] Unknown encoder 'libx264'", "Error initializing filter 'lutyuv' with args"):
            self.assertEqual(PI.classify(t), "app-bug", t)
        self.assertEqual(PI.classify("CalledProcessError: Command '['ffmpeg', '-y']' returned non-zero exit status 8."),
                         "unknown")                                       # says ffmpeg, but nothing about a file
        self.assertEqual(PI.classify("Error opening input file /Volumes/dji/DJI_0079.MP4."), "media")
        d = tempfile.mkdtemp()
        with open(os.path.join(d, PI.LOG), "w") as f:
            f.write(json.dumps(dict(event="stage-fail", job="V1", stage="render", error=nofilter, code="app-bug",
                                    params={})) + "\n")
            f.write(json.dumps(dict(event="project-end", exit_code=5, status="failed")) + "\n")
        write_json(os.path.join(d, PI.REC), dict(pid=None, started=1, offset=0, exit=5, finished=2))
        f = PI.failure(d)
        self.assertEqual((f["code"], f["stage"]), ("app-bug", "render"))
        with open(os.path.join(d, PI.LOG), "w") as fh:
            fh.write(json.dumps(dict(event="stage-fail", job="V1", stage="render", error="x: No such file or directory",
                                     code="media-unmounted", params=dict(file="DJI_0079.MP4", volume="dji"))) + "\n")
            fh.write(json.dumps(dict(event="project-end", exit_code=5, status="failed")) + "\n")
        f = PI.failure(d)
        self.assertEqual((f["code"], f["params"]), ("media-unmounted", dict(file="DJI_0079.MP4", volume="dji")))

    def test_failure_document_carries_tool_and_fix(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, PI.LOG), "w") as f:
            f.write(json.dumps(dict(event="stage-fail", job="AIGC", stage="render", error=DYLD)) + "\n")
            f.write(json.dumps(dict(event="project-end", exit_code=5, status="failed")) + "\n")
        write_json(os.path.join(d, PI.REC), dict(pid=None, started=1, offset=0, exit=5, finished=2))
        f = PI.failure(d)
        self.assertEqual((f["code"], f["tool"], f["fix"]), ("tool-node", "node", "brew-reinstall-node"))
        self.assertNotIn("/opt/homebrew", f["error"])


class MissingKey(unittest.TestCase):
    """Dogfood 2026-10-11: the course voice stopped on "OPENAI_API_KEY is not set in the environment" (a raw
    traceback). A missing key is its own code: the service and the fix, never "log in again" or "didn't start"."""
    NEW = ("RuntimeError: tts.py exit 1: No OpenAI key: OPENAI_API_KEY is not set. Add your OpenAI key in Settings > "
           "AI, or use the free local voice.")
    OLD = ("RuntimeError: tts.py exit 1:\nTraceback (most recent call last):\n  File \"tts.py\", line 69\n"
           "RuntimeError: OPENAI_API_KEY is not set in the environment")

    def test_classified_with_the_service(self):
        for text in (self.NEW, self.OLD):
            self.assertEqual(PI.classify(text), "ai-key-missing", text)
            self.assertEqual(PI.tool_fix("ai-key-missing", text)["params"]["service"], "OpenAI")
        self.assertEqual(PI.tool_fix("ai-key-missing", self.NEW)["params"]["fix"], "free-voice")
        self.assertEqual(PI.tool_fix("ai-key-missing", self.OLD)["params"]["fix"], "add-key")

    def test_failure_document_names_the_service(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, PI.LOG), "w") as f:
            f.write(json.dumps(dict(event="stage-fail", job="ep1", stage="voice", error=self.NEW,
                                    code="ai-key-missing", params=dict(service="OpenAI", fix="free-voice"))) + "\n")
            f.write(json.dumps(dict(event="project-end", exit_code=5, status="failed")) + "\n")
        write_json(os.path.join(d, PI.REC), dict(pid=None, started=1, offset=0, exit=5, finished=2))
        out = PI.failure(d)
        self.assertEqual((out["code"], out["stage"], out["params"]), ("ai-key-missing", "voice",
                                                                       dict(service="OpenAI", fix="free-voice")))
        with open(os.path.join(d, PI.LOG), "w") as f:                  # an older engine: no code on the event
            f.write(json.dumps(dict(event="stage-fail", job="ep1", stage="voice", error=self.OLD)) + "\n")
            f.write(json.dumps(dict(event="project-end", exit_code=5, status="failed")) + "\n")
        out = PI.failure(d)
        self.assertEqual((out["code"], out["params"]["service"]), ("ai-key-missing", "OpenAI"))


class FreeVoiceNotDownloaded(unittest.TestCase):
    """The app's free voice (Kokoro) is a one-time download: before it, the voice step names that and the desk offers
    the download (code tool-voice, fix download-voice) - never "Part of Reelfold didn't start"."""
    TEXT = ("RuntimeError: tts.py exit 1: The free voice is not downloaded yet: download it in Settings > Downloads "
            "(Free voice), then try again.")

    def test_classified(self):
        self.assertEqual(PI.classify(self.TEXT), "tool-voice")
        self.assertEqual(PI.tool_fix("tool-voice", self.TEXT), dict(tool="voice", fix="download-voice"))

    def test_failure_document(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, PI.LOG), "w") as f:
            f.write(json.dumps(dict(event="stage-fail", job="ep1", stage="voice", error=self.TEXT, code="tool-voice",
                                    params=dict(tool="voice", fix="download-voice"))) + "\n")
            f.write(json.dumps(dict(event="project-end", exit_code=5, status="failed")) + "\n")
        write_json(os.path.join(d, PI.REC), dict(pid=None, started=1, offset=0, exit=5, finished=2))
        out = PI.failure(d)
        self.assertEqual((out["code"], out["stage"], out["params"]), ("tool-voice", "voice",
                                                                       dict(tool="voice", fix="download-voice")))


class ToolHealth(unittest.TestCase):
    def test_tools_in_capabilities_info_real_mode_only(self):
        class R:
            def json(self, *a, **k):
                return {"recipes": [], "capabilities": ["deliver"]}

        c = CP.Capabilities(R())
        c._tools = dict(node=dict(ok=False, error="node unavailable: ...", fix="brew reinstall node"),
                        ffmpeg=dict(ok=True))
        info = c.info()
        self.assertFalse(info["tools"]["node"]["ok"])
        self.assertNotIn("tools", CP.Capabilities(fixed=set()).info())

    def test_health_shapes(self):
        n = CP.node_health()
        self.assertTrue({"ok", "version", "path", "error", "fix", "checked"} <= set(n))
        f = CP.ffmpeg_health()
        self.assertTrue({"ok", "path", "ffprobe", "version", "error"} <= set(f))


if __name__ == "__main__":
    unittest.main()
