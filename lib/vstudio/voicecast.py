"""Voice casting: which narration voice a video gets, picked for its kind (history, course, vlog, promo ...), its
language, platform, script tone and audience - by the AI, else by rules - from the catalog in ``voices.json``.

    from vstudio import voicecast as VC
    VC.cast("zh", "qwen", kind="history", title="夜色下的太空针塔", script="1962 年 ...")
      -> {engine: qwen, speaker: uncle_fu, style: "用沉稳、庄重的纪录片旁白语气 ...", reason: "...", by: ai | rules,
          kind: history, provider: claude-code}
    VC.cast(..., instruction="换个男声", current={"speaker": "serena"})    # her words in chat: a different voice

The catalog (``voices.json``): the nine speakers of Qwen3-TTS-12Hz-1.7B-CustomVoice (the model's own list, its
config.json ``spk_id``; dylan / eric speak dialect for Chinese text) and the Kokoro English voices, each with its
gender, tone and fit tags; ``styles`` = the delivery instruction per kind that Qwen3-TTS CustomVoice takes (its
``instruct``; Kokoro has none); ``rules`` = the rule casting per language and kind (first available voice wins).

The AI: one ``llm.complete("planner", ...)`` call, so the step follows the project's AI routing like every other
plan step (a step override env VSTUDIO_LLM_PLANNER_PROVIDER > the project's ``ai`` > the task route > the default).
No model / a reply that is not one of the candidates: the rules decide (``by: rules``).

A voice she chose is never re-cast: ``explicit(value)`` -> her voice (a speaker named in project.yaml, in chat, in the
Inbox) or None. Values the projects carry under ``voice``:
    "qwen" / "kokoro" / "auto" / "marin" (an engine or OpenAI's voice): nothing chosen -> cast
    "uncle_fu" / "qwen:uncle_fu" / "傅叔"                                 : her pick -> kept (``by: you``)
    {engine, speaker, style, reason, by: ai | rules}                      : a cast (kept until she asks for another)
    {engine, speaker, style?, by: you}  (or no ``by``)                    : her pick

CLI: ``python -m vstudio.voicecast list [--lang zh]`` / ``cast --lang zh --kind history [--title T] [--ask 换个男声]``
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(HERE, "voices.json")
CAST_BY = ("ai", "rules")                 # a voice the engine picked (re-castable); anything else is hers
_CAT = None

# her words -> the kind of video (zh / en / fr); first match in this order wins
KIND_WORDS = (
    ("kids", r"儿童|孩子|小朋友|宝宝|童话|绘本|亲子|\bkids?\b|children|nursery|bedtime|enfants?"),
    ("news", r"新闻|快讯|播报|时事|\bnews\b|headline|bulletin|actualit"),
    ("history", r"历史|史话|古代|朝代|年代|往事|世博|建于|始建|\d{3,4}\s*年|history|historic|centur|dynasty|"
                r"\bancient\b|world'?s fair|histoire"),
    ("documentary", r"纪录|纪实|人文|档案|documentar|docu-?series"),
    ("course", r"课程|课堂|第.{1,3}[课讲节]|讲座|教学|上课|学习|入门|lesson|course|lecture|class|cours\b|le[cç]on"),
    ("tutorial", r"教程|手把手|怎么做|如何|步骤|攻略|how[- ]to|tutorial|step[- ]by[- ]step|walkthrough|guide|tuto"),
    ("tech", r"\bai\b|\bmcp\b|\bapi\b|编程|代码|算法|模型|技术|科技|code|coding|programming|software|developer|tech"),
    ("explainer", r"科普|讲解|解读|原理|为什么|是什么|explain|explainer|what is|why does|how does|expliqu"),
    ("promo", r"宣传|推广|发布会|上线|新品|launch|promo|trailer|teaser|announce|lancement"),
    ("product", r"产品|好物|种草|测评|开箱|review|unbox|product|gadget|produit"),
    ("comedy", r"搞笑|段子|吐槽|整活|funny|comedy|meme|sketch|humou?r"),
    ("travel", r"旅行|旅游|游记|打卡|航拍|城市漫步|citywalk|travel|trip|journey|voyage|drone|aerial"),
    ("vlog", r"vlog|日常|记录生活|一天|day in|daily|routine"),
    ("essay", r"随笔|散文|诗意|情绪|氛围|独处|秋天|夜晚|essay|reflect|poetic|mood|solitude"),
    ("story", r"故事|讲述|传说|story|tale|legend|histoire de"),
    ("lifestyle", r"生活方式|穿搭|美食|探店|家居|lifestyle|recipe|cooking|food|outfit"),
)
# a vertical short-video platform leans lively when nothing else says what the video is
SHORT_PLATFORMS = ("douyin", "tiktok", "kuaishou", "instagram", "reels", "youtube-shorts", "xiaohongshu:vertical")

_MALE = r"男声|男生|男的|男人|男配音|大叔|male|\bman\b|\bguy\b|voix (?:d'homme|masculine)"
_FEMALE = r"女声|女生|女的|女人|女配音|female|woman|\bgirl\b|\blady\b|voix (?:de femme|f[ée]minine)"
_TONE_WORDS = (
    ("deep", r"低沉|浑厚|磁性|厚重|深沉|deep|low|bass|grave"),
    ("authoritative", r"权威|庄重|正式|严肃|稳重|authoritative|serious|formal|solemn"),
    ("calm", r"沉稳|平静|安静|舒缓|慢一点|calm|soothing|slow|quiet|pos[ée]e?"),
    ("warm", r"温暖|温柔|亲切|柔和|warm|gentle|soft|kind|douce?"),
    ("energetic", r"有活力|有激情|激昂|带劲|燃|energetic|hype|punchy|exciting|dynamique"),
    ("lively", r"活泼|轻快|欢快|俏皮|可爱|lively|upbeat|cheerful|playful|bubbly|enjou"),
    ("youthful", r"年轻|少年|少女|青春|young|youthful|jeune"),
    ("mature", r"成熟|老练|年长|mature|older|seasoned"),
    ("local", r"方言|北京话|京腔|四川话|川话|dialect|accent"),
)


class CastError(ValueError):
    pass


# --------------------------------------------------------------------------- the catalog
def catalog():
    """voices.json (read once)."""
    global _CAT
    if _CAT is None:
        with open(CATALOG, encoding="utf-8") as f:
            _CAT = json.load(f)
    return _CAT


def voices(engine=None, lang=None):
    """The catalog's voices, of ``engine`` and native in ``lang`` when given."""
    return [v for v in catalog()["voices"] if (engine is None or v["engine"] == engine)
            and (lang is None or lang in v["native"])]


