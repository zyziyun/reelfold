"""Platform habits: how long a video SHOULD be on each platform, per content kind, and the other per-platform customs
(chapters, aspects, caption style / density, title and hook habits, hashtags, cover, posting times). The hard limits
(canvas, max length, loudness ...) stay in ``vstudio.platform``; these are the editable conventions.

    from vstudio import platform_habits as H
    H.habits("bilibili")                 # the merged profile: file <- persona <- Settings › Publishing
    H.band("youtube", "history")         # {min: 240, target: 480, max: 720, form: "long", chapters: True, ...}
    H.lengths(["youtube", "xiaohongshu"], "film", footage_max=300)   # {"youtube": 240, "xiaohongshu": 60}
    H.cuts(["youtube", "bilibili", "xiaohongshu"], {"youtube": 480, "bilibili": 480, "xiaohongshu": 90})
        # [{id: "long", platforms: [youtube, bilibili], length_s: 480, chapters: True},
        #  {id: "short", platforms: [xiaohongshu], length_s: 90, chapters: False}]
    H.set_limits("youtube", min_s=300, max_s=600)   # Settings › Publishing ($VSTUDIO_HOME/platforms.json)

Sources, lowest precedence first:
  1. ``references/platforms/<name>.md`` - YAML front matter per platform (the place to evolve a platform's habits;
     its prose is for people). A platform without a file falls back to its ``vstudio.platform`` sweet spot.
  2. persona ``platforms.<name>.lengths`` (``{kind: [min, target, max]}``), ``platforms.<name>.limits``
     (``{min_s, max_s}``: a clamp over every kind) and any other habit key (``chapters``, ``captions`` ...).
  3. Settings › Publishing: ``$VSTUDIO_HOME/platforms.json`` ``{name: {min_s, max_s}}`` (the desk writes it).
Every band is then clamped to the platform's hard limits (``vstudio.platform`` ``length.min`` / ``length.max``).

Kinds: history, essay, film, photos, reel, vlog, talking_head, course (aliases: explainer -> history,
photo-story -> photos, talkinghead -> talking_head, lesson -> course, beat -> reel ...). A beat-cut reel never goes
under ``REEL_MIN_S`` where the platform allows it.
"""
import copy
import json
import os
import re

from . import platform as P

KINDS = ("history", "essay", "film", "photos", "reel", "vlog", "talking_head", "course")
KIND_ALIASES = {"explainer": "history", "documentary": "history", "photo-story": "photos", "photostory": "photos",
                "photo": "photos", "talkinghead": "talking_head", "talking-head": "talking_head", "口播": "talking_head",
                "lesson": "course", "lesson-clips": "course", "longform-course": "course", "beat": "reel",
                "fun": "reel", "short": "reel", "music": "film", "calm": "film", "trip": "vlog"}
REEL_MIN_S = 20.0
MIN_S = 15.0                 # no cut shorter than this (a footage cap stops here)
SETTINGS = "platforms.json"
DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "references",
                   "platforms")
_CACHE = {}


def kind_of(kind):
    k = str(kind or "").strip().lower().replace(" ", "_")
    k = KIND_ALIASES.get(k, k)
    return k if k in KINDS else "film"


def path_of(name):
    return os.path.join(DIR, f"{P.canonical(name)}.md")


def _front(path):
    """YAML front matter of a platform file (cached by mtime) -> dict ({} when missing or broken)."""
    try:
        st = os.stat(path)
    except OSError:
        return {}
    hit = _CACHE.get(path)
    if hit and hit[0] == st.st_mtime:
        return copy.deepcopy(hit[1])
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            text = f.read()
        m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
        d = yaml.safe_load(m.group(1)) if m else {}
        d = d if isinstance(d, dict) else {}
    except (OSError, ValueError, ImportError, Exception):  # noqa: BLE001  (a broken file never breaks a plan)
        d = {}
    _CACHE[path] = (st.st_mtime, d)
    return copy.deepcopy(d)


def _home():
    return os.path.abspath(os.path.expanduser(os.environ.get("VSTUDIO_HOME") or "~/.config/vstudio"))


def settings_path():
    return os.path.join(_home(), SETTINGS)


