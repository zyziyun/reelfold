"""The free Chinese voice: Qwen3-TTS 1.7B CustomVoice through mlx-audio (vstudio.qwen_synth, vstudio.qwen_bpe), and
the rules that pick it - a Chinese line meant for the free voice is said by it once it is on this computer (her review:
"中文的tts语音得改一下，现在的太难听了"; the A/B is in the desk's ux/zh-voice notes).

No model is needed: the synthesis child is replaced by a fake ``subprocess.run`` and the tokenizer is checked on a
tiny vocabulary. With the real model (VSTUDIO_QWEN_TTS_MODEL = the downloaded folder) the tokenizer is also checked
against ids recorded from transformers' Qwen2Tokenizer, and with mlx-audio + mlx-whisper a take is transcribed back
(Whisper round trip). The desk's bundle verify always says a Chinese line with the bundled runtime
(apps/desk/scripts/runtime/bundle.mjs verifyChineseVoice).

    python3 -m pytest tests/test_qwen_tts.py -q
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import wave

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from vstudio import narration, proctail, qwen_synth as QS, tts  # noqa: E402
from vstudio.qwen_bpe import QwenBPE, bytes_to_unicode  # noqa: E402

REAL_MODEL = os.environ.get(tts.QWEN_MODEL_ENV)          # read before the fixtures clear it


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (tts.QWEN_MODEL_ENV, tts.KOKORO_MODEL_ENV, tts.MANAGED_ENV, tts.PREFS_ENV, "VSTUDIO_TTS_ENGINE",
              "OPENAI_API_KEY", "ELEVENLABS_API_KEY", tts.ZH_LOCAL_ENV, "VSTUDIO_TTS_BASE_URL"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def here(monkeypatch):
    """This computer has the free voices (Apple silicon + mlx-audio) and the Chinese one is not switched off."""
    monkeypatch.delenv(tts.QWEN_OFF_ENV, raising=False)
    monkeypatch.setattr(tts, "installed", lambda e: True)
    monkeypatch.setattr(tts, "available_engine", lambda name="auto": "kokoro" if name in (None, "auto") else name)


# ------------------------------------------------------------------------------------------------ which voice speaks
def test_chinese_on_the_free_voice_goes_to_qwen(here):
    assert tts.qwen_ready() and tts.zh_engine("kokoro") == "qwen" and tts.zh_engine("auto") == "auto"
    assert tts.zh_engine("openai") == "openai" and tts.zh_engine("clone") == "clone"   # they speak Chinese themselves
    assert tts.zh_voice_engine() == "qwen" and tts.zh_narration_ok()
    plan = narration.voice_plan("zh")
    assert (plan["narrate"], plan["sub_lead"], plan["engine"], plan["note"]) == ("zh", "zh", "qwen", None)
    assert narration.voice_plan("en")["engine"] == "kokoro"                            # English stays on Kokoro


def test_in_the_app_only_once_downloaded(here, monkeypatch, tmp_path):
    monkeypatch.setenv(tts.MANAGED_ENV, "1")
    assert not tts.qwen_ready() and tts.zh_engine("kokoro") == "kokoro"
    assert tts.zh_voice_engine() is None                                   # English narration + the download note
    assert "Settings > Voice" in tts.ZH_LOCAL_NOTE["en"] and "设置 > 配音" in tts.ZH_LOCAL_NOTE["zh"]
    monkeypatch.setenv(tts.ZH_LOCAL_ENV, "1")
    assert tts.zh_voice_engine() == "kokoro"                               # she asked for Kokoro's Mandarin anyway
    monkeypatch.delenv(tts.ZH_LOCAL_ENV)
    monkeypatch.setenv(tts.QWEN_MODEL_ENV, str(tmp_path))                   # the download is there
    assert tts.qwen_ready() and tts.zh_voice_engine() == "qwen"


def test_settings_switch_for_the_builtin_chinese_voice(here, monkeypatch, tmp_path):
    """Settings > Voice "use the built-in Chinese voice until then" (prefs zh_local): Kokoro's Mandarin narrates a
    Chinese version only while Qwen3-TTS is not downloaded; once it is, Qwen3-TTS always wins (it IS the better
    voice). Off (the default): English narration + Chinese subtitles, and the plan card offers the download."""
    monkeypatch.setenv(tts.MANAGED_ENV, "1")
    prefs = tmp_path / "tts-prefs.json"
    monkeypatch.setenv(tts.PREFS_ENV, str(prefs))
    prefs.write_text(json.dumps(dict(zh_voice="serena", zh_local=False)))
    assert not tts.zh_local_opt_in() and tts.zh_voice_engine() is None
    assert narration.voice_plan("zh")["narrate"] == "en"
    prefs.write_text(json.dumps(dict(zh_voice="serena", zh_local=True)))         # read on every take: no restart
    assert tts.zh_local_opt_in() and tts.zh_voice_engine() == "kokoro"
    assert narration.voice_plan("zh")["narrate"] == "zh"
    model = tmp_path / "qwen"
    model.mkdir()
    monkeypatch.setenv(tts.QWEN_MODEL_ENV, str(model))                           # downloaded: Qwen3-TTS, not Kokoro
    assert tts.zh_voice_engine() == "qwen" and tts.zh_voice("qwen") == "serena"


def test_switched_off_or_no_apple_silicon(monkeypatch):
    monkeypatch.setattr(tts, "available_engine", lambda name="auto": "kokoro")
    monkeypatch.setenv(tts.QWEN_OFF_ENV, "off")
    monkeypatch.setattr(tts, "installed", lambda e: True)
    assert not tts.qwen_ready() and tts.zh_voice_engine() is None
    monkeypatch.delenv(tts.QWEN_OFF_ENV)
    monkeypatch.setattr(tts, "installed", lambda e: e not in ("kokoro", "qwen", "clone"))
    assert not tts.qwen_ready()


def test_her_chinese_voice_choice(here, monkeypatch, tmp_path):
    assert tts.zh_voice("qwen") == "serena" == tts.ZH_VOICE["qwen"]
    prefs = tmp_path / "tts-prefs.json"
    prefs.write_text(json.dumps({"zh_voice": "uncle_fu"}))
    monkeypatch.setenv(tts.PREFS_ENV, str(prefs))
    assert tts.zh_voice("qwen") == "uncle_fu"
    prefs.write_text(json.dumps({"zh_voice": "zf_xiaobei"}))                # not a Qwen speaker: the default
    assert tts.zh_voice("qwen") == "serena"
    prefs.write_text("{not json")
    assert tts.zh_voice("qwen") == "serena" and tts.zh_voice("kokoro") == "zf_xiaobei"
    assert tts.pick_engine("qwen3") == "qwen" and "qwen" in tts.LOCAL and "qwen" in tts.ENGINES


# ------------------------------------------------------------------------------------------------ synthesis (faked)
def _fake_child(calls, seconds=2.0):
    def run(cmd, input=None, capture_output=True, text=True, env=None, **kw):
        if "vstudio.qwen_synth" not in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        calls.append(dict(cmd=cmd, text=input, env=env))
        out = cmd[cmd.index("--out") + 1]
        with wave.open(out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\x00\x10" * int(24000 * seconds))
        return subprocess.CompletedProcess(cmd, 0, "qwen: ok", "")
    return run


def test_synth_runs_the_child_offline_on_the_downloaded_folder(here, monkeypatch, tmp_path):
    model = tmp_path / "qwen3-tts"
    model.mkdir()
    monkeypatch.setenv(tts.QWEN_MODEL_ENV, str(model))
    monkeypatch.setenv(tts.MANAGED_ENV, "1")
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: object() if n == "mlx_audio" else None)
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_child(calls))
    from vstudio import media
    monkeypatch.setattr(media, "run", lambda cmd, **kw: _ffmpeg_copy(cmd))
    out = tts.synth("大家好，今天聊聊 MCP。", engine="qwen", voice=tts.zh_voice("qwen"), out=str(tmp_path / "a.wav"),
                    speed=1.1)
    assert os.path.exists(out) and len(calls) == 1
    c = calls[0]
    assert c["cmd"][c["cmd"].index("--model") + 1] == str(model) and c["cmd"][c["cmd"].index("--voice") + 1] == "serena"
    assert c["env"]["HF_HUB_OFFLINE"] == "1" and c["text"] == "大家好，今天聊聊 MCP。"
    assert _LAST_FFMPEG and "atempo=1.1000" in " ".join(_LAST_FFMPEG)     # Qwen3-TTS has no speed: ffmpeg does it


_LAST_FFMPEG = []


def _ffmpeg_copy(cmd):
    import shutil
    _LAST_FFMPEG[:] = cmd
    shutil.copyfile(cmd[cmd.index("-i") + 1], cmd[-1])


def test_not_downloaded_in_the_app_names_the_chinese_voice(here, monkeypatch, tmp_path):
    monkeypatch.setenv(tts.MANAGED_ENV, "1")
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: object() if n == "mlx_audio" else None)
    with pytest.raises(tts.VoiceNotDownloaded) as e:
        tts.synth("你好", engine="qwen")
    assert e.value.chinese and "free Chinese voice is not downloaded" in str(e.value)
    assert proctail.voice_failure(str(e.value)) == dict(code="tool-voice",
                                                        params=dict(tool="voice", fix="download-zh-voice"))
    assert proctail.voice_failure(str(tts.VoiceNotDownloaded()))["params"]["fix"] == "download-voice"


# ------------------------------------------------------------------------------------------------ the take's checks
def test_long_lines_go_in_sentence_pieces():
    text = "清晨的薄雾慢慢散开，湖面上倒映着远处的雪山。" * 8
    ps = QS.pieces(text)
    assert len(ps) > 1 and all(len(p) <= QS.MAX_PIECE for p in ps) and "".join(ps) == text
    assert QS.pieces("短句。") == ["短句。"]
    run_on = "这是一个没有句号但是有逗号，" * 20
    assert all(len(p) <= QS.MAX_PIECE for p in QS.pieces(run_on))


def test_a_take_that_runs_on_or_stops_early_is_not_plausible():
    line = "大家好，今天我们聊一聊怎么用 MCP 把大模型连到你自己的工具上。"
    e = QS.expected_seconds(line)
    assert 5.0 < e < 9.0
    assert QS.plausible(6.6, line) and QS.plausible(9.5, line)
    assert not QS.plausible(16.7, line + "")      # the 4-bit model's babble after the line (A/B line 1: 16.7 s)
    assert not QS.plausible(1.0, line)


def test_silence_is_trimmed_to_a_breath():
    import numpy as np
    sr = 24000
    a = np.concatenate([np.zeros(sr), 0.2 * np.ones(sr), np.zeros(3 * sr)]).astype("float32")
    b = QS.trim_silence(a, sr)
    assert 1.0 <= len(b) / sr <= 1.0 + 2 * 0.12 + 0.05


def test_codec_imports_stay_light(monkeypatch):
    """mlx_audio.codec's __init__ imports every codec (chatterbox -> tokenizers, MiMo -> scipy); the child registers
    the two package modules bare so only mimi loads."""
    if not importlib.util.find_spec("mlx_audio"):
        pytest.skip("mlx-audio not installed")
    for k in [k for k in sys.modules if k == "mlx_audio.codec" or k.startswith("mlx_audio.codec.")]:
        monkeypatch.delitem(sys.modules, k)
    QS.light_codec_imports()
    import mlx_audio.codec as C
    assert not hasattr(C, "Mimi")                                  # the bare package, not codec/__init__.py
    from mlx_audio.codec.models.mimi import modules                # noqa: F401  (a submodule still loads)


# ------------------------------------------------------------------------------------------------ the tokenizer
def _toy(tmp_path):
    bm = bytes_to_unicode()
    sp = bm[ord(" ")]
    vocab = {c: i for i, c in enumerate(sorted(set(bm.values())))}
    merges = [("h", "e"), ("he", "l"), ("hel", "l"), ("hell", "o"), (sp, "w")]
    for a, b in merges:
        vocab.setdefault(a + b, len(vocab))
    (tmp_path / "vocab.json").write_text(json.dumps(vocab))
    (tmp_path / "merges.txt").write_text("#version: 0.2\n" + "\n".join(f"{a} {b}" for a, b in merges) + "\n")
    (tmp_path / "tokenizer_config.json").write_text(json.dumps({"added_tokens_decoder": {
        "9000": {"content": "<|im_start|>"}, "9001": {"content": "<tts_text_bos>"},
        "9002": {"content": "<tts_text_bos_single>"}}}))
    return QwenBPE.from_dir(str(tmp_path)), vocab, sp


def test_bpe_merges_by_rank_and_keeps_special_tokens_whole(tmp_path):
    tok, vocab, sp = _toy(tmp_path)
    assert tok.encode("hello") == [vocab["hello"]]
    assert tok.encode("hello wow") == [vocab["hello"], vocab[sp + "w"], vocab["o"], vocab["w"]]
    assert tok.encode("<|im_start|>hello<tts_text_bos_single>") == [9000, vocab["hello"], 9002]   # longest first
    ids = tok.encode("好")                                               # 3 UTF-8 bytes, no merges -> 3 ids
    assert len(ids) == 3


@pytest.mark.skipif(not (REAL_MODEL and os.path.isfile(os.path.join(REAL_MODEL, "vocab.json"))),
                    reason="VSTUDIO_QWEN_TTS_MODEL (the downloaded Qwen3-TTS folder) not set")
def test_bpe_matches_transformers_on_the_real_vocabulary():
    tok = QwenBPE.from_dir(REAL_MODEL)
    # recorded from transformers.AutoTokenizer (Qwen2Tokenizer) on mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit
    assert tok.encode("<|im_start|>assistant\n大家好，今天聊聊 MCP 和 Tool Calling。<|im_end|>\n<|im_start|>assistant\n") \
        == [151644, 77091, 198, 99466, 52801, 3837, 100644, 115604, 79148, 58143, 13474, 32291, 1773, 151645, 198,
            151644, 77091, 198]
    assert tok.encode("It's GPT-4o's API: 1962年，184米！") == [2132, 594, 479, 2828, 12, 19, 78, 594, 5333, 25, 220,
                                                                16, 24, 21, 17, 7948, 3837, 16, 23, 19, 72261, 6313]


@pytest.mark.slow  # a real take + Whisper: a minute on Apple silicon (pyproject.toml tiers)
@pytest.mark.skipif(not (REAL_MODEL and os.path.isdir(REAL_MODEL) and importlib.util.find_spec("mlx_audio")
                         and importlib.util.find_spec("mlx_whisper")),
                    reason="needs VSTUDIO_QWEN_TTS_MODEL, mlx-audio and mlx-whisper")
def test_whisper_round_trip(tmp_path, monkeypatch):
    import re
    import mlx_whisper
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    line = "大家好，今天我们聊一聊怎么用 MCP 把大模型连到你自己的工具上。银行行长说，我们还得多学习。"
    wav = tts.synth(line, engine="qwen", voice="serena", model=REAL_MODEL, out=str(tmp_path / "t.wav"))
    model = os.environ.get("VSTUDIO_WHISPER_MLX") or "mlx-community/whisper-large-v3-turbo"
    hyp = mlx_whisper.transcribe(wav, path_or_hf_repo=model, language="zh",
                                 initial_prompt="以下是普通话的句子。")["text"]
    norm = lambda s: re.sub(r"[^\w]", "", s.lower())
    ref, got = norm(line), norm(hyp)
    d = list(range(len(got) + 1))
    for i, a in enumerate(ref, 1):
        p, d[0] = d[0], i
        for j, b in enumerate(got, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (a != b))
    assert d[-1] / len(ref) < 0.1, hyp


@pytest.mark.parametrize("text,locale,expected", [
    ("今日は動画を作ります。", None, "japanese"), ("오늘 영상을 만듭니다.", None, "korean"),
    ("Сегодня делаем видео.", None, "russian"), ("Bonjour", "fr-FR", "french"),
    ("Hello", "KO_kr", "korean"), ("你好", None, "chinese"), ("Hello", None, "english")])
def test_language_is_preserved_or_inferred_from_distinctive_script(text, locale, expected):
    assert QS.language_for(text, locale) == expected
    assert QS.expected_seconds(text) > 0


def test_non_latin_duration_is_not_treated_as_zero():
    for text in ["今日は動画の字幕を確認します。", "오늘 동영상의 자막을 확인합니다.",
                 "Сегодня мы проверяем субтитры в этом видео."]:
        assert QS.expected_seconds(text) > 2
        assert QS.plausible(4, text)
    with pytest.raises(ValueError, match="does not support"):
        QS.language_for("test", "ar")


def test_qwen_language_reaches_child_and_separates_cache(here, monkeypatch, tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    monkeypatch.setenv(tts.QWEN_MODEL_ENV, str(model))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a: object() if n == "mlx_audio" else None)
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_child(calls))
    from vstudio import media
    monkeypatch.setattr(media, "run", lambda cmd, **kw: _ffmpeg_copy(cmd))
    en = tts.synth("Bonjour", engine="qwen", language="en")
    fr = tts.synth("Bonjour", engine="qwen", language="fr-FR")
    assert en != fr
    assert tts.synth("Bonjour", engine="qwen", language="French") == fr
    assert [c["cmd"][c["cmd"].index("--lang") + 1] for c in calls] == ["english", "french"]
