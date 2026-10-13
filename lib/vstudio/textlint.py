"""Text lint: the on-screen words of a render, checked like a designer would before it is shown (research note
editing-skills-2026-10 #4; references/STYLE_RULES.md, AESTHETICS.md P5 / P6 / P9). Titles and burned captions are
the most visible "cheap template" signal: too many words per line, a line that starts with ，, emoji, 。。, three
type styles in one frame, stroke + shadow + colour box stacked on one word, a Chinese line on YouTube.

    from vstudio import textlint
    items = textlint.lint(["今天聊聊剪辑", "这个功能真的很好用。。"], platform="xiaohongshu:full")
    items = textlint.lint([{"text": "Day one in Kyoto", "start": 1.2}], platform="youtube", kind="title",
                          frame_size=(1920, 1080), boxes=[(200, 400, 1700, 560)],
                          styles=[{"font": "serif-display", "size": 80}, {"font": "cjk", "size": 44}])

Returns firstpass items (``firstpass._item`` shape: id, ok, severity, value, zh, en, fix_zh, fix_en), one per rule
that applies, all ``warn`` (taste and typos, never a reason to block a render). ``value`` lists the first offenders
as "#n (12.4s) text". ``vstudio.firstpass.run`` lints the cues of every render (``check_text``).

Rules (ids):
  type-length   words per on-screen line: a title line <= 12 CJK characters (CJK 1 / latin 0.5) or <= 6 English
                words (8 on a horizontal canvas); a caption must fit the platform's caption box
                (``caption.max_chars_zh`` / ``max_chars_en`` per line, ``max_lines`` lines)
  type-kinsoku  避头尾: no line starts with ，。、！？… / a dash / ·, none ends with “（《, no one-character last line
                (``subs.kinsoku_violations``; explicit line breaks are checked as given, the rest as balanced_wrap
                would break them)
  type-area     on-screen text boxes cover at most 20 % of the frame (needs ``boxes`` + ``frame_size``)
  type-styles   at most 2 type styles (font + size + weight) in one frame (needs ``styles``)
  type-stacked  no style stacks three treatments at once: stroke + shadow + a colour fill / box (STYLE_RULES S2)
  type-emoji    no emoji in on-screen text (P5)
  type-punct    no doubled punctuation (，， 。。 、、 ,, .. - an ellipsis … / ... is fine)
  type-lang     on a one-language platform (YouTube: English, P9; the Chinese platforms: Chinese) no line whose
                majority script is the other language. Conservative: on a Chinese platform capitalised words,
                acronyms and numbers (names, brands) never count against a line; a bilingual cue (one line each
                language) is left alone. The caption-language-vs-platform check is a separate firstpass item.
"""
import re

from . import subs

AREA_MAX = 0.20
STYLES_MAX = 2
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍\U0001F1E6-\U0001F1FF]")
_DOUBLE = re.compile(r"，，|。。|、、|；；|,,|(?<!\.)\.\.(?!\.)")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
_NUM = re.compile(r"\d")


def _item(id_, ok, zh, en, value=None, fix_zh="", fix_en="", severity="warn"):
    return dict(id=id_, ok=ok, severity=severity, value=value, zh=zh, en=en, fix_zh=fix_zh, fix_en=fix_en)


def _norm(texts):
    """str | {text, start} | (text, start) -> [(n, start or None, text)] (markup removed, empty texts dropped)."""
    out = []
    for i, t in enumerate(texts or []):
        start = None
        if isinstance(t, dict):
            t, start = t.get("text", ""), t.get("start")
        elif isinstance(t, (tuple, list)):
            t, start = (list(t) + [None])[:2]
        s = subs.strip_markup(str(t or "")).strip()
        if s:
            out.append((i + 1, start, s))
    return out


def _tag(n, start, text):
    at = f" ({float(start):.1f}s)" if isinstance(start, (int, float)) else ""
    return f"#{n}{at} {text}"


def _cjk_count(s):
    return sum(1 for c in s if "㐀" <= c <= "鿿" or "豈" <= c <= "﫿")


def _is_latin_line(s):
    return _cjk_count(s) == 0 and bool(_WORD.search(s))


def _profile(platform):
    """A platform name / Profile -> (Profile or None, registry name or None)."""
    if platform is None:
        return None, None
    from . import platform as PL
    if isinstance(platform, PL.Profile):
        return platform, platform.name
    try:
        return PL.profile(str(platform)), str(platform).split(":")[0]
    except (KeyError, ValueError):
        return None, str(platform).split(":")[0]


