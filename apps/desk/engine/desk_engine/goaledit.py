"""「Edit the collection」: what she says to a goal's group (a made 合集) -> what the group does. Read by
``Goals.say``; pure (unit-tested), no model call - her words are routed by these rules, the work itself runs on the
group's AI (the planner of the new videos, each clip's own AI for an edit across the group).

  more    "再做 3 条" / "补够 12 条" / "再做一条关于渡轮的" / "make 2 more videos" / "another one about the ferry"
          -> {kind: more, n?, to?, about?}  new plan cards cut from the clips no video plays yet
  recut   "给 Needle After Dark 多加几个镜头" / "换掉第 3 个镜头" / "换一批镜头" / "add shots to video 2"
          -> {kind: recut, video?, shot?, mode: add | replace | swap}  that video's re-cut (its unused candidates)
  fanout  anything else: "全部加水印" / "所有 YouTube 版本加英文旁白" / "全部换成更安静的音乐"
          -> {kind: fanout, scope {lang?}}  every made video's clips, each through its own clip AI
"""
import difflib
import re

_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "几": 3,
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "a few": 3, "few": 3, "a couple of": 2, "another": 1, "un": 1, "une": 1, "deux": 2, "trois": 3, "quelques": 3}
_N = r"(\d{1,2}|[一两二三四五六七八九十几]|one|two|three|four|five|six|seven|eight|nine|ten|a few|a couple of|another|une?|deux|trois|quelques)"
_UNIT = r"\s*(?:条|个|支|部|期)"
_SHOT = r"(镜头|片段|素材|画面|空镜|shots?|clips?|footage|takes?|plans?\b|séquences?|rushes)"
_SWAP = r"(换一批|换些|换几个|换掉|替换|换成别的|replace|swap|change the shots|remplace)"
_ADDSHOT = r"(多加|加几|加点|加些|再加|多放|多用|add|more|ajoute|plus de)"
_MORE = re.compile(
    r"再(?:多)?(?:做|剪|出|来|拍)\s*" + _N + r"?" + _UNIT + r"|多做(?:几|" + _N + r")" + r"|"
    r"补(?:够|齐|足|到)\s*(?P<to>\d{1,2}|[一两二三四五六七八九十]+)?" + r"|"
    r"\b(?:make|add|do|cut|create)\s+" + _N + r"\s+(?:more\s+)?(?:new\s+)?(?:videos?|films?|edits?|ones?|cuts?)\b|"
    r"\b" + _N + r"\s+more\b|\bmore videos\b|\banother\s+(?:one|video|film|edit|cut)\b|"
    r"\b(?:fill|top)\s+(?:it\s+|the (?:group|collection)\s+)?up\b|"
    r"\bencore\s+" + _N + r"?\s*vid[ée]os?|\bplus de vid[ée]os\b|\bcompl[ée]te[rz]?\b", re.I)
_ABOUT = re.compile(r"关于\s*(?P<a>.+?)\s*(?:的(?:视频|片子|短片|片)?)?\s*[。!！?？]*$|\babout\s+(?P<b>.+?)[.!?]*$|"
                    r"\bsur\s+(?P<c>.+?)[.!?]*$", re.I)
_SHOT_N = re.compile(r"第\s*(\d{1,2}|[一两二三四五六七八九十]+)\s*(?:个|段|颗)?\s*(?:镜头|片段|画面)|"
                     r"\bshot\s*(?:#|no\.?\s*)?(\d{1,2})\b|\b(\d{1,2})(?:st|nd|rd|th)\s+shot\b|\bplan\s+(\d{1,2})\b",
                     re.I)
_VID_N = re.compile(r"第\s*(\d{1,2}|[一两二三四五六七八九十]+)\s*(?:条|个|支)(?!\s*镜头)|\bvideo\s*#?\s*(\d{1,2})\b|\bv(\d{1,2})\b",
                    re.I)
_EN = re.compile(r"youtube|英文|英语|english|anglais|tiktok|instagram|\bx\b", re.I)
_ZH = re.compile(r"小红书|b站|bilibili|xiaohongshu|douyin|抖音|中文|汉语|chinese|chinois|视频号", re.I)


