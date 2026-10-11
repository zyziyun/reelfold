"""The free offline voice (Kokoro-82M via mlx-audio) as the desk app runs it: a local model folder the app downloaded
(apps/desk/packaging/assets.json tts-kokoro -> VSTUDIO_KOKORO_MODEL), never a fetch by the engine inside the app
(VSTUDIO_TTS_MODELS_MANAGED=1), and English number words without num2words (vstudio.numwords_en; the app's runtime
ships no LGPL num2words).

No model and no mlx-audio are needed: the synthesis child is replaced by a fake ``subprocess.run``. A real take runs
when VSTUDIO_KOKORO_MODEL points at a downloaded folder and mlx-audio is installed (the desk's bundle verify always
runs one with the bundled runtime: apps/desk/scripts/runtime/bundle.mjs verifyVoice).

    python3 -m pytest tests/test_tts_kokoro_local.py -q
"""
import importlib.util
import os
import pathlib
import subprocess
import sys
import wave

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from vstudio import proctail, tts  # noqa: E402
from vstudio.numwords_en import num2words  # noqa: E402

REAL_MODEL = os.environ.get("VSTUDIO_KOKORO_MODEL")      # read before the fixtures clear it


@pytest.fixture
def kokoro_dir(tmp_path):
    d = tmp_path / "some-snapshot-hash"           # any folder name loads (the model type is named)
    (d / "voices").mkdir(parents=True)
    (d / "config.json").write_text("{}")
    for v in ("zf_xiaobei", "af_heart"):
        (d / "voices" / f"{v}.safetensors").write_bytes(b"x")
    return d


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (tts.KOKORO_MODEL_ENV, tts.MANAGED_ENV, "VSTUDIO_TTS_ENGINE"):
        monkeypatch.delenv(k, raising=False)


# ------------------------------------------------------------------ number words (misaki.en without num2words)
@pytest.mark.parametrize("n, to, words", [
    (0, "cardinal", "zero"),
    (21, "cardinal", "twenty-one"),
    (123, "cardinal", "one hundred and twenty-three"),
    (1001, "cardinal", "one thousand and one"),
    (1200, "cardinal", "one thousand, two hundred"),
    (1234567, "cardinal", "one million, two hundred and thirty-four thousand, five hundred and sixty-seven"),
    (-5, "cardinal", "minus five"),
    (1, "ordinal", "first"),
    (21, "ordinal", "twenty-first"),
    (12, "ordinal", "twelfth"),
    (40, "ordinal", "fortieth"),
    (101, "ordinal", "one hundred and first"),
    (1984, "year", "nineteen eighty-four"),
    (1900, "year", "nineteen hundred"),
    (1905, "year", "nineteen oh-five"),
    (2000, "year", "two thousand"),
    (2005, "year", "two thousand and five"),
    (2010, "year", "twenty ten"),
    (2024, "year", "twenty twenty-four"),
])
def test_number_words_match_num2words(n, to, words):
    # expected values are num2words 0.5.14's English output (compared over 0..10^15 when this was written)
    assert num2words(n, to=to) == words


def test_decimals_match_num2words():
    assert num2words(3.14) == "three point one four"
    assert num2words(3.5) == "three point five"
    assert num2words(2.0) == "two"
    assert num2words(-2.75) == "minus two point seven five"
    with pytest.raises(NotImplementedError):
        num2words(3, to="currency")


# ------------------------------------------------------------------ where the model comes from
def test_model_env_then_persona_then_hub(kokoro_dir, monkeypatch):
    assert tts.kokoro_model() == tts.DEFAULT_MODEL["kokoro"]
    assert tts.kokoro_voices() is None                        # a hub repo: any voice, fetched on use
    monkeypatch.setenv(tts.KOKORO_MODEL_ENV, str(kokoro_dir))
    assert tts.kokoro_model() == str(kokoro_dir)
    assert tts.kokoro_voices() == ["af_heart", "zf_xiaobei"]
    assert tts.kokoro_model("other/repo") == "other/repo"     # an explicit model wins
    assert tts.kokoro_lang(str(kokoro_dir / "voices" / "zf_xiaobei.safetensors")) == "z"


def test_ready_only_with_the_download_in_the_app(kokoro_dir, monkeypatch):
    assert tts.kokoro_ready()                                 # CLI: mlx-audio fetches the repo on use
    monkeypatch.setenv(tts.MANAGED_ENV, "1")
    assert not tts.kokoro_ready()                             # the app before its download
    monkeypatch.setenv(tts.KOKORO_MODEL_ENV, str(kokoro_dir))
    assert tts.kokoro_ready()


