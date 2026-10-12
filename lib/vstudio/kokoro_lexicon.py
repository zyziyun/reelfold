"""Curated pronunciations (misaki / Kokoro phonemes, American English) for names the local English voice gets wrong.

misaki without espeak-ng has no entry for many names: "Elliott" went through the respelling route and came out as
"El Yacht", "Elvis" as "el-VEE-iz", Puget / Dreyfus letter by letter. These entries are phonemes in misaki's own
alphabet (the symbols its dictionaries use: A = eɪ, I = aɪ, O = oʊ, W = aʊ, Y = ɔɪ, T = the American flap, ᵊ = a
reduced schwa; ˈ / ˌ stress sits right before the stressed vowel), so they are the FIRST lookup - before misaki's own
dictionaries, before any respelling (photo-story ``SAY_TTS``) and before the spelling fallback.

    from vstudio import kokoro_lexicon as KL
    KL.install(g2p.lexicon)        # kokoro_synth.english / kokoro_g2p.english_g2p do this
    KL.phonemes("Elliott")         # -> "ˈɛliət"
    KL.known("Puget")              # -> True

Add a name: the phonemes of a similar dictionary word are the best guide (``misaki.en.G2P()(word)``); check it by
ear with ``python -m vstudio.kokoro_synth --voice af_heart --text "..."`` and a Whisper transcript.
"""

import re

VERSION = 1      # bump when an entry changes: a cached take of a line that names one is made again (vstudio.tts)

# name -> phonemes. Keys are the written form (capitalised); the lowercase form is added when misaki has no word of
# that spelling (so "smith" / "cove" keep the dictionary's own entries).
NAMES = {
    # people
    "Elliott": "ˈɛliət", "Elliot": "ˈɛliət", "Eliot": "ˈɛliət",
    "Elvis": "ˈɛlvɪs", "Presley": "pɹˈɛsli",
    "Dreyfus": "dɹˈAfəs", "Louis": "lˈui",
    "Yamasaki": "jˌɑməsˈɑki", "Minoru": "mˌinˈOɹu",
    "Wilkes": "wˈɪlks", "Vancouver": "vænkˈuvəɹ",
    "Denny": "dˈɛni", "Yesler": "jˈɛsləɹ", "Boeing": "bˈOɪŋ",
    "Nguyen": "ŋwˈɪn", "Siobhan": "ʃəvˈɔn", "Niamh": "nˈiv", "Joaquin": "wɑkˈin", "Xavier": "zˈAviəɹ",
    "Saoirse": "sˈɜɹʃə", "Aoife": "ˈifə", "Chloe": "klˈOi", "Zoe": "zˈOi",
    # Pacific Northwest places
    "Puget": "pjˈuʤɪt", "Seattle": "siˈæTᵊl", "Klondike": "klˈɑndˌIk", "Interbay": "ˈɪntəɹbˌA",
    "Smith": "smˈɪθ", "Cove": "kˈOv", "Kirkland": "kˈɜɹklənd", "Vantage": "vˈæntɪʤ", "Columbia": "kəlˈʌmbiə",
    "Tacoma": "təkˈOmə", "Rainier": "ɹAnˈɪɹ", "Spokane": "spOkˈæn", "Snoqualmie": "snOkwˈɔlmi",
    "Puyallup": "pjuˈæləp", "Yakima": "jˈækəmˌɑ", "Wenatchee": "wənˈæʧi", "Chelan": "ʃəlˈæn",
    "Issaquah": "ˈɪsəkwˌɑ", "Bellevue": "bˈɛlvju", "Ballard": "bˈæləɹd", "Alki": "ˈælkI",
    "Duwamish": "duwˈɑmɪʃ", "Olympia": "əlˈɪmpiə", "Sequim": "skwˈɪm", "Mukilteo": "mˌʌkəltˈAO",
    "Willamette": "wɪlˈæmɪt", "Oregon": "ˈɔɹɪɡən", "Coulee": "kˈuli", "Leavenworth": "lˈɛvənwˌɜɹθ",
    "Snohomish": "snOhˈOmɪʃ", "Tukwila": "tʌkwˈɪlə", "Edmonds": "ˈɛdmənz", "Shilshole": "ʃˈɪlʃˌOl",
}


def phonemes(word):
    """The curated phonemes of ``word`` (as written, or capitalised), else None."""
    w = str(word or "")
    return NAMES.get(w) or NAMES.get(w[:1].upper() + w[1:].lower()) if w else None


def known(word):
    return phonemes(word) is not None


def mentions(text):
    """The curated names a text says (as written), in order - e.g. for a cache key that changes with the lexicon."""
    return list(dict.fromkeys(w for w in re.findall(r"[A-Za-z]+", str(text or "")) if w in NAMES))


def install(lexicon):
    """Put the curated names first in a misaki ``Lexicon`` (its ``golds``, which every lookup reads before the
    silver dictionary and the fallback). Returns the lexicon. Idempotent."""
    golds = getattr(lexicon, "golds", None)
    if golds is None or getattr(lexicon, "_vstudio_names", False):
        return lexicon
    silvers = getattr(lexicon, "silvers", {}) or {}
    for w, ps in NAMES.items():
        golds[w] = ps
        low = w.lower()
        if low not in golds and low not in silvers:
            golds[low] = ps
    try:
        lexicon._vstudio_names = True
    except AttributeError:
        pass
    return lexicon
