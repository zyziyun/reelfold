"""Which editing template fits this video: the inputs + the request -> a template (recipe + params + shot policy) with a
reason she reads and can change.

    from vstudio.brain import template as T
    sig = T.signals(analysis, prompt)             # intake analysis (vstudio.intake.inventory.analyze) + her words
    d = T.classify(sig)                           # {template, recipe, params, label, reason {en, zh}, confidence,
                                                  #  by: rules | her | ai, alternatives [...], signals}
    d = T.classify(sig, fixed_recipe="vlog")      # her explicit recipe: only its templates compete

Signals: speech share, talking head / several people / screen recording, aerial (a DJI flight log next to the
clip, a DJI file name), motion level (``shots`` per-second motion when known), photos vs clips, music, length,
night / golden hour, and the request's words (en / zh). Her explicit words win: a template she names (卡点, 历史,
口播, "fast cuts on the beat", "reflective voice-over") is ``by: her``; what only the materials suggest is
``by: rules``. A close call (margin < ``AMBIGUOUS``) may be asked of the routed AI (``judge``); without one the
rules' pick stands and says it was close.
"""
import json
import os
import re

from . import presets as P

AMBIGUOUS = 0.12

# request words -> template, (pattern, weight). English and Chinese; matched on the lower-cased request.
WORDS = {
    "beat-short": (r"卡点|快节奏|快剪|燃|动感|节奏感|on the beat|beat[- ]?(?:cut|sync)|fast cuts|upbeat|energetic|"
                   r"hype|punchy|action reel|\breel\b", 3.0),
    "travel-calm": (r"舒缓|安静|慢节奏|治愈|电影感|高级感|空镜|no voice|unhurried|calm|cinematic film|slow premium|"
                    r"golden[- ]hour film|music bed|follow the light|just music", 2.0),
    "trip-vlog": (r"vlog|旅行记录|旅游|旅行|road[- ]trip|trip vlog|travel vlog|day in|place and time captions", 2.0),
    "history-explainer": (r"历史|history|historic|heritage|world'?s fair|built (?:in|for)|verifiable facts|"
                          r"故事背景", 3.0),
    "documentary": (r"纪录片|documentary|observational", 3.0),
    "essay": (r"随笔|感悟|独白|reflective (?:voice|essay)|voice-over about|essay|letting go|内心", 2.5),
    "photo-story": (r"照片故事|照片做成|文艺片|photo story|from these photos|slideshow", 2.5),
    "th-refined": (r"口播|精剪|去气口|去口癖|剪干净|talking[- ]head|to camera|filler", 3.0),
    "lecture-shorts": (r"切片|切成|拆条|分集|长视频|lecture|webinar|course recording|long recording|into shorts|clips? from",
                       2.5),
    "conversation-clips": (r"播客|访谈|对话|采访|podcast|interview|conversation|call recording|zoom", 2.5),
    "concept-explainer": (r"讲解视频|科普|原理|3b1b|3blue1brown|explain (?:how|why|what)|concept|explainer", 2.0),
    "product-promo": (r"宣传|推广|promo|advert|commercial|product video|广告", 2.5),
    "launch-film": (r"发布视频|上线|产品发布|版本更新|launch|release video|changelog|product hunt|demo video", 2.5),
    "ai-short": (r"短剧|ai ?生成|aigc|可灵|即梦|ai short|ai drama|text[- ]to[- ]video", 3.0),
}
NO_VOICE = re.compile(r"no voice|without (?:a )?voice|不要旁白|纯音乐|只要音乐|no narration|music only", re.I)
VOICE = re.compile(r"narrat|voice-?over|旁白|解说|配音", re.I)
DJI_NAME = re.compile(r"^DJI_\d{8,}", re.I)


# --------------------------------------------------------------------------- signals
def _speech_s(f):
    if f.get("speech_s") is not None:
        return float(f["speech_s"])
    if f.get("speech") is True:
        return float(f.get("duration") or 0) * 0.8
    return 0.0