# ------------------------------------------------------------------ the take
class FakeRun:
    def __init__(self, ok=True):
        self.calls, self.ok = [], ok

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if self.ok:
            out = cmd[cmd.index("--out") + 1]
            with wave.open(out, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(24000)
                w.writeframes(b"\0\0" * 24000)
        return subprocess.CompletedProcess(cmd, 0 if self.ok else 1, "", "" if self.ok else "boom")


@pytest.fixture
def mlx_audio_present(monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(tts.importlib.util, "find_spec", lambda n, *a: object() if n == "mlx_audio" else real(n, *a))


def test_local_folder_take_is_offline(kokoro_dir, tmp_path, monkeypatch, mlx_audio_present):
    monkeypatch.setenv(tts.KOKORO_MODEL_ENV, str(kokoro_dir))
    monkeypatch.setenv(tts.MANAGED_ENV, "1")
    run = FakeRun()
    monkeypatch.setattr(tts.subprocess, "run", run)
    dst = tmp_path / "raw.wav"
    tts._kokoro("你好。", "zf_xiaobei", 1.0, tts.kokoro_model(), str(dst), str(tmp_path))
    cmd, kw = run.calls[0]
    assert cmd[:3] == [sys.executable, "-m", "vstudio.kokoro_synth"]
    assert cmd[cmd.index("--voice") + 1] == str(kokoro_dir / "voices" / "zf_xiaobei.safetensors")
    assert cmd[cmd.index("--lang") + 1] == "z"
    assert kw["input"] == "你好。"                              # the text on stdin, never on the command line
    assert kw["env"]["HF_HUB_OFFLINE"] == "1"
    assert str(ROOT / "lib") in kw["env"]["PYTHONPATH"].split(os.pathsep)
    assert dst.exists()


def test_voice_the_folder_lacks_names_what_it_has(kokoro_dir, tmp_path, monkeypatch, mlx_audio_present):
    monkeypatch.setattr(tts.subprocess, "run", FakeRun())
    with pytest.raises(RuntimeError, match=r"'zf_xiaoxiao' is not downloaded .*af_heart, zf_xiaobei"):
        tts._kokoro("你好", "zf_xiaoxiao", 1.0, str(kokoro_dir), str(tmp_path / "o.wav"), str(tmp_path))


def test_app_never_fetches_the_model(tmp_path, monkeypatch, mlx_audio_present):
    monkeypatch.setenv(tts.MANAGED_ENV, "1")
    run = FakeRun()
    monkeypatch.setattr(tts.subprocess, "run", run)
    with pytest.raises(tts.VoiceNotDownloaded) as e:
        tts._kokoro("hi", "af_heart", 1.0, tts.kokoro_model(), str(tmp_path / "o.wav"), str(tmp_path))
    assert not run.calls
    # the desk words it and offers the download (pilot failure code tool-voice)
    assert proctail.tool_failure(f"RuntimeError: tts.py exit 1: {e.value}") == dict(
        code="tool-voice", params=dict(tool="voice", fix="download-voice"))
    row = next(r for r in tts.providers(probe=False) if r["provider"] == "kokoro")
    assert not row["ready"]


def test_child_failure_is_reported(kokoro_dir, tmp_path, monkeypatch, mlx_audio_present):
    monkeypatch.setattr(tts.subprocess, "run", FakeRun(ok=False))
    with pytest.raises(RuntimeError, match=r"kokoro failed \(exit 1\):\s+boom"):
        tts._kokoro("hi", "af_heart", 1.0, str(kokoro_dir), str(tmp_path / "o.wav"), str(tmp_path))


@pytest.mark.skipif(not (REAL_MODEL and importlib.util.find_spec("mlx_audio")),
                    reason="needs VSTUDIO_KOKORO_MODEL (a downloaded Kokoro folder) and mlx-audio")
def test_real_take(tmp_path, monkeypatch):
    monkeypatch.setenv(tts.KOKORO_MODEL_ENV, REAL_MODEL)
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path))
    for text, voice in (("你好，欢迎来到这门课。", "zf_xiaobei"), ("Welcome back.", "af_heart")):
        with wave.open(tts.synth(text, engine="kokoro", voice=voice, cache=False)) as w:
            assert w.getframerate() == tts.SR and w.getnframes() > tts.SR // 2
