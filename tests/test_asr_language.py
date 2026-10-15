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


@pytest.mark.parametrize('text,expected', [
    ('Привет мир.', ['Привет', 'мир.']),
    ('مرحبا بالعالم.', ['مرحبا', 'بالعالم.']),
    ('यह पहला वीडियो है।', ['यह', 'पहला', 'वीडियो', 'है।']),
    ('Café crème.', ['Café', 'crème.']),
    ('Cafe\u0301 cre\u0300me.', ['Cafe\u0301', 'cre\u0300me.']),
    ('你好，world!', ['你', '好，', 'world!']),
    ('こんにちは世界。', list('こんにちは世') + ['界。']),
    ('안녕 세계.', ['안녕', '세계.']),
    ('«Hello» (world)!', ['«Hello»', '(world)!']),
    ('**Keep** literal markup.', ['**Keep**', 'literal', 'markup.']),
])
def test_segment_only_timing_preserves_unicode_words_and_server_text(text, expected):
    words = asr._spread_words(dict(text=text, start=1.25, end=5.25))
    assert [w['word'].strip() for w in words] == expected
    assert ''.join(w['word'] for w in words) == text
    assert words[0]['start'] == 1.25 and words[-1]['end'] == 5.25
    assert all(1.25 <= w['start'] < w['end'] <= 5.25 for w in words)
    assert all(a['end'] == b['start'] for a, b in zip(words, words[1:]))
    from vstudio import subs
    cues = subs.cues_from_words(words, fixes=False)
    assert subs.join_caption(c.text for c in cues) == text


@pytest.mark.parametrize('text', ['', '  ', '…!?', '😊'])
def test_segment_only_non_speech_does_not_become_a_word(text):
    assert asr._spread_words(dict(text=text, start=0, end=2)) == []


@pytest.mark.parametrize('start,end', [(2, 1), (1, 1), (-1, 2), (0, float('nan')), (0, float('inf'))])
def test_segment_only_invalid_times_are_not_fabricated(start, end):
    with pytest.raises(ValueError, match='invalid start/end'):
        asr._spread_words(dict(text='مرحبا.', start=start, end=end))


@pytest.mark.parametrize('invalid_times', [False, True])
def test_approximate_cached_words_recover_locally_without_retranscribing(tmp_path, monkeypatch, invalid_times):
    import json
    src = tmp_path / 'recording.wav'
    src.write_bytes(b'cache-hit never decodes this fixture')
    monkeypatch.setattr(asr, '_backend', lambda backend='auto': 'openai-compatible')
    monkeypatch.setattr(asr, '_hst', lambda *a: None)
    def forbidden(*args, **kwargs):
        pytest.fail('A cached segment must be repaired without audio extraction or another provider call')
    monkeypatch.setattr(asr.media, 'extract_wav', forbidden)
    monkeypatch.setitem(asr._RUN, 'openai-compatible', forbidden)
    raw = dict(language='ar', backend='openai-compatible', segments=[
        dict(start=1, end=3, text='مرحبا بالعالم.', approx_words=True, words=[])])
    if invalid_times:
        raw['segments'][0]['end'] = 0
    key = asr._cache_key(asr.file_hash(str(src)), 'ar', 'test', True, None, 'openai-compatible', None)
    cp = tmp_path / 'recording.wav.asr.json'
    cp.write_text(json.dumps({key: raw}, ensure_ascii=False))
    before = cp.read_bytes()
    def read():
        return asr.transcribe(str(src), language='ar', prompt='test', fix_terms=False, drop_hallucinated=False)
    if invalid_times:
        with pytest.raises(ValueError, match='invalid start/end'):
            read()
    else:
        result = read()
        assert [w['w'] for w in result['words']] == ['مرحبا', 'بالعالم.']
        assert result['segments'][0]['approx_words'] is True
    assert cp.read_bytes() == before


def test_verified_word_times_are_never_evenly_redistributed():
    raw = dict(language='ru', backend='openai', segments=[dict(start=0, end=4, text='Привет мир.', words=[
        dict(word='Привет', start=.3, end=.8), dict(word=' мир.', start=2.4, end=3.1)])])
    result = asr._finish(raw, None, False)
    assert [(w['t'], w['te']) for w in result['words']] == [(.3, .8), (2.4, 3.1)]


@pytest.mark.parametrize('texts,expected', [
    (['Hello.', 'Check captions.'], 'Hello. Check captions.'),
    (['Привет.', 'Проверьте субтитры.'], 'Привет. Проверьте субтитры.'),
    (['مرحبا.', 'راجع الترجمة.'], 'مرحبا. راجع الترجمة.'),
    (['안녕하세요.', '다시 만나요.'], '안녕하세요. 다시 만나요.'),
    (['你好。', '再见。'], '你好。再见。'),
])
@pytest.mark.parametrize('drop_filter', [False, True])
def test_transcript_segment_seams_preserve_language_spacing(texts, expected, drop_filter):
    raw = dict(segments=[dict(start=i, end=i+1, text=t, words=[]) for i,t in enumerate(texts)])
    result = asr._finish(raw, None, False, drop_hallucinated=drop_filter)
    assert result['text'] == expected
    assert [s['text'] for s in result['segments']] == texts


def test_hallucination_removal_keeps_readable_transcript_seams():
    raw = dict(segments=[dict(start=i, end=i+1, text=t, words=[]) for i,t in
                         enumerate(['Hello.', '字幕志愿者', 'Check captions.'])])
    result = asr._finish(raw, None, False, drop_hallucinated=True)
    assert result['text'] == 'Hello. Check captions.'
    assert len(result['dropped']) == 1 and len(raw['segments']) == 3
