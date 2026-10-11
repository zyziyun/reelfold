"""Comparable tokens for Chinese narration (中文讲解): the TTS / ASR checks and the cue alignment.

ASR writes Chinese numbers either way ("七分钟" / "7分钟"), English terms in any case ("MCP server" / "MCPServer")
and drops punctuation, so both sides are normalised the same way before they are compared:
  Chinese numerals -> digits (七 -> 7, 二十五 -> 25, 零点五 -> 0.5, 二零二五 -> 2025), latin lower-cased,
  then one token per CJK character, per latin word (split at case / digit changes) and per number.
"""
import re

DIG = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
UNIT = {"十": 10, "百": 100, "千": 1000, "万": 10**4, "亿": 10**8}
NUM_RUN = re.compile(r"[零〇一二两三四五六七八九十百千万亿]+(?:点[零〇一二两三四五六七八九]+)?")
TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+|[㐀-鿿豈-﫿]")


def _int(s):
    if not any(c in UNIT for c in s):                      # 二零二五 -> 2025 (read digit by digit)
        return int("".join(str(DIG[c]) for c in s)) if s else 0
    total, section, cur = 0, 0, 0
    for c in s:
        if c in DIG:
            cur = DIG[c]
        elif c in ("万", "亿"):
            total += (section + cur) * UNIT[c]
            section = cur = 0
        else:
            section += (cur or 1) * UNIT[c]
            cur = 0
    return total + section + cur


def cn_number(s):
    """One run of Chinese numerals -> its digits ("二十五" -> "25", "零点五" -> "0.5")."""
    whole, _, frac = s.partition("点")
    try:
        out = str(_int(whole))
    except KeyError:
        return s
    if frac:
        out += "." + "".join(str(DIG[c]) for c in frac)
    return out


def digits(text):
    return NUM_RUN.sub(lambda m: cn_number(m.group(0)), text or "")


ACRONYM = re.compile(r"(?<![A-Za-z])[A-Z]{2,5}(?![a-z])")


def acronyms(text):
    """All-caps words of ``text`` ("MCP", "API", "RAG"), lower-cased - spoken letter by letter."""
    return {a.lower() for a in ACRONYM.findall(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text or ""))}


def tokens(text, letters=False, spelled=()):
    """Comparable tokens of a Chinese (+ English terms) text.
    ``letters``: an acronym is one token per letter ("MCP" -> m c p, as ASR may write "M.C.P." or "M C P"), and so is
    any word in ``spelled`` (the script's acronyms, lower-cased: ASR writing "Mcp" / "rag" for "MCP" / "RAG")."""
    s = digits(text).replace("%", "百分之")
    s = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)   # "MCPServer" / "McpServer" -> two words
    if letters:
        s = ACRONYM.sub(lambda m: " ".join(m.group(0)), s)
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s).lower()
    out = TOKEN.findall(s)
    if letters and spelled:
        out = [c for t in out for c in (list(t) if t in spelled else [t])]
    return out


# how a Mandarin listener says a letter, as one pinyin syllable (ASR in Chinese writes "DG" for 地基 di ji)
LETTER_SOUND = {"a": "ei", "b": "bi", "c": "xi", "d": "di", "e": "yi", "g": "ji", "i": "ai", "j": "jie", "k": "kai",
                "n": "en", "o": "ou", "p": "pi", "q": "kiu", "t": "ti", "u": "you", "v": "wei", "y": "wai", "z": "zei"}


def sound_keys(toks):
    """Tokens -> how they sound: a CJK character -> its toneless pinyin (ASR homophones: 调用 / 掉用 both "diao"), a
    single letter -> its Mandarin letter name, anything else as is. Without a pinyin backend: the tokens."""
    try:
        from vstudio.proofread import pinyin_of
    except Exception:  # noqa: BLE001
        return list(toks)
    cjk = "".join(t for t in toks if len(t) == 1 and ord(t) > 0x2E80)
    py = iter(pinyin_of(cjk) or [])
    out = []
    for t in toks:
        if len(t) == 1 and ord(t) > 0x2E80:
            out.append(next(py, t))
        else:
            out.append(LETTER_SOUND.get(t, t))
    return out


def sentences(text):
    """Script sentences: split after 。！？!? (and . followed by a space)."""
    return [p.strip() for p in re.split(r"(?<=[。！？!?])|(?<=\.)\s+", (text or "").strip()) if p and p.strip()]


def width(s):
    """Display width: CJK = 1, latin / digits / space = 0.5 (same measure as pair_cues.zh_len)."""
    return sum(1 if ord(c) > 0x2E80 else 0.5 for c in (s or "").strip())
