"""Storyboard: config + shots -> a timed plan per cut (demo / loop / one feature clip), language and canvas.

    from vstudio.launch import story as S
    plan = S.plan(cfg, shots, "demo", "en", "16:9")      # {cut, lang, aspect, W, H, duration, layout, scenes, ...}
    S.plan(cfg, shots, "clip", "zh", "9:16", feature="plan")
    S.text_share(plan)                                   # share of the runtime with text on screen (<= film.text)

Pure functions (no rendering), so the rhythm, the timing and the camera are unit-tested.

The film language is a rhythm of different shots, like a product film (not one template per feature). Every scene
has a ``layout``:
  full     the UI fills the frame (no window chrome, no text); the camera glides / pushes onto the action
  macro    a detail shot, 2.5-4x on one UI element (where the screen changes), a slow drift; it continues the take
           of the scene before it, cut in on the beat
  split    two moments side by side (16:9) or stacked (9:16, 1:1): a feature's two shots, or two features
  float    the window floats on a clean light field, a small lower-third caption under it
  type     kinetic type only: one short line set large on a soft gradient field, between shot sequences
  chapter  a chapter card: the opening (product name + version) and features that carry ``chapter:``
  end      logo, call to action, site
  brand    (arc: launch) the name card: the positioning line as a kicker, the wordmark slammed in letter by letter,
           badges (free / open source / MIT / Mac) snapping in under it
  reel     (arc: launch) a montage: one window, a hard cut on every beat through a moment of each feature, a filmstrip
           of them running under a fixed playhead (the promise line above it)
  waterfall (a block) hundreds of real video thumbnails pour down the frame and land as the tiles of the wordmark,
           which then resolves into the solid name in heavy type (the tagline under it)
  lift     (a block) the platforms' marks rise from below and lift three heavy words ("Create · Edit · Publish" /
           "做 · 剪 · 发") into place, the promise line under them
  hook     (a block) one heavy line slammed in (a short's opening line)
``rhythm`` picks them per film: features are grouped into short sequences; a sequence opens on a type beat (its first
feature's line), the lead feature gets an establishing shot and a detail cut, the rest rotate through float / split /
full. No two adjacent scenes share a layout, and text is on screen for at most ``film.text`` (0.4) of the runtime:
lower thirds, then type beats are dropped (from the end) until it is.

``film.arc: launch`` tells the positioning as a story (learnt from launch films such as OpenFilm's): a cold open on
the product, the brand card, a fast reel of everything it does (cuts ~1 beat), then the chapters (``chapter:`` on a
feature; a chapter's ``chips`` fan out around its title, e.g. every platform), slower single takes inside them, and
an end card with the badges. ``plain`` (default) is the film without the brand card and the reel.

Consecutive scenes overlap by ``XF`` seconds (the transition); with a music bed every transition is centred on a beat
(beat_sync). A loop ends on a crossfade back into frame 0.
"""
from . import config as C
from . import timing as TM

XF = 0.35                     # scene overlap (the transition)
LEAD = 0.55                   # the camera starts moving this long before the action it frames
HOLD = 1.5                    # minimum time the camera stays on an action
MERGE = 0.6                   # actions closer than this share one camera move
LT_IN, LT_HOLD = 0.3, 2.6     # a lower third arrives this long after its scene lands and stays up this long
FOOTAGE = ("full", "macro", "split", "float")
CARDS = ("chapter", "type", "end", "brand", "waterfall", "lift", "hook")
TITLES = ("type", "chapter", "brand", "waterfall", "lift", "hook")     # a card footage zooms out of
REEL = "reel"
ARCS = ("plain", "launch")
VARIETY = ("calm", "balanced", "lively")
CAPTIONS = ("auto", "type", "lower", "none")

# canvas geometry (px). ``text`` = the box every word stays inside: the intersection of the safe boxes of every
# platform the canvas is posted to, clear of their button columns (config.CANVAS_PLATFORMS; asserted in tests).
# The footage may run under platform UI. ``float`` = the floating window (lower third under it), ``split`` = the two
# panes, ``zoom`` = the push range per layout (x the cover fit of the box), ``type_px`` = type beat size range.
LAYOUTS = {
    "16:9": dict(text=(96, 64, 1824, 984), full=(0, 0, 1920, 1080), float=(160, 56, 1600, 840),
                 split=((96, 110, 846, 790), (978, 110, 846, 790)), labels="below", lt_px=38, lt_lines=1, label_px=30,
                 type_px=(96, 64), type_lines=2, type_w=1400, chapter_px=150, eyebrow_px=24, oneliner_px=44,
                 radius=18, zooms=dict(full=(1.1, 1.45), float=(1.5, 2.4), split=(1.05, 1.6)),
                 win=(160, 56, 1600, 840), zoom=(1.5, 2.4), base_zoom=1.0, punch=1.9,
                 reel=dict(view=(400, 150, 1120, 700), strip=(880, 92), title_y=78, title_px=34),
                 kicker_px=36, badge_px=30, chip_px=32),
    "1:1": dict(text=(84, 84, 996, 984), full=(0, 0, 1080, 1080), float=(60, 56, 960, 780),
                split=((40, 140, 1000, 410), (40, 604, 1000, 410)), labels="above", lt_px=36, lt_lines=2, label_px=28,
                type_px=(80, 54), type_lines=3, type_w=860, chapter_px=124, eyebrow_px=22, oneliner_px=40,
                radius=16, zooms=dict(full=(1.05, 1.4), float=(1.5, 2.6), split=(1.0, 1.5)),
                win=(60, 56, 960, 780), zoom=(1.5, 2.6), base_zoom=1.0, punch=2.0,
                reel=dict(view=(140, 200, 800, 500), strip=(750, 84), title_y=116, title_px=30),
                kicker_px=32, badge_px=26, chip_px=30),
    "9:16": dict(text=(96, 300, 900, 1420), full=(0, 0, 1080, 1920), float=(40, 360, 1000, 880),
                 split=((40, 356, 1000, 520), (40, 962, 1000, 520)), labels="above", lt_px=44, lt_lines=2, label_px=32,
                 type_px=(92, 60), type_lines=3, type_w=800, chapter_px=140, eyebrow_px=26, oneliner_px=46,
                 radius=22, zooms=dict(full=(1.0, 1.3), float=(1.5, 2.6), split=(1.0, 1.5)),
                 win=(40, 360, 1000, 880), zoom=(1.5, 2.6), base_zoom=1.0, punch=2.0,
                 reel=dict(view=(40, 560, 1000, 625), strip=(1230, 112), title_y=420, title_px=40),
                 kicker_px=40, badge_px=34, chip_px=38),
}
# screen time (s, before the overlap) and its floor per layout
SECONDS = dict(full=3.0, macro=2.2, split=3.8, float=3.6, chapter=2.2, type=2.0, end=3.2, brand=3.0, waterfall=4.2,
               lift=3.2, hook=1.9)