def _cn(s):
    """'12' / '十二' / '两' -> int, else None."""
    if s is None:
        return None
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    if s in _NUM:
        return _NUM[s]
    if re.fullmatch(r"[一二三四五六七八九]?十[一二三四五六七八九]?", s):
        a, _, b = s.partition("十")
        return (_NUM.get(a, 1) if a else 1) * 10 + (_NUM.get(b, 0) if b else 0)
    return None


def _norm(s):
    return re.sub(r"[\W_]+", "", str(s or "").lower())


def match_video(text, videos):
    """The video her words name: "第 2 条" / "video 2" / "v2", else the title (English or Chinese) that most of it
    appears in her words. -> video id or None."""
    m = _VID_N.search(text or "")
    ids = [v.get("id") for v in videos]
    if m:
        k = _cn(next(g for g in m.groups() if g))
        if m.group(3):                                  # "v2": the id itself
            return f"v{k}" if f"v{k}" in ids else None
        return ids[k - 1] if k and 0 < k <= len(ids) else None
    t = _norm(text)
    best, score = None, 0.0
    for v in videos:
        for title in (v.get("title"), v.get("title_zh")):
            n = _norm(title)
            if len(n) < 2:
                continue
            m2 = difflib.SequenceMatcher(None, t, n, autojunk=False).find_longest_match(0, len(t), 0, len(n))
            cjk = bool(re.search(r"[一-鿿]", n))
            # most of the title, or one long word of it ("the waterfront video")
            enough = m2.size >= (3 if cjk else 6) and (m2.size >= len(n) * 0.5 or m2.size >= (4 if cjk else 8))
            if enough and m2.size / len(n) > score:
                best, score = v.get("id"), m2.size / len(n)
    return best


def scope_of(text):
    """Which versions an edit across the group is for: {lang: en} ("all YouTube versions", "英文版"), {lang: zh}
    ("小红书和 B站"), {} = every version."""
    en, zh = bool(_EN.search(text or "")), bool(_ZH.search(text or ""))
    # "加英文旁白" names the voice's language, not the versions: only a platform / "版本" word picks versions
    plat_en = re.search(r"youtube|tiktok|instagram|英文版|english version", text or "", re.I)
    plat_zh = re.search(r"小红书|b站|bilibili|xiaohongshu|douyin|抖音|视频号|中文版|chinese version", text or "", re.I)
    if plat_en and not plat_zh:
        return dict(lang="en")
    if plat_zh and not plat_en:
        return dict(lang="zh")
    if en != zh and re.search(r"版本|版|versions?", text or "", re.I):
        return dict(lang="en" if en else "zh")
    return {}


def intent(text, videos, need=0):
    """Her words to the group -> {kind: more | recut | fanout | empty, ...} (module doc). ``videos``: the group's
    videos ({id, title, title_zh}); ``need``: how many short of what she asked for (「补够」 with no number)."""
    s = (text or "").strip()
    if not s:
        return dict(kind="empty")
    vid = match_video(s, videos)
    shot = _SHOT_N.search(s)
    shot_n = _cn(next((g for g in shot.groups() if g), None)) if shot else None
    if re.search(_SHOT, s, re.I) and (vid or shot_n or re.search(_SWAP, s, re.I) or re.search(_ADDSHOT, s, re.I)):
        mode = "replace" if shot_n else "swap" if re.search(_SWAP, s, re.I) and not re.search(r"多加|加几|add", s, re.I) \
            else "add"
        return dict(kind="recut", video=vid, shot=shot_n, mode=mode)
    m = _MORE.search(s)
    if m:
        a = _ABOUT.search(s)
        about = next((x for x in (a.groups() if a else ()) if x), None)
        to = _cn(m.group("to"))
        to_span = m.span("to")
        n = next((_cn(g) for i, g in enumerate(m.groups(), 1) if g and m.span(i) != to_span and _cn(g)), None)
        if n is None and re.search(r"\banother\b", m.group(0), re.I):
            n = 1
        fill = re.search(r"补(?:够|齐|足|到)|fill|top|compl", m.group(0), re.I)
        if fill and not to:                         # "fill it up to 12" / "compléter à 12"
            num = re.search(r"(?:to|à|到|够)\s*(\d{1,2})", s[m.start():], re.I)
            to = int(num.group(1)) if num else None
        if fill and not n:
            n = None if to else (need or None)
        return dict(kind="more", n=n, to=to, about=(about or "").strip(" ，,。") or None)
    return dict(kind="fanout", scope=scope_of(s))
