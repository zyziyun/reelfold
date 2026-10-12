"""The free voice (Kokoro) crashed on some line lengths - demo 2026-10-11 (an English explainer from lesson notes):
"kokoro failed (exit 1): ValueError: [broadcast_shapes] Shapes (1,534600,1) and (1,534900,9) cannot be broadcast",
the same line on every retry, until the narration was reworded into short lines.

Root cause: Kokoro's vocoder (mlx-audio istftnet.SineGen) resamples its F0 track by 1/300 and back by 300, sizing
each step as ceil(n * scale) in floating point; for about one frame count in five (534600 * (1/300) =
1782.0000000000002 -> 1783) the sine source came back 300 samples longer than its voiced mask. A fixed function of
the line's phoneme durations, so retries never helped. vstudio.kokoro_synth.exact_interpolate sizes both resamples
exactly (mlx-audio 0.5.x also trims afterwards; 0.4.x, a plain pip install, did not). Around it: a line any voice
still fails on is retried once in two halves (tts.synth_split) and otherwise stops naming the line; Mandarin pieces
always fit Kokoro's 510-phoneme window, also for run-ons without commas.

Fuzz-style: sizes, splits and chunks over thousands of random lengths / mixtures (zh, en, mixed, numbers, run-ons,
single words); the real misaki G2P where installed; the real vocoder where mlx-audio is installed; real takes in both
a Mandarin and an English voice when VSTUDIO_KOKORO_MODEL points at a downloaded Kokoro folder.

    python3 -m pytest tests/test_kokoro_lengths.py -q
"""
import importlib.util
import math
import os
import pathlib
import random
import sys
import wave

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP = ROOT / "workflows" / "explainer" / "scripts"
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(EXP))

from vstudio import kokoro_g2p as K, kokoro_synth as KS, proctail, tts  # noqa: E402

REAL_MODEL = os.environ.get("VSTUDIO_KOKORO_MODEL")
HAS_MLX_AUDIO = bool(importlib.util.find_spec("mlx_audio"))
HAS_MISAKI = all(importlib.util.find_spec(m) for m in ("misaki", "jieba", "spacy", "en_core_web_sm"))

# the demo's four narration lines (English, voice af_heart): lines 1 and 3 crashed on every take
DEMO = [
    "Put on a pair of noise-cancelling headphones, and the world goes quiet — the engine's hum fades away. But here's "
    "the strange truth: they don't block sound. There's no wall inside the ear cup, no cushion that swallows the "
    "noise. Instead, the headphones add sound — carefully shaped sound that erases the noise before it reaches your "
    "ear. Here's how that trick works.",
    "The headphones use exactly that. A tiny microphone on each ear cup listens to the outside noise. A chip measures "
    "the wave and builds its exact opposite: high where the noise is low, low where the noise is high. It plays that "
    "opposite wave into your ear, right on top of the noise.",
]

EN = ("the a sound wave noise headphones cancel opposite microphone chip listens predict steady hum engine fan voice "
      "door quiet air pressure squeezes over and again key trick works because sudden changes fast through Postgres "
      "GitHub LangChain OpenAI MCP API USB-C GPT-4o HTTP+SSE A2A don't it's we'll").split()
ZHW = ["声音", "耳机", "降噪", "引擎", "风扇", "麦克风", "芯片", "波形", "安静", "预测", "相反", "抵消", "的", "是", "了"]
NUM = ["3", "2024", "1.5", "100%", "42", "0.003", "1,000", "24 kHz", "1782"]
P_EN = [".", ",", "!", "?", ";", ":", " —", "...", ""]
P_ZH = ["。", "，", "！", "？", "；", "：", "——", "……", "、", ""]


def random_text(r, kind=None):
    """A random narration line: zh / en / mixed, numbers, single words, run-ons, odd trailing punctuation."""
    kind = kind or r.choice(["en", "zh", "mixed"])
    if r.random() < .1:
        return r.choice(EN + ZHW + NUM) + r.choice(["", ".", "。", "!", "?", "...", "——", "…", " "])
    sents = []
    for _ in range(r.choice([1, 1, 2, 3, 5, 10, 25])):
        words = []
        for _ in range(r.choice([1, 2, 3, 6, 12, 30, 80])):
            k = kind if kind != "mixed" else r.choice(["en", "zh", "zh", "num"])
            words.append(r.choice(EN if k == "en" else ZHW if k == "zh" else NUM))
            if r.random() < .12:
                words.append(r.choice(P_EN if kind == "en" else P_ZH + P_EN))
        sep = " " if kind == "en" else r.choice(["", " "])
        sents.append(sep.join(words) + r.choice(P_EN if kind == "en" else P_ZH))
    if r.random() < .15:                                              # a run-on: no sentence ends at all
        return " ".join(s.rstrip(".。!?！？…") for s in sents)
    return (" " if kind == "en" else "").join(sents)