FLOOR = dict(full=2.0, macro=1.6, split=3.0, float=3.0, chapter=1.8, type=1.5, end=2.4, brand=2.4, reel=2.0,
             waterfall=3.6, lift=2.6, hook=1.5)
WATERFALL_TEXT = 2.3          # the wordmark resolves (words on screen) this long into a waterfall block
LIFT_WORDS = {"en": ["Create", "Edit", "Publish"], "zh": ["做", "剪", "发"]}
LIFT_PLATFORMS = ["youtube", "tiktok", "instagram", "x", "linkedin", "xiaohongshu", "douyin", "bilibili",
                  "wechat-channels"]
REEL_MAX = 7                  # moments in the reel
REEL_CUT = 0.75               # about this long per moment (s), rounded to whole beats of the music bed
ROTATION = {"calm": ("float", "full"), "balanced": ("float", "split", "full"), "lively": ("split", "full", "float")}
PHRASE = {"calm": (3,), "balanced": (3, 2), "lively": (2,)}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def shot_for(feat, shots):
    sid = feat.get("shot") or feat["id"]
    if sid not in shots:
        raise C.ConfigError(f"feature '{feat['id']}': no shot '{sid}' (have: {', '.join(sorted(shots)) or 'none'}); "
                            "run the capture step or add capture.images")
    return shots[sid]


def media_window(feat, shot):
    """(in, out) seconds of the shot this feature plays (feature.trim [a, b], default the whole shot)."""
    a, b = (feat.get("trim") or [0, shot.get("duration") or 6.0])[:2]
    b = min(float(b), float(shot.get("duration") or b))
    if b - float(a) < 1.0:
        raise C.ConfigError(f"feature '{feat['id']}': trim {a}-{b} is shorter than 1 s")
    return float(a), b


def film_opts(cfg):
    f = dict(variety="balanced", text=0.4, captions="auto", arc="plain", blocks=None, cold_open=True)
    f.update({k: v for k, v in (cfg.get("film") or {}).items() if v is not None})
    return f


# ------------------------------------------------------------------------------------------------ camera
def _fit(win, shot):
    """Cover-fit scale of the shot (its pixel size) into the window."""
    _, _, W, H = win
    sw, sh = float(shot.get("w") or W), float(shot.get("h") or H)
    return max(W / sw, H / sh), sw, sh


def cam_pose(win, shot, cx, cy, zoom):
    """Window-local GSAP transform {x, y, scale} (transform-origin 0 0) that puts the normalised shot point
    (cx, cy) at the window centre at ``zoom`` x the cover fit, clamped so the shot always covers the window."""
    _, _, W, H = win
    fit, sw, sh = _fit(win, shot)
    s = fit * max(1.0, zoom)
    x = clamp(W / 2 - cx * sw * s, W - sw * s, 0.0)
    y = clamp(H / 2 - cy * sh * s, H - sh * s, 0.0)
    return dict(x=round(x, 1), y=round(y, 1), scale=round(s, 5))


def focus_events(shot, t0, t1, tmap=None):
    """The shot's focus boxes inside [t0, t1] (media seconds) -> [(scene_t, cx, cy, box_w, box_h)], merged when
    closer than MERGE. tmap: media second -> scene second (default: t - t0)."""
    tmap = tmap or (lambda m: m - t0)
    ev = []
    for f in sorted(shot.get("focus") or [], key=lambda f: f["t"]):
        if not (t0 <= f["t"] <= t1):
            continue
        t = tmap(f["t"])
        cx, cy = f["x"] + f.get("w", 0) / 2, f["y"] + f.get("h", 0) / 2
        if ev and t - ev[-1][0] < MERGE:
            continue
        ev.append((t, cx, cy, f.get("w", 0.1), f.get("h", 0.1)))
    return ev


def camera(layout, shot, t0, t1, dur, tmap=None):
    """Keyframes [{t, x, y, scale, d, ease}] for a still camera with punch-ins (camera: still / captured shots):
    open framed on the whole shot (or, on a narrow window, the first action), punch in on each action, pull back
    when the next one is far off."""
    win = layout["win"]
    z0, punch = layout["base_zoom"], layout["punch"]
    ev = focus_events(shot, t0, t1, tmap)
    fit, sw, sh = _fit(win, shot)
    narrow = (win[2] / win[3]) < (sw / sh) * 0.8          # the window shows a crop: follow the action
    first = (ev[0][1], ev[0][2]) if ev and narrow else (0.5, 0.5)
    keys = [dict(t=0.0, d=0.0, ease="none", **cam_pose(win, shot, *first, z0))]
    for i, (t, cx, cy, bw, bh) in enumerate(ev):
        # do not zoom past the point where the acted-on element fills ~60 % of the window
        zmax = max(1.0, min(2.6, 0.6 / max(bw * sw * fit / win[2], bh * sh * fit / win[3], 1e-3)))
        z = clamp(z0 * punch, 1.0, max(z0, zmax))
        start = max(keys[-1]["t"] + keys[-1]["d"], t - LEAD)
        if start >= dur - 0.4:
            break
        keys.append(dict(t=round(start, 3), d=round(min(LEAD + 0.15, dur - start), 3), ease="power2.inOut",
                         **cam_pose(win, shot, cx, cy, z)))
        nxt = ev[i + 1][0] if i + 1 < len(ev) else dur
        if nxt - t > HOLD + LEAD + 0.9 and t + HOLD < dur - 1.0:
            back = (cx, cy) if narrow else (0.5, 0.5)
            keys.append(dict(t=round(t + HOLD, 3), d=0.7, ease="power2.inOut", **cam_pose(win, shot, *back, z0)))
    return keys