def signals(analysis, prompt="", footage_facts=None, shot_metrics=None):
    """Intake analysis (+ optional ``vstudio.footage.facts`` per clip and ``shots`` metrics) + request -> signals.
    ``footage_facts``: {path: facts}; ``shot_metrics``: {path: shots.analyze() doc}. Both optional."""
    files = (analysis or {}).get("files") or []
    vids = [f for f in files if f.get("kind") == "video"]
    imgs = [f for f in files if f.get("kind") == "image"]
    auds = [f for f in files if f.get("kind") == "audio"]
    docs = [f for f in files if f.get("kind") == "text" and f.get("shape") not in ("telemetry", "subtitles")]
    tele = [f for f in files if f.get("kind") == "text" and f.get("shape") == "telemetry"]
    vs = sum(float(f.get("duration") or 0) for f in vids)
    sp = sum(_speech_s(f) for f in vids)
    th = sum(float(f.get("duration") or 0) for f in vids if f.get("talking_head"))
    facts = footage_facts or {}
    aerial_n = sum(1 for f in vids if DJI_NAME.match(os.path.basename(f.get("path") or f.get("rel") or "")) or
                   (facts.get(f.get("path")) or {}).get("gps"))
    hours = []
    for f in vids:
        rec = str((facts.get(f.get("path")) or {}).get("recorded") or "")
        if len(rec) >= 13 and rec[11:13].isdigit():
            hours.append(int(rec[11:13]))
    motion = None
    if shot_metrics:
        ms = [s.get("motion", 0.0) for a in shot_metrics.values() for s in (a or {}).get("secs") or []]
        if ms:
            ms.sort()
            motion = round(ms[len(ms) // 2], 2)
    orient = [f.get("orientation") for f in vids if f.get("orientation")]
    return dict(
        prompt=(prompt or "").strip(), videos=len(vids), photos=len(imgs), docs=len(docs),
        music=sum(1 for f in auds if f.get("speech") is False), voice_audio=sum(1 for f in auds if f.get("speech")),
        video_s=round(vs, 1), longest_s=round(max([float(f.get("duration") or 0) for f in vids] or [0]), 1),
        speech_share=round(sp / vs, 2) if vs else 0.0, talking_head_share=round(th / vs, 2) if vs else 0.0,
        multi_person=any(f.get("multi_person") for f in vids), screen=any(f.get("screen_share") for f in vids),
        aerial=bool(tele) or (aerial_n >= max(1, len(vids) // 2) if vids else False),
        short_clips=sum(1 for f in vids if 0 < float(f.get("duration") or 0) < 15),
        motion=motion, night=bool(hours) and sum(h >= 22 or h < 5 for h in hours) >= len(hours) / 2,
        golden=bool(hours) and sum(17 <= h < 22 for h in hours) >= len(hours) / 2,
        vertical=bool(orient) and sum(o == "vertical" for o in orient) > len(orient) / 2,
        no_voice=bool(NO_VOICE.search(prompt or "")), wants_voice=bool(VOICE.search(prompt or "")) and not
        NO_VOICE.search(prompt or ""))


# --------------------------------------------------------------------------- scores
def _words(prompt):
    t = (prompt or "").lower()
    out = {}
    for pid, (rx, w) in WORDS.items():
        hits = re.findall(rx, t, re.I)
        if hits:
            out[pid] = w + 0.25 * (len(hits) - 1)
    return out


def _r(en, zh):
    return dict(en=en, zh=zh)


def scores(s):
    """signals -> {template: (score, [reasons {en, zh}])}: the materials' evidence, then her words on top."""
    sc = {pid: [0.0, []] for pid in P.PRESETS}

    def add(pid, v, en, zh):
        sc[pid][0] += v
        if en:
            sc[pid][1].append(_r(en, zh))

    footage = s["videos"] and s["speech_share"] < 0.35 and not s["screen"]
    speech = s["videos"] and s["speech_share"] >= 0.35
    if footage:
        n = s["videos"]
        add("travel-calm", 1.0, f"{n} clip(s) with no talking", f"{n} 段素材，没有人说话")
        add("trip-vlog", 0.6, "", "")
        add("beat-short", 0.4, "", "")
        add("history-explainer", 0.2, "", "")
        add("essay", 0.2, "", "")
        if s["aerial"]:
            add("travel-calm", 0.6, "drone footage (DJI flight log)", "无人机航拍（有 DJI 飞行记录）")
            add("history-explainer", 0.3, "", "")
        if s["motion"] is not None:
            if s["motion"] >= 12:
                add("beat-short", 1.2, f"a lot of motion in frame ({s['motion']})", f"画面运动多（{s['motion']}）")
            elif s["motion"] <= 5:
                add("travel-calm", 0.5, "slow, steady movement", "运动缓慢平稳")
        if s["short_clips"] >= 8:
            add("beat-short", 0.8, f"{s['short_clips']} short clips", f"{s['short_clips']} 段短素材")
        if s["night"]:
            add("travel-calm", 0.2, "shot at night", "夜景")
        if s["golden"]:
            add("travel-calm", 0.3, "evening light", "傍晚的光")
        if s["wants_voice"]:
            for pid in ("history-explainer", "essay", "documentary"):
                add(pid, 1.0, "she asks for a voice-over", "要求配旁白")
            add("travel-calm", -0.8, "", "")
        if s["no_voice"]:
            for pid in ("history-explainer", "essay", "documentary"):
                add(pid, -1.5, "", "")
    if s["photos"] and s["photos"] >= max(1, s["videos"]):
        add("photo-story", 1.6, f"{s['photos']} photos", f"{s['photos']} 张照片")
        if s["wants_voice"]:
            add("essay", 0.8, "", "")
    if speech:
        sh = s["speech_share"]
        if s["multi_person"]:
            add("conversation-clips", 1.6, "several people talking", "多人对话")
        if s["screen"] or s["longest_s"] >= 900:
            add("lecture-shorts", 1.4, "a long recording" if not s["screen"] else "a screen recording with a voice",
                "长录播" if not s["screen"] else "有讲解声音的录屏")
        if s["talking_head_share"] >= 0.5 and s["longest_s"] < 900:
            add("th-refined", 1.6, "one person talking to camera", "一个人对着镜头讲")
        elif s["longest_s"] < 900:
            add("th-refined", 0.9, f"speech in {int(sh * 100)}% of the footage", f"{int(sh * 100)}% 的时长有人说话")
        add("product-promo", 0.2, "", "")
    if s["videos"] and s["screen"] and not speech:
        add("launch-film", 0.9, "a silent screen recording", "无声录屏")
    if not s["videos"] and not s["photos"]:
        if s["docs"]:
            add("concept-explainer", 1.4, f"{s['docs']} document(s), no footage", f"{s['docs']} 份文档，没有素材")
        else:
            add("concept-explainer", 0.6, "no footage: the visuals are drawn", "没有素材：画面靠绘制")
            add("ai-short", 0.3, "", "")
    for pid, v in _words(s["prompt"]).items():
        # her words: only templates the materials can make (a beat reel needs footage, a 口播 edit needs speech)
        if pid in ("beat-short", "travel-calm", "trip-vlog", "history-explainer", "documentary", "essay") and \
                not (s["videos"] or s["photos"]):
            continue
        if pid in ("th-refined", "lecture-shorts", "conversation-clips", "product-promo") and not speech and \
                s["videos"]:
            continue
        add(pid, v, "the request says so", "需求里这样写")
    return {k: (round(v[0], 2), v[1]) for k, v in sc.items()}


def _reason(pid, reasons, s, lang):
    p = P.get(pid)
    seen, bits = set(), []
    for r in reasons:
        t = r[lang]
        if t not in seen:
            seen.add(t)
            bits.append(t)
    head = P.label(pid, lang)
    if lang == "zh":
        return f"{head}：{'，'.join(bits[:4]) or '默认'} → {p['blurb']['zh']}"
    return f"{head}: {', '.join(bits[:4]) or 'the default'} → {p['blurb']['en']}"


def classify(s, fixed_recipe=None, judge=None, keep=None):
    """signals -> the template decision (module doc). ``fixed_recipe``: her explicit recipe (only its templates
    compete). ``keep``: a template she chose before (``by: her``): returned as is. ``judge(s, candidates)`` -> {pick,
    reason} or None: the AI for a close call."""
    if keep and keep in P.PRESETS:
        p = P.get(keep)
        return dict(template=keep, recipe=p["recipe"], params=dict(p["params"]), label=P.label(keep, "en"),
                    label_zh=P.label(keep, "zh"), by="her", confidence=1.0,
                    reason=dict(en=f"{P.label(keep, 'en')}: your choice", zh=f"{P.label(keep, 'zh')}：你选的"),
                    alternatives=[], signals=s)
    sc = scores(s)
    pool = {k: v for k, v in sc.items() if not fixed_recipe or P.get(k)["recipe"] == fixed_recipe}
    if not pool:                                   # a recipe with no template (polish, cover ...): no template
        return None
    ranked = sorted(pool.items(), key=lambda kv: -kv[1][0])
    top, (best, why) = ranked[0][0], ranked[0][1]
    second = ranked[1][1][0] if len(ranked) > 1 else 0.0
    margin = (best - second) / max(abs(best), 1e-6) if best > 0 else 0.0
    said = bool(_words(s["prompt"]).get(top))
    by = "her" if said else "rules"
    ai = None
    if not said and margin < AMBIGUOUS and judge and len(ranked) > 1:
        cands = [k for k, _ in ranked[:3]]
        try:
            ai = judge(s, cands)
        except Exception:  # noqa: BLE001  (no model / a bad reply: the rules' pick stands)
            ai = None
        if ai and ai.get("pick") in cands:
            top, by = ai["pick"], "ai"
            why = pool[top][1]
    p = P.get(top)
    alts = [dict(P.card(k, "en"), label_zh=P.label(k, "zh"), score=v[0]) for k, v in ranked if k != top][:3]
    reason = dict(en=_reason(top, why, s, "en"), zh=_reason(top, why, s, "zh"))
    if by == "ai" and ai.get("reason"):
        reason = dict(en=f"{P.label(top, 'en')}: {ai['reason']}", zh=f"{P.label(top, 'zh')}：{ai['reason']}")
    elif by == "rules" and margin < AMBIGUOUS and len(ranked) > 1:
        reason = dict(en=reason["en"] + f" (close call with {P.label(ranked[1][0], 'en')})",
                      zh=reason["zh"] + f"（和{P.label(ranked[1][0], 'zh')}很接近）")
    return dict(template=top, recipe=p["recipe"], params=dict(p["params"]), label=P.label(top, "en"),
                label_zh=P.label(top, "zh"), by=by, confidence=round(max(0.0, min(1.0, 0.5 + margin)), 2),
                reason=reason, alternatives=alts, signals=s)


def ai_judge(complete=None, timeout=60):
    """A ``judge`` for ``classify`` backed by the routed model (task ``planner``)."""
    def run(s, cands):
        if complete is None:
            from vstudio import llm
            fn = llm.complete
        else:
            fn = complete
        rows = [P.card(c, "en") for c in cands if c in P.PRESETS]
        sig = {k: v for k, v in s.items() if k != "prompt"}
        prompt = (f"Request: {s.get('prompt') or '(none)'}\nMaterials: {json.dumps(sig)}\nTemplates: "
                  f"{json.dumps(rows, ensure_ascii=False)}\n\nWhich template makes the best video from these materials "
                  'for this request? Reply {"pick": "<id>", "reason": "one short sentence"}.')
        r = fn("planner", "You are a film editor choosing how to cut a video. Restraint over gimmicks.", prompt,
               schema=True, max_tokens=400, timeout=timeout, cli_timeout=timeout, retries=0)
        if not isinstance(r, dict) or r.get("provider") == "none":
            return None
        js = r.get("json") or {}
        return dict(pick=js.get("pick"), reason=str(js.get("reason") or "")[:200])
    return run


def for_plan_project(p, analysis, prompt, intent=None, judge=None):
    """An intake plan's sub-project -> its template decision (None for a recipe without templates). Her explicit
    recipe (a phrase in the request, ``recipe=`` from the desk) keeps its recipe; the template inside it is chosen."""
    mats = set(p.get("materials") or [])
    sub = dict(analysis, files=[f for f in analysis.get("files") or [] if not mats or f.get("id") in mats or
                                (f.get("kind") == "text" and f.get("shape") == "telemetry")])
    s = signals(sub, prompt)
    d = classify(s, fixed_recipe=p["recipe"], judge=judge)
    if d is None:
        return None
    # a style she set in words wins over the template's (rules.parse_prompt: 卡点 -> fun, 舒缓 -> calm)
    if intent and intent.get("style") and p["recipe"] == "vlog":
        want = "beat-short" if intent["style"] == "fun" else d["template"] if d["template"] != "beat-short" \
            else "travel-calm"
        if want != d["template"]:
            d = classify(s, keep=want)
            d["by"] = "her"
    return d


def material_recipe(analysis, prompt=""):
    """The recipe the materials alone point to for footage / photos (intake's rule planner, nothing named):
    photo-story or vlog, decided by the same signals as the template."""
    d = classify(signals(analysis, prompt))
    if d and d["recipe"] in ("vlog", "photo-story"):
        return d["recipe"]
    s = signals(analysis, prompt)
    return "photo-story" if s["photos"] >= max(1, s["videos"]) else "vlog"