def _norm(s):
    return re.sub(r"[\s_\-·.]+", "", str(s or "").lower())


def find(name, engine=None):
    """A voice by id (``qwen:uncle_fu``), speaker (``uncle_fu``, ``Uncle Fu``) or its label's name (``傅叔``) -> the
    catalog entry, or None."""
    n = _norm(name)
    if not n:
        return None
    for v in voices(engine):
        names = {_norm(v["id"]), _norm(v["speaker"])} | {_norm(re.split(r"\s+[—·]\s+|\s*·\s*", lb)[0])
                                                         for lb in v["label"].values()}
        if n in names:
            return v
    return None


def style_for(kind, lang):
    """The delivery instruction for ``kind`` in ``lang`` (Qwen3-TTS ``instruct``), or None."""
    s = catalog()["styles"].get(kind or "") or {}
    return s.get("zh" if lang == "zh" else "en")


def label(v, ui="en"):
    """A voice's name for her (``Uncle Fu — calm, deep male``); ``v`` an entry, a cast or a speaker name."""
    e = v if isinstance(v, dict) and v.get("label") else find(v.get("speaker") if isinstance(v, dict) else v)
    if not e:
        return str((v or {}).get("speaker") if isinstance(v, dict) else v or "")
    return e["label"].get("zh" if ui == "zh" else "en") or e["label"]["en"]