def _lines(text, kind, prof, horizontal):
    """On-screen lines: the explicit breaks when the text has them, else how the renderer would wrap it."""
    if "\n" in text:
        return [ln.strip() for ln in text.split("\n") if ln.strip()]
    if kind == "title":
        return subs.split_two(text) if subs.text_width(text) > 12 or len(_WORD.findall(text)) > (8 if horizontal else 6) \
            else [text]
    cap = (prof.caption if prof else None) or {}
    width = cap.get("max_chars_zh", 16) if not _is_latin_line(text) else cap.get("max_chars_en", 36) / 2
    return subs.balanced_wrap(text, width)


# ------------------------------------------------------------------------------------------------ rules
def _length(rows, kind, prof, horizontal):
    bad = []
    if kind == "title":
        max_words = 8 if horizontal else 6
        for n, st, t, lines in rows:
            for ln in lines:
                if (_is_latin_line(ln) and len(_WORD.findall(ln)) > max_words) or \
                        (not _is_latin_line(ln) and subs.text_width(ln) > 12):
                    bad.append(_tag(n, st, ln))
        return _item("type-length", not bad, f"标题每行字数克制（中文 ≤ 12 字 / 英文 ≤ {max_words} 词）",
                     f"title lines are short (<= 12 CJK characters / <= {max_words} English words)", bad[:5] or None,
                     "拆成两行或删词：一行只放一个意思", "split into two lines or cut words: one idea per line")
    cap = (prof.caption if prof else None) or dict(max_chars_zh=16, max_chars_en=36, max_lines=2)
    zh_max, en_max, max_lines = cap.get("max_chars_zh", 16), cap.get("max_chars_en", 36), cap.get("max_lines", 2)
    for n, st, t, lines in rows:
        over = [ln for ln in lines if (subs.char_len(ln) > en_max if _is_latin_line(ln) else subs.text_width(ln) > zh_max)]
        if over or len(lines) > max_lines:
            bad.append(_tag(n, st, t))
    where = prof.name if prof else "default"
    return _item("type-length", not bad, f"每条字幕放得下（每行中文 ≤ {zh_max} 字 / 英文 ≤ {en_max} 字符，最多 {max_lines} 行，{where}）",
                 f"each caption fits (<= {zh_max} CJK / {en_max} latin characters per line, <= {max_lines} lines, {where})",
                 bad[:5] or None, "把长句拆成两条字幕（subs.caption_chunks）", "split long captions (subs.caption_chunks)")


def _kinsoku(rows):
    bad = []
    for n, st, t, lines in rows:
        v = subs.kinsoku_violations(lines)
        if v:
            bad.append(_tag(n, st, " / ".join(lines)))
    return _item("type-kinsoku", not bad, "断行守避头尾（行首没有，。！？、行尾没有“（《、末行不是单字）",
                 "line breaks keep kinsoku (no line opens with closing punctuation, none ends with an opening one, "
                 "no one-character last line)", bad[:5] or None,
                 "用 subs.balanced_wrap 重新断行，别手动插换行", "re-wrap with subs.balanced_wrap instead of manual breaks")


def _area(boxes, frame_size):
    W, H = frame_size
    area = 0.0
    for b in boxes:
        x0, y0, x1, y1 = (float(v) for v in b[:4])
        area += max(0.0, min(x1, W) - max(x0, 0)) * max(0.0, min(y1, H) - max(y0, 0))
    share = area / float(W * H) if W and H else 0.0
    return _item("type-area", share <= AREA_MAX, f"文字面积不超过画面的 {AREA_MAX:.0%}（现在 {share:.0%}）",
                 f"text covers at most {AREA_MAX:.0%} of the frame (now {share:.0%})", round(share, 3),
                 "少放字：一屏一个意思，其余进字幕或文案", "fewer words on screen: one idea per frame, the rest in the post")


def _style_key(s):
    return (str(s.get("font") or ""), int(round(float(s.get("size") or 0) / 2.0)), str(s.get("weight") or ""))


def _saturated(color):
    try:
        from .draw import rgb
        r, g, b = (v / 255.0 for v in rgb(color)[:3])
    except Exception:                                    # noqa: BLE001 - an unreadable colour counts as plain
        return False
    hi, lo = max(r, g, b), min(r, g, b)
    return hi > 0 and (hi - lo) / hi > 0.35


def _treatments(s):
    t = []
    if float(s.get("stroke") or 0) > 0:
        t.append("stroke")
    if s.get("shadow"):
        t.append("shadow")
    if s.get("box") or s.get("band") or (s.get("color") and _saturated(s["color"])):
        t.append("colour/box")
    return t