def push_camera(layout, shot, t0, t1, dur, tmap=None):
    """The launch-film camera for a scene from a recording: an establishing frame of the window (biased toward the
    action), a fast eased push (``layout["zoom"]`` x the cover fit) onto where the screen changes, a calm follow when
    the action moves on, and a slow creep so the frame never sits dead. Keyframes never overlap (a smooth path, no
    jitter) and every pose keeps the shot covering the window."""
    tmap = tmap or (lambda m: m - t0)
    win = layout["win"]
    zlo, zhi = layout.get("zoom") or (1.4, 2.4)
    fit, sw, sh = _fit(win, shot)
    narrow = (win[2] / win[3]) < (sw / sh) * 0.8
    vis_w, vis_h = win[2] / (sw * fit), win[3] / (sh * fit)          # the part of the shot the window shows at 1x
    ev = []
    for f in sorted(shot.get("focus") or [], key=lambda f: f["t"]):
        if not (t0 - 1.5 <= f["t"] <= t1):
            continue
        bw, bh = max(f.get("w", 0), 0.26), max(f.get("h", 0), 0.2)    # never zoom onto a sliver (a progress line)
        z = clamp(0.82 / max(bw / vis_w, bh / vis_h, 1e-3), zlo, zhi)
        ev.append((max(0.0, tmap(max(f["t"], t0))), f["x"] + f.get("w", 0) / 2, f["y"] + f.get("h", 0) / 2, z))
    if not ev:
        ev = [(0.0, 0.5, 0.45, zlo)]
    _, cx, cy, z1 = ev[0]
    z1 = max(z1, min(zhi, 1.12))                                       # the push always goes in
    est = (0.5 + (cx - 0.5) * (0.8 if narrow else 0.35), 0.5 + (cy - 0.5) * 0.35)
    keys = [dict(t=0.0, d=0.0, ease="none", **cam_pose(win, shot, *est, 1.04))]
    push_d = round(min(1.05, max(0.6, dur * 0.3)), 3)
    keys.append(dict(t=0.12, d=push_d, ease="power3.inOut", **cam_pose(win, shot, cx, cy, z1)))
    cur = (cx, cy, z1)
    end = 0.12 + push_d
    moves = 0
    for t, ex, ey, ez in ev[1:]:
        if moves >= 2 or t > dur - 1.1:
            break
        if t < end + 0.35:
            continue
        # only move when the action leaves the middle of what is on screen
        if abs(ex - cur[0]) < 0.22 * vis_w / cur[2] and abs(ey - cur[1]) < 0.22 * vis_h / cur[2]:
            continue
        z = clamp((cur[2] + ez) / 2, zlo, zhi)
        start = round(max(end + 0.05, t - 0.45), 3)
        d = round(min(0.9, dur - start - 0.2), 3)
        if d < 0.45:
            break
        keys.append(dict(t=start, d=d, ease="power2.inOut", **cam_pose(win, shot, ex, ey, z)))
        cur, end, moves = (ex, ey, z), start + d, moves + 1
    if dur - end > 0.8:                                                # a slow creep in: the frame keeps breathing
        keys.append(dict(t=round(end, 3), d=round(dur - end, 3), ease="sine.out",
                         **cam_pose(win, shot, cur[0], cur[1], min(zhi * 1.05, cur[2] * 1.06))))
    return keys


MACRO = (2.5, 4.0)            # a detail shot: this many times the whole UI (contain fit of the shot in the frame)


def macro_target(shot, t0, t1):
    """The one UI element a detail shot frames -> (cx, cy, w, h): the smallest place where the screen changes inside
    [t0, t1] (never a sliver: at least 9 % x 7 % of the shot), else the middle of the UI."""
    best = None
    for f in sorted(shot.get("focus") or [], key=lambda f: f["t"]):
        if not (t0 - 1.0 <= f["t"] <= t1):
            continue
        w, h = max(f.get("w", 0), 0.09), max(f.get("h", 0), 0.07)
        area = w * h
        if area > 0.36:                                   # a page switch: not a detail
            continue
        if best is None or area < best[0] - 1e-6:
            best = (area, f["x"] + f.get("w", 0) / 2, f["y"] + f.get("h", 0) / 2, w, h)
    return best[1:] if best else (0.5, 0.42, 0.3, 0.2)


def macro_camera(win, shot, t0, t1, dur, aspect=None):
    """A detail shot: ``MACRO`` (2.5-4x) the whole UI on one element, framed so it fills ~60 % of the frame, with a
    slow drift in (no jump cut inside the shot). On a vertical canvas the full-bleed frame is already a crop: the
    detail goes at least 1.35x past it."""
    _, _, W, H = win
    fit, sw, sh = _fit(win, shot)
    contain = min(W / sw, H / sh)
    cx, cy, bw, bh = macro_target(shot, t0, t1)
    s = min(0.6 * W / (bw * sw), 0.6 * H / (bh * sh))
    s = clamp(s, contain * MACRO[0], contain * MACRO[1])
    s = max(s, fit * (1.35 if H > W else 1.08))
    z = s / fit
    a = dict(t=0.0, d=0.0, ease="none", **cam_pose(win, shot, cx - 0.012, cy + 0.006, z * 0.95))
    b = dict(t=0.0, d=round(dur, 3), ease="sine.inOut", **cam_pose(win, shot, cx, cy, z * 1.03))
    return [a, b]


# ------------------------------------------------------------------------------------------------ plans
def shot_ids(feat):
    """A feature's shots in order: ``shot`` is one id or a list (a split scene: both moments side by side)."""
    sid = feat.get("shot") or feat["id"]
    return [str(x) for x in sid] if isinstance(sid, list) else [sid]


