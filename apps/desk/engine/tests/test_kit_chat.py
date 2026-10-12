"""The clip chat on a launch-kit film (dogfood 2026-10-12, her 0.2.7 promo: "not premium enough, show the features
clearly" got an editorial look, studio sound and a chapter rule stacked on the finished film). The engine answers
such a request with launch.config.yaml keys (``route: launch-kit``, ``kit.patch``; vstudio.project.outkit); the desk
acts at once like any chat change: writes them through ``output kit`` and runs the project again, so the kit renders
the film again - or says it is busy. The CLI and the background run are faked here (the engine side is
tests/test_output_kit.py)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import outputs as OU  # noqa: E402

PATCH = {"brand": {"backdrop": "deep"}, "motion": {"seconds": 0.45}}


class FakePilot:
    def __init__(self):
        self.runner, self.resumed = object(), []

    def _resume(self, d):
        self.resumed.append(d)
        return True


class KitChatTest(unittest.TestCase):
    def setUp(self):
        self.o = OU.Outputs(tempfile.mkdtemp(), history=None)
        self.o._ext = True
        self.calls = []
        self.o._cli = lambda args, timeout=600: self.calls.append(args) or {"ok": True, "backup": "/p/work/b.yaml"}
        self.o.autopilot = FakePilot()
        self.e = {"dir": "/p", "kind": "project"}

    def out(self, patch=PATCH):
        return {"turn": "t1-ab", "warnings": [{"code": "kit-backdrop", "message": "dark"}],
                "kit": {"patch": patch, "applied": False}}

    def test_writes_the_kit_and_runs_it_again(self):
        out = self.out()
        with mock.patch.object(OU.pilot, "running", return_value=False), \
                mock.patch.object(OU.pilot, "queued", return_value=None):
            self.o._kit_rerender(self.e, "main/demo-en-16x9.mp4", out)
        kit, chat = self.calls
        self.assertEqual(kit[:5], ["kit", "--project", "/p", "--output", "main/demo-en-16x9.mp4"])
        self.assertEqual(OU.json.loads(kit[kit.index("--set") + 1]), PATCH)
        self.assertEqual(self.o.autopilot.resumed, ["/p"])
        self.assertEqual([w["code"] for w in out["warnings"]], ["kit-backdrop", "kit-rerender"])
        self.assertTrue(out["kit"]["applied"])
        self.assertEqual(chat[:2], ["chat", "--project"])                  # the turn keeps the reply
        self.assertIn("kit-rerender", chat[-1])

    def test_busy_project_or_nothing_to_change(self):
        out = self.out()
        with mock.patch.object(OU.pilot, "running", return_value=True):
            self.o._kit_rerender(self.e, "main/demo-en-16x9.mp4", out)
        self.assertEqual([c[0] for c in self.calls], ["chat"])            # no config written, no run
        self.assertEqual(out["warnings"][-1]["code"], "kit-busy")
        self.assertEqual(self.o.autopilot.resumed, [])
        self.calls.clear()
        out = self.out(patch={})
        self.o._kit_rerender(self.e, "main/demo-en-16x9.mp4", out)
        self.assertEqual(self.calls, [])
        self.assertEqual([w["code"] for w in out["warnings"]], ["kit-backdrop"])


if __name__ == "__main__":
    unittest.main()
