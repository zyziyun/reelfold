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


def tokens(text):
    """Comparable tokens of a Chinese (+ English terms) text."""
    s = digits(text).replace("%", "百分之")
    s = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)   # "MCPServer" / "McpServer" -> two words
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s).lower()
    return TOKEN.findall(s)


def sentences(text):
    """Script sentences: split after 。！？!? (and . followed by a space)."""
    return [p.strip() for p in re.split(r"(?<=[。！？!?])|(?<=\.)\s+", (text or "").strip()) if p and p.strip()]


def width(s):
    """Display width: CJK = 1, latin / digits / space = 0.5 (same measure as pair_cues.zh_len)."""
    return sum(1 if ord(c) > 0x2E80 else 0.5 for c in (s or "").strip())