def _squash(s):
    return "".join(s.split())


# ------------------------------------------------------------------ the vocoder's resample sizes
def test_scaled_size_is_exact_for_every_frame_count():
    assert math.ceil(534600 * (1 / 300)) == 1783                        # the demo's crash: one frame too many
    assert KS.scaled_size(534600, 1 / 300) == 1782
    assert KS.scaled_size(147600, 1 / 300) == 492                       # the second take of the demo's line 3
    for n in range(1, 40000):
        assert KS.scaled_size(300 * n, 1 / 300) == n
        assert KS.scaled_size(n, 300) == 300 * n
    assert KS.scaled_size(301, 1 / 300) == 2                            # not a multiple: rounded up, as mlx-audio
    assert KS.scaled_size(1, 1 / 300) == 1


@pytest.mark.skipif(not HAS_MLX_AUDIO, reason="mlx-audio not installed (Apple Silicon)")
def test_real_sine_source_matches_its_f0_on_crashing_lengths():
    import mlx.core as mx
    from mlx_audio.tts.models.kokoro import istftnet
    KS.exact_interpolate()
    KS.exact_interpolate()                                              # idempotent
    assert istftnet.interpolate._vstudio_exact
    gen = istftnet.SourceModuleHnNSF(sampling_rate=24000, upsample_scale=300, harmonic_num=8, voiced_threshod=10)
    for frames in (1782, 492, 7, 14, 111, 1783, 1000):
        f0 = mx.full((1, 300 * frames, 1), 180.0)
        sine, noise, uv = gen(f0)
        mx.eval(sine)
        assert sine.shape == (1, 300 * frames, 1) and uv.shape == (1, 300 * frames, 1), frames


# ------------------------------------------------------------------ Mandarin pieces always fit the window
@pytest.mark.parametrize("seed", range(6))
def test_chunks_fuzz_fit_and_keep_every_character(seed):
    r = random.Random(seed)
    for _ in range(300):
        text = random_text(r)
        limit = r.choice([8, 20, 60, 500])
        out = K.chunks(text, len, limit=limit)
        assert _squash("".join(out)) == _squash(text), text            # nothing dropped, nothing doubled
        assert all(c.strip() for c in out)                              # no empty piece (an empty segment)
        assert all(len(c) <= limit for c in out), (limit, [c for c in out if len(c) > limit])


def test_a_run_on_without_marks_is_still_cut():
    assert K.chunks("声" * 50, len, limit=12) and all(len(c) <= 12 for c in K.chunks("声" * 50, len, limit=12))
    words = " ".join(["noise"] * 40)
    assert all(len(c) <= 30 for c in K.chunks(words, len, limit=30))
    assert K.chunks("   ", len) == [] and K.chunks("。", len) == ["。"]


@pytest.mark.skipif(not HAS_MISAKI, reason="misaki[zh,en] + en_core_web_sm not installed (the desk runtime has them)")
def test_real_misaki_fuzz_never_raises_and_fits_510():
    from misaki import zh
    g = K.MixedZhG2P(zh.ZHG2P())
    measure = lambda s: len(g(s)[0])                                    # noqa: E731
    r = random.Random(7)
    for _ in range(60):
        text = random_text(r, r.choice(["zh", "mixed", "en"]))
        for c in K.chunks(text, measure):
            assert measure(c) <= 510, c


# ------------------------------------------------------------------ a failed line: retried in two halves
@pytest.mark.parametrize("seed", range(4))
def test_split_in_two_fuzz(seed):
    r = random.Random(100 + seed)
    for _ in range(400):
        text = random_text(r)
        halves = tts.split_in_two(text)
        if halves is None:
            assert len(text.split()) <= 1 and sum("一" <= c <= "鿿" for c in text) < 2, text
            continue
        a, b = halves
        assert a.strip() and b.strip(), text
        assert _squash(a + b) == _squash(text)


def test_split_in_two_prefers_the_middle_sentence_end():
    assert tts.split_in_two("One chip. Many cores. A million threads.  Each runs once.") == \
        ("One chip. Many cores.", "A million threads. Each runs once.")
    assert tts.split_in_two("先说结论，再看例子，最后总结") == ("先说结论，", "再看例子，最后总结")
    assert tts.split_in_two("noise cancelling works") == ("noise cancelling", "works")
    assert tts.split_in_two("降噪耳机") == ("降噪", "耳机")
    assert tts.split_in_two("Headphones.") is None and tts.split_in_two("声") is None


