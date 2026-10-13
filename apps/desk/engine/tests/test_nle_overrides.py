"""The clip editor's two engine hand-offs: "Export for editing software…" (engine ``output nle``: one clip or a whole
project, format / media checked here, refused plainly when the engine cannot) and her hand edits (engine
``overrides`` in the clip document, ``override_reset`` ops passed through)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import outputs as OU  # noqa: E402
from desk_engine.common import BadRequest  # noqa: E402


def _outputs(oid="ep1/xiaohongshu-vertical", listed=True):
    o = OU.Outputs.__new__(OU.Outputs)
    calls = []
    e = dict(id="p1", dir="/tmp/proj", kind="project")
    o._clip = lambda item, clip: (e, dict(id=clip, files=[dict(path="/tmp/proj/a.mp4")]))
    o._entry = lambda item, max_age=3.0: e
    o._output_id = lambda e_, c: oid
    o._engine_list = lambda e_: {"/tmp/proj/a.mp4": oid} if listed else None
    o._adopt_on_first_edit = lambda e_: None
    o._cli = lambda args, timeout=600: calls.append(args) or dict(ok=True, format=args[args.index("--format") + 1],
                                                                 dir="/tmp/x", main="/tmp/x/clip.xml")
    return o, calls


class NleExport(unittest.TestCase):
    def test_one_clip_goes_to_the_engine(self):
        o, calls = _outputs()
        r = o.nle("p1", "c1", "jianying", media="copy", to_app=True)
        self.assertEqual(r["format"], "jianying")
        self.assertEqual(calls[0][:5], ["nle", "--project", "/tmp/proj", "--output", "ep1/xiaohongshu-vertical"])
        self.assertIn("--to-app", calls[0])
        self.assertEqual(calls[0][calls[0].index("--media") + 1], "copy")

    def test_a_whole_project(self):
        o, calls = _outputs()
        o.nle_all("p1", "xmeml")
        self.assertEqual(calls[0][:4], ["nle", "--project", "/tmp/proj", "--all"])
        self.assertNotIn("--to-app", calls[0])

    def test_bad_requests_and_no_engine(self):
        o, _ = _outputs()
        for fmt, media in (("imovie", "link"), ("xmeml", "move"), (None, "link")):
            with self.assertRaises(BadRequest):
                o.nle("p1", "c1", fmt, media=media)
        o, calls = _outputs(oid=None, listed=False)
        with self.assertRaises(OU.EngineMessage) as cm:
            o.nle("p1", "c1", "xmeml")
        self.assertEqual(cm.exception.doc["code"], "nle-needs-engine")
        with self.assertRaises(OU.EngineMessage):
            o.nle_all("p1", "otio")
        self.assertEqual(calls, [])


class Overrides(unittest.TestCase):
    def test_reset_op_is_validated(self):
        ok = OU.validate_ops([dict(op="override_reset", key="caption_style:color")])
        self.assertEqual(ok[0]["key"], "caption_style:color")
        OU.validate_ops([dict(op="override_reset", key="effect:fx3")])
        OU.validate_ops([dict(op="override_reset", key="title")])
        for bad in ("", "Title", "x" * 30, "effect:../../etc", None):
            with self.assertRaises(BadRequest):
                OU.validate_ops([dict(op="override_reset", key=bad)])

    def test_the_clip_document_carries_her_edits(self):
        o = OU.Outputs.__new__(OU.Outputs)
        base = dict(duration=10.0, fps=30, mode="flattened", words=[], files=[])
        eng = dict(output=dict(duration=10.0), state=dict(trim=[None, None], cuts=[], speed=1.0, captions={}),
                   history=dict(steps=[]), overrides=[
                       dict(key="title", label=dict(code="override-title", message="title band", message_zh="标题条",
                                                    params={}), at="2026-10-12T10:00:00", added=False, by_step="s1"),
                       dict(nokey=True)])
        out = o._normalise(base, eng, "p1")
        self.assertEqual([x["key"] for x in out["overrides"]], ["title"])
        self.assertEqual(out["overrides"][0]["label"]["code"], "override-title")
        self.assertNotIn("by_step", out["overrides"][0])


if __name__ == "__main__":
    unittest.main()
