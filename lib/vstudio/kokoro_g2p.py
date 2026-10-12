"""Kokoro's Mandarin G2P with the English inside it spoken as English (中文讲解 full of MCP, Agent, Tool Calling, API).

misaki's ZHG2P (what mlx-audio builds for ``lang_code="z"``, the Kokoro v1.0 phoneme set) passes every non-Chinese
run through *as letters*: "地基先打好：Tool Calling。" becomes ``... xau↓: Tool Calling.``, and Kokoro reads the
raw graphemes as if they were phonemes (heard: "多拉林"). Its English hook (``en_callable``) exists only for the v1.1
frontend, which this model does not use, and misaki's usual English fallback is espeak-ng (GPL, kept out of the
app's runtime).

``MixedZhG2P`` splits a text into Chinese and Latin runs: Chinese (with its punctuation and numbers) goes to
misaki's ZHG2P unchanged, each Latin run ("Tool Calling", "MCP server", "USB-C", "A2A") to misaki's English G2P
(dictionary + spaCy tags, no espeak) with its voiceless stops aspirated (``aspirate``), so the Mandarin voice says
the terms in English. Acronyms come out letter by
letter (misaki spells all-caps words it has no entry for); a word in neither dictionary is ``spell_fallback``-ed
(camelCase / known pieces, else its letters) instead of silently skipped.

    from vstudio.kokoro_g2p import MixedZhG2P
    pipeline.g2p = MixedZhG2P(pipeline.g2p)          # kokoro_synth.py does this for lang "z"
"""
import re

# a Latin run: words (letters, inner digits / ' - + . /) separated by spaces, e.g. "Tool Calling", "HTTP+SSE",
# "GPT-4o"; a number on its own stays with the Chinese (read in Chinese, as before)
_WORD = r"[A-Za-z][A-Za-z0-9'’+\-./]*"
LATIN_RUN = re.compile(rf"{_WORD}(?:[ \t]+{_WORD})*")
_PUNCT_START = re.compile(r"^[,.!?:;)\]”’…—\-]")


def split_runs(text):
    """[(is_latin, run)] in order; Latin runs lose trailing ./-/' (they are the sentence's punctuation)."""
    out, last = [], 0
    for m in LATIN_RUN.finditer(text):
        run = m.group(0)
        core = run.rstrip(".-'’/ ")
        end = m.start() + len(core)
        if m.start() > last:
            out.append((False, text[last:m.start()]))
        out.append((True, core))
        last = end
    if last < len(text):
        out.append((False, text[last:]))
    return [(lat, r) for lat, r in out if r]


def join_phonemes(parts):
    """Join phoneme chunks with single spaces, none before punctuation."""
    s = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        s += p if not s or _PUNCT_START.match(p) else " " + p
    return s


def _pieces(word):
    """camelCase / digit pieces: "LangChain" -> Lang, Chain; "GPT4o" -> GPT, 4, o; "OpenAI" -> Open, AI."""
    return re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", word)


def _segment(word, known):
    """Cheapest split of a lowercase ``word`` into dictionary words (cost 1) and spelled letters (cost 2)."""
    n = len(word)
    best = [(0, [])] + [None] * n
    for i in range(n):
        if best[i] is None:
            continue
        c, parts = best[i]
        for j in range(i + 1, n + 1):
            piece = word[i:j]
            cost = 1 if (j - i >= 2 and known(piece)) else 2 if j - i == 1 else None
            if cost is not None and (best[j] is None or best[j][0] > c + cost):
                best[j] = (c + cost, parts + [(piece, cost == 1)])
    return best[n][1]


class SpellFallback:
    """misaki ``G2P(fallback=...)`` for a word in neither dictionary (where espeak-ng would be): camelCase pieces
    and dictionary sub-words ("Postgres" -> post + g + res), the rest letter by letter - never silence."""

    def __init__(self, lexicon):
        self.lexicon = lexicon

    def _known(self, w):
        lx = self.lexicon
        return w in lx.golds or w in lx.silvers

    def _word(self, w):
        lx = self.lexicon
        ps = lx.golds.get(w) or lx.silvers.get(w)
        if isinstance(ps, dict):
            ps = ps.get("NOUN") or ps.get("DEFAULT")
        return ps

    def phonemes(self, word):
        out = []
        for p in _pieces(word):
            if p.isdigit():
                from .numwords_en import num2words
                out.extend(self.phonemes(w) for w in re.findall(r"[a-z]+", num2words(int(p))))
                continue
            if p.isupper() and len(p) > 1:                  # an acronym: its letters
                out.append(self.lexicon.get_NNP(p)[0] or "")
                continue
            low = p.lower()
            ps = self._word(low) or self._word(p)
            if ps:
                out.append(ps)
                continue
            for piece, is_word in _segment(low, self._known):
                out.append(self._word(piece) if is_word else (self.lexicon.get_NNP(piece)[0] or ""))
        return "".join(x for x in out if x)

    def __call__(self, token):
        ps = self.phonemes(token.text)
        return (ps or None), 1


