"""A clip that is a launch-kit film: ``items/<item>/kit/{demo,clips,readme}/*.mp4`` of a ``launch-kit`` project.

Such a clip is a finished motion-design promo (the product window on a backdrop, kinetic feature captions, a camera
that pushes onto the action, a music bed) with no speech. The clip editor's effects are made for recordings of a
person talking (studio sound, chapter rules, a title band, a restyled look) and stacked on the flattened film they
only make it worse. A request about how the film looks, moves or presents the features ("not premium enough, show
the features clearly", "slower", "a darker background", "focus on the calendar") is a change to the KIT:
``launch.config.yaml`` (pace, motion, backdrop, music, each feature's time on screen) and a re-render through the
kit (the recipe's render stage watches that file). Literal edits of the file itself (a cover, a trim, an export,
a cut of a selected range) stay with the editor.

    src = source(rec)                      # None, or {item, config, cut, lang, aspect, speech, ...}
    wants_kit(text, focus)                 # a request for the kit, not for the editor?
    plan(src, text) -> {patch, changes, summary}       # rules, deterministic (no model)
    apply(src, patch) -> {config, backup}               # writes launch.config.yaml (header comments kept)
"""
import copy
import os
import re
import time

import yaml

CUTS = ("demo", "clips", "readme")
MIN_SCENE = 4.5                # seconds a feature needs on screen to be read (caption up + the action played)
NAME_RE = re.compile(r"-(en|zh)-(16x9|9x16|1x1)\b")

# ------------------------------------------------------------------------------------------------ the request
_PREMIUM = (r"高端|大气|上档次|档次|高级|质感|精致|大片|电影感|好看点|更好看|不好看|效果不好|不够好|不太好|一般般|廉价|土|丑|"
            r"premium|high[- ]?end|classy|polish|cinematic|professional|elegant|sleek|looks? cheap|not good|"
            r"looks? bad|boring|bland|amateur")
_FEATURES = (r"功能.{0,8}(?:清晰|清楚|完整|完备|展示|看清|看不清|讲清)|(?:清晰|清楚|完整|完备)的?.{0,6}(?:展示|呈现)|"
             r"展示.{0,6}功能|每个功能|"
             r"show(?:case|s|ing)?\b.{0,20}\bfeatures?|features?\b.{0,20}\b(?:clear|clearly|readable|visible)|"
             r"see (?:what|the) (?:it|feature)")
_SLOWER = r"太快|慢一点|慢点|放慢|节奏慢|too fast|slower|slow (?:it )?down|more time|看不清"
_FASTER = r"太慢|快一点|快点|加快|节奏快|紧凑|拖沓|too slow|faster|speed (?:it )?up|tighter|snappier|drags?"
_PACE = r"节奏|pacing|\bpace\b|rhythm"
_CAMERA_STILL = r"不要(?:推|晃|动)|别(?:推|晃)|镜头(?:别|不要)动|固定镜头|静止|camera still|no (?:zoom|push|camera move)|static"
_CAMERA = r"运镜|推镜|推近|推进|镜头|特写|camera|zoom in|push in|close[- ]?up"
_TRANSITION = r"转场|transition"
_BACKDROP = r"(?<!音乐)(?<!背景音)背景(?!音)|底色|backdrop|background(?! music)"
_DARK = r"深色|暗|黑|夜|dark|deep|night"
_LIGHT = r"浅色|亮|白|light|bright|paper|white"
_MUSIC = r"音乐|配乐|bgm|\bmusic\b"
_NO_MUSIC = r"不要音乐|去掉音乐|不配乐|静音|no music|without music|remove (?:the )?music|mute"
# the film language: every scene the same template / the titles look bad -> the rhythm and the type of the film
_SAMENESS = (r"每一?(?:帧|个镜头|个画面|段|屏)都|都(?:是)?一样|一个样|千篇一律|单调|没(?:有)?变化|太死板|同一个?(?:模板|样式|套路)|"
             r"模板化|呈现方式|多样|"
             r"(?:every|each) (?:shot|scene|frame|slide)\b.{0,30}\b(?:same|identical|template)|same (?:template|layout)|"
             r"looks? the same|monoton|repetitive|more variety|vari(?:ety|ed)|mix it up|all the same")
_TYPE_UGLY = (r"(?:标题|字幕|文字|字体|大字|字)(?:太|好|很|有点|也)?(?:丑|难看|土|大|多|重|粗|不好看)|(?:丑|难看)的?(?:标题|字)|"
              r"(?:titles?|headlines?|captions?|type|typography|text|fonts?)\b.{0,20}\b(?:ugly|bad|big|heavy|loud|"
              r"too much|cheap|clunky)|(?:ugly|clunky|heavy) (?:titles?|headlines?|type|text|fonts?)|less text")