def settings():
    """Settings › Publishing overrides: {name: {min_s, max_s}} ({} when none)."""
    try:
        with open(settings_path(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return {P.canonical(k): v for k, v in (d.get("platforms") or {}).items() if isinstance(v, dict)}


def set_limits(name, min_s=None, max_s=None, reset=False):
    """Her own length range for one platform (Settings › Publishing): every kind's band is clamped into it.
    ``reset``: back to the platform file's habits. -> the settings."""
    n = P.canonical(name)
    if n not in P.PLATFORMS:
        raise ValueError(f"unknown platform {name!r}")
    lim = dict(P.PLATFORMS[n].get("length") or {})
    hard_lo, hard_hi = float(lim.get("min") or 1), float(lim.get("max") or 43200)
    cur = settings()
    if reset:
        cur.pop(n, None)
    else:
        row = dict(cur.get(n) or {})
        for key, v in (("min_s", min_s), ("max_s", max_s)):
            if v is None:
                continue
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not hard_lo <= float(v) <= hard_hi:
                raise ValueError(f"{key}: {hard_lo:g}-{hard_hi:g} s for {n}")
            row[key] = int(round(float(v)))
        if row.get("min_s") and row.get("max_s") and row["min_s"] > row["max_s"]:
            raise ValueError("min_s is above max_s")
        cur[n] = row
    os.makedirs(_home(), exist_ok=True)
    tmp = settings_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dict(platforms=cur), f, ensure_ascii=False, indent=1)
    os.replace(tmp, settings_path())
    return settings()


def _fallback(name):
    """A platform with no file: its sweet spot for every kind (long-form when the sweet spot starts >= 3 min)."""
    L = (P.PLATFORMS.get(name) or {}).get("length") or {}
    lo, hi = (L.get("sweet") or [15, 90])[:2]
    band = [lo, round((lo + hi) / 2), hi]
    return dict(platform=name, form="long" if lo >= 180 else "short", lengths={k: list(band) for k in KINDS},
                chapters=dict(use=bool(((P.PLATFORMS.get(name) or {}).get("chapters") or {}).get("supported"))))


def habits(name, use_persona=True, use_settings=True):
    """The platform's habits (module doc), merged: file <- persona <- Settings › Publishing."""
    n = P.canonical(str(name).split(":")[0])
    d = _front(path_of(n)) or _fallback(n)
    d.setdefault("platform", n)
    d.setdefault("form", "short")
    d.setdefault("lengths", {})
    src = "file" if os.path.exists(path_of(n)) else "builtin"
    if use_persona:
        pp = P._persona_platform(n)
        own = {k: v for k, v in pp.items() if k in ("lengths", "limits", "form", "chapters", "captions", "title", "hook",
                                                      "hashtags", "cover", "posting", "aspects")}
        if own:
            d = P._merge(d, own)
            src = "persona"
    if use_settings:
        s = settings().get(n)
        if s:
            d["limits"] = dict(d.get("limits") or {}, **{k: v for k, v in s.items() if k in ("min_s", "max_s")})
            src = "settings"
    d["source"] = src
    return d


def form(name):
    """"long" (YouTube, B站, 知乎, Dailymotion: chapters, the full story) or "short" (everything else)."""
    return "long" if habits(name).get("form") == "long" else "short"


def band(name, kind, use_persona=True, use_settings=True):
    """{min, target, max, form, chapters, source} in seconds for one platform and content kind, clamped to her
    limits (Settings / persona) and the platform's hard limits; a reel never under REEL_MIN_S where allowed."""
    n = P.canonical(str(name).split(":")[0])
    h = habits(n, use_persona, use_settings)
    k = kind_of(kind)
    raw = (h.get("lengths") or {}).get(k) or (h.get("lengths") or {}).get("film") or _fallback(n)["lengths"][k]
    try:
        lo, tg, hi = (float(x) for x in list(raw)[:3])
    except (TypeError, ValueError):
        lo, tg, hi = (float(x) for x in _fallback(n)["lengths"][k])
    lim = h.get("limits") or {}
    if lim.get("min_s"):
        lo, tg, hi = max(lo, float(lim["min_s"])), max(tg, float(lim["min_s"])), max(hi, float(lim["min_s"]))
    if lim.get("max_s"):
        lo, tg, hi = min(lo, float(lim["max_s"])), min(tg, float(lim["max_s"])), min(hi, float(lim["max_s"]))
    hard = (P.PLATFORMS.get(n) or {}).get("length") or {}
    hlo, hhi = float(hard.get("min") or 1), float(hard.get("max") or 1e9)
    if k == "reel" and hhi >= REEL_MIN_S:
        lo, tg, hi = max(lo, REEL_MIN_S), max(tg, REEL_MIN_S), max(hi, REEL_MIN_S)
    lo, tg, hi = (min(hhi, max(hlo, x)) for x in (lo, tg, hi))
    lo, hi = min(lo, hi), max(lo, hi)
    tg = min(hi, max(lo, tg))
    ch = h.get("chapters") or {}
    chapters = bool(ch.get("use")) and tg >= float(ch.get("from_s") or 0)
    return dict(min=int(round(lo)), target=int(round(tg)), max=int(round(hi)), form=h.get("form") or "short",
                chapters=chapters, source=h.get("source"))


def lengths(platforms, kind, footage_max=None, asked=None, unify_forms=True):
    """Per-platform target seconds for one video: each platform's band target, capped by what the footage carries
    (``footage_max``: never past it, but a platform's own minimum - a reel's 20 s - is kept) and her own length
    (``asked``: the seconds her request named - her words win over the habits; only the hard limits clamp them).
    ``unify_forms``: the short platforms share one length when their bands allow it, and so do the long ones."""
    out = {}
    reel = kind_of(kind) == "reel"
    for p in platforms or []:
        n = P.canonical(str(p).split(":")[0])
        if n not in P.PLATFORMS:
            continue
        b = band(n, kind)
        hard = (P.PLATFORMS.get(n) or {}).get("length") or {}
        hlo, hhi = float(hard.get("min") or 1), float(hard.get("max") or 1e9)
        t = float(asked) if asked else float(b["target"])
        if footage_max and not asked:
            t = min(t, max(float(footage_max), float(b["min"]) if reel else 0.0))
        floor = REEL_MIN_S if reel and hhi >= REEL_MIN_S else MIN_S
        t = min(hhi, max(hlo, floor, t))
        out[p] = int(round(t / 5.0) * 5) if t >= 30 else int(round(t))
    return unify(out, kind) if unify_forms else out


def unify(lens, kind):
    """Platforms of one form whose bands overlap share one length (one render instead of three near-equal ones): the
    median of their lengths, clamped into the common part of their bands. Lengths she set herself are not passed
    here (the plan card keeps every platform's own number)."""
    out = dict(lens)
    by_form = {}
    for p in lens:
        by_form.setdefault(form(p), []).append(p)
    for ps in by_form.values():
        if len(ps) < 2:
            continue
        bs = [band(p, kind) for p in ps]
        lo, hi = max(b["min"] for b in bs), min(b["max"] for b in bs)
        if lo > hi:
            continue
        xs = sorted(lens[p] for p in ps)
        mid = xs[len(xs) // 2]
        t = min(hi, max(lo, mid))
        t = min(t, max(xs))                              # never longer than the longest (a footage cap holds)
        for p in ps:
            out[p] = int(t)
    return out


def cuts(platforms, lens, kind=None):
    """The renders one video needs: platforms grouped by their target length (equal lengths share one cut), longest
    first. -> [{id, platforms, length_s, form, chapters}]: ids "long" / "short" when there are two, "main" for one,
    "long-<s>" / "short-<s>" beyond that."""
    groups = {}
    for p in platforms or []:
        if p in (lens or {}):
            groups.setdefault(int(lens[p]), []).append(p)
    rows = []
    for secs in sorted(groups, reverse=True):
        ps = groups[secs]
        f = "long" if any(form(p) == "long" for p in ps) else "short"
        ch = any(band(p, kind or "film")["chapters"] for p in ps) and f == "long"
        rows.append(dict(platforms=ps, length_s=secs, form=f, chapters=ch))
    if len(rows) == 1:
        rows[0]["id"] = "main"
    elif len(rows) == 2:
        rows[0]["id"], rows[1]["id"] = "long", "short"
    else:
        for r in rows:
            r["id"] = f"{r['form']}-{r['length_s']}"
    return rows


def table(kinds=KINDS, platforms=None):
    """Every platform's bands for the docs / the desk: [{platform, label, form, chapters, source, limits, lengths}]."""
    out = []
    for n in platforms or P.ORDER:
        h = habits(n)
        out.append(dict(platform=n, label=h.get("label") or (P.PLATFORMS.get(n) or {}).get("label") or n,
                        form=h.get("form"), source=h.get("source"), limits=h.get("limits") or {},
                        hard=dict(min=(P.PLATFORMS[n].get("length") or {}).get("min"),
                                  max=(P.PLATFORMS[n].get("length") or {}).get("max")),
                        lengths={k: band(n, k) for k in kinds}))
    return out


def fmt_len(secs, lang="en"):
    """90 -> "90 s", 240 -> "4 min", 330 -> "5.5 min" (中文: 秒 / 分钟)."""
    s = float(secs)
    if s < 120:
        return f"{int(round(s))} 秒" if lang == "zh" else f"{int(round(s))} s"
    m = round(s / 60.0 * 2) / 2
    v = f"{m:g}"
    return f"{v} 分钟" if lang == "zh" else f"{v} min"


def cut_note(params):
    """One line for a drafter's prompt about which cut it writes (an item of vstudio.intake.plan.split_by_cut):
    the long cut tells the whole story (more shots / beats, chapters where its platforms use them), the short cut
    keeps the strongest moments with a hook at once. "" for a single-cut item."""
    params = params or {}
    cut = params.get("cut")
    if cut not in ("long", "short"):
        return ""
    plats = [str(p).split(":")[0] for p in params.get("platforms") or []]
    try:
        secs = int(float(params.get("length_s") or 0))
    except (TypeError, ValueError):
        secs = 0
    names = ", ".join(plats) or "its platforms"
    if cut == "long":
        ch = any(band(p, "history")["chapters"] for p in plats if p in P.PLATFORMS)
        return (f"This is the LONG cut for {names} (about {secs} s): tell the whole story - more beats, more shots, "
                f"fuller narration, unhurried holds" + ("; organise it in 3-6 chapters (SECTIONS / chapter names)"
                                                         if ch else "") + ". Fill the length with real material; never "
                "pad with repetition.")
    return (f"This is the SHORT cut for {names} (about {secs} s): only the strongest moments, the hook in the first "
            "2 seconds, no chapters, tight lines.")
