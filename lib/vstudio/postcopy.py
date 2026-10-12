"""Post copy for videos without speech (travel vlogs, drone films, photo stories): a hook / title, a short body
(2-4 lines; a longer YouTube description), topic hashtags within each platform's limits, the place (offline, from
the DJI flight logs), the music credit when the track asks for one - per platform, in that platform's language.

    from vstudio import postcopy as PC
    ctx = PC.context(request="帮我剪一个西雅图红叶的视频", title="Seattle in Red", footage=[...],
                     music={"title": ..., "credit": "Music: ... (CC BY 4.0)"}, duration=59.5)
    d = PC.draft(ctx, ["youtube", "tiktok", "xiaohongshu:full"])        # routed AI, else the rules
    d["per_platform"]["xiaohongshu"]   # {"title", "body", "tags", "lang"}
    PC.post_json(d)                    # -> the post.json vstudio.export reads (``per_platform`` blocks)

Language per platform (``copy_lang``): persona ``publish.copy_lang.<platform>`` > the Chinese platforms take
persona ``publish.copy_lang.cn`` (default Chinese) > the international ones take persona ``publish.copy_lang.intl``
(default English). Her own title is kept on the platforms in its language.

``draft``: the routed ``copy`` model (vstudio.llm; Claude Code / any API / a local model) writes each language once
from the facts (place, month, aerial or not, her words, her title, the music); every answer is checked (non-empty,
no hashtags in the body, title fitted to the platform, tag count within the platform's limit, voice rules) and any
missing part is filled from the rules. No model, or a failed call: the rules draft (``source: rules``), said so in
``notes``. Both drafts are kept so the creator can switch (the vlog recipe's ``copy`` decision).
"""
import re

from . import publish

# topic vocabulary: a pattern in her words / title -> (English phrase, Chinese phrase, English tags, Chinese tags)
TOPICS = [
    (r"红叶|枫叶|落叶|fall foliage|autumn leaves|red leaves|maple|foliage|leaf.?peep",
     "fall foliage", "红叶", ["fallfoliage", "autumnleaves"], ["红叶", "秋日限定"]),
    (r"秋|autumn|\bfall\b", "autumn", "秋天", ["autumn"], ["秋天"]),
    (r"樱花|cherry blossom|sakura", "cherry blossoms", "樱花", ["cherryblossom"], ["樱花"]),
    (r"雪|snow|winter|冬", "snow", "雪景", ["winter", "snow"], ["雪景"]),
    (r"日落|夕阳|sunset|golden hour", "sunset", "日落", ["sunset", "goldenhour"], ["日落"]),
    (r"日出|sunrise", "sunrise", "日出", ["sunrise"], ["日出"]),
    (r"夜景|night|city lights", "city lights", "夜景", ["nightview"], ["夜景"]),
    (r"海|beach|ocean|coast|sea\b", "the coast", "海边", ["beach", "coast"], ["海边"]),
    (r"山|mountain|hike|徒步|peak", "the mountains", "山野", ["mountains", "hiking"], ["徒步"]),
    (r"湖|lake", "the lake", "湖边", ["lake"], ["湖景"]),
    (r"花|flower|bloom", "flowers", "花", ["flowers"], ["花"]),
    (r"城市|city|街|street|citywalk|city walk", "the city", "城市", ["citywalk"], ["城市漫步"]),
    (r"航拍|无人机|drone|aerial|from above|大疆|dji", "from above", "航拍", ["dronevideo", "aerialview"],
     ["航拍", "无人机航拍"]),
    (r"旅行|旅游|travel|trip|vacation|holiday|度假", "travel", "旅行", ["travel"], ["旅行"]),
    (r"vlog|日常|daily", "vlog", "vlog", ["vlog"], ["vlog"]),
]
SEASON = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring", 6: "summer", 7: "summer",
          8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
SEASON_ZH = {"winter": "冬天", "spring": "春天", "summer": "夏天", "autumn": "秋天"}
MONTH_EN = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
            "November", "December"]