_EMPHASIS = r"突出|强调|重点|多给|多展示|多停|emphasi[sz]e|highlight|focus on|more (?:time )?on|spend more"
# what the editor does to the file as it is (never the kit): a cover, an export, trims / cuts by the second, a
# selected range, captions of the speech, undo
_EDITOR = (r"封面|cover|thumbnail|导出|export|版本|version|竖屏|横屏|方形|\d+\s*[:：]\s*\d+|剪掉|删掉|去掉开头|去掉结尾|"
           r"(?:开头|结尾|前|后|最后)\s*\d+(?:\.\d+)?\s*秒|first \d|last \d|trim|\bcut\b|撤销|undo|水印|watermark|"
           r"(?:\d+(?:\.\d+)?)\s*(?:倍速?|x\b|×)|lufs|音量|volume|louder|quieter")


def _has(rx, text):
    return bool(re.search(rx, text or "", re.I))


def wants_kit(text, focus=None):
    """Is this a change to the launch kit (the film's look, motion, pacing, backdrop, music, how the features are
    shown) rather than an edit of the file as it is? A selected range / effect in focus, or a literal editor request
    (cover, export, trim by the second, a speed factor), stays with the editor."""
    t = (text or "").strip()
    if not t or (focus and (focus.get("range") or focus.get("effect") or focus.get("cues"))):
        return False
    kit = any(_has(rx, t) for rx in (_PREMIUM, _FEATURES, _SLOWER, _FASTER, _PACE, _CAMERA, _TRANSITION, _BACKDROP,
                                     _MUSIC, _EMPHASIS, _SAMENESS, _TYPE_UGLY))
    if not kit:
        return False
    if _has(_EDITOR, t) and not any(_has(rx, t) for rx in (_PREMIUM, _FEATURES, _SAMENESS, _TYPE_UGLY)):
        return False
    return True


