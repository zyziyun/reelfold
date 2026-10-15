"""Spoken language: "auto" detects it per recording (the desk app sets VSTUDIO_ASR_LANGUAGE=auto for a creator without
a persona, whose bundled example persona says "zh"); the intake samples detect once and reuse it."""
import shutil

import pytest

from vstudio import asr
from vstudio.intake import inventory as I


def test_default_language_env_then_persona(monkeypatch):
    monkeypatch.delenv("VSTUDIO_ASR_LANGUAGE", raising=False)
    assert asr.default_language() == asr._persona_language()
    monkeypatch.setenv("VSTUDIO_ASR_LANGUAGE", "Auto")
    assert asr.default_language() == "auto"


def test_auto_detects_before_transcribing(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    src = tmp_path / "a.wav"
    import numpy as np
    from vstudio import audio
    audio.write_wav(str(src), np.zeros((16000, 1), dtype=np.float32), 16000)
    calls = []
    monkeypatch.setitem(asr._DETECT, "mlx", lambda wav, model: "en")
    monkeypatch.setitem(asr._RUN, "mlx", lambda wav, language, *a, **k: calls.append(language) or [])
    monkeypatch.setattr(asr, "_backend", lambda name="auto": "mlx")
    monkeypatch.setenv("VSTUDIO_ASR_LANGUAGE", "auto")
    tr = asr.transcribe(str(src), cache=False)
    assert calls and calls[0] == "en" and tr["language"] == "en"
    # a detection that fails falls back to the persona's language, never crashes the transcription
    monkeypatch.setitem(asr._DETECT, "mlx", lambda wav, model: (_ for _ in ()).throw(RuntimeError("no model")))
    calls.clear()
    asr.transcribe(str(src), cache=False)
    assert calls[0] == asr._persona_language()


def test_intake_samples_detect_once(tmp_path, monkeypatch):
    langs = []

    def fake(wav, language):
        langs.append(language)
        return dict(language="en", segments=[dict(start=0, end=2, text="hello there everyone")], words=[])
    monkeypatch.setattr(I, "TRANSCRIBE", fake)
    monkeypatch.setattr(I, "_wav_sample", lambda src, dst, st, ln: dst)
    out = I.speech_facts("x.mp4", 300.0, True, "sample", str(tmp_path), "k")
    assert out["language"] == "en"
    assert langs == [None, "en", "en"]           # the first sample detects, the next two reuse it


@pytest.mark.parametrize("texts,spoken", [
    (["Привет мир", "До встречи"], ["Привет", "мир", "До", "встречи"]),
    (["مرحبا بالعالم", "إلى اللقاء"], ["مرحبا", "بالعالم", "إلى", "اللقاء"]),
    (["नमस्ते दुनिया", "फिर मिलेंगे"], ["नमस्ते", "दुनिया", "फिर", "मिलेंगे"]),
    (["Café crème", "Été fini"], ["Cafe\u0301", "cre\u0300me", "E\u0301te\u0301", "fini"]),
    (["你好世界", "再见朋友"], ["你好", "世界", "再见", "朋友"]),
    (["こんにちは世界", "また会いましょう"], ["こんにちは", "世界", "また", "会いましょう"]),
    (["안녕하세요 여러분", "다음에 만나요"], ["안녕하세요", "여러분", "다음에", "만나요"]),
    (["１２ photos", "Très bien"], ["12", "photos", "Très", "bien"]),
])
def test_script_cues_keep_multilingual_word_timestamps(texts, spoken):
    words = [dict(w=w, t=t, te=t + 0.6) for w, t in zip(spoken, [0.4, 1.2, 3.1, 4.2])]
    assert asr.align_script(texts, words, 5.5) == [dict(start=0.4, end=1.8), dict(start=3.1, end=4.8)]


def test_alignment_preserves_accent_distinctions_and_ignores_markup():
    assert asr.alignment_tokens("**été** ≠ été / été") == ["été", "été", "été"]
    # All-accent words used to disappear completely, yielding zero-duration cues.
    assert asr.align_script(["é", "è"], [("è", 0.1, 0.4), ("é", 1.2, 1.5)], 2)[0] == dict(start=1.2, end=1.5)
    assert asr.alignment_tokens("don't DON’T") == ["dont", "dont"]


def test_photo_story_selects_multilingual_spoken_variant():
    import importlib.util
    import sys
    from pathlib import Path
    scripts = str(Path(__file__).resolve().parents[1] / "workflows/photo-story/scripts")
    sys.path.insert(0, scripts)
    try:
        spec = importlib.util.spec_from_file_location("photo_tts_unicode_test", Path(scripts) / "photostory/tts.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        variants = [["До встречи", "Привет мир"], ["Привет мир", "До встречи"]]
        words = [("Привет", 0.4, 1.0), ("мир", 1.2, 1.8), ("До", 3.1, 3.7), ("встречи", 4.2, 4.8)]
        assert mod.best_align(variants, words, 5.5) == [dict(start=0.4, end=1.8), dict(start=3.1, end=4.8)]
    finally:
        sys.path.remove(scripts)