def _kokoro_dir():
    try:
        from vstudio import tts
        d = tts.kokoro_model()
    except Exception:  # noqa: BLE001
        return None
    return d if d and os.path.isdir(d) else None


def available(v):
    """The voice can speak on this computer: a Kokoro voice of a local model folder (the desk app's download has only
    some) must be in its voices/; otherwise the engine fetches it."""
    if v["engine"] != "kokoro":
        return True
    d = _kokoro_dir()
    if not d or not os.path.isdir(os.path.join(d, "voices")):
        return True
    return os.path.isfile(os.path.join(d, "voices", f"{v['speaker']}.safetensors"))


def candidates(engine, lang):
    """The voices the casting may pick for narration in ``lang`` on ``engine``."""
    return [v for v in voices(engine, lang) if available(v)]


def narration_engine(lang, engine="auto"):
    """The engine that will say narration in ``lang`` here (vstudio.tts's own resolution: the free voice -> Qwen3-TTS
    for Chinese once it is ready) -> "qwen" | "kokoro" | another engine (no catalog: nothing to cast)."""
    from vstudio import tts
    e = str(engine or "auto").lower()
    e = tts.ALIASES.get(e, e)
    if e == "auto":
        e = tts.available_engine()
    if lang == "zh":
        e = tts.zh_engine(e)
    return e


# --------------------------------------------------------------------------- values in projects
def parse(value, engine=None):
    """A ``voice`` value as projects carry it -> {engine, speaker, style, reason, by} | None (nothing named)."""
    if isinstance(value, dict):
        sp = value.get("speaker") or value.get("voice")
        e = find(sp, value.get("engine")) or find(sp)
        if not e:
            return None
        out = dict(engine=e["engine"], speaker=e["speaker"], style=value.get("style") or None,
                   reason=value.get("reason") or None, by=value.get("by") or "you")
        for k in ("kind", "provider", "at"):
            if value.get(k):
                out[k] = value[k]
        return out
    if isinstance(value, str) and value.strip():
        e = find(value.strip(), engine) or find(value.strip())
        if e:
            return dict(engine=e["engine"], speaker=e["speaker"], style=None, reason=None, by="you")
    return None


def explicit(value, engine=None):
    """Her own voice in ``value`` (a speaker she named, a pick she made) -> the parsed voice, or None (nothing chosen,
    or the engine's own cast: those may be cast again)."""
    p = parse(value, engine)
    return p if p and p.get("by") not in CAST_BY else None


def is_cast(value):
    """``value`` is a cast the engine made (by ai / rules)."""
    p = parse(value)
    return bool(p and p.get("by") in CAST_BY)


# --------------------------------------------------------------------------- what the video is
def kind_of(*texts):
    """Her request / title / script -> the kind of video (``KIND_WORDS``), or None."""
    t = "\n".join(str(x) for x in texts if x)
    if not t.strip():
        return None
    best, score = None, 0
    for k, rx in KIND_WORDS:
        n = len(re.findall(rx, t, re.I))
        if n > score:
            best, score = k, n
    return best


def wants(instruction):
    """Her words about the voice ("换个男声", "a deeper voice", "用 vivian") -> {gender, tones, speaker}."""
    t = str(instruction or "")
    out = dict(gender=None, tones=[], speaker=None)
    if re.search(_FEMALE, t, re.I):
        out["gender"] = "female"
    elif re.search(_MALE, t, re.I):
        out["gender"] = "male"
    out["tones"] = [k for k, rx in _TONE_WORDS if re.search(rx, t, re.I)]
    for v in voices():
        for nm in [v["speaker"], v["speaker"].replace("_", " ")] + [re.split(r"\s+[—·]\s+|\s*·\s*", lb)[0]
                                                                     for lb in v["label"].values()]:
            if len(nm) >= 2 and re.search(rf"(?<![A-Za-z]){re.escape(nm)}(?![A-Za-z])", t, re.I):
                out["speaker"] = v
                break
        if out["speaker"]:
            break
    return out


