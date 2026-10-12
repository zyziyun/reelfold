"""An explainer whose visuals came out plain (her MCP course, 2026-10-11: text lines on a dark ground) is redrawn
from the desk without redoing the voice: the clip page's "Redo the visuals" and her words in the clip / project chat
("画面太素了，重新设计一下" / "more diagrams" / "refais les visuels") run ``vstudio.project remake --do scenes`` in the
background; a remake no model drew fails as ``ai-needs-model`` (the desk's own words, Try again re-runs the remake,
not a plain resume); the Inbox gets the needs-model fields of a step that needs an AI model.
Real engine CLI for the decisions; the background spawn is captured."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _isolate  # noqa: E402,F401

from desk_engine import intake as IN  # noqa: E402
from desk_engine import pilot as P  # noqa: E402
from desk_engine.autopilot import Autopilot, remake_intent  # noqa: E402
from desk_engine.caps import CliRunner  # noqa: E402
from desk_engine.inbox import author_block  # noqa: E402

ENGINE = os.environ.get("VSTUDIO_ENGINE_PATH") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
ID = "abcdefabcdef"


class FakeHistory:
    def __init__(self, d):
        self.d = d

    def find(self, item, **_kw):
        return dict(id=item, dir=self.d, kind="project")


def finished_explainer(root):
    """A finished explainer item (its scenes drawn by the old rules, a render) made with the real engine."""
    env = dict(os.environ, PYTHONPATH=os.path.join(ENGINE, "lib"), VSTUDIO_HOME=os.path.join(root, "vhome"))
    code = (
        "import sys, os, json\n"
        "from vstudio.project.core import Project\n"
        "from vstudio.project import drafts as DR\n"
        "p = Project.create(sys.argv[1], recipe='explainer', name='MCP course', items=[dict(id='ep1')])\n"
        "d = os.path.join(p.dir, 'items', 'ep1')\n"
        "os.makedirs(os.path.join(d, 'compositions'), exist_ok=True)\n"
        "open(os.path.join(d, 'compositions', 'f01-mn.html'), 'w').write('<template>text lines</template>')\n"
        "DR.write_side(os.path.join(d, 'compositions'), 'scenes', dict(by='rules'))\n"
        "os.makedirs(os.path.join(d, 'renders'), exist_ok=True)\n"
        "open(os.path.join(d, 'renders', 'ep1.mp4'), 'wb').write(b'video')\n"
        "print(p.dir)\n")
    import subprocess
    out = subprocess.run([sys.executable, "-c", code, os.path.join(root, "course")], env=env, capture_output=True,
                         text=True, check=True).stdout.strip().splitlines()[-1]
    return out, env


class VisualsIntentTest(unittest.TestCase):
    def test_her_words(self):
        for text in ("画面太素了，重新设计一下", "重新设计画面", "画面太单调", "多加点图解", "视觉重做一下",
                     "Redo the visuals", "please redesign the scenes", "more diagrams please",
                     "the visuals are too plain", "Refais les visuels", "plus de schémas", "visuels trop simples"):
            self.assertEqual(remake_intent(text), dict(visuals=True), text)
        for text in ("make it tighter", "重写发布文案", "add a 9:16 version", "加个封面", "redo the voice"):
            self.assertNotIn("visuals", remake_intent(text) or {}, text)


class RedoVisualsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vis-")
        self.d, self.env = finished_explainer(self.tmp)
        self.spawned = []
        self._spawn = P.spawn
        P.spawn = lambda python, env, d, provider=None, bus=None, args=None: self.spawned.append(args) or {}
        self.ap = Autopilot(FakeHistory(self.d), CliRunner(sys.executable, self.env))

    def tearDown(self):
        P.spawn = self._spawn

    def test_the_clip_page_and_the_chat_redo_the_visuals(self):
        doc = self.ap.get(ID)
        vis = [c for c in doc["choices"] if c.get("remake_as") == "visuals"]
        self.assertEqual([(c["checkpoint"], c["item"], c["choice"]) for c in vis], [("scenes", "ep1", "rules")])
        self.assertIsNone(doc["failure"])
        self.assertEqual(self.ap.remake(ID, "ep1", {"scenes": None}), dict(ok=True, started=True, do={"scenes": None}))
        args, = self.spawned
        self.assertEqual(args[args.index("remake"):], ["remake", "--dir", self.d, "--item", "ep1", "--do", "scenes",
                                                       "--json-events"])
        self.spawned.clear()
        said = self.ap.remake_asked(ID, remake_intent("画面太素了，重新设计一下"), clip="ep1/youtube-horizontal")
        self.assertEqual([m["code"] for m in said], ["remake-visuals"])
        self.assertIn("配音和字幕不变", said[0]["message_zh"])
        self.assertIn("--do", self.spawned[0])

    def test_a_remake_no_model_drew_fails_in_her_words_and_try_again_remakes(self):
        args = ["-m", "vstudio.project", "remake", "--dir", self.d, "--item", "ep1", "--do", "scenes", "--json-events"]
        with open(os.path.join(self.d, P.LOG), "w", encoding="utf-8") as f:
            f.write(json.dumps(dict(event="stage-fail", job="ep1", stage="scenes", code="ai-needs-model",
                                    params=dict(provider="claude-code", what="visuals"),
                                    error="The visuals need an AI model — Claude Code didn't answer.")) + "\n")
            # the CLI's own closing line repeats the error without the code
            f.write(json.dumps(dict(ok=False, type="RemakeError",
                                    error="The visuals need an AI model — Claude Code didn't answer.")) + "\n")
        with open(os.path.join(self.d, P.REC), "w", encoding="utf-8") as f:
            json.dump(dict(pid=None, exit=1, offset=0, args=args, provider=None), f)
        fail = self.ap.get(ID)["failure"]
        self.assertEqual((fail["code"], fail["params"]["what"]), ("ai-needs-model", "visuals"))
        it = IN.Intake(os.path.join(self.tmp, "desk"), None, CliRunner(sys.executable, self.env), "real")
        it._need_engine = lambda: None
        it.retry_pilot(self.d)
        self.assertEqual(self.spawned[-1][1:], args)              # the remake again, not `run --resume`


class RemakeFailureIsANoticeTest(unittest.TestCase):
    """Her MCP course, 2026-10-11: a redo whose scene 14 kept calling fetch() put the finished course in Needs you as
    "The first clip stopped" with a Confirm button. The old video still stands: the project stays Ready, the failure
    is a notice of its own (which scene, why), Try again redraws only what is missing."""

    def test_a_failed_redo_keeps_the_project_ready_with_its_own_words(self):
        from unittest import mock
        from desk_engine.common import Registry
        from desk_engine.history import History
        from desk_engine.inbox import Inbox
        root = tempfile.mkdtemp(prefix="vis-")
        d, _env = finished_explainer(root)
        args = ["-m", "vstudio.project", "remake", "--dir", d, "--item", "ep1", "--do", "scenes", "--json-events"]
        err = "Scene 14 of 14 couldn't be drawn: it tried to load data from the internet, which a video can't do."
        with open(os.path.join(d, P.LOG), "w", encoding="utf-8") as f:
            f.write(json.dumps(dict(event="stage-fail", job="ep1", stage="scenes", code="stage-visuals-failed",
                                    params=dict(scene="14", id="f14-mcp-a2a", total="14", n="1", why="network"),
                                    error=err)) + "\n")
            f.write(json.dumps(dict(ok=False, type="RemakeError", error=err)) + "\n")
        with open(os.path.join(d, P.REC), "w", encoding="utf-8") as f:
            json.dump(dict(pid=None, exit=1, offset=0, args=args, provider=None, finished=1.0), f)
        fail = P.failure(d)
        self.assertEqual((fail["code"], fail["remake"], fail["params"]["scene"], fail["params"]["why"]),
                         ("stage-visuals-failed", True, "14", "network"))
        with mock.patch.dict(os.environ, {"DESK_HISTORY_WATCH": root}):
            data = os.path.join(root, "desk")
            h = History(data, Registry(data))
            row = next(r for r in h.list()["items"] if os.path.realpath(r["dir"]) == os.path.realpath(d))
            self.assertNotEqual(row.get("status"), "failed")
            self.assertNotIn("failure", row)
            self.assertEqual(row["remake_failure"]["code"], "stage-visuals-failed")
            self.assertFalse([i for i in Inbox(data, h).list()["items"] if i["kind"] == "failed"])


class InboxNeedsModelTest(unittest.TestCase):
    def test_the_inbox_gets_the_needs_model_fields(self):
        pd = tempfile.mkdtemp(prefix="inb-")
        os.makedirs(os.path.join(pd, "state", "checkpoints", "ep1"))
        pay = dict(id="scenes", item="ep1", recipe="explainer", file=os.path.join(pd, "items", "ep1", "compositions"),
                   is_dir=True, draft_state="missing", review=None, needs_ai=True, ai_provider="claude-code",
                   draft_error="The visuals need an AI model — Claude Code didn't answer.",
                   draft_error_code="ai-needs-model", draft_error_params=dict(provider="claude-code", what="visuals"))
        with open(os.path.join(pd, "state", "checkpoints", "ep1", "scenes.json"), "w", encoding="utf-8") as f:
            json.dump(pay, f)
        a = author_block(dict(item="ep1", id="scenes"), pd)
        self.assertEqual((a["draft_error_code"], a["draft_error_params"], a["needs_ai"], a["ai_provider"]),
                         ("ai-needs-model", dict(provider="claude-code", what="visuals"), True, "claude-code"))
        self.assertTrue(a["can_draft"])                            # "Draft it for me" = ask the AI again


if __name__ == "__main__":
    unittest.main()