# ------------------------------------------------------------------------------------------------ the clip
def source(rec):
    """The launch kit behind an output record (``outputs.resolve``) -> {item, item_dir, config, cut, lang, aspect,
    speech} or None (not a launch-kit film)."""
    if not rec or rec.get("kind") != "project":
        return None
    owner = rec.get("owner") or ""
    try:
        with open(os.path.join(owner, "project.yaml"), encoding="utf-8") as f:
            proj = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not str(proj.get("recipe") or "").startswith("launch-kit"):
        return None
    f = os.path.abspath(rec.get("orig", {}).get("file") or rec.get("file") or "")
    rel = os.path.relpath(f, os.path.join(owner, "items")).replace(os.sep, "/").split("/")
    # <item>/kit/<cut>/<name>.mp4 (the kit's out folder may be named otherwise: the config says so)
    if len(rel) < 4 or rel[0] in ("..", "") or rel[2] not in CUTS:
        return None
    item_dir = os.path.join(owner, "items", rel[0])
    cfg_path = os.path.join(item_dir, "launch.config.yaml")
    if not os.path.isfile(cfg_path):
        return None
    try:
        with open(cfg_path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        raw = {}
    m = NAME_RE.search(os.path.basename(f))
    vo = (raw.get("voiceover") or {}).get("enabled") if isinstance(raw.get("voiceover"), dict) else False
    return dict(item=rel[0], item_dir=item_dir, config=cfg_path, cut=rel[2], file=f,
                lang=m.group(1) if m else None, aspect=m.group(2).replace("x", ":") if m else None,
                speech=bool(vo), raw=raw)


def context(src):
    """What the clip is, for the model of the clip chat (so it never treats a promo film as a talking head)."""
    raw = src.get("raw") or {}
    mo = raw.get("motion") or {}
    feats = [dict(id=f.get("id"), caption=f.get("caption"), seconds=f.get("seconds"))
             for f in raw.get("features") or [] if isinstance(f, dict)]
    return dict(kind="launch-kit film", cut=src["cut"], language=src.get("lang"), aspect=src.get("aspect"),
                speech=src["speech"],
                note=("A finished motion-design promo made by the launch kit (product window on a backdrop, kinetic "
                      "feature captions, camera pushes, a music bed)" + ("" if src["speech"] else ", with NO speech")
                      + ". Do not add talking-head treatments (studio sound, chapter rules, a title band, a new look, "
                      "a second music bed): the look, pacing, camera, backdrop, music and how each feature is shown "
                      "are changed in the launch kit (launch.config.yaml) and re-rendered there, not with these ops. "
                      "Here: only literal edits of this file (cover, trim, a selected cut, exports)."),
                kit=dict(pace=raw.get("pace"), motion=dict(transition=mo.get("transition"), seconds=mo.get("seconds"),
                                                           camera=mo.get("camera")),
                         backdrop=(raw.get("brand") or {}).get("backdrop") or "studio",
                         theme=(raw.get("brand") or {}).get("theme"), music=raw.get("music"), features=feats))


def refuse(src, op):
    """An editor op the model proposed that a launch-kit film must not get -> the reason (a message), or None: a
    voice treatment on a film with no voice, a second music bed over the kit's own."""
    if op.get("op") != "effect_add":
        return None
    eff = op.get("effect")
    if eff == "studio-sound" and not src.get("speech"):
        return _m("kit-no-voice", "Studio sound cleans a voice; this launch film has none.", "人声增强是给人声用的，这条发布成片没有人声。")
    music = (src.get("raw") or {}).get("music", "auto")
    if eff == "music-bed" and music not in (None, False, "none", "off"):
        return _m("kit-has-music", "The launch film already has its music bed (change it in the kit: say “change the "
                                   "music to calm”).", "这条发布成片已经有背景音乐了（在套件里换：说「音乐换成 calm」）。")
    return None


# ------------------------------------------------------------------------------------------------ the change
def _m(code, en, zh, **params):
    return dict(code=code, message=en, message_zh=zh, params=params)


def _caps(f):
    """A feature's on-screen line in every language it has (plain, no 【】 marks)."""
    c = f.get("caption")
    vals = list(c.values()) if isinstance(c, dict) else [c]
    return [re.sub(r"[【】]", "", str(v)).strip() for v in vals if v]


def _feature_named(feats, text):
    """The feature her words name: one of its id words ("calendar") or its whole on-screen line, in the request."""
    low = (text or "").lower()
    best = None
    for f in feats:
        keys = [re.sub(r"[.。!！?？]+$", "", x).lower() for x in _caps(f)]
        keys += [w for w in re.split(r"[-_\s]+", str(f.get("id") or "").lower()) if len(w) >= 4 and not w.isdigit()]
        for k in keys:
            if len(k) >= 2 and k in low and (best is None or len(k) > best[0]):
                best = (len(k), f)
    return best[1] if best else None


def plan(src, text):
    """Her request -> the kit change: {patch (keys of launch.config.yaml), changes [message], summary}. Rules only,
    so the same words always make the same change; what it cannot place returns no patch and says what the kit
    can change."""
    raw = copy.deepcopy(src.get("raw") or {})
    t = text or ""
    patch, changes = {}, []
    mo = dict(raw.get("motion") or {})
    brand = raw.get("brand") or {}
    pace = float(raw.get("pace") or 1.0)
    feats = [dict(f) for f in raw.get("features") or [] if isinstance(f, dict)]
    demo = raw.get("demo") or {}
    premium, clear = _has(_PREMIUM, t), _has(_FEATURES, t)

    def motion(**kw):
        for k, v in kw.items():
            if mo.get(k) != v:
                patch.setdefault("motion", {})[k] = v
                mo[k] = v

    # pacing: "slower" / "too fast" -> every recording at its real speed; "tighter" -> a little faster
    # (her pace stays unless she says so: "clearly" makes the scenes longer, not the recordings slower)
    slower = _has(_SLOWER, t) or (_has(_PACE, t) and not _has(_FASTER, t) and premium)
    faster = _has(_FASTER, t) and not slower
    if slower and pace > 1.0:
        patch["pace"] = 1.0
        changes.append(_m("kit-pace", f"Pace {pace:g}× -> 1×: each feature plays at its real speed.",
                          f"节奏从 {pace:g}× 调回 1×：每个功能按真实速度播放。", before=pace, after=1.0))
    elif faster and pace < 1.3:
        new = round(min(1.3, pace + 0.1), 2)
        patch["pace"] = new
        changes.append(_m("kit-pace", f"Pace {pace:g}× -> {new:g}×: a tighter cut.", f"节奏从 {pace:g}× 加快到 {new:g}×。",
                          before=pace, after=new))
    if clear and feats:
        # every feature at least MIN_SCENE s on screen, inside the film's length (the growth shrinks to fit)
        cap = float(demo.get("max_seconds") or 60) - float(demo.get("end_seconds") or 3.2)
        cur = {f["id"]: float(f.get("seconds") or MIN_SCENE) for f in feats}
        grow = {k: max(0.0, MIN_SCENE - v) for k, v in cur.items()}
        room = cap - sum(cur.values())
        k_ = 0.0 if room <= 0 else min(1.0, room / (sum(grow.values()) or 1.0))
        n = 0
        for f in feats:
            new = round(cur[f["id"]] + grow[f["id"]] * k_, 1)
            if f.get("seconds") is None or new > float(f["seconds"]) + 0.05:
                f["seconds"] = new
                n += 1
        if n:
            lo, hi = min(float(f["seconds"]) for f in feats), max(float(f["seconds"]) for f in feats)
            span = f"{lo:g}-{hi:g}" if hi > lo else f"{lo:g}"
            patch["features"] = [dict(id=f["id"], seconds=f["seconds"]) for f in feats]
            changes.append(_m("kit-feature-time", f"{n} features stay on screen longer ({span} s each), so every "
                                                  "action can be read.",
                              f"{n} 个功能在画面上停留更久（每个 {span} 秒），每个操作都看得清。", n=n, seconds=span))
    # emphasis on one feature
    if _has(_EMPHASIS, t):
        f = _feature_named(feats, t)
        if f:
            cur = float(f.get("seconds") or 4.5)
            f["seconds"] = round(min(9.0, cur + 1.5), 1)
            rows = {x["id"]: x for x in patch.get("features") or []}
            rows[f["id"]] = dict(id=f["id"], seconds=f["seconds"])
            patch["features"] = list(rows.values())
            cs = _caps(f) or [str(f["id"])]
            changes.append(_m("kit-feature-focus", f"“{cs[0]}” stays {f['seconds']:g} s on screen.",
                              f"「{cs[-1]}」在画面上停留 {f['seconds']:g} 秒。", feature=f["id"], seconds=f["seconds"]))
    # camera
    if _has(_CAMERA_STILL, t):
        if mo.get("camera", "push") != "still":
            motion(camera="still")
            changes.append(_m("kit-camera-still", "The camera stays still on each recording.", "镜头不再推近，固定在画面上。"))
    elif premium or clear or _has(_CAMERA, t):
        if mo.get("camera", "push") != "push":
            motion(camera="push")
            changes.append(_m("kit-camera-push", "The camera pushes in on where the action is.", "镜头推近到操作发生的位置。"))
    # transitions: premium = a calmer, longer hand-over; "faster" = shorter
    if premium or _has(_TRANSITION, t):
        sec = float(mo.get("seconds") or 0.35)
        if _has(r"cross ?fade|dissolve|叠化|淡", t) and mo.get("transition") != "crossfade":
            motion(transition="crossfade")
        new = round(max(0.2, sec - 0.1), 2) if faster else round(max(sec, 0.45), 2)
        if abs(new - sec) > 0.01:
            motion(seconds=new)
        if "motion" in patch and ("transition" in patch["motion"] or "seconds" in patch["motion"]):
            changes.append(_m("kit-transition", f"Transitions: {mo.get('transition') or 'crossfade'}, "
                                                f"{mo.get('seconds'):g} s hand-over.",
                              f"转场：{mo.get('transition') or 'crossfade'}，{mo.get('seconds'):g} 秒过渡。",
                              transition=mo.get("transition"), seconds=mo.get("seconds")))
    # the film language: "every shot looks the same" -> more variety (detail cuts, split screens, full-bleed UI, type
    # beats between sequences); "the titles are ugly" -> lighter, smaller type and less of it on screen
    same, ugly = _has(_SAMENESS, t), _has(_TYPE_UGLY, t)
    film = dict(raw.get("film") or {})
    typ = dict(raw.get("type") or {})
    if same and film.get("variety", "balanced") != "lively":
        patch.setdefault("film", {})["variety"] = "lively"
        changes.append(_m("kit-film-variety", "Every scene gets its own shot: full-bleed UI, close-ups on the action, "
                                              "split screens and short type beats, never the same layout twice in a "
                                              "row.",
                          "每个镜头换一种呈现：整屏界面、操作特写、左右分屏、段落之间一句大字，相邻镜头不重复。"))
    if same or ugly:
        cap = float(film.get("text", 0.4))
        new_cap = 0.3 if ugly else min(cap, 0.35)
        if cap > new_cap + 1e-6:
            patch.setdefault("film", {})["text"] = new_cap
            changes.append(_m("kit-film-text", f"Words on screen at most {new_cap:.0%} of the time: a type beat opens "
                                               "each section, the rest are small captions or none.",
                              f"文字最多占 {new_cap:.0%} 的时长：每段开头一句大字，其余是小字说明或不加字。",
                              share=new_cap))
        if film.get("captions") not in (None, "auto"):
            patch.setdefault("film", {})["captions"] = "auto"
    if ugly:
        w = int(typ.get("weight") or 560)
        sc = float(typ.get("scale") or 1.0)
        tp = {}
        if w > 520:
            tp["weight"] = 520
        if sc > 0.9:
            tp["scale"] = 0.9
        if tp:
            patch["type"] = tp
            changes.append(_m("kit-type", "Type set lighter and a little smaller (Inter / Noto Sans SC medium, tight "
                                          "tracking), fading in out of a soft blur; no headline box over the shots.",
                              "文字更轻、略小（Inter / 思源黑体 Medium，字距收紧），柔和淡入；画面上不再压大标题。"))
    # backdrop
    cur_bd = brand.get("backdrop") or "studio"
    dark_theme = str(brand.get("theme") or "") in ("night", "mono")
    bd = None
    if _has(_BACKDROP, t):
        bd = "deep" if _has(_DARK, t) else ("paper" if _has(r"paper|纸|flat|平", t) else
                                             "studio" if _has(_LIGHT, t) else ("deep" if dark_theme else "studio"))
    elif premium and dark_theme and not (same or ugly):
        bd = "deep"                                           # a night brand: the film on the dark teal-black stage
    if bd and bd != cur_bd:
        patch.setdefault("brand", {})["backdrop"] = bd
        words = dict(deep=("a deep dark backdrop with white type", "深色背景，白色文字"),
                     studio=("a bright studio backdrop", "明亮的工作室背景"), paper=("a flat paper backdrop", "纯色纸张背景"))
        changes.append(_m("kit-backdrop", f"The film sits on {words[bd][0]}.", f"画面改为{words[bd][1]}。", backdrop=bd))
    # music
    if _has(_NO_MUSIC, t):
        if raw.get("music") not in (None, "none", False):
            patch["music"] = "none"
            changes.append(_m("kit-music-off", "No music bed.", "去掉背景音乐。"))
    elif _has(_MUSIC, t):
        from vstudio import music as MU
        mood = next((x for x in MU.moods() if re.search(rf"\b{x}\b", t, re.I)), None) or MU.mood_of(t)
        if mood and mood != raw.get("music"):
            patch["music"] = mood
            changes.append(_m("kit-music", f"Music bed: {mood}.", f"背景音乐换成 {mood}。", mood=mood))
    summary = None
    if changes:
        summary = "Changed in the launch kit, then the films are rendered again: " + " ".join(c["message"] for c in changes)
    return dict(patch=patch, changes=changes, summary=summary)


def merged(raw, patch):
    """``raw`` (the YAML as written) with ``patch`` applied: dicts merged, ``features`` matched by id."""
    out = copy.deepcopy(raw)
    for k, v in (patch or {}).items():
        if k == "features":
            rows = {r["id"]: r for r in v}
            out["features"] = [dict(f, **{kk: vv for kk, vv in rows.get(f.get("id"), {}).items() if kk != "id"})
                               if isinstance(f, dict) else f for f in out.get("features") or []]
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = dict(out[k], **v)
        else:
            out[k] = v
    return out


def apply(src, patch):
    """Write the kit change into launch.config.yaml (the file's leading comment lines kept; the previous file kept
    as ``work/launch.config.before-<time>.yaml``) after checking it like the kit does -> {config, backup}."""
    from vstudio.launch import config as LC
    path = src["config"]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    raw = yaml.safe_load(text) or {}
    new = merged(raw, patch)
    cfg = LC._merge(LC.DEFAULTS, new)
    errs = [e for e in LC.validate(dict(cfg, out=os.path.join(src["item_dir"], "kit")), check_files=False)]
    if errs:
        raise ValueError("launch.config.yaml: " + "; ".join(errs[:5]))
    head = []
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            head.append(line)
        else:
            break
    work = os.path.join(src["item_dir"], "work")
    os.makedirs(work, exist_ok=True)
    backup = os.path.join(work, f"launch.config.before-{time.strftime('%Y%m%d-%H%M%S')}.yaml")
    with open(backup, "w", encoding="utf-8") as f:
        f.write(text)
    body = yaml.safe_dump(new, allow_unicode=True, sort_keys=False, width=120)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(("\n".join(head) + "\n" if head else "") + body)
    os.replace(tmp, path)
    return dict(config=path, backup=backup)