# how many hashtags a post gets (capped by the platform's own maximum)
TAG_COUNT = {"tiktok": 4, "youtube": 3, "youtube-shorts": 3, "instagram": 5, "x": 2, "facebook": 3, "threads": 1,
             "linkedin": 3, "xiaohongshu": 6, "douyin": 5, "bilibili": 6, "wechat-channels": 3, "kuaishou": 3,
             "weibo": 3}
LONG_BODY = {"youtube", "bilibili"}            # a description, not a caption
CN_PLATFORMS = {"xiaohongshu", "douyin", "bilibili", "wechat-channels", "kuaishou", "weibo", "zhihu"}


def _persona(path, default=None):
    return publish._p(path, default)


def platform_key(target):
    return publish.platform_name(str(target).split(":")[0])


def detect_request_lang(text):
    return publish.detect_lang(text or "") if (text or "").strip() else None


def copy_lang(platform, request=None):
    """The language of one platform's copy: persona ``publish.copy_lang.<platform>``; a Chinese platform ->
    ``publish.copy_lang.cn`` (default zh: its audience reads Chinese, whatever language she typed the request in -
    an English request used to get English copy on 小红书 / B站); an international one -> ``publish.copy_lang.intl``
    (default en). ``request`` is kept for callers; it no longer decides."""
    pl = platform_key(platform)
    cfg = _persona("publish.copy_lang", {}) or {}
    if isinstance(cfg, str):
        cfg = {"intl": cfg}
    if cfg.get(pl) in ("en", "zh"):
        return cfg[pl]
    if pl in CN_PLATFORMS:
        return cfg.get("cn") if cfg.get("cn") in ("en", "zh") else "zh"
    return cfg.get("intl") if cfg.get("intl") in ("en", "zh") else "en"


def topics(text):
    out = []
    for pat, en, zh, ten, tzh in TOPICS:
        if re.search(pat, text or "", re.I):
            out.append(dict(en=en, zh=zh, tags_en=ten, tags_zh=tzh))
    return out


def context(request=None, title=None, footage=(), music=None, duration=None, place=None, aerial=None, date=None):
    """The facts the copy is written from (no pixels, no transcript: a vlog has neither words nor a script)."""
    from . import places
    pl = place if place is not None else places.from_footage(footage)
    pl = pl or {}
    date = date or pl.get("date")
    month = int(date[5:7]) if date and re.match(r"\d{4}-\d\d", date) else None
    text = " ".join(x for x in (request, title) if x)
    aer = aerial if aerial is not None else pl.get("aerial")
    tps = topics(text + (" drone" if aer else ""))
    m = dict(music or {})
    credit = m.get("credit") if m.get("credit") else None
    return dict(request=(request or "").strip(), title=(title or "").strip(), place=pl.get("en") and dict(
        en=pl["en"], zh=pl.get("zh") or pl["en"]) or None, month=month, season=SEASON.get(month) if month else None,
        aerial=bool(aer), topics=tps, music=dict(title=m.get("title"), credit=credit) if (m.get("title") or credit)
        else None, duration=duration, request_lang=detect_request_lang(request))


# ---------------------------------------------------------------- hashtags
def _tag_clean(t, lang):
    t = str(t or "").strip().lstrip("#").strip()
    t = re.sub(r"[#,，。.!！?？]", "", t)
    if lang == "en" or re.fullmatch(r"[\x00-\x7f]+", t):
        t = re.sub(r"\s+", "", t)
    return t[:30]


def tag_limit(platform):
    from . import platform as P
    pl = platform_key(platform)
    n = TAG_COUNT.get(pl, 3)
    try:
        mx = (P.profile(pl).hashtags or {}).get("max")
    except Exception:  # noqa: BLE001
        mx = None
    cap = publish.HASHTAG_CAP.get(pl)
    for lim in (mx, cap):
        if lim is not None:
            n = min(n, int(lim))
    return max(0, n)


