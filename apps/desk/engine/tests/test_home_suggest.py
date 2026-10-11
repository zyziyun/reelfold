"""Home's suggestion chips come from her own signals only (homesuggest.py): a request sent more than once, a fresh
recording in a watched folder that no project or request uses yet. Nothing canned: no signals -> nothing."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _isolate  # noqa: E402,F401

from desk_engine import homesuggest as HS  # noqa: E402


class FakeHistory:
    def __init__(self, watch, items):
        self._watch, self._items = watch, items

    def watch(self):
        return self._watch

    def list(self):
        return dict(items=self._items)


class FakeIntake:
    def __init__(self, jobs):
        self.jobs = {str(k): j for k, j in enumerate(jobs)}


def touch(path, size=4096, age=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\0" * size)
    t = time.time() - age
    os.utime(path, (t, t))


class RecurringTest(unittest.TestCase):
    def test_only_requests_sent_twice_count_spacing_and_case_aside(self):
        jobs = [dict(prompt="Cut my weekly Q&A into clips", started=10), dict(prompt="cut my weekly  q&a into clips ", started=30),
                dict(prompt="A one-off explainer", started=40), dict(prompt="", started=50), dict(prompt="Tips", started=1),
                dict(prompt="tips", started=2), dict(prompt="TIPS", started=3)]
        out = HS.recurring(jobs)
        self.assertEqual([(x["n"], x["prompt"]) for x in out], [(3, "TIPS"), (2, "cut my weekly  q&a into clips")])

    def test_none_when_nothing_repeats(self):
        self.assertEqual(HS.recurring([dict(prompt="a"), dict(prompt="b")]), [])


class RecordingsTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hs-")
        self.watch = os.path.join(self.root, "Recordings")

    def test_fresh_unused_recordings_newest_first(self):
        touch(os.path.join(self.watch, "monday.mov"), age=7200)
        touch(os.path.join(self.watch, "day2", "tuesday.mp4"), age=60)
        touch(os.path.join(self.watch, "old.mp4"), age=10 * 86400)          # too old
        touch(os.path.join(self.watch, "notes.txt"))                         # not a recording
        touch(os.path.join(self.watch, "tiny.mp4"), size=10)                 # an empty file
        touch(os.path.join(self.watch, "used.mp4"))                          # a request has it
        touch(os.path.join(self.watch, "in-project.mp4"))                    # a project has it
        touch(os.path.join(self.watch, "proj", "project.yaml"))
        touch(os.path.join(self.watch, "proj", "render.mp4"))                # a project's own output
        touch(os.path.join(self.watch, "a", "b", "deep.mp4"))                # deeper than one level
        with open(os.path.join(self.watch, "proj", "project.yaml"), "w") as f:
            f.write("items:\n- id: '001'\n  inputs:\n    video: [%s]\n" % os.path.join(self.watch, "in-project.mp4"))
        h = FakeHistory([self.watch], [dict(kind="project", dir=os.path.join(self.watch, "proj"))])
        i = FakeIntake([dict(prompt="x", inputs=[os.path.join(self.watch, "used.mp4")], started=1)])
        out = HS.suggestions(h, i)
        self.assertEqual([x["name"] for x in out["recordings"]], ["tuesday.mp4", "monday.mov"])
        self.assertEqual(out["recordings"][0]["folder"], "Recordings")
        self.assertEqual(out["recurring"], [])

    def test_a_folder_given_to_a_request_covers_its_files(self):
        touch(os.path.join(self.watch, "batch", "one.mp4"))
        i = FakeIntake([dict(prompt="x", inputs=[os.path.join(self.watch, "batch")])])
        self.assertEqual(HS.suggestions(FakeHistory([self.watch], []), i)["recordings"], [])

    def test_no_watched_folder_no_recordings(self):
        self.assertEqual(HS.suggestions(FakeHistory([os.path.join(self.root, "missing")], []), FakeIntake([])),
                         dict(recurring=[], recordings=[]))


if __name__ == "__main__":
    unittest.main()