def xf_of(cfg):
    return float((cfg.get("motion") or {}).get("seconds", XF))


def _unit(cfg, fid, lang):
    f = C.feature(cfg, fid)
    cap = f.get("caption")
    return dict(id=fid, shots=shot_ids(f), caption=C.text(cap, lang),
                all_captions=[C.plain(str(v)) for v in (cap.values() if isinstance(cap, dict) else [cap]) if v], kicker=C.text(f.get("kicker"), lang),
                seconds=float(f["seconds"]) if f.get("seconds") else None, chapter=C.text(f.get("chapter"), lang),
                layout=f.get("layout") if f.get("layout") in FOOTAGE else None, chips=chips(cfg, f.get("chips"), lang),
                vo=C.text(f.get("vo"), lang) if (cfg.get("voiceover") or {}).get("enabled") else "")


def chips(cfg, v, lang):
    """A chapter's chips -> [str]: a list (per language or not), or ``platforms`` = the config's platforms by their
    names (international first; the Chinese name on a Chinese film)."""
    if v == "platforms":
        from vstudio import platform as P
        out = []
        for name in P.ordered([P.canonical(x.split(":")[0]) for x in cfg.get("platforms") or []]):
            lab = P.PLATFORMS.get(name, {}).get("label") or name
            lab = lab.split(" (")[0]
            if any("\u4e00" <= c <= "\u9fff" for c in lab) and " " in lab:   # "小红书 RedNote"
                zh, en = lab.split(" ", 1)
                lab = zh if lang == "zh" else en
            if lab not in out:
                out.append(lab)
        return out
    return C.texts(v, lang)


def _words(text, lang):
    t = C.plain(text)
    return len(t.replace(" ", "")) / 2.6 if lang == "zh" else len(t.split())


def _type_seconds(text, lang):
    return round(clamp(1.3 + 0.12 * _words(text, lang), 1.7, 2.8), 2)


def reel_slot(grid):
    """Seconds per moment of the reel: whole beats of the bed (about REEL_CUT), else REEL_CUT."""
    if not grid:
        return REEL_CUT
    return round(grid[0] * max(1, round(REEL_CUT / grid[0])), 3)


def reel_units(units, n=REEL_MAX):
    """The features the reel shows: all of them, or ``n`` spread evenly over the film."""
    if len(units) <= n:
        return list(units)
    return [units[round(i * (len(units) - 1) / (n - 1))] for i in range(n)]


