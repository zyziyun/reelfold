"""Settings › Music routes (desk_engine/music.py over vstudio.music): the library with its licences and tempo, the
built-in beds with a preview each, favourites / bans written where the engine reads them per pick, and the library
folder among the media roots (the previews play). Run: npm run test:engine."""
import http.client
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401  (VSTUDIO_HOME / DESK_DATA_DIR -> a temp folder, first)

from desk_engine.app import serve  # noqa: E402
from desk_engine.common import EventBus, Registry  # noqa: E402
from desk_mock import MockEngine, make_api  # noqa: E402

TOKEN = "m" * 48
ORIGIN = "app://desk"


class MusicApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        from vstudio import music as MU
        cls.MU = MU
        first = MU.library_doc()["tracks"][0]
        cls.lib = os.path.join(cls.tmp, "library")
        os.makedirs(cls.lib)
        with open(os.path.join(cls.lib, first["file"]), "wb") as f:       # one track "downloaded" (right size)
            f.write(b"\0" * first["size"])
        cls.first = first
        cls.env = mock.patch.dict(os.environ, {MU.LIBRARY_ENV: cls.lib, "VSTUDIO_CACHE": os.path.join(cls.tmp, "c")})
        cls.env.start()
        bus = EventBus()
        cls.engine = MockEngine(cls.tmp, Registry(cls.tmp), bus, step=0.01)
        cls.api = make_api(cls.engine, bus, TOKEN, [ORIGIN])
        cls.httpd = serve(cls.api)

    @classmethod
    def tearDownClass(cls):
        cls.engine.shutdown()
        cls.httpd.shutdown()
        cls.env.stop()

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

    def test_a_library_and_builtins(self):
        st, d = self.req("GET", "/api/music")
        self.assertEqual(st, 200, d)
        self.assertEqual(d["total"], len(self.MU.library_doc()["tracks"]))
        self.assertEqual(d["installed"], 1)
        row = next(t for t in d["tracks"] if t["id"] == f"lib:{self.first['id']}")
        self.assertTrue(row["installed"] and row["path"].startswith(self.lib))
        self.assertTrue(row["license"].startswith("CC0") and row["licence_evidence"].startswith("https://"))
        self.assertEqual([b["mood"] for b in d["builtins"]], list(self.MU.STYLES))
        self.assertTrue(all(b["path"] and os.path.exists(b["path"]) for b in d["builtins"]))   # each one to listen to
        st, roots = self.req("GET", "/api/roots")
        self.assertIn(self.lib, roots)

    def test_b_favourite_and_ban(self):
        tid = f"lib:{self.first['id']}"
        st, d = self.req("POST", "/api/music/prefs", dict(id=tid, favourite=True))
        self.assertEqual(st, 200, d)
        self.assertEqual(d["prefs"]["favourites"], [tid])
        st, d = self.req("POST", "/api/music/prefs", dict(id="builtin:bright", banned=True))
        self.assertTrue(next(b for b in d["builtins"] if b["id"] == "builtin:bright")["banned"])
        self.assertEqual(self.MU.prefs()["banned"], ["builtin:bright"])          # what the engine's picks read
        self.assertNotIn("builtin:bright", [t["id"] for t in self.MU.rank("卡点", style="fun")])
        for bad in (dict(id="../x", banned=True), dict(id=tid, favourite="yes"), dict(favourite=True)):
            st, _ = self.req("POST", "/api/music/prefs", bad)
            self.assertEqual(st, 400, bad)


if __name__ == "__main__":
    unittest.main()
