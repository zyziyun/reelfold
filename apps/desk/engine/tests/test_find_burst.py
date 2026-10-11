"""All projects asks for every recent project's clips at once: each lookup (History.find) that missed the 3 s listing
cache listed every folder again - 220 projects were 220 full listings (27 s before the list showed, a bulk Archive of
all of them 21 s). Lookups that miss together now share one listing; one begun after a lookup asked is as fresh as
its own (a project not in it is not there)."""
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _isolate  # noqa: E402,F401

from desk_engine.common import Registry  # noqa: E402
from desk_engine.history import History  # noqa: E402


class FindBurstTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.h = History(d, Registry(d))
        self.calls = 0
        ids = [f"{k:012x}" for k in range(200)]

        def slow_list(archived=False, **kw):
            self.calls += 1
            begun = time.time()
            time.sleep(0.05)
            rows = [dict(id=i, dir=f"/p/{i}", kind="project") for i in (ids if not archived else [])]
            if archived:
                self.h._last_archived = (begun, rows)
            else:
                self.h._last = (begun, rows)
            return dict(items=rows)
        self.h.list = slow_list
        self.ids = ids

    def test_two_hundred_lookups_at_once_share_one_listing(self):
        out, errs = [], []

        def one(i):
            try:
                out.append(self.h.find(i)["id"])
            except Exception as e:  # noqa: BLE001
                errs.append(e)
        ts = [threading.Thread(target=one, args=(i,)) for i in self.ids]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errs, [])
        self.assertEqual(sorted(out), sorted(self.ids))
        self.assertLessEqual(self.calls, 2)

    def test_a_missing_project_is_looked_for_in_a_listing_of_its_own_time(self):
        self.h.find(self.ids[0])
        n = self.calls
        with self.assertRaises(KeyError):
            self.h.find("ffffffffffff")
        self.assertEqual(self.calls, n + 2)          # the plain list again (begun after it asked), then the archived


if __name__ == "__main__":
    unittest.main()