def rhythm(cfg, units, lang, cut, drop=frozenset(), opening=True, slot=REEL_CUT):
    """The film's shot list -> [scene skeleton {kind, layout, dur, min, text, ...}] (no media yet).
    ``drop``: text the planner took out to stay under film.text: ("lower", id) / ("type", id) / ("reel", "reel").
    ``slot``: seconds per moment of the reel (arc: launch)."""
    fo = film_opts(cfg)
    caps, variety = fo["captions"], fo["variety"] if fo["variety"] in VARIETY else "balanced"
    xf = xf_of(cfg)
    product = cfg["product"]
    out = []

    def add(**sc):
        sc.setdefault("text", "")
        sc["dur"] = round(sc.pop("screen") + xf, 3)
        sc["min"] = round(FLOOR[sc["layout"]] + xf, 3)
        out.append(sc)

    def prev():
        return out[-1]["layout"] if out else None

    def feat(layout, us, screen, text="", panes=None, labels=None):
        add(kind="feature", layout=layout, id=us[0]["id"], units=[u["id"] for u in us], screen=screen, text=text,
            labels=[x for x in labels] if labels and any(labels) else [],
            caption=us[0]["caption"], kicker=us[0]["kicker"], vo=us[0]["vo"],
            panes=panes or [dict(fid=u["id"], sid=u["shots"][0], k=0) for u in us])

    def lower_ok(u):
        return caps in ("auto", "lower") and ("lower", u["id"]) not in drop and bool(u["caption"])

    def type_ok(u):
        return caps in ("auto", "type") and ("type", u["id"]) not in drop and bool(u["caption"])

    def T(u, default=4.5):
        return u["seconds"] or default

    units = list(units)
    if cut == "loop":
        for k, u in enumerate(units):
            lay = ("float", "full", "macro")[k % 3]
            feat(lay, [u], T(u, 5.0), text=u["caption"] if lay == "float" and lower_ok(u) else "")
        return out
    if cut == "clip":
        u = dict(units[0], seconds=max(units[0]["seconds"] or 0, 8.0))   # a clip lets its one feature breathe
        if type_ok(u):
            add(kind="type", layout="type", id=u["id"], text=u["caption"], screen=_type_seconds(u["caption"], lang))
        if len(u["shots"]) > 1:
            feat("split", [u], T(u, 6.0), panes=[dict(fid=u["id"], sid=s, k=k) for k, s in enumerate(u["shots"][:2])])
            feat("full", [u], 3.0, panes=[dict(fid=u["id"], sid=u["shots"][-1], k=len(u["shots"]) - 1)])
        else:
            est = "full" if type_ok(u) or not lower_ok(u) else "float"
            feat(est, [u], T(u, 6.0) * 0.6, text=u["caption"] if est == "float" else "")
            feat("macro", [u], max(2.4, T(u, 6.0) * 0.4), panes=[dict(fid=u["id"], sid=u["shots"][0], k=0, cont=True)])
        add(kind="end", layout="end", screen=float(cfg["clips"]["end_seconds"]) - xf)
        return out

    # demo
    d = cfg["demo"]
    arc = fo.get("arc") == "launch"
    name = product["name"]
    version = str(product.get("version") or "")
    opener = dict(kind="chapter", layout="chapter", id="opening", title=name,
                  eyebrow=C.text(product.get("name_zh"), lang) if lang == "zh" else "",
                  version=version.lstrip("vV"), sub="", screen=SECONDS["chapter"])
    if arc:                                               # the brand card: positioning kicker, wordmark, badges
        opener = dict(kind="brand", layout="brand", id="opening", title=name, version=version.lstrip("vV"),
                      eyebrow=C.text(product.get("name_zh"), lang) if lang == "zh" else "",
                      kicker=C.text(product.get("tagline"), lang), badges=C.texts(product.get("badges"), lang),
                      screen=SECONDS["brand"])
    names = [x.lower() for x in (name, C.text(product.get("name_zh"), "zh")) if x]
    named = units and any(n in c.lower() for n in names for c in units[0]["all_captions"])
    blocks = list(fo["blocks"]) if arc and fo.get("blocks") is not None else (["brand", "reel"] if arc else [])
    cold = fo.get("cold_open", True) is not False
    if opening and units and cold and (named or (arc and not d.get("title_card", True))):
        u = units.pop(0)                                  # her first line is the product's name: a cold open, then it
        feat("full", [u], T(u, 3.0) * 0.8, panes=[dict(fid=u["id"], sid=u["shots"][0], k=0, first=True)])
        if not arc:
            add(**opener)
    elif opening and not arc and d.get("title_card", True):
        opener["sub"] = C.text(product.get("one_liner"), lang)
        opener["screen"] = float(d.get("title_seconds") or SECONDS[opener["layout"]]) - xf
        add(**opener)
    elif opening and arc and "brand" in blocks and not out:
        opener["screen"] = float(d.get("title_seconds") or SECONDS["brand"]) - xf
    for b in blocks if opening else []:
        if b == "brand":
            add(**opener)
        elif b == "reel" and (units or fo.get("reel")):   # the reel: everything it does, a cut on every beat
            ru = [_unit(cfg, fid, lang) for fid in fo["reel"]] if fo.get("reel") else reel_units(units)
            promise = C.text(product.get("promise"), lang)
            add(kind="reel", layout=REEL, id="reel", units=[u["id"] for u in ru], slot=slot, screen=slot * len(ru),
                text=promise if promise and caps != "none" and ("reel", "reel") not in drop else "",
                panes=[dict(fid=u["id"], sid=u["shots"][-1], k=0) for u in ru])
            out[-1]["min"] = out[-1]["dur"]
        elif b == "waterfall":                            # real thumbnails pour into the wordmark
            add(kind="waterfall", layout="waterfall", id="waterfall", title=name,
                eyebrow=C.text(product.get("name_zh"), lang) if lang == "zh" else "",
                kicker=C.text(product.get("tagline"), lang), screen=SECONDS["waterfall"])
        elif b == "lift":                                 # the platforms lift Create · Edit · Publish
            words = C.texts((fo.get("lift") or {}).get("words"), lang) or LIFT_WORDS["zh" if lang == "zh" else "en"]
            pls = (fo.get("lift") or {}).get("platforms") or LIFT_PLATFORMS
            add(kind="lift", layout="lift", id="lift", words=words, platforms=list(pls),
                sub=C.text((fo.get("lift") or {}).get("sub") or product.get("promise"), lang) if caps != "none" else "",
                screen=SECONDS["lift"])
        elif b == "hook":                                 # one heavy line
            line = C.text(fo.get("hook"), lang)
            add(kind="hook", layout="hook", id="hook", text=line, kicker=C.text(fo.get("hook_kicker"), lang),
                screen=round(clamp(1.2 + 0.1 * _words(line, lang), 1.6, 2.6), 2))
    # sequences: a chapter: feature starts a new one; otherwise PHRASE sizes in turn
    seqs, cur, sizes = [], [], PHRASE[variety]
    for u in units:
        if cur and (u["chapter"] or len(cur) >= sizes[len(seqs) % len(sizes)]):
            seqs.append(cur)
            cur = []
        cur.append(u)
    if cur:
        seqs.append(cur)
    if len(seqs) > 1 and len(seqs[-1]) == 1 and not seqs[-1][0]["chapter"] and len(seqs[-2]) < 3:
        tail = seqs.pop()                                 # no one-shot tail sequence
        seqs[-1] = seqs[-1] + tail
    rot = ROTATION[variety]
    ptr = [0]
    nchap = 0
    for si, seq in enumerate(seqs):
        hero, rest = seq[0], seq[1:]
        if hero["chapter"]:
            nchap += 1
            add(kind="chapter", layout="chapter", id=hero["id"], title=hero["chapter"], eyebrow=f"{nchap:02d}", sub="",
                chips=hero["chips"], screen=SECONDS["chapter"] + (0.6 if hero["chips"] else 0.0))
        elif prev() not in CARDS and type_ok(hero) and out:
            add(kind="type", layout="type", id=hero["id"], text=hero["caption"],
                screen=_type_seconds(hero["caption"], lang))
        elif not out and type_ok(hero):
            add(kind="type", layout="type", id=hero["id"], text=hero["caption"],
                screen=_type_seconds(hero["caption"], lang))
        after_card = prev() == "chapter" or (prev() == "type" and out[-1].get("id") != hero["id"])
        # the lead feature: an establishing shot (full; float with its line when no type beat said it) + a detail
        if len(hero["shots"]) > 1:
            said = out and out[-1].get("id") == hero["id"] and out[-1]["layout"] == "type"
            feat("split", [hero], T(hero), text="", labels=[hero["caption"]] if lower_ok(hero) and not said else [],
                 panes=[dict(fid=hero["id"], sid=s, k=k) for k, s in enumerate(hero["shots"][:2])])
        else:
            est = hero["layout"] or ("float" if after_card and lower_ok(hero) else "full")
            if est == prev():
                est = "float" if est == "full" else "full"
            said = out[-1].get("id") == hero["id"] and out[-1]["layout"] != "chapter"    # a chapter names the act only
            text = hero["caption"] if est == "float" and lower_ok(hero) and not said else ""
            if variety != "calm" and est != "macro":
                feat(est, [hero], max(FLOOR[est], T(hero) * 0.56), text=text)
                feat("macro", [hero], max(FLOOR["macro"], T(hero) * 0.44),
                     panes=[dict(fid=hero["id"], sid=hero["shots"][0], k=0, cont=True)])
            else:
                feat(est, [hero], T(hero), text=text)
        # the rest of the sequence rotates through float / split / full, never twice in a row
        j = 0
        while j < len(rest):
            u = rest[j]
            if len(u["shots"]) > 1:
                feat("split", [u], T(u), labels=[u["caption"]] if lower_ok(u) else [],
                     panes=[dict(fid=u["id"], sid=s, k=k) for k, s in enumerate(u["shots"][:2])])
                j += 1
                continue
            pair = j + 1 < len(rest) and len(rest[j + 1]["shots"]) == 1 and not rest[j + 1]["layout"]
            since = next((n for n, x in enumerate(reversed(out)) if x["layout"] == "split"), len(out))
            if u["layout"]:
                lay = u["layout"]
            elif pair and since >= 4 and prev() != "split" and variety != "calm":
                lay = "split"                              # two moments side by side, now and then
            else:
                lay = None
                for k in range(len(rot)):
                    cand = rot[(ptr[0] + k) % len(rot)]
                    if cand == prev() or (cand == "split" and not pair):
                        continue
                    lay = cand
                    ptr[0] += k + 1
                    break
                lay = lay or ("full" if prev() != "full" else "float")
            if lay == "split" and j + 1 < len(rest):
                v = rest[j + 1]
                feat("split", [u, v], max(T(u), T(v)),
                     labels=[x["caption"] if lower_ok(x) else "" for x in (u, v)] if lower_ok(u) or lower_ok(v) else [])
                j += 2
                continue
            if lay == "macro":
                feat("macro", [u], T(u))
            else:
                feat(lay, [u], T(u), text=u["caption"] if lay == "float" and lower_ok(u) else "")
            j += 1
    add(kind="end", layout="end", screen=float(d["end_seconds"]) - xf)
    return fix_adjacent(out)