def rules_tags(ctx, lang, platform):
    tags = []
    if ctx.get("place"):
        tags.append(ctx["place"]["en"] if lang == "en" else ctx["place"]["zh"])
    for tp in ctx.get("topics") or []:
        tags += tp["tags_en"] if lang == "en" else tp["tags_zh"]
    if ctx.get("season") and not any(t in ("autumn", "秋天") for t in tags):
        tags.append(ctx["season"] if lang == "en" else SEASON_ZH[ctx["season"]])
    if lang == "en" and ctx.get("place"):
        tags.append("visit" + ctx["place"]["en"])
    tags.append("travel" if lang == "en" else "旅行vlog")
    out = list(dict.fromkeys(_tag_clean(t, lang) for t in tags if _tag_clean(t, lang)))
    return out[:tag_limit(platform)]


def fit_tags(tags, lang, platform, ctx=None):
    """Model tags -> cleaned, deduplicated, within the platform's count (rules tags fill a short list)."""
    out = list(dict.fromkeys(_tag_clean(t, lang) for t in tags or [] if _tag_clean(t, lang)))
    n = tag_limit(platform)
    if len(out) < min(n, 2) and ctx is not None:
        out = list(dict.fromkeys(out + rules_tags(ctx, lang, platform)))
    return out[:n]


# ---------------------------------------------------------------- the rules draft
def _subject(ctx, lang):
    tp = [t for t in ctx.get("topics") or [] if t["en"] not in ("from above", "travel", "vlog")]
    if lang == "en":
        return tp[0]["en"] if tp else (ctx["season"] if ctx.get("season") else "a few quiet moments")
    return tp[0]["zh"] if tp else (SEASON_ZH[ctx["season"]] if ctx.get("season") else "一些安静的时刻")


def _rules_title(ctx, lang):
    place = (ctx.get("place") or {}).get(lang)
    subj = _subject(ctx, lang)
    if lang == "en":
        t = f"{place} {subj}".strip() if place else subj[:1].upper() + subj[1:]
        if ctx.get("aerial"):
            t += " from above"
        return t[:1].upper() + t[1:]
    t = f"{place}的{subj}" if place else subj
    return t + ("｜航拍" if ctx.get("aerial") else "")


def _credit_line(ctx, lang):
    m = ctx.get("music") or {}
    if m.get("credit"):
        return m["credit"]
    return None


def rules_post(ctx, platform, lang):
    """A plain, specific post from the facts alone (no model) -> {title, body, tags, lang}."""
    pl = platform_key(platform)
    place = (ctx.get("place") or {}).get(lang)
    subj = _subject(ctx, lang)
    month = MONTH_EN[ctx["month"]] if ctx.get("month") else None
    if lang == "en":
        where = f" in {place}" if place else ""
        when = f" this {month}" if month else ""
        lines = [f"{subj[:1].upper() + subj[1:]}{where}{when}" + (", seen from above." if ctx.get("aerial") else "."),
                 "Turn the sound up and take a slow minute with it."]
        if pl in LONG_BODY:
            lines.append(("Shot on a drone" if ctx.get("aerial") else "Filmed") + (f" around {place}" if place else "")
                         + (f" in {month}" if month else "") + ", edited for a calm watch.")
            lines.append("Where should I fly next? Tell me in the comments.")
    else:
        where = f"{place}的" if place else ""
        when = f"{ctx['month']}月" if ctx.get("month") else ""
        lines = [f"{when}{where}{subj}" + ("，从天上看是另一种颜色。" if ctx.get("aerial") else "，刚刚好。"),
                 "戴上耳机，慢慢看完这一分钟。"]
        if pl in LONG_BODY:
            lines.append(("无人机航拍" if ctx.get("aerial") else "实拍") + (f"于{place}" if place else "")
                         + "，剪成一支安静的片子。")
            lines.append("下一站想看哪里？评论区告诉我。")
    cr = _credit_line(ctx, lang)
    if cr:
        lines.append(cr)
    title = ctx["title"] if ctx.get("title") and publish.detect_lang(ctx["title"]) == lang else _rules_title(ctx, lang)
    return dict(title=title, body="\n".join(lines), tags=rules_tags(ctx, lang, platform), lang=lang)


