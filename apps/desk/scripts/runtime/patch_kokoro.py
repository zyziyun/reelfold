"""Bundle-time patch: Kokoro (mlx-audio + misaki) without espeak-ng and without num2words.

The app's runtime keeps its licences permissive. Kokoro's English G2P (misaki.en) has two optional helpers it cannot
use there:
  - espeak-ng (GPL-3.0, via ``espeakng-loader`` + ``phonemizer-fork``): misaki's fallback for words missing from its
    dictionaries. ``packaging/runtime.lock.json`` drops both (uv override). mlx-audio already treats a failing
    ``EspeakFallback()`` as "no fallback" (out-of-dictionary words are skipped), but it imports ``misaki.espeak``
    *before* that try, so the import error would stop every English voice. This moves the import inside the try.
  - num2words (LGPL-2.1): number words. ``misaki/en.py`` imports it at the top; this falls back to the engine's own
    ``vstudio.numwords_en`` (same English output for the calls misaki makes; the engine is on the runtime's
    PYTHONPATH).
Chinese (misaki.zh: jieba + pypinyin + cn2an) needs neither.

    python patch_kokoro.py <site-packages>     # run by scripts/runtime/bundle.mjs after pip install

Fails loudly when a file no longer looks as expected (a new mlx-audio / misaki release): re-check and update the patch.
tests: scripts/runtime/test_patch_kokoro.py.
"""
import os
import sys

MARK = "# Reelfold runtime"

PIPELINE = os.path.join("mlx_audio", "tts", "models", "kokoro", "pipeline.py")
PIPELINE_OLD = ("            espeak = _get_misaki_espeak()\n"
                "            try:\n"
                "                fallback = espeak.EspeakFallback(")
PIPELINE_NEW = ("            try:\n"
                f"                espeak = _get_misaki_espeak()  {MARK}: no espeak-ng -> no fallback (patch_kokoro.py)\n"
                "                fallback = espeak.EspeakFallback(")

MISAKI_EN = os.path.join("misaki", "en.py")
MISAKI_OLD = "from num2words import num2words\n"
MISAKI_NEW = ("try:\n"
              "    from num2words import num2words\n"
              f"except ImportError:  {MARK}: no num2words (LGPL) -> vstudio.numwords_en (patch_kokoro.py)\n"
              "    from vstudio.numwords_en import num2words\n")


def _patch(src, old, new, name):
    if MARK in src:
        return src
    if src.count(old) != 1:
        raise SystemExit(f"{name} changed: expected exactly one\n{old}\n- update apps/desk/scripts/runtime/patch_kokoro.py")
    return src.replace(old, new)


def patch_pipeline(src):
    """mlx_audio kokoro pipeline.py source -> patched (idempotent)."""
    return _patch(src, PIPELINE_OLD, PIPELINE_NEW, PIPELINE)


def patch_misaki_en(src):
    """misaki/en.py source -> patched (idempotent)."""
    return _patch(src, MISAKI_OLD, MISAKI_NEW, MISAKI_EN)


def main(site):
    for rel, fn in ((PIPELINE, patch_pipeline), (MISAKI_EN, patch_misaki_en)):
        path = os.path.join(site, rel)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        out = fn(src)
        if out != src:
            with open(path, "w", encoding="utf-8") as f:
                f.write(out)
        print(f"patched {path}")


if __name__ == "__main__":
    main(sys.argv[1])