def fix_adjacent(scenes):
    """No two adjacent scenes share a layout: a repeated footage layout becomes full / float (whichever differs from
    both neighbours; a float that was not planned carries no text)."""
    for i in range(1, len(scenes)):
        a, b = scenes[i - 1], scenes[i]
        if a["layout"] != b["layout"] or b["layout"] not in FOOTAGE:
            continue
        nxt = scenes[i + 1]["layout"] if i + 1 < len(scenes) else None
        for alt in ("full", "float", "macro"):
            if alt not in (a["layout"], nxt) and not (alt == "macro" and not b["panes"][0].get("cont")):
                if b["layout"] == "split" and len(b["panes"]) > 1:
                    b["panes"] = b["panes"][:1]
                b["layout"], b["labels"] = alt, []
                if alt != "float":
                    b["text"] = ""
                break
    return scenes


def adjacent_ok(scenes):
    return all(a["layout"] != b["layout"] for a, b in zip(scenes, scenes[1:]))


# ------------------------------------------------------------------------------------------------ timing
def beat_grid(cfg, cut):
    """(period, phase) of the film's music bed, or None (a loop is silent; motion.beat: false turns it off)."""
    if cut == "loop" or (cfg.get("motion") or {}).get("beat") is False:
        return None
    m = cfg.get("music")
    if not m:
        return None
    from vstudio import music as MU
    return MU.beat_grid(m.get("file") or m.get("mood"))


def beat_sync(scenes, grid, xf, floor=4.0):
    """Stretch / trim each scene (by under a beat) so every transition's midpoint lands on a beat of the bed; a
    scene is never trimmed under its ``min`` (default ``floor``) s (a short one only stretches)."""
    period, phase = grid
    t = 0.0
    for i, s in enumerate(scenes[:-1]):
        fl = s.get("min", floor)
        cut = t + s["dur"] - xf / 2
        k = round((cut - phase) / period)
        nxt = k * period + phase - xf / 2
        while nxt - t + xf < min(fl, s["dur"]) - 1e-6:
            nxt += period
        s["dur"] = round(nxt - t + xf, 3)
        t = nxt
    return scenes


def _starts(scenes, xf):
    t = 0.0
    for i, s in enumerate(scenes):
        s["start"] = round(t, 3)
        t += s["dur"] - (xf if i < len(scenes) - 1 else 0.0)
    return round(t, 3)


def text_spans(scenes, xf):
    """[(t0, t1)] when words are on screen: every card (minus the half-overlaps) and every lower third."""
    out, n = [], len(scenes)
    for i, s in enumerate(scenes):
        a, b = s["start"], s["start"] + s["dur"]
        if s["layout"] == "waterfall":                  # words only once the wordmark resolves
            out.append((a + WATERFALL_TEXT, b - (xf / 2 if i < n - 1 else 0.0)))
        elif s["layout"] in CARDS or (s["layout"] == REEL and s.get("text")):
            out.append((a + (xf / 2 if i else 0.0), b - (xf / 2 if i < n - 1 else 0.0)))
        elif s.get("text") or s.get("labels"):
            t0 = a + (xf * 0.55 if i else 0.0) + LT_IN
            out.append((t0, min(t0 + LT_HOLD, b - xf / 2)))
    return out


def text_share(plan_or_scenes, xf=None, total=None):
    """Share of the runtime with text on screen (the union of text_spans / the duration)."""
    if isinstance(plan_or_scenes, dict):
        scenes, xf, total = plan_or_scenes["scenes"], plan_or_scenes["xf"], plan_or_scenes["duration"]
    else:
        scenes = plan_or_scenes
    spans = sorted(x for x in text_spans(scenes, xf) if x[1] > x[0])
    tot, cur = 0.0, None
    for a, b in spans:
        if cur and a <= cur[1]:
            cur[1] = max(cur[1], b)
        else:
            if cur:
                tot += cur[1] - cur[0]
            cur = [a, b]
    if cur:
        tot += cur[1] - cur[0]
    return tot / total if total else 0.0