# ---------------------------------------------------------------- the AI draft
LANG_SCHEMA = {"type": "object", "required": ["title", "hook", "body", "description", "tags"], "properties": {
    "title": {"type": "string"}, "hook": {"type": "string"}, "body": {"type": "string"},
    "description": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}}


def _facts(ctx):
    f = []
    if ctx.get("request"):
        f.append(f"Her request: {ctx['request'][:600]}")
    if ctx.get("title"):
        f.append(f"Her title: {ctx['title']}")
    if ctx.get("place"):
        f.append(f"Place: {ctx['place']['en']} ({ctx['place']['zh']})")
    if ctx.get("month"):
        f.append(f"Filmed in: {MONTH_EN[ctx['month']]} ({ctx['season']})")
    f.append("Footage: " + ("drone / aerial shots" if ctx.get("aerial") else "handheld / ground shots"))
    if ctx.get("topics"):
        f.append("Topics: " + ", ".join(t["en"] for t in ctx["topics"]))
    if ctx.get("duration"):
        f.append(f"Length: {ctx['duration']:.0f} s, no voice-over (music + pictures)")
    if (ctx.get("music") or {}).get("title"):
        f.append(f"Music: {ctx['music']['title']}")
    return "\n".join(f)


def prompt(ctx, langs):
    rules = " ".join(_persona("voice.rules", []) or [])
    names = {"en": "English", "zh": "Simplified Chinese"}
    system = (
        "You write social-media post copy for a short travel / scenery video (no voice-over: music and pictures). "
        "Only use the facts given: never invent names, places, dates, gear or numbers. Concrete and calm, no "
        "clickbait, no emoji, no 'link in bio', no call to like / follow. For each language asked, return:\n"
        "- title: <= 40 characters for English, <= 18 Chinese characters; specific (place / subject); keep her own "
        "title if one is given in that language (fix only an em-dash)\n"
        "- hook: one short line that makes someone stop scrolling, different from the title\n"
        "- body: 2-3 short lines for TikTok / 小红书 / 抖音 captions (newline-separated, no hashtags)\n"
        "- description: 4-6 lines for a YouTube description (what it is, where / when, how it was filmed if known, "
        "a question to the viewer; no hashtags, no timestamps)\n"
        "- tags: 6-8 topic hashtags without '#', specific to this video (place, subject, season, aerial), no "
        "generic tags like fyp / viral / 推荐\n"
        + (f"Voice rules: {rules}\n" if rules else "") + "Answer with JSON only: {"
        + ", ".join(f'"{lg}": {{title, hook, body, description, tags}}' for lg in langs) + "}.")
    return system, f"Write the copy in: {', '.join(names[lg] for lg in langs)}.\n\nFACTS:\n{_facts(ctx)}"


def _schema(langs):
    return {"type": "object", "required": list(langs), "properties": {lg: LANG_SCHEMA for lg in langs}}


