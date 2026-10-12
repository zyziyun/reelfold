"""The desk's reads of a run store (batch.db, WAL) while a run writes it: one at a time on a plain query-only
connection (common.read_db). Read-only (mode=ro) opens from many request threads at once hung every engine thread in
sqlite3.connect / close - the Inbox and All projects stopped answering while a resumed run worked."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _isolate  # noqa: E402,F401

from desk_engine.common import read_db  # noqa: E402

WRITER = r"""
import sqlite3, sys, time
con = sqlite3.connect(sys.argv[1], timeout=30, isolation_level=None)
t0 = time.time()
n = 0
while time.time() - t0 < 2.5:
    con.execute("BEGIN IMMEDIATE")
    con.execute("UPDATE jobs SET state = ? WHERE id = 'a'", (f"s{n}",))
    con.execute("COMMIT")
    n += 1
"""


class ReadDbTest(unittest.TestCase):
    def test_many_threads_read_while_a_run_writes(self):
        d = tempfile.mkdtemp()
        db = os.path.join(d, "batch.db")
        con = sqlite3.connect(db, isolation_level=None)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE jobs (id TEXT, state TEXT)")
        con.execute("INSERT INTO jobs VALUES ('a', 'planned')")
        con.close()
        w = subprocess.Popen([sys.executable, "-c", WRITER, db])
        done, errors = [], []

        def reader():
            try:
                for _ in range(30):
                    with read_db(db) as c:
                        c.execute("SELECT state FROM jobs").fetchall()
                done.append(1)
            except sqlite3.Error as e:            # a busy read is allowed to fail, never to hang
                errors.append(str(e))
        threads = [threading.Thread(target=reader, daemon=True) for _ in range(16)]
        t0 = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        w.wait(30)
        self.assertFalse(any(t.is_alive() for t in threads), "a reader hung")
        self.assertLess(time.time() - t0, 30)
        self.assertEqual(len(done) + len(errors), 16)
        with read_db(db) as c:                    # never writes
            with self.assertRaises(sqlite3.Error):
                c.execute("DELETE FROM jobs")

    def test_reads_while_the_engine_opens_and_closes_the_run_store(self):
        """All projects at scale: the desk's reads (history, inbox) and the engine's own Store opens / closes of the
        same batch.db on other threads. With conda's / python-build-standalone's sqlite a connect racing a close
        hung both for ever (every request of the engine with them) within a second or two."""
        from vstudio.batch.store import Store
        d = tempfile.mkdtemp()
        Store(d, create=True).close()
        db = os.path.join(d, "batch.db")
        n = {"r": 0, "w": 0}
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    with read_db(db) as c:
                        c.execute("SELECT count(*) FROM jobs").fetchall()
                except sqlite3.Error:
                    pass
                n["r"] += 1

        def opener():
            while not stop.is_set():
                st = Store(d)
                st.jobs()
                st.close()
                n["w"] += 1
        threads = [threading.Thread(target=f, daemon=True) for f in (reader, reader, opener, opener)]
        for t in threads:
            t.start()
        last = None
        for _ in range(6):
            time.sleep(0.5)
            now = (n["r"], n["w"])
            self.assertNotEqual(now, last, f"run-store reads hung at {now}")
            last = now
        stop.set()
        for t in threads:
            t.join(5)
        self.assertFalse(any(t.is_alive() for t in threads), "a thread hung")


if __name__ == "__main__":
    unittest.main()