def _fit_demo(cfg, scenes, xf, grid):
    """Squeeze / stretch the footage so the demo lands inside [min_seconds, max_seconds] after the beat snap."""
    d = cfg["demo"]
    lo, hi = float(d["min_seconds"]), float(d["max_seconds"])
    base = {id(s): s["dur"] for s in scenes}
    target = None
    for _ in range(4):
        foot = [s for s in scenes if s["layout"] in FOOTAGE]
        for s in scenes:
            s["dur"] = base[id(s)]
        total = sum(s["dur"] for s in scenes) - xf * (len(scenes) - 1)
        goal = target if target is not None else (hi if total > hi else lo if total < lo else None)
        if goal is not None and foot:
            body = sum(s["dur"] for s in foot)
            k = max(0.2, (body + goal - total) / body)
            for s in foot:
                s["dur"] = round(max(s["min"], s["dur"] * k) if k < 1 else min(s["dur"] * k, s["dur"] + 2.5), 3)
        if grid:
            beat_sync(scenes, grid, xf)
        total = _starts(scenes, xf)
        if total <= hi + 1e-6 or grid is None:
            break
        target = (target if target is not None else hi) - (total - hi) - 0.3
    total = _starts(scenes, xf)
    if total > hi and scenes[-1]["layout"] == "end":         # the last few frames come off the end card
        scenes[-1]["dur"] = round(max(scenes[-1]["min"], scenes[-1]["dur"] - (total - hi)), 3)
    return _starts(scenes, xf)


def _pane_media(cfg, shots, p, target, anchor):
    """One pane's take: the stretch of the shot that fills ``target`` s at the cut's pace (idle stretches ramped)."""
    feat = C.feature(cfg, p["fid"])
    f = dict(feat, shot=p["sid"])
    tr = feat.get("trim")
    if isinstance(tr, list) and tr and isinstance(tr[0], list):
        f["trim"] = tr[min(p.get("k", 0), len(tr) - 1)]
    shot = shot_for(f, shots)
    rate = float(feat.get("rate") or cfg.get("pace") or 1.0)
    spans = TM.idle_spans(shot) if shot["kind"] == "video" and feat.get("ramp", True) else []
    if f.get("trim"):
        a, b = media_window(f, shot)
    elif shot.get("clip") and shot["kind"] == "video":
        a, b = TM.best_window(shot, target, spans, rate, anchor=anchor)
    else:
        a, b = media_window(f, shot)
    return dict(kind=shot["kind"], file=shot["file"], still=shot.get("still"), w=shot.get("w"), h=shot.get("h"),
                at=a, until=b, rate=rate, segs0=TM.segments(a, b, spans, rate)), shot


def pane_boxes(layout, scene):
    """The window box(es) of a footage scene."""
    lay = scene["layout"]
    if lay == "split":
        return list(layout["split"][:len(scene["panes"])])
    if lay == "float":
        return [layout["float"]]
    return [layout["full"]]


def _place(cfg, scenes, layout, shots, xf, aspect):
    """Media and camera for every footage scene, once the timing is final. A detail scene (``cont``) continues the
    take of the scene before it from where the cut leaves it."""
    still = (cfg.get("motion") or {}).get("camera") == "still"
    for i, s in enumerate(scenes):
        if s["layout"] == REEL:
            _place_reel(cfg, s, layout, shots, xf)
            continue
        if s["layout"] not in FOOTAGE:
            continue
        boxes = pane_boxes(layout, s)
        for k, p in enumerate(s["panes"]):
            if p.get("cont") and i and scenes[i - 1]["layout"] in FOOTAGE:
                q = scenes[i - 1]["panes"][0]
                base, off, shot = q["_base"], q["_off"] + scenes[i - 1]["dur"] - xf, shots[q["shot"]]
                media = dict(q["media"])
            else:
                span = s["dur"]
                j = i + 1
                while j < len(scenes) and scenes[j]["layout"] in FOOTAGE and scenes[j]["panes"][0].get("cont"):
                    span += scenes[j]["dur"] - xf
                    j += 1
                media, shot = _pane_media(cfg, shots, p, span + xf, "start" if p.get("first") else "end")
                base, off = TM.fit(media.pop("segs0"), span), 0.0
            segs = TM.window(base, off, off + s["dur"])
            p["_base"], p["_off"], p["shot"] = base, off, shot["id"]
            media["segs"] = segs
            media["end"] = base[-1][1] if base else media["until"]
            p["media"] = media
            p["play"] = round(min(s["dur"], TM.length(segs)), 3)
            box = boxes[min(k, len(boxes) - 1)]
            m0 = segs[0][0] if segs else media["end"]
            m1 = segs[-1][1] if segs else media["end"]
            tmap = (lambda t, g=segs: TM.to_scene(g, t)) if segs else (lambda t: 0.0)
            L = dict(layout, win=box, zoom=layout["zooms"].get(s["layout"], layout["zoom"]))
            if s["layout"] == "macro":
                p["cam"] = macro_camera(box, shot, m0, m1, s["dur"], aspect)
            elif still or not shot.get("auto_focus"):
                p["cam"] = camera(L, shot, m0, m1, s["dur"], tmap)
            else:
                p["cam"] = push_camera(L, shot, m0, m1, s["dur"], tmap)
            p["box"] = list(box)
    for s in scenes:
        for p in s.get("panes") or []:
            p.pop("_base", None)
            p.pop("_off", None)


def reel_cuts(scene, xf):
    """Scene-relative start of each moment of a reel: the first is up from the start (under the transition in), the
    rest on the slot grid from the middle of that transition (on the beats when the scene starts on one)."""
    return [0.0] + [round(xf / 2 + k * scene["slot"], 3) for k in range(1, len(scene["panes"]))]