def _styles(styles):
    keys = {_style_key(s) for s in styles}
    out = [_item("type-styles", len(keys) <= STYLES_MAX, f"同一画面最多 {STYLES_MAX} 种字体样式（现在 {len(keys)}）",
                 f"at most {STYLES_MAX} type styles in one frame (now {len(keys)})", len(keys),
                 "标题一种、正文一种；层级靠字号和字重，不靠换字体", "one title style and one text style; hierarchy "
                 "from size and weight, not more faces")]
    stacked = [f"{s.get('font') or '?'} {'+'.join(_treatments(s))}" for s in styles if len(_treatments(s)) >= 3]
    out.append(_item("type-stacked", not stacked, "没有描边 + 阴影 + 色块叠在一起的字", "no stroke + shadow + colour box "
                     "stacked on one text", stacked[:3] or None, "只留一种：画面上用柔和阴影，纸面上什么都不加",
                     "keep one treatment: a soft shadow over video, nothing on paper"))
    return out


def _emoji(rows):
    bad = [_tag(n, st, t) for n, st, t, _ in rows if _EMOJI.search(t)]
    return _item("type-emoji", not bad, "画面文字里没有 emoji", "no emoji in on-screen text", bad[:5] or None,
                 "删掉 emoji；情绪交给画面和语气", "drop the emoji; let the picture carry the mood")


def _punct(rows):
    bad = [_tag(n, st, t) for n, st, t, _ in rows if _DOUBLE.search(t)]
    return _item("type-punct", not bad, "没有重复的标点（，， 。。 ,, ..）", "no doubled punctuation (，， 。。 ,, ..)",
                 bad[:5] or None, "删掉多余的标点；省略号用 …… 或 ...", "remove the extra mark; an ellipsis is … or ...")


def _wrong_share(line, lang):
    """(wrong, right) widths of a line for a platform language (CJK 1, a latin letter 0.5). On a Chinese platform
    words with a capital (iPhone, AI), and anything with a digit are names / brands / numbers and count for neither."""
    cjk = float(_cjk_count(line))
    words = _WORD.findall(line)
    if lang == "zh":
        plain = [w for w in words if not (any(c.isupper() for c in w) or _NUM.search(w))]   # iPhone, AI, M4
        return 0.5 * sum(len(w) for w in plain), cjk
    return cjk, 0.5 * sum(len(w) for w in words)


def _lang(rows, platform_name):
    from . import platform as PL
    lang = PL.lang_for(platform_name)
    if not lang or not (PL.lang_fixed(platform_name) or lang == "zh"):
        return None
    bad = []
    for n, st, t, lines in rows:
        if len(lines) > 1 and {bool(_cjk_count(ln)) for ln in lines} == {True, False}:
            continue                                     # a bilingual cue: one line in each language, on purpose
        for ln in lines:
            wrong, right = _wrong_share(ln, lang)
            if wrong > right:
                bad.append(_tag(n, st, ln))
                break
    want_zh, want_en = ("中文", "Chinese") if lang == "zh" else ("英文", "English")
    return _item("type-lang", not bad, f"{platform_name} 的画面文字是{want_zh}（没有以另一种语言为主的行）",
                 f"on-screen text on {platform_name} is {want_en} (no line mostly in the other language)", bad[:5] or None,
                 f"按平台出{want_zh}版：YouTube 全英文，小红书 / B站 中文", f"make the {want_en} version for this platform")


def lint(texts, platform=None, frame_size=None, boxes=None, styles=None, kind="caption"):
    """Lint on-screen texts -> firstpass items (all ``warn``). texts: [str | {text, start} | (text, start)]; an
    explicit ``\\n`` is a line break. platform: a name ("youtube", "xiaohongshu:full") or a ``platform.Profile`` (caption
    limits, canvas, language). frame_size: (w, h), default the platform canvas. boxes: [(x0, y0, x1, y1)] of the text
    visible in ONE frame (area rule). styles: [{font, size, weight, color, stroke, shadow, box}] used in ONE frame
    (style-count and stacking rules). kind: ``caption`` (platform caption box) or ``title`` (≤ 12 字 / ≤ 6 words)."""
    prof, pname = _profile(platform)
    if frame_size is None and prof is not None:
        frame_size = (prof.w, prof.h)
    horizontal = bool(frame_size) and frame_size[0] > frame_size[1]
    rows = [(n, st, t, _lines(t, kind, prof, horizontal)) for n, st, t in _norm(texts)]
    items = []
    if rows:
        items += [_length(rows, kind, prof, horizontal), _kinsoku(rows), _emoji(rows), _punct(rows)]
        if pname:
            lang = _lang(rows, pname)
            if lang:
                items.append(lang)
    if boxes and frame_size:
        items.append(_area(boxes, frame_size))
    if styles:
        items += _styles(styles)
    return items
