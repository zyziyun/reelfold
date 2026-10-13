"""A finished vlog brought up to date from the desk (her Seattle project, finished before the framing / copy steps):
the clip page reads its framing from the exports (``choices``, ``by: before``), switching it or "Rewrite post copy"
runs ``vstudio.project remake`` in the background (only what it changes), and the clip / project chat sends "follow
the subject, no blur / rewrite the post copy" (zh / en / fr) there instead of guessing an edit (a 9:16 version).
Real engine CLI; the background spawn is captured and run here."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _isolate  # noqa: E402,F401

from desk_engine import pilot as P  # noqa: E402
from desk_engine.autopilot import Autopilot, remake_intent  # noqa: E402
from desk_engine.caps import CliRunner  # noqa: E402
from desk_engine.projask import ProjectAsk  # noqa: E402

ENGINE = os.environ.get("VSTUDIO_ENGINE_PATH") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
ID = "abcdefabcdef"


class FakeHistory:
    def __init__(self, d):
        self.d = d

    def find(self, item, **_kw):
        return dict(id=item, dir=self.d, kind="project")


class RemakeIntentTest(unittest.TestCase):
    def test_her_words(self):
        asks = {
            "竖屏版本改成跟随主体裁切（不要模糊背景），并为每个平台重新写完整的发布文案，然后重新导出":
                dict(framing="follow", copy=True),
            "竖屏不要模糊背景": dict(framing="follow"),
            "竖屏用模糊背景填充": dict(framing="blur"),
            "重写发布文案": dict(copy=True),
            "Follow the subject on the vertical versions, no blur": dict(framing="follow"),
            "use a blurred background for vertical": dict(framing="blur"),
            "Rewrite the post copy for each platform": dict(copy=True),
            "Suivre le sujet, sans flou": dict(framing="follow"),
            "Réécris le texte de publication": dict(copy=True),
        }
        for text, want in asks.items():
            self.assertEqual(remake_intent(text), want, text)
        for text in ("make it tighter", "add a 9:16 version", "写一下封面文案", "rewrite the captions", "出抖音版"):
            self.assertIsNone(remake_intent(text), text)

    def test_voice_words_are_kept_for_the_casting(self):
        for text in ("换个男声", "配音换成女声", "声音太年轻了", "用 vivian 的声音", "a calmer voice please",
                     "change the voice", "changer de voix"):
            self.assertEqual(remake_intent(text), dict(voice=text), text)
        for text in ("声音大一点", "去掉音乐", "字幕大一点", "voice-over timing is off by 2 seconds"):
            self.assertNotIn("voice", remake_intent(text) or {}, text)


@unittest.skipIf(os.name == "nt" or not shutil.which("ffmpeg"), "needs ffmpeg for the video")
class RemakeOldVlogTest(unittest.TestCase):
    def test_old_vlog_setting_switch_copy_and_chat(self):
        tmp = tempfile.mkdtemp(prefix="rmk-")
        env = dict(os.environ, PYTHONPATH=os.path.join(ENGINE, "lib"), VSTUDIO_HOME=os.path.join(tmp, "vhome"),
                   VSTUDIO_LLM_PROVIDER="none", VSTUDIO_DEFAULT_PERSONA="1", VSTUDIO_MUSIC_DIRS="",
                   VSTUDIO_BATCH_BENCH=os.path.join(tmp, "bench.json"), VSTUDIO_LLM_COPY_PROVIDER="none")
        for k in ("VSTUDIO_PERSONA", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            env.pop(k, None)
        fx = os.path.join(ENGINE, "apps", "desk", "tests", "e2e", "fixture", "vlog_project.py")
        r = subprocess.run([sys.executable, fx, tmp, "--old"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        d = json.loads(r.stdout.strip().splitlines()[-1])["dir"]
        ex = os.path.join(d, "items", "main", "exports")
        spawned = []
        saved = P.spawn
        P.spawn = lambda python, env_, dd, provider=None, bus=None, args=None: spawned.append(args) or {}
        try:
            ap = Autopilot(FakeHistory(d), CliRunner(sys.executable, env))
            ch = {c["checkpoint"]: c for c in ap.get(ID)["choices"]}
            self.assertEqual((ch["framing"]["choice"], ch["framing"]["by"]), ("blur", "before"))
            self.assertEqual((ch["copy"]["choice"], ch["copy"]["by"]), (None, "before"))
            with self.assertRaises(Exception):
                ap.remake(ID, "main", {"framing": "sideways"})              # not one of its options
            with self.assertRaises(Exception):
                ap.remake(ID, "main", {"music": None})                      # not a setting of the clip
            # the clip chat: her request on the TikTok clip -> one background remake of both settings
            said = ap.remake_asked(ID, remake_intent("竖屏版本改成跟随主体裁切（不要模糊背景），并为每个平台重新写完整的"
                                                     "发布文案，然后重新导出"), clip="main/tiktok-vertical")
            self.assertEqual([m["code"] for m in said], ["remake-follow", "remake-copy"])
            args = spawned[-1]
            self.assertEqual(args[1:4], ["-m", "vstudio.project", "remake"])
            self.assertIn("framing=follow", args)
            self.assertIn("copy", args)
            # run what the desk started (the real engine)
            r = subprocess.run(args, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
            ev = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
            self.assertEqual(ev[-1]["event"], "project-end")
            self.assertEqual(ev[-1]["exit_code"], 0)
            with open(os.path.join(ex, "manifest.json"), encoding="utf-8") as f:
                man = {e["platform"]: e for e in json.load(f)["exports"]}
            self.assertEqual(man["tiktok"]["reframe"]["mode_used"], "subject")
            for e in man.values():
                with open(os.path.join(ex, e["post"]), encoding="utf-8") as f:
                    txt = f.read()
                self.assertGreaterEqual(len([x for x in txt.split("\n") if x.strip()]), 3, txt)
                self.assertIn("#", txt)
            ch = {c["checkpoint"]: c for c in ap.get(ID)["choices"]}
            self.assertEqual((ch["framing"]["choice"], ch["framing"]["by"]), ("follow", "her"))
            self.assertEqual((ch["copy"]["choice"], ch["copy"]["by"]), ("rules", "her"))
            # asked again: nothing to make for the framing, it says so; the project chat finds the same settings
            said = ap.remake_asked(ID, remake_intent("follow the subject"), clip="main/tiktok-vertical")
            self.assertEqual([m["code"] for m in said], ["remake-already-follow"])
            n = len(spawned)
            pa = ProjectAsk(outputs=None)
            pa.autopilot = ap
            self.assertEqual([m["code"] for m in pa._remake_asked(ID, dict(kind="project"), "Use a blurred fill")],
                             ["remake-blur"])
            self.assertEqual(len(spawned), n + 1)
            self.assertIn("framing=blur", spawned[-1])
            self.assertIsNone(ap.remake_asked(ID, remake_intent("make it tighter"), clip="main/tiktok-vertical"))
        finally:
            P.spawn = saved


if __name__ == "__main__":
    unittest.main()