def _place_reel(cfg, s, layout, shots, xf):
    """Media + camera for each moment of a reel: the stretch of the take that ends on its result, framed a little
    in on where the screen changes and creeping in."""
    box = layout["reel"]["view"]
    cuts = reel_cuts(s, xf) + [s["dur"]]
    for k, p in enumerate(s["panes"]):
        play = round(cuts[k + 1] - cuts[k], 3)
        media, shot = _pane_media(cfg, shots, p, play, "end")
        base = TM.fit(media.pop("segs0"), play)
        segs = TM.window(base, 0.0, play)
        media["segs"] = segs
        media["end"] = base[-1][1] if base else media["until"]
        m0 = segs[0][0] if segs else media["end"]
        m1 = segs[-1][1] if segs else media["end"]
        cx, cy, _, _ = macro_target(shot, m0, m1)
        cx, cy = 0.5 + (cx - 0.5) * 0.6, 0.5 + (cy - 0.5) * 0.6        # toward the action, the UI still reads whole
        p.update(media=media, shot=shot["id"], box=list(box), at=cuts[k], play=play,
                 thumb=round((m0 + m1) / 2, 3) if shot["kind"] == "video" else 0.0,
                 cam=[dict(t=0.0, d=0.0, ease="none", **cam_pose(box, shot, cx, cy, 1.12)),
                      dict(t=0.0, d=play, ease="none", **cam_pose(box, shot, cx, cy, 1.2))])


def plan(cfg, shots, cut, lang, aspect, feature=None):
    """cut: demo | loop | clip (clip needs ``feature``)."""
    if aspect not in LAYOUTS:
        raise ValueError(f"aspect {aspect}: one of {', '.join(LAYOUTS)}")
    W, H = C.ASPECTS[aspect]
    layout = dict(LAYOUTS[aspect])
    xf = xf_of(cfg)
    if cut == "demo":
        ids = C.cut_features(cfg, "demo")
    elif cut == "loop":
        ids = C.cut_features(cfg, "loop")
    elif cut == "clip":
        if not feature:
            raise ValueError("clip needs a feature id")
        ids = [feature]
    else:
        raise ValueError(f"cut {cut}: demo | loop | clip")
    units = [_unit(cfg, fid, lang) for fid in ids]
    for u in units:                                       # a missing shot is a clear error before anything else
        for sid in u["shots"]:
            shot_for(dict(C.feature(cfg, u["id"]), shot=sid), shots)
    grid = beat_grid(cfg, cut)
    cap = float(film_opts(cfg)["text"])
    drop = set()
    slot = reel_slot(grid)
    while True:
        scenes = rhythm(cfg, units, lang, cut, frozenset(drop), slot=slot)
        if cut == "demo":
            total = _fit_demo(cfg, scenes, xf, grid)
        elif cut == "loop":
            each = (cfg["loop"]["seconds"] + xf * len(scenes)) / len(scenes)   # the closing crossfade overlaps too
            for s in scenes:
                s["dur"] = round(each, 3)
            total = _starts(scenes, xf)
        else:
            cp = cfg["clips"]
            total = _starts(scenes, xf)
            foot = [s for s in scenes if s["layout"] in FOOTAGE]
            if total < cp["min_seconds"] and foot:
                extra = (cp["min_seconds"] - total) / len(foot)
                for s in foot:
                    s["dur"] = round(s["dur"] + extra, 3)
            elif total > cp["max_seconds"] and foot:
                k = (sum(s["dur"] for s in foot) - (total - cp["max_seconds"])) / sum(s["dur"] for s in foot)
                for s in foot:
                    s["dur"] = round(max(s["min"], s["dur"] * k), 3)
            if grid:
                beat_sync(scenes, grid, xf)
            total = _starts(scenes, xf)
        loop_total = total - xf if cut == "loop" else total
        if text_share(scenes, xf, loop_total) <= cap + 1e-6:
            break
        # take text out until it fits: lower thirds first, then type beats, from the end of the film
        cands = [("lower", u) for s in reversed(scenes) if s["layout"] in FOOTAGE and (s.get("text") or s.get("labels"))
                 for u in reversed(s["units"])]
        cands += [("type", s["id"]) for s in reversed(scenes) if s["layout"] == "type"]
        cands += [("reel", "reel") for s in scenes if s["layout"] == REEL and s.get("text")]
        cands = [c for c in cands if c not in drop]
        if not cands:
            break
        drop.add(cands[0])
    _place(cfg, scenes, layout, shots, xf, aspect)
    if cut == "loop":
        total = round(total - xf, 3)                         # last scene crossfades into the first frame
    tr = (cfg.get("motion") or {}).get("transition", "crossfade")
    return dict(cut=cut, lang=lang, aspect=aspect, W=W, H=H, duration=total, layout=layout, scenes=scenes,
                feature=feature, xf=xf, loop=cut == "loop", transition="crossfade" if cut == "loop" else tr,
                beat=list(grid) if grid else None, dropped=sorted(list(x) for x in drop),
                arc=film_opts(cfg)["arc"] if cut == "demo" else "plain",
                text_share=round(text_share(scenes, xf, total), 3))


def caption_cues(p):
    """[{start, end, text}] of the words on screen (firstpass checks their spelling / terms): type beats, chapter
    titles and lower thirds, in order."""
    out = []
    for s in p["scenes"]:
        txt = s.get("text") if s["layout"] not in ("chapter", "brand", "waterfall") else s.get("title")
        if s["layout"] == "lift":
            txt = " · ".join(s.get("words") or []) + (f' / {s["sub"]}' if s.get("sub") else "")
        if s["layout"] == "hook" and s.get("kicker"):
            txt = f'{s["kicker"]} / {txt}'
        if s["layout"] in ("brand", "waterfall") and s.get("kicker"):
            txt = f'{s["kicker"]} / {txt}'
        if s.get("chips"):
            txt = f'{txt} / {" · ".join(s["chips"])}'
        if s["layout"] == "brand" and s.get("badges"):
            txt = f'{txt} / {" · ".join(s["badges"])}'

        txt = txt or " / ".join(x for x in s.get("labels") or [] if x)
        if s["layout"] in ("end",) or not txt:
            continue
        out.append(dict(start=s["start"], end=round(s["start"] + s["dur"], 3), text=C.plain(txt)))
    return out


def frames(n, total):
    """n evenly spaced sample times inside (0, total) - used for snapshot checks."""
    return [round(total * (i + 0.5) / n, 2) for i in range(n)] if n > 0 and total > 0 else []
