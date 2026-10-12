"""launch-kit: the engine drafts ``launch.config.yaml`` from what she gave it (her recordings + her brief + her
request), so the kit never runs on the seeded example (Acme Notes, a CHANGELOG.md that is not there).

    draft_config(ctx, cp, path, template)    # the config checkpoint's drafter (vstudio.project.drafts.DRAFTERS)

Rules first, from her own words: the brief's shot table (take file -> on-screen line in English and 中文, the
scene length) becomes the features, in its order, each on its take; her recordings become ``capture.clips``;
the request sets the canvases ("16:9, 9:16 and 1:1"), the languages, the pace ("1.1×"), the length ("50-second"),
the transitions ("fast smooth animated transitions" -> push / zoom-through, ~10 frames), the opening ("no hook",
"open on Home" -> no title card), the built-in music mood ("tech") and the look ("dark", "teal"). A release
source is written only when one is really there (a CHANGELOG.md among her files). No shot table (or an
instruction to follow): the generic AI drafter writes the file from the template; its ``release.changelog`` is
dropped when that file is not in the project.
"""
import os
import re

import yaml

from vstudio.launch import config as LC
from vstudio.launch import features as FE

ASPECT_RE = re.compile(r"\b(16|9|1|4)\s*[:x×]\s*(9|16|1|5)\b")
PACE_RE = re.compile(r"(?<![\d.])(\d(?:\.\d{1,2})?)\s*(?:×|x\b|倍)", re.I)
SECONDS_RE = re.compile(r"(\d{2,3})\s*(?:-|\s)?(?:seconds?|secs?\b|s\b|秒)", re.I)
SITE_RE = re.compile(r"\b((?:https?://)?(?:[a-z0-9-]+\.)+(?:com|app|io|dev|ai|org|net|so|co)(?:/[\w./-]*)?)\b", re.I)
NAME_VER_RE = re.compile(r"\b((?:[A-Z][\w-]{1,30} ){0,2}[A-Z][\w-]{1,30})\s+v?(\d+\.\d+(?:\.\d+)?)\b")
# colour words in a brief -> an accent that reads on the dark / light preset (teal = the Reelfold app's accent)
COLORS = {"teal": ("#4FBFAE", "#0F7A6C"), "青": ("#4FBFAE", "#0F7A6C"), "blue": ("#5B9BF0", "#2F6F9F"),
          "蓝": ("#5B9BF0", "#2F6F9F"), "green": ("#5FBF7A", "#2E7D4F"), "绿": ("#5FBF7A", "#2E7D4F"),
          "purple": ("#A88BF0", "#6B4FB8"), "紫": ("#A88BF0", "#6B4FB8"), "orange": ("#F0A050", "#B8651F"),
          "橙": ("#F0A050", "#B8651F"), "amber": ("#E0A458", "#A86A1F"), "yellow": ("#E8C55A", "#9A7A12")}
PLATFORM_WORDS = (("x", r"\bx\b|twitter|推特"), ("linkedin", r"linkedin|领英"), ("youtube", r"youtube|油管"),
                  ("tiktok", r"tiktok"), ("instagram", r"instagram|\bins\b|reels"), ("xiaohongshu", r"小红书|xiaohongshu|rednote"),
                  ("bilibili", r"bilibili|b站|哔哩"), ("douyin", r"抖音|douyin"))


def _read(p, n=200_000):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read(n)
    except OSError:
        return ""


def _inputs(ctx):
    notes, clips, images = [], [], []
    for k, v in (ctx.inputs or {}).items():
        for p in (v if isinstance(v, list) else [v]):
            if not isinstance(p, str):
                continue
            ext = os.path.splitext(p)[1].lower()
            if ext in (".md", ".txt"):
                notes.append(p)
            elif ext in (".mp4", ".mov", ".m4v", ".webm"):
                clips.append(p)
            elif ext in (".png", ".jpg", ".jpeg") and k != "brand":
                images.append(p)
    return notes, sorted(clips, key=os.path.basename), sorted(images, key=os.path.basename)


def _rel(ctx, p):
    """A file she gave -> the path the config uses: inputs/<name> (prepare links it there), else absolute."""
    linked = os.path.join(ctx.item_dir, "inputs", os.path.basename(p))
    return f"inputs/{os.path.basename(p)}" if os.path.exists(linked) else os.path.abspath(p)


