"""Chinese narration with English terms on the free voice (Kokoro, Mandarin): dogfood 2026-10-11, her MCP course
stopped at the voice - "TTS dropped sentences after retries ... line 02: ['地基先打好：Tool Calling。']".

Root cause: misaki's Mandarin G2P (Kokoro v1.0) passes Latin text through as raw letters, so Kokoro read "Tool
Calling" as phoneme symbols (heard "多拉林"); and mlx-audio cut every chunk at 510 phonemes, silently dropping the end
of long Chinese lines ("ReAct pattern." in line 13). vstudio.kokoro_g2p reads Latin runs with misaki's English G2P
(no espeak-ng), aspirated for the Mandarin voice, and cuts lines into pieces that fit. The take check compares by
sound (pinyin), acronyms letter by letter, so an English term heard as "MCP" / "M.C.P." / "Mcp" counts.

The G2P parts run with fakes; the real-misaki test only where misaki[zh,en] + spaCy's model are installed (the desk's
runtime: bundle.mjs verify synthesises a mixed sentence).

    python3 -m pytest tests/test_kokoro_mixed.py -q
"""
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "workflows" / "explainer" / "scripts"))

from vstudio import kokoro_g2p as K, proctail  # noqa: E402
import vo_check  # noqa: E402
import zhtext  # noqa: E402


# ------------------------------------------------------------------ G2P: Latin runs read as English
def test_split_runs_keeps_terms_whole_and_punctuation_chinese():
    assert K.split_runs("地基先打好：Tool Calling。") == [(False, "地基先打好："), (True, "Tool Calling"), (False, "。")]
    assert K.split_runs("连上 GitHub、Postgres。USB-C 口和 HTTP+SSE，A2A 来了") == [
        (False, "连上 "), (True, "GitHub"), (False, "、"), (True, "Postgres"), (False, "。"), (True, "USB-C"),
        (False, " 口和 "), (True, "HTTP+SSE"), (False, "，"), (True, "A2A"), (False, " 来了")]
    # a number on its own stays Chinese (read in Chinese, as before); a sentence-final "." is punctuation
    assert K.split_runs("2025 年 3 月发布 MCP.") == [(False, "2025 年 3 月发布 "), (True, "MCP"), (False, ".")]


def test_mixed_g2p_sends_latin_to_english_and_aspirates():
    zh = lambda s: (f"<{s.strip()}>" if s.strip() else "", None)          # noqa: E731
    en = lambda s: ({"Tool Calling": "tˈul kˈɔlɪŋ", "MCP": "ˌɛmsˌipˈi"}[s], [])  # noqa: E731
    g = K.MixedZhG2P(zh, en)
    assert g("地基先打好：Tool Calling。") == ("<地基先打好：> tʰˈul kʰˈɔlɪŋ <。>", None)
    assert g("MCP 很简单") == ("ˌɛmsˌipʰˈi <很简单>", None)


def test_aspirate_only_voiceless_stops_before_a_vowel():
    assert K.aspirate("tˈul kˈɔlɪŋ") == "tʰˈul kʰˈɔlɪŋ"
    assert K.aspirate("ˌApˌiˈI") == "ˌApʰˌiˈI"
    assert K.aspirate("spˈɛk stɹˈim") == "spˈɛk stɹˈim"            # after s: unaspirated, as in English
    assert K.aspirate("dˈip ɡˈʊd") == "dˈip ɡˈʊd"                  # voiced stops and word-final p untouched


def test_join_phonemes_no_space_before_punctuation():
    assert K.join_phonemes(["xau↓:", "tʰˈul", ".", "", " ʨje→ "]) == "xau↓: tʰˈul. ʨje→"


def test_spell_fallback_never_silent():
    golds = {"post": "pˈOst", "chain": "ʧˈAn", "res": "ɹˈɛz"}
    lex = SimpleNamespace(golds=golds, silvers={}, get_NNP=lambda w: ("".join(f"[{c.upper()}]" for c in w), 3))
    fb = K.SpellFallback(lex)
    assert fb.phonemes("Postgres") == "pˈOst[G]ɹˈɛz"              # dictionary pieces, the rest as letters
    assert fb.phonemes("LangChain") == "[L][A][N][G]ʧˈAn"         # camelCase pieces
    assert fb.phonemes("XYZ") == "[X][Y][Z]"                       # an acronym: its letters
    assert fb(SimpleNamespace(text="Postgres")) == ("pˈOst[G]ɹˈɛz", 1)


