"""Parse an explainer SCRIPT.md (format in WORKFLOW.md §2) into lines.

    ## Line N — <label> (Frame N)
    **Delivery:** ...            (optional)
        spoken narration, 4-space indented (may span several indented lines)
    ZH: 中文字幕原文              (English narration: the 中文 subtitle)
    EN: English subtitle          (Chinese narration: optional English subtitle)

The narration language is the spoken blocks' language: Chinese when most of their letters are CJK
(``narration_lang``), else English. English narration keeps the original shape (spoken EN + ``ZH:``).
Chinese narration (中文讲解) speaks the indented block, its subtitle IS that text, and an ``EN:`` line adds an
English subtitle under it.

parse_script(path) -> [{"n", "label", "frame", "delivery", "spoken", "lang", "en", "zh"}]
  spoken: the indented block (what TTS says), joined exactly like align_cues.py
  en / zh: the subtitle text per language (for English narration en == spoken; for Chinese zh == spoken)
"""
import re

CJK = re.compile(r"[㐀-鿿豈-﫿]")
LATIN = re.compile(r"[A-Za-z]+")


def text_lang(text):
    """"zh" when CJK characters outnumber latin words (a Chinese sentence with English terms is Chinese)."""
    return "zh" if len(CJK.findall(text or "")) > len(LATIN.findall(text or "")) else "en"


def _joined(lines, cjk):
    # Chinese wraps without spaces: indented continuation lines join directly unless a latin word meets a latin word
    if not cjk:
        return " ".join(lines)
    out = ""
    for ln in lines:
        if out and re.search(r"[A-Za-z0-9]$", out) and re.match(r"[A-Za-z0-9]", ln):
            out += " "
        out += ln
    return out


def spoken_of(block):
    """The indented (spoken) part of one '## Line' block."""
    lines = [ln.strip() for ln in block.split("\n") if ln.startswith("    ") and ln.strip()]
    return _joined(lines, text_lang(" ".join(lines)) == "zh")


def parse_script(path):
    text = open(path, encoding="utf-8").read()
    out = []
    for b in re.split(r"\n## Line ", "\n" + text)[1:]:
        head = b.split("\n", 1)[0]
        m = re.match(r"(\d+)\s*(?:[—–-]+\s*(.*?))?\s*(?:\(Frame\s*(\d+)\))?\s*$", head)
        if not m:
            continue
        n = int(m.group(1))
        spoken = spoken_of(b)
        zh = " ".join(ln[3:].strip() for ln in b.split("\n") if ln.startswith("ZH:"))
        en = " ".join(ln[3:].strip() for ln in b.split("\n") if ln.startswith("EN:"))
        lang = text_lang(spoken)
        if lang == "zh":
            zh = spoken
        else:
            en = spoken
        dm = re.search(r"\*\*Delivery:\*\*\s*(.+)", b)
        out.append(dict(n=n, label=(m.group(2) or f"Line {n}").strip(), frame=int(m.group(3) or n),
                        delivery=dm.group(1).strip() if dm else "", spoken=spoken, lang=lang, en=en, zh=zh))
    return out


def narration_lang(lines):
    """The project's narration language from parsed lines: "zh" when most spoken text is Chinese."""
    return text_lang(" ".join(L["spoken"] for L in lines)) if lines else "en"


def script_lang(path):
    try:
        return narration_lang(parse_script(path))
    except OSError:
        return "en"


def slug(label, maxlen=18):
    s = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rsplit("-", 1)[0] or s[:maxlen]
    return s or "scene"
