"""Settings › Publishing › Video length (desk_engine/platform_lengths.py over vstudio.platform_habits): every platform's
length bands per kind, her own range written where the engine's planner reads it, bad input refused; a goal's plan
card carries each video's per-platform lengths, cuts and what the footage can carry. Run: npm run test:engine."""
import http.client
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401  (VSTUDIO_HOME / DESK_DATA_DIR -> a temp folder, first)

from desk_engine.app import serve  # noqa: E402
from desk_engine.common import EventBus, Registry  # noqa: E402
from desk_mock import MockEngine, make_api  # noqa: E402

TOKEN = "p" * 48
ORIGIN = "app://desk"


class PlatformLengthsApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        bus = EventBus()
        cls.engine = MockEngine(cls.tmp, Registry(cls.tmp), bus, step=0.01)
        cls.api = make_api(cls.engine, bus, TOKEN, [ORIGIN])
        cls.httpd = serve(cls.api)

    @classmethod
    def tearDownClass(cls):
        cls.engine.shutdown()
        cls.httpd.shutdown()

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.api.port, timeout=60)
        h = {"Host": f"127.0.0.1:{self.api.port}", "Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None)

    def test_a_every_platform_with_its_bands(self):
        st, d = self.req("GET", "/api/platform-lengths")
        self.assertEqual(st, 200, d)
        from vstudio import platform as P
        self.assertEqual([r["platform"] for r in d["platforms"]], P.ORDER)       # international first
        yt = next(r for r in d["platforms"] if r["platform"] == "youtube")
        self.assertEqual((yt["form"], yt["source"]), ("long", "file"))
        self.assertGreaterEqual(yt["lengths"]["history"]["target"], 240)
        self.assertIn("reel", d["kinds"])

    def test_b_her_range_is_kept_and_read_by_the_planner(self):
        st, d = self.req("POST", "/api/platform-lengths", dict(platform="xiaohongshu", min_s=60, max_s=120))
        self.assertEqual(st, 200, d)
        row = next(r for r in d["platforms"] if r["platform"] == "xiaohongshu")
        self.assertEqual((row["limits"], row["source"]), ({"min_s": 60, "max_s": 120}, "settings"))
        from vstudio import platform_habits as H
        self.assertEqual(H.lengths(["xiaohongshu"], "film"), {"xiaohongshu": 60})   # what the goal planner uses
        st, d = self.req("POST", "/api/platform-lengths", dict(platform="xiaohongshu", reset=True))
        self.assertEqual(next(r for r in d["platforms"] if r["platform"] == "xiaohongshu")["source"], "file")
        for bad in (dict(platform="youtube-shorts", max_s=900), dict(platform="myspace", max_s=60),
                    dict(platform="youtube", min_s="long"), dict(min_s=30)):
            st, _ = self.req("POST", "/api/platform-lengths", bad)
            self.assertEqual(st, 400, bad)


if __name__ == "__main__":
    unittest.main()