def request_settings(req, brief=""):
    """Her request (+ the brief for the look) -> the config keys it decides (only the ones it says)."""
    r = req or ""
    low = r.lower()
    both = (r + "\n" + (brief or "")).lower()
    out = {}
    asp = []
    for a, b in ASPECT_RE.findall(r):
        key = f"{a}:{b}"
        if key in LC.ASPECTS and key not in asp:
            asp.append(key)
    if asp:
        out["aspects"] = asp
    m = PACE_RE.search(r)
    if m and 0.5 <= float(m.group(1)) <= 3.0 and float(m.group(1)) != 1.0:
        out["pace"] = float(m.group(1))
    m = SECONDS_RE.search(r)
    if m and 10 <= int(m.group(1)) <= 180:
        out["seconds"] = int(m.group(1))
    if re.search(r"cross ?fade|dissolve|叠化|淡入淡出", low):
        out["transition"] = "crossfade"
    elif re.search(r"transition|转场", low):
        fast = re.search(r"fast|quick|snappy|快", low)
        out["transition"] = "mix" if re.search(r"smooth|animated|顺滑|动画|push|zoom|slide", low) or fast else "push"
        out["transition_seconds"] = 0.3 if fast else 0.45
    if re.search(r"no (?:clickbait )?hook|without a hook|open(?:s|ing)? on\b|start(?:s)? on\b|no intro|不要钩子|没有钩子|"
                 r"直接从|开场直接", low):
        out["title_card"] = False
    if re.search(r"no music|without music|不要音乐|不配乐", low):
        out["music"] = "none"
    else:
        from vstudio import music
        moods = [x for x in music.moods() if re.search(rf"\b{x}\b", low)]
        if moods:
            out["music"] = moods[0]
    wants_extra = re.search(r"clips? (?:per|for each) feature|feature clips|\bgif\b|readme|loop|每个功能|短片|动图", low)
    if re.search(r"promo|宣传片|launch video|demo video|发布视频|演示视频", low) and not wants_extra:
        out["make"] = ["demo"]
    if re.search(r"\bdark\b|深色|暗色|黑底|night", both):
        out["theme"] = "night"
    for word, (dark, light) in COLORS.items():
        if re.search(rf"\b{word}\b" if word.isascii() else word, both):
            out["accent"] = dark if out.get("theme") == "night" else light
            break
    plats = [p for p, rx in PLATFORM_WORDS if re.search(rx, low)]
    if plats:
        if "youtube" in plats and "9:16" in (out.get("aspects") or []):
            plats.insert(plats.index("youtube") + 1, "youtube-shorts")
        out["platforms"] = plats
    return out


def _product(req, brief, end):
    """Name, version, 中文 name, site, one-liner from the request / brief / its end-card line."""
    name = ver = None
    for text in ((brief or "").split("\n", 3)[:3] + [req or "", brief or ""]):
        m = NAME_VER_RE.search(text or "")
        if m:
            name, ver = m.group(1), m.group(2)
            break
    p = {"name": name or "", "version": ver and f"v{ver}"}
    end_en, end_zh = (end or {}).get("en") or "", (end or {}).get("zh") or ""
    sm = SITE_RE.search(end_en) or SITE_RE.search(brief or "")
    if sm:
        site = sm.group(1)
        p["site"] = site if site.startswith("http") else f"https://{site}"
    if name and end_zh:
        zm = re.search(r"([㐀-鿿]{1,8})\s*" + re.escape(name), end_zh)
        if zm:
            p["name_zh"] = zm.group(1)

    def strip(s):
        s = SITE_RE.sub("", s or "")
        if name:
            s = re.sub(rf"^\s*(?:[㐀-鿿]{{1,8}}\s*)?{re.escape(name)}\s*(?:[—–:-]+|——)?\s*", "", s)
        s = s.strip().strip("—–-").strip()
        return (s[:1].upper() + s[1:]) if s else ""
    one = {}
    if strip(end_en):
        one["en"] = strip(end_en)
    if strip(end_zh):
        one["zh"] = strip(end_zh)
    if not one and brief:
        m = re.search(r",\s+the ([^.\n]{8,120})\.", brief)
        if m:
            one["en"] = FE._plain(m.group(1))[:1].upper() + FE._plain(m.group(1))[1:]
    p["one_liner"] = one
    return p