def english_g2p():
    """misaki's American English G2P without espeak-ng: unknown words through ``SpellFallback``."""
    from misaki import en
    g = en.G2P(trf=False, british=False, fallback=None, unk="")
    g.fallback = SpellFallback(g.lexicon)
    return g


# misaki's vowels (A I O W Y = its diphthongs, ᵊ a reduced schwa); an optional stress mark sits before the vowel
_ASPIRATE = re.compile(r"(?<![sʃ])([ptk])(?=[ˈˌ]?[aeiouæɑɒɔəɛɜɪʊʌɐᵊAIOWY])")


def aspirate(ps):
    """English p / t / k before a vowel (not after s) -> pʰ / tʰ / kʰ. English voiceless stops are aspirated there;
    a Mandarin voice reads a plain t as its unaspirated d (pinyin d / b / g): "tool calling" was heard as "度高零",
    "MCP / API" as "MCB / ABI". With the aspiration the Chinese voice says them recognisably."""
    return _ASPIRATE.sub(r"\1ʰ", ps)


class MixedZhG2P:
    """Callable like misaki's ZHG2P (text -> (phonemes, None)); Latin runs read by the English G2P.
    ``zh``: the pipeline's ZHG2P; ``en``: a misaki English G2P (built on first English run when None)."""

    def __init__(self, zh, en=None):
        self.zh, self._en = zh, en

    @property
    def en(self):
        if self._en is None:
            self._en = english_g2p()
        return self._en

    def __call__(self, text, *a, **k):
        parts = []
        for latin, run in split_runs(text):
            if latin:
                ps = self.en(run)
                parts.append(aspirate(ps[0] if isinstance(ps, tuple) else ps))
            else:
                ps = self.zh(run)
                parts.append(ps[0] if isinstance(ps, tuple) else ps)
        return join_phonemes(parts), None


MAX_PHONEMES = 500           # Kokoro reads at most 510 phonemes per chunk; mlx-audio cuts the rest off silently
_SENT_END = re.compile(r"(?<=[。！？!?；;])|(?<=\.)\s+")
_CLAUSE_END = re.compile(r"(?<=[，、：,:—])")
_WORD_END = re.compile(r"(?<=\s)")


def _cut(text, n):
    """``text`` in ``n`` pieces of about equal length (a run-on with no mark or space left to split at)."""
    k = -(-len(text) // max(1, n))
    return [text[i:i + k] for i in range(0, len(text), k)]


def chunks(text, measure, limit=MAX_PHONEMES):
    """Split ``text`` into pieces whose phonemes (``measure(piece)`` = their length) fit Kokoro's window: whole
    sentences joined while they fit, a sentence too long on its own split at its commas, a clause still too long at
    its spaces, and a run-on with neither cut into even pieces. mlx-audio only splits Chinese at ASCII . ! ? and
    truncates past 510 phonemes, which silently dropped the end of long lines."""
    levels = (_CLAUSE_END.split, _WORD_END.split, lambda p: _cut(p, measure(p) // limit + 1), None)

    def pack(parts, level):
        out, cur = [], ""
        for p in parts:
            if not p.strip():
                continue
            if cur and measure(cur + p) > limit:
                out.append(cur)
                cur = ""
            split = levels[level]
            if not cur and split is not None and measure(p) > limit:
                pieces = split(p)
                if len(pieces) > 1:
                    out.extend(pack(pieces, level + 1))
                    continue
                if level + 1 < len(levels) and levels[level + 1] is not None:
                    out.extend(pack([p], level + 1))
                    continue
            cur += p
        if cur.strip():
            out.append(cur)
        return out
    return [c.strip() for c in pack(_SENT_END.split(text.strip()), 0) if c.strip()]
