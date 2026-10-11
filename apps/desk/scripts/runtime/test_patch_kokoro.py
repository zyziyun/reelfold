"""The Kokoro patch (patch_kokoro.py): English without espeak-ng and without num2words.

Run: python3 -m unittest discover -s scripts/runtime (npm run test:scripts). The source-level tests use the exact
lines of mlx-audio 0.5.8 / misaki 0.9.4; the installed-package test runs only where mlx-audio and misaki are installed
(a dev environment; the bundled runtime is checked end to end by bundle.mjs verifyVoice)."""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_kokoro as P  # noqa: E402

PIPELINE_SRC = '''        if lang_code in "ab":
            en = _get_misaki_en()
            espeak = _get_misaki_espeak()
            try:
                fallback = espeak.EspeakFallback(british=lang_code == "b")
            except Exception as e:
                logging.warning("EspeakFallback not Enabled: OOD words will be skipped")
                fallback = None
        elif lang_code == "z":
            zh = _get_misaki_zh()
        else:
            espeak = _get_misaki_espeak()
'''

MISAKI_SRC = '''from . import data
from .token import MToken
from dataclasses import dataclass, replace
from num2words import num2words
from typing import List, Optional, Tuple, Union
'''


class PatchSource(unittest.TestCase):
    def test_espeak_import_moves_inside_the_try(self):
        out = P.patch_pipeline(PIPELINE_SRC)
        head = out.split("elif lang_code", 1)[0]
        self.assertIn("            try:\n                espeak = _get_misaki_espeak()", head)
        self.assertEqual(head.count("_get_misaki_espeak()"), 1)
        self.assertIn("        else:\n            espeak = _get_misaki_espeak()\n", out)   # other languages unchanged
        self.assertEqual(P.patch_pipeline(out), out)                                       # idempotent

    def test_num2words_falls_back_to_the_engine(self):
        out = P.patch_misaki_en(MISAKI_SRC)
        self.assertIn("try:\n    from num2words import num2words\nexcept ImportError:", out)
        self.assertIn("    from vstudio.numwords_en import num2words\n", out)
        self.assertEqual(P.patch_misaki_en(out), out)
        compile(out, "en.py", "exec")

    def test_changed_files_fail_loudly(self):
        with self.assertRaises(SystemExit):
            P.patch_pipeline(PIPELINE_SRC.replace("            espeak = _get_misaki_espeak()\n            try:", "            try:"))
        with self.assertRaises(SystemExit):
            P.patch_misaki_en(MISAKI_SRC.replace("from num2words import num2words\n", ""))


@unittest.skipUnless(importlib.util.find_spec("mlx_audio") and importlib.util.find_spec("misaki"),
                     "needs mlx-audio and misaki installed")
class PatchInstalled(unittest.TestCase):
    def test_patches_a_copy_of_the_installed_packages(self):
        site = tempfile.mkdtemp()
        try:
            for name, rel in (("mlx_audio", P.PIPELINE), ("misaki", P.MISAKI_EN)):
                src = os.path.join(os.path.dirname(importlib.util.find_spec(name).origin), *rel.split(os.sep)[1:])
                dst = os.path.join(site, rel)
                os.makedirs(os.path.dirname(dst))
                shutil.copyfile(src, dst)
            try:
                P.main(site)
            except SystemExit as e:  # a different release than the pins: the bundle step would stop the same way
                self.skipTest(f"installed release differs from the pins: {e}")
            for rel in (P.PIPELINE, P.MISAKI_EN):
                with open(os.path.join(site, rel), encoding="utf-8") as f:
                    src = f.read()
                self.assertIn(P.MARK, src)
                compile(src, rel, "exec")
        finally:
            shutil.rmtree(site)


if __name__ == "__main__":
    unittest.main()