def _wav(path, n, sr=48000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\1\0" * n)
    return str(path)


def test_concat_wavs_joins_with_a_pause(tmp_path):
    out = tts.concat_wavs([_wav(tmp_path / "a.wav", 1000), _wav(tmp_path / "b.wav", 500)], str(tmp_path / "o.wav"))
    with wave.open(out) as w:
        assert w.getframerate() == 48000 and w.getnframes() == 1500 + int(48000 * tts.GAP_S)


def _run_tts(tmp_path, monkeypatch, synth, lines):
    import runpy
    from vstudio import media
    (tmp_path / "SCRIPT.md").write_text("# Script\n\n" + "".join(
        f"## Line {i} — s\n\n    {t}\n\n" for i, t in enumerate(lines, 1)))
    monkeypatch.setattr(tts, "synth", synth)
    monkeypatch.setattr(tts, "installed", lambda engine: True)
    monkeypatch.setattr(media, "duration", lambda p: 1.0)
    monkeypatch.setattr(sys, "argv", ["tts.py", "--project", str(tmp_path), "--engine", "kokoro", "--no-check"])
    runpy.run_path(str(EXP / "tts.py"), run_name="__main__")


def test_voice_stage_retries_a_failing_line_split_in_two(tmp_path, monkeypatch, capsys):
    calls = []

    def synth(text, out=None, **k):
        calls.append(text)
        if len(text) > 30:                                              # the voice dies on the whole line
            raise RuntimeError("kokoro failed (exit 1):\nValueError: [broadcast_shapes] Shapes (1,534600,1) and "
                               "(1,534900,9) cannot be broadcast.")
        p = out or str(tmp_path / f"take{len(calls)}.wav")
        return _wav(p, 4800)

    _run_tts(tmp_path, monkeypatch, synth, ["Short line.", "One chip has many cores. A million threads run it."])
    assert calls == ["Short line.", "One chip has many cores. A million threads run it.",
                     "One chip has many cores.", "A million threads run it."]
    with wave.open(str(tmp_path / "audio/vo/line02.wav")) as w:
        assert w.getnframes() == 2 * 4800 + int(48000 * tts.GAP_S)
    assert "line 02: the voice failed (RuntimeError: ValueError: [broadcast_shapes]" in capsys.readouterr().out


def test_voice_stage_names_the_line_when_the_split_fails_too(tmp_path, monkeypatch):
    def synth(text, out=None, **k):
        if "cores" in text:
            raise RuntimeError("kokoro failed (exit 1):\nValueError: boom")
        return _wav(out or str(tmp_path / "t.wav"), 4800)

    with pytest.raises(SystemExit) as e:
        _run_tts(tmp_path, monkeypatch, synth, ["Fine line.", "One chip has many cores. Each one is small."])
    msg = str(e.value)
    assert msg.startswith("TTS failed on a line, also split in two")
    assert "line 02: ['One chip has many cores. Each one is small.'] RuntimeError: ValueError: boom; split in two: " \
           "RuntimeError: ValueError: boom" in msg and "line 01" not in msg
    assert proctail.tool_failure("RuntimeError: tts.py exit 1:\n" + msg) == dict(code="stage-voice-failed", params=dict(
        line="2", sentence="One chip has many cores. Each one is small", lines="1", fix="rephrase-line"))


def test_a_missing_key_or_download_is_not_retried(tmp_path, monkeypatch):
    calls = []

    def synth(text, out=None, **k):
        calls.append(text)
        raise tts.VoiceNotDownloaded()

    with pytest.raises(tts.VoiceNotDownloaded):
        _run_tts(tmp_path, monkeypatch, synth, ["One chip has many cores. Each one is small."])
    assert len(calls) == 1


# ------------------------------------------------------------------ real takes (a downloaded model + mlx-audio)
@pytest.mark.skipif(not (REAL_MODEL and HAS_MLX_AUDIO and HAS_MISAKI),
                    reason="needs VSTUDIO_KOKORO_MODEL (a downloaded Kokoro folder), mlx-audio and misaki")
def test_real_takes_fuzz_both_voices():
    from mlx_audio.tts.utils import load_model
    m = load_model(REAL_MODEL, model_type="kokoro")
    r = random.Random(11)
    cases = [(t, "af_heart") for t in DEMO] + [("Headphones.", "af_heart"), ("降噪。", "zf_xiaobei")]
    cases += [(random_text(r, k), v) for k, v in (("en", "af_heart"), ("zh", "zf_xiaobei"), ("mixed", "zf_xiaobei"),
                                                   ("en", "am_michael"), ("mixed", "zm_yunxi"), ("zh", "zm_yunxi"))
              for _ in range(3)]
    for text, voice in cases:
        lang = "z" if voice.startswith("z") else "a"
        audio, sr = KS.synth(text, m, os.path.join(REAL_MODEL, "voices", f"{voice}.safetensors"), lang)
        assert sr == 24000 and len(audio) > sr // 10, (voice, text)