def test_chunks_fit_kokoros_phoneme_window():
    text = "第一句话。" * 3 + "很长的一句，" * 6 + "完。"
    measure = len                                                      # one "phoneme" per character
    out = K.chunks(text, measure, limit=12)
    assert "".join(out) == text.strip()
    assert all(len(c) <= 12 for c in out)
    assert out[0] == "第一句话。第一句话。"                          # whole sentences while they fit
    assert K.chunks("短句。", measure, limit=12) == ["短句。"]


@pytest.mark.skipif(not (importlib.util.find_spec("misaki") and importlib.util.find_spec("jieba")
                         and importlib.util.find_spec("spacy") and importlib.util.find_spec("en_core_web_sm")),
                    reason="misaki[zh,en] + en_core_web_sm not installed (the desk runtime has them)")
def test_real_misaki_reads_the_english_terms():
    from misaki import zh
    raw = zh.ZHG2P()("地基先打好：Tool Calling。")[0]
    assert "Tool Calling" in raw                                       # the bug: graphemes passed on as phonemes
    ps = K.MixedZhG2P(zh.ZHG2P())("地基先打好：Tool Calling。接上 MCP 和 Postgres。")[0]
    assert "Tool" not in ps and "MCP" not in ps and "tʰˈul" in ps and "kʰˈɔlɪŋ" in ps
    assert "ˌɛmsˌipʰˈi" in ps and "pʰˈOst" in ps                      # an acronym spelled; an unknown word not skipped


# ------------------------------------------------------------------ the take check: mixed zh / en ASR text
LINE2 = "地基先打好：Tool Calling。接上工具之后，LLM 不再直接回文本，而是回一段 JSON，声明它想调用哪个函数。"


def test_check_accepts_how_asr_writes_a_good_mixed_take():
    # heard on the fixed take: 地基 as "DG", 调用 as 掉用, Tool as "2", JSON as "J.S.O.N."
    heard = "DG先拿好2calling,接上工具之后,LLM不再直接回文本,而是回一段J.S.O.N.,声明他想掉用哪个函数。"
    r = vo_check.check(LINE2, heard)
    assert r["missing"] == [], r


def test_check_still_finds_a_dropped_mixed_sentence():
    heard = "接上工具之后LLM不再直接回文本而是回一段JSON声明他想调用哪个函数"
    assert vo_check.check(LINE2, heard)["missing"] == ["地基先打好：Tool Calling。"]
    heard = "地基先打好Tool Calling"
    assert vo_check.check(LINE2, heard)["missing"] == ["接上工具之后，LLM 不再直接回文本，而是回一段 JSON，声明它想调用哪个函数。"]


def test_acronyms_compare_letter_by_letter_whatever_the_case():
    script = "MCP 和 RAG 都用 API。"
    spelled = zhtext.acronyms(script)
    assert spelled == {"mcp", "rag", "api"}
    a = zhtext.tokens(script, letters=True, spelled=spelled)
    for heard in ("MCP和RAG都用API", "M.C.P.和rag都用Api", "M C P 和 R A G 都用 a p i"):
        assert zhtext.tokens(heard, letters=True, spelled=spelled) == a, heard
    assert zhtext.tokens("MCPServer", letters=True) == ["m", "c", "p", "server"]
    assert zhtext.tokens(script) == ["mcp", "和", "rag", "都", "用", "api"]       # the cue alignment: unchanged


def test_sound_keys_match_homophones():
    pytest.importorskip("pypinyin")
    assert zhtext.sound_keys(list("调用")) == zhtext.sound_keys(list("掉用")) == ["diao", "yong"]
    assert zhtext.sound_keys(["d", "g"]) == zhtext.sound_keys(list("地基")) == ["di", "ji"]


# ------------------------------------------------------------------ the failure in her words
def test_the_dropped_sentence_failure_is_coded_with_its_scene_and_sentence():
    err = ("RuntimeError: tts.py exit 1:\nline 02:   23.8s  155 chars\nline 02: take dropped 1 sentence(s): "
           "['地基先打好：Tool Calling。']\nline 03:   20.6s  154 chars\n"
           "TTS dropped sentences after retries (re-run with --fresh N, rephrase, or split the line):\n"
           "  line 02: ['地基先打好：Tool Calling。']\n  line 09: [\"It's here.\"]")
    assert proctail.tool_failure(err) == dict(code="stage-voice-dropped", params=dict(
        line="2", sentence="地基先打好：Tool Calling", lines="2", fix="rephrase-line"))
    assert proctail.voice_dropped("line 02: take dropped 1 sentence(s): ['x']; new take") is None