def _change_asked(instruction):
    return bool(re.search(r"换|另|别的|不要|不想|other|another|different|change|switch|swap|autre|chang", str(instruction or ""),
                          re.I))


# --------------------------------------------------------------------------- casting
def _platform_kind(platforms):
    pl = [str(p).lower() for p in platforms or []]
    return "vlog" if pl and all(any(p.startswith(s) for s in SHORT_PLATFORMS) for p in pl) else None


def rule_cast(lang, engine, kind=None, platforms=None, instruction=None, current=None, audience=None):
    """The rules' voice (no model): her words first (a named speaker, then gender / tone), else the kind's list in
    ``voices.json`` rules, else the language default. -> a cast dict (``by: rules``) | None (no catalog voice here)."""
    lang = "zh" if lang == "zh" else "en"
    cands = candidates(engine, lang)
    if not cands:
        return None
    if audience and re.search(r"儿童|孩子|kid|child", str(audience), re.I):
        kind = "kids"
    k = kind or _platform_kind(platforms) or "default"
    cur = (current or {}).get("speaker") if isinstance(current, dict) else current
    w = wants(instruction)
    order = [x for x in (catalog()["rules"].get(lang, {}).get(k) or []) + catalog()["rules"].get(lang, {}).get(
        "default", [])]
    by_id = {v["id"]: v for v in cands}
    ranked = [by_id[i] for i in dict.fromkeys(order) if i in by_id] + [v for v in cands if v["id"] not in order]
    why = None
    if w["speaker"] and w["speaker"]["id"] in by_id:
        pick, why = w["speaker"], "you named this voice"
    else:
        pool = ranked
        if instruction and cur and (_change_asked(instruction) or w["gender"] or w["tones"]):
            pool = [v for v in pool if v["speaker"] != cur] or pool
        if w["gender"]:
            pool = [v for v in pool if v["gender"] == w["gender"]] or pool
        if w["tones"]:
            scored = sorted(pool, key=lambda v: -len(set(w["tones"]) & set(v["tone"])))
            pool = scored if len(set(w["tones"]) & set(scored[0]["tone"])) else pool
        if "local" not in w["tones"]:     # a dialect voice only when she asks for one (or the kind's list has it)
            pool = [v for v in pool if not v.get("dialect") or v["id"] in order[:1]] or pool
        pick = pool[0]
        if instruction:
            why = "your request: " + str(instruction).strip()[:60]
    style = style_for(k if k != "default" else None, lang) if engine == "qwen" else None
    if not why:
        what = k if k != "default" else "general"
        why = f"{what} video: {', '.join(pick['tone'][:3])} {pick['gender']} voice"
    return dict(engine=pick["engine"], speaker=pick["speaker"], style=style, reason=why, by="rules", kind=kind)


SYSTEM = ("You are the casting director for a video's narration voice. Pick the ONE voice from the candidate list "
          "that best fits the video's kind, language, platform, script tone and audience, and write the delivery "
          "instruction the TTS model is given (one sentence, in the narration's language; how to say it: pace, "
          "mood, emphasis - never what to say). History / documentary / news: calm, authoritative. Course / "
          "tutorial: clear and warm. Vlog / short reels: lively. A dialect voice only for casual local content or "
          "when asked. Reply with JSON only: {\"speaker\": \"<a candidate's speaker id>\", \"style\": \"<delivery "
          "instruction>\", \"reason\": \"<one short line for the creator: why this voice>\"}.")


def _brief(v):
    return dict(speaker=v["speaker"], gender=v["gender"], tone=v["tone"], fit=v["fit"], desc=v["desc"],
                **({"dialect": v["dialect"]} if v.get("dialect") else {}))