def rules_config(ctx):
    """The config from her files + request, or None when her brief has no shot table to take the lines from."""
    notes, clips, images = _inputs(ctx)
    req = ctx.request()
    brief_path = next((n for n in notes if os.path.basename(n).lower() != "changelog.md"), None)
    brief = _read(brief_path) if brief_path else ""
    if not clips or not brief:
        return None
    got = FE.from_brief(brief, clips)
    feats_src = got["features"]
    langs = [x for x in (ctx.params.get("languages") or ["en"]) if x in LC.LANGS] or ["en"]
    if not feats_src or any(not f["caption"].get(lang) for f in feats_src for lang in langs):
        return None
    rs = request_settings(req, brief)
    prod = _product(req, brief, got.get("end"))
    if not prod["name"] or not prod["one_liner"]:
        return None
    by_name = {os.path.basename(c): c for c in clips}
    features = []
    for f in feats_src:
        ids = [LC._clip_id(s) for s in f["shots"] if s in by_name]
        if not ids:
            continue
        feat = {"id": f["id"], "shot": ids[0] if len(ids) == 1 else ids,
                "caption": {lang: f["caption"][lang] for lang in langs}}
        if f.get("seconds"):
            feat["seconds"] = f["seconds"]
        features.append(feat)
    cfg = {"out": "kit",
           "product": {k: v for k, v in prod.items() if v},
           "brand": {"theme": rs.get("theme", "editorial")},
           "languages": langs}
    if rs.get("accent"):
        cfg["brand"]["colors"] = {"accent": rs["accent"]}
    if rs.get("platforms"):
        cfg["platforms"] = rs["platforms"]
    cfg["capture"] = {"clips": [_rel(ctx, c) for c in clips]}
    if images:
        cfg["capture"]["images"] = [{"id": LC._clip_id(i), "file": _rel(ctx, i)} for i in images]
    cfg["features"] = features
    if rs.get("pace"):
        cfg["pace"] = rs["pace"]
    cfg["motion"] = {"transition": rs.get("transition", "crossfade"),
                     "seconds": rs.get("transition_seconds", 0.35), "camera": "push"}
    end_s = (got.get("end") or {}).get("seconds")
    demo = {"title_card": rs.get("title_card", True)}
    if end_s:
        demo["end_seconds"] = max(2.4, min(5.0, float(end_s)))
    total = sum(float(f.get("seconds") or 5.0) for f in features) + float(end_s or 3.2)
    want = rs.get("seconds") or total
    demo["max_seconds"] = round(max(want, total) + 4)
    demo["min_seconds"] = round(max(10, min(want, total) - 8))
    if rs.get("aspects"):
        demo["renders"] = [f"{lang}:{a}" for lang in langs for a in rs["aspects"]]
    cfg["demo"] = demo
    if rs.get("make"):
        cfg["make"] = rs["make"]
    if end_s is not None or got.get("end"):
        cfg["end_card"] = {"cta": dict(prod["one_liner"])}
    cfg["music"] = rs.get("music", "auto")
    cfg["gallery"] = {"shots": [f["id"] for f in features[:4]], "note": {"en": "Sample data", "zh": "示例数据"}}
    return cfg


HEADER = ("# launch.config.yaml - drafted by Reelfold from your clips, your brief and your request.\n"
          "# Every key: $VSTUDIO/workflows/launch-kit/examples/launch.config.example.yaml. Edit anything; "
          "Reelfold keeps your edits.\n")


def _review(cfg, lang):
    feats = cfg.get("features") or []
    n_r = len((cfg.get("demo") or {}).get("renders") or []) or None
    if lang == "zh":
        text = (f"按你的 brief 起草：{len(feats)} 个镜头，每个配一句屏幕文字"
                + (f"（{'、'.join(cfg['languages'])}）" if cfg.get("languages") else "")
                + (f"，{n_r} 个版本" if n_r else "") + "。")
    else:
        text = (f"Drafted from your brief: {len(feats)} shots, each with its on-screen line"
                + (f" ({', '.join(cfg['languages'])})" if cfg.get("languages") else "")
                + (f", {n_r} versions" if n_r else "") + ".")
    lines = [dict(code="draft.line", params=dict(label=LC.text(f.get("caption"), lang))) for f in feats[:14]]
    return dict(kind="outline", summary=dict(code="draft.generic", params=dict(text=text)), lines=lines)


def drop_missing_release(path):
    """A drafted config that names a release source that is not in the project (the template's CHANGELOG.md):
    drop it, so the kit drafts from the clips and the brief. -> True when the file changed."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(data, dict) or not isinstance(data.get("release"), dict):
        return False
    rel = data["release"]
    root = os.path.dirname(os.path.abspath(path))
    ch = rel.get("changelog")
    if ch and not os.path.isfile(os.path.join(root, os.path.expanduser(str(ch)))):
        rel.pop("changelog", None)
        rel.pop("version", None)
        if not rel:
            data.pop("release")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=110)
        return True
    return False


EXAMPLE_MARKS = ("acme.example", "Acme Notes")


def config_unfinished(path):
    """Still the seeded example (an older app's copy of it is not byte-identical to today's template): its made-up
    product (Acme Notes, acme.example) -> never an answer, the engine drafts hers."""
    if not os.path.isfile(path):
        return False
    text = _read(path, 400_000)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    if not isinstance(data, dict):
        return True
    p = data.get("product") if isinstance(data.get("product"), dict) else {}
    return str(p.get("name") or "") == EXAMPLE_MARKS[1] or EXAMPLE_MARKS[0] in str(p.get("site") or "")


def draft_config(ctx, cp, path, template=None, instruction=None, complete=None):
    """The config checkpoint's drafter: rules from her brief's shot table when it has one (and no instruction to
    follow), else the generic AI drafter (the template + the guide + her request); a release source that is not
    there is dropped either way. -> the draft record, or None (nothing drafted)."""
    from .. import drafts as DR
    cfg = None if instruction else rules_config(ctx)
    if cfg is not None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(HEADER)
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False, width=110)
        return dict(by="rules", instruction=None, review=_review(cfg, ctx.lang()))
    rec = DR.generic(ctx, cp, path, template=template, instruction=instruction, complete=complete)
    if rec:
        drop_missing_release(path)
    return rec