def _clean_text(t):
    t = re.sub(r"(?<![A-Za-z0-9&])#[^\s#，。！？、,.!?]+#?", "", str(t or ""))    # hashtags belong in the tag line
    t = "\n".join(re.sub(r"[ \t]+", " ", x).strip() for x in t.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _lines(t, n):
    xs = [x for x in _clean_text(t).split("\n") if x.strip()]
    return "\n".join(xs[:n])


def _voice(text, notes):
    from .clipcopy import _voice_fix
    return _voice_fix(text, notes)


def ai_post(block, ctx, platform, lang, notes):
    """One language block of the model's answer -> the post of one platform (checked; rules fill the gaps)."""
    pl = platform_key(platform)
    base = rules_post(ctx, platform, lang)
    b = block if isinstance(block, dict) else {}
    title = _clean_text(b.get("title")).replace("\n", " ") or base["title"]
    if ctx.get("title") and publish.detect_lang(ctx["title"]) == lang:
        title = ctx["title"]
    if pl in LONG_BODY:
        body = _lines(b.get("description"), 6) or base["body"]
    else:
        hook = _clean_text(b.get("hook")).replace("\n", " ")
        body = "\n".join(x for x in (hook, _lines(b.get("body"), 3)) if x) or base["body"]
        body = _lines(body, 4)
    cr = _credit_line(ctx, lang)
    if cr and cr not in body:
        body += "\n" + cr
    title, body = _voice(title, notes), _voice(body, notes)
    return dict(title=title, body=body, tags=fit_tags(b.get("tags"), lang, platform, ctx), lang=lang)


def _platform_list(platforms):
    return list(dict.fromkeys(platform_key(p) for p in platforms or ["xiaohongshu"]))


def rules_draft(ctx, platforms):
    pls = _platform_list(platforms)
    per = {pl: rules_post(ctx, pl, copy_lang(pl, ctx.get("request"))) for pl in pls}
    notes = ["written from the facts alone (place, month, your words): no text model was used"]
    for pl, d in per.items():
        d["title"], d["body"] = _voice(d["title"], notes), _voice(d["body"], notes)
        if publish.title_max(pl):
            d["title"] = publish.fit_title(d["title"], pl)[0]
    return dict(per_platform=per, source="rules", provider=None, notes=list(dict.fromkeys(notes)))


def draft(ctx, platforms, provider="auto", complete=None, timeout=180):
    """The AI draft when a ``copy`` model is routed (else / on failure the rules draft) ->
    {per_platform {pl: {title, body, tags, lang}}, source "llm:<provider>" | "rules", provider, notes, error?}."""
    from . import llm
    pls = _platform_list(platforms)
    langs = list(dict.fromkeys(copy_lang(pl, ctx.get("request")) for pl in pls))
    rd = rules_draft(ctx, pls)
    if complete is None:
        route = llm.route("copy", None if provider in (None, "auto") else provider)
        if route.provider == "none":
            return rd
        complete = llm.complete
    system, user = prompt(ctx, langs)
    try:
        r = complete("copy", system, user, schema=_schema(langs),
                     provider=None if provider in (None, "auto") else provider, timeout=timeout, cli_timeout=timeout)
    except Exception as e:  # noqa: BLE001  (no key / CLI logged out / timeout: the rules draft, said so)
        return dict(rd, error=f"{type(e).__name__}: {str(e)[:300]}", notes=rd["notes"] + [
            f"the AI could not write it ({type(e).__name__}): written from the facts instead"])
    j = (r or {}).get("json")
    if not isinstance(j, dict) or not any(isinstance(j.get(lg), dict) for lg in langs):
        return dict(rd, error="the model's answer had no copy", notes=rd["notes"] + [
            "the AI's answer had no usable copy: written from the facts instead"])
    notes = []
    per = {}
    for pl in pls:
        lg = copy_lang(pl, ctx.get("request"))
        per[pl] = ai_post(j.get(lg) or {}, ctx, pl, lg, notes)
        if publish.title_max(pl):
            per[pl]["title"], note = publish.fit_title(per[pl]["title"], pl)
            if note:
                notes.append(f"{pl}: title shortened ({note})")
    prov = (r or {}).get("provider") or "custom"
    return dict(per_platform=per, source=f"llm:{prov}", provider=prov, model=(r or {}).get("model"),
                notes=list(dict.fromkeys(notes)))


def post_json(d, title=None):
    """A draft -> the post.json vstudio.export reads: ``per_platform`` blocks (each in its own language) win over
    the flat keys; ``lang_by_platform`` says which language went where. Persona tags are not added (the topic tags
    are this video's)."""
    per = d.get("per_platform") or {}
    first = next(iter(per.values()), {})
    return dict(title=title or first.get("title") or "", body=first.get("body") or "", tags=first.get("tags") or [],
                per_platform=per, lang_by_platform={k: v.get("lang") for k, v in per.items()},
                use_persona_tags=False, source=d.get("source"))