def cast(lang, engine, kind=None, platforms=None, title=None, request=None, script=None, audience=None,
         instruction=None, current=None, complete=None, ui="en"):
    """The narration voice for this video -> {engine, speaker, style, reason, by: ai | rules, kind, provider?}, or
    None when ``engine`` has no catalog voices for ``lang`` (OpenAI, a cloned voice, a TTS server: their own voice).
    ``complete``: ``llm.complete`` (default) or a stand-in; False = rules only. ``instruction``: her words ("换个男声"),
    ``current`` the voice she has now (a change asked for picks another one)."""
    lang = "zh" if lang == "zh" else "en"
    kind = kind or kind_of(request, title, (script or "")[:1500])
    base = rule_cast(lang, engine, kind, platforms, instruction, current, audience)
    if base is None:
        return None
    w = wants(instruction)
    if w["speaker"] and base["reason"] == "you named this voice":
        base["by"] = "you"                 # she named it: hers, not the engine's
        return base
    if complete is False:
        return base
    cands = candidates(engine, lang)
    cur = (current or {}).get("speaker") if isinstance(current, dict) else current
    body = dict(language="Chinese (Mandarin)" if lang == "zh" else "English", kind=kind or "unknown",
                platforms=list(platforms or []), title=title or "", audience=audience or "",
                request=str(request or "")[:600], script_excerpt=str(script or "")[:900],
                candidates=[_brief(v) for v in cands])
    if instruction:
        body["creator_asks"] = str(instruction)[:200]
        if cur:
            body["current_voice"] = cur
            body["note"] = "she asked for a change: pick a different voice that matches her words"
    reason_lang = "Chinese" if ui == "zh" else "French" if ui == "fr" else "English"
    try:
        if complete is None:
            from vstudio import llm
            complete = llm.complete
        r = complete("planner", SYSTEM, json.dumps(body, ensure_ascii=False) +
                     f"\nWrite the reason in {reason_lang}.", schema=True, max_tokens=600, timeout=120,
                     cli_timeout=120, retries=1, effort="low")
    except Exception as e:  # noqa: BLE001  (no model / it failed: the rules' voice, said so)
        base["ai_error"] = str(e)[:200]
        return base
    js = r.get("json") if isinstance(r, dict) and isinstance(r.get("json"), dict) else None
    sp = str((js or {}).get("speaker") or "").strip().lower()
    pick = next((v for v in cands if v["speaker"] == sp), None)
    if not pick or (instruction and cur and _change_asked(instruction) and pick["speaker"] == cur and
                    base["speaker"] != cur):
        return base
    style = str(js.get("style") or "").strip()[:240] or base.get("style")
    if engine != "qwen":
        style = None                       # Kokoro takes no delivery instruction
    reason = re.sub(r"\s+", " ", str(js.get("reason") or "").strip())[:140] or base["reason"]
    return dict(engine=pick["engine"], speaker=pick["speaker"], style=style, reason=reason, by="ai", kind=kind,
                provider=(r or {}).get("provider"))


def record(c):
    """A cast as the project stores it (``voice: {engine, speaker, style, reason, by}``)."""
    return {k: c[k] for k in ("engine", "speaker", "style", "reason", "by", "kind", "provider") if c.get(k)}


# --------------------------------------------------------------------------- CLI
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="the catalog")
    ls.add_argument("--lang")
    ls.add_argument("--engine")
    c = sub.add_parser("cast", help="cast a voice")
    c.add_argument("--lang", default="zh")
    c.add_argument("--engine", default="auto")
    c.add_argument("--kind")
    c.add_argument("--title")
    c.add_argument("--request")
    c.add_argument("--platform", action="append")
    c.add_argument("--ask", help="her words about the voice (换个男声)")
    c.add_argument("--current")
    c.add_argument("--rules", action="store_true", help="no model")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for v in voices(a.engine, a.lang):
            print(f"{v['id']:<20} {v['gender']:<6} {'/'.join(v['native']):<3} {', '.join(v['tone']):<40} "
                  f"{', '.join(v['fit'])}" + ("" if available(v) else "  (not on this computer)"))
        return
    eng = narration_engine(a.lang, a.engine)
    out = cast(a.lang, eng, kind=a.kind, platforms=a.platform, title=a.title, request=a.request,
               instruction=a.ask, current=a.current, complete=False if a.rules else None)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
