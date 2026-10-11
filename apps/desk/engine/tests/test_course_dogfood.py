"""Dogfood fixes (2026-10-10, a course from Notion lecture notes): the watcher never lists a Reelfold home / cache
folder (an isolated VSTUDIO_HOME like _vhome, a VSTUDIO_CACHE) as a project, and a failed explainer storyboard on
lecture notes keeps its code (stage-script-format, fix draft-script) so the app can say what to do."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401


class WatcherSkipsStores(unittest.TestCase):
    def test_home_and_cache_folders_are_not_projects(self):
        from desk_engine import history as H
        root = tempfile.mkdtemp()
        work = os.path.join(root, "course")
        home, cache = os.path.join(work, "_vhome"), os.path.join(work, "_vcache")
        for d in (home, cache, os.path.join(cache, "tts"), os.path.join(cache, "intake"), os.path.join(home, "p")):
            os.makedirs(d, exist_ok=True)
        open(os.path.join(home, "persona.local.yaml"), "w").close()
        open(os.path.join(home, "projects.json"), "w").close()
        open(os.path.join(home, "p", "project.yaml"), "w").close()     # an isolated run's own project
        self.assertTrue(H.is_store(home) and H.is_store(cache))
        self.assertFalse(H.is_store(work))
        found = H.scan_folder(root, depth=3)
        self.assertFalse([d for _, d in found if "_vhome" in d or "_vcache" in d], found)


class ScriptFormatFailureIsWorded(unittest.TestCase):
    def test_the_code_and_fix_reach_the_failure(self):
        from desk_engine import pilot
        d = tempfile.mkdtemp()
        err = "RuntimeError: storyboard_from_script.py exit 1: no '## Line N' blocks in SCRIPT.md"
        ev = dict(event="stage-fail", job="ep1", stage="storyboard", error=err, code="stage-script-format",
                  params=dict(fix="draft-script"))
        with open(os.path.join(d, pilot.LOG), "w", encoding="utf-8") as f:
            f.write(json.dumps(ev) + "\n" + json.dumps(dict(event="project-end", exit_code=1)) + "\n")
        with open(os.path.join(d, pilot.REC), "w", encoding="utf-8") as f:
            json.dump(dict(pid=None, exit=1), f)
        got = pilot.failure(d)
        self.assertEqual(got["code"], "stage-script-format")
        self.assertEqual((got.get("params") or {}).get("fix") or got.get("fix"), "draft-script")


if __name__ == "__main__":
    unittest.main()
