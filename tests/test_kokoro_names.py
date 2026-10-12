"""The local English voice (Kokoro, misaki without espeak-ng) says curated names from phonemes, first: "Elliott"
went through a respelling ("ell yacht") and Whisper heard "El Yacht"; Elvis, Puget, Dreyfus were spelled out. A take
of a line naming one is made again when the lexicon changes (vstudio.tts cache key)."""
import os

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_curated_names_are_phonemes_first():
    from vstudio import kokoro_lexicon as KL

    class Lex:
        golds, silvers = {"smith": "smˈɪθ", "Smith": "smˈɪθ"}, {}
    lx = KL.install(Lex())
    assert lx.golds["Elliott"] == "ˈɛliət" and lx.golds["elliott"] == "ˈɛliət" and lx.golds["smith"] == "smˈɪθ"
    assert KL.known("elvis") and not KL.known("Elvish") and KL.phonemes("Puget") == "pjˈuʤɪt"
    assert KL.mentions("Elliott Bay, Puget Sound and Elliott again") == ["Elliott", "Puget"]
    for w in ("Elliott", "Elvis", "Puget", "Dreyfus", "Yamasaki", "Minoru", "Klondike", "Interbay", "Smith", "Cove",
              "Seattle", "Kirkland", "Vantage", "Columbia", "Wilkes", "Vancouver"):
        assert KL.known(w), w


def test_curated_names_reach_misaki():
    pytest.importorskip("misaki")
    from vstudio import kokoro_g2p as K
    g = K.english_g2p()
    ps = g("Elliott Bay, Elvis and Puget Sound.")[0]
    assert ps.startswith("ˈɛliət bˈA") and "ˈɛlvɪs" in ps and "pjˈuʤɪt" in ps
    assert K.unknown_words("Elliott Bay and Elvis in Seattle near Puget Sound with Hoquiam") == ["Hoquiam"]


def test_tts_cache_key_follows_the_lexicon(monkeypatch, tmp_path):
    src = open(os.path.join(ROOT, "lib/vstudio/tts.py"), encoding="utf-8").read()
    assert "kokoro_lexicon.mentions(text)" in src and "#names" in src
