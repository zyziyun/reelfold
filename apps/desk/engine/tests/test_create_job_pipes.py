"""A Create background job whose child logs a lot on stderr still finishes: stderr is drained while stdout is read
(Windows pipes hold about 4 KB; a child blocked on its log never printed its result - the recorder hung)."""
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine.common import EventBus  # noqa: E402
from desk_engine.create import CreateApi, Refused  # noqa: E402


class Runner:
    def __init__(self, path):
        self.python = sys.executable
        self.env = dict(os.environ, PYTHONPATH=path, PYTHONIOENCODING="utf-8")


def fake_create(body):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "vstudio", "create"))
    open(os.path.join(d, "vstudio", "__init__.py"), "w").close()
    open(os.path.join(d, "vstudio", "create", "__init__.py"), "w").close()
    with open(os.path.join(d, "vstudio", "create", "__main__.py"), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(body))
    return d


class JobPipesTest(unittest.TestCase):
    def run_job(self, body, limit=None):
        api = CreateApi(tempfile.mkdtemp(), EventBus(), runner=Runner(fake_create(body)))
        out = {}
        t = threading.Thread(target=lambda: out.update(r=self._call(api, limit)), daemon=True)
        t.start()
        t.join(60)
        self.assertFalse(t.is_alive(), "the job never finished (blocked on a full stderr pipe)")
        return out["r"]

    @staticmethod
    def _call(api, limit):
        try:
            return api._run_job(["record", "ingest", "x"], lambda ev: None, limit)
        except Refused as e:
            return e

    def test_a_chatty_child_still_returns_its_result(self):
        r = self.run_job("""
            import json, sys
            sys.stderr.write("progress 50% |#####     | 本机\\n" * 8000)   # far more than any pipe buffer
            sys.stderr.flush()
            print(json.dumps({"event": "create.progress", "stage": "clean"}), flush=True)
            print(json.dumps({"result": {"ok": True, "dir": "x"}}), flush=True)
        """)
        self.assertEqual(r, {"ok": True, "dir": "x"})

    def test_a_failure_says_the_last_log_line(self):
        r = self.run_job("""
            import sys
            sys.stderr.write("noise\\n" * 8000 + "ffmpeg: no such file\\n")
            sys.exit(1)
        """)
        self.assertIsInstance(r, Refused)
        self.assertIn("ffmpeg: no such file", str(r.doc))


class RecordingJobRetryTest(unittest.TestCase):
    def test_concurrent_identical_ingests_share_one_job_and_failure_can_retry(self):
        from concurrent.futures import ThreadPoolExecutor
        import time
        api = CreateApi(tempfile.mkdtemp(), EventBus())
        release = threading.Event()
        calls = []
        def run(args, event, limit):
            calls.append(args)
            if not release.wait(5):
                raise RuntimeError("test timed out")
            raise RuntimeError("disk unavailable")
        api._run_job = run
        args = ["record", "ingest", "/tmp/example-session", "--target", "edit"]
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: api.job("ingest", args), range(8)))
            self.assertEqual(len({r["job"] for r in results}), 1)
            self.assertEqual(len(calls), 1)
            other = api.job("ingest", args[:-1] + ["assembled"])
            self.assertNotEqual(other["job"], results[0]["job"])
        finally:
            release.set()
        deadline = time.monotonic() + 5
        while any(j["state"] == "running" for j in api.jobs.values()) and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(all(j["state"] == "error" for j in api.jobs.values()))
        api._run_job = lambda *args: {"ok": True}
        retry = api.job("ingest", args)
        self.assertNotEqual(retry["job"], results[0]["job"])


if __name__ == "__main__":
    unittest.main()
