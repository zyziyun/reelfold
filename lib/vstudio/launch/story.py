"""Storyboard: config + shots -> a timed plan per cut (demo / loop / one feature clip), language and canvas.

    from vstudio.launch import story as S
    plan = S.plan(cfg, shots, "demo", "en", "16:9")      # {cut, lang, aspect, W, H, duration, layout, scenes}
    S.plan(cfg, shots, "clip", "zh", "9:16", feature="plan")

Pure functions (no rendering), so the timing and the camera are unit-tested. Scenes:
  title    product mark + name + one-liner (demo only)
  feature  kicker + kinetic caption + the product shot in a window; the camera follows the shot's focus boxes
           (punch-in on each click / typed field, pull back between actions)
  end      logo, call to action, site
Consecutive scenes overlap by ``XF`` seconds (crossfade). A loop ends on a crossfade back into its first frame.
"""
from . import config as C
from . import timing as TM

XF = 0.35                     # scene crossfade
LEAD = 0.55                   # the camera starts moving this long before the action it frames
HOLD = 1.5                    # minimum time the camera stays on an action
MERGE = 0.6                   # actions closer than this share one camera move

# canvas layouts (px). Text boxes stay inside the intersection of the safe boxes of every platform the canvas is
# posted to (config.CANVAS_PLATFORMS; asserted in tests); the product window may run under platform UI.
LAYOUTS = {
    "16:9": dict(text=(120, 64, 1800, 196), kicker_px=24, caption_px=(56, 40), caption_lines=1,
                 win=(288, 212, 1344, 840), base_zoom=1.0, punch=1.45, title_px=124, oneliner_px=44),
    "1:1": dict(text=(72, 62, 1008, 288), kicker_px=22, caption_px=(50, 36), caption_lines=2,
                win=(60, 318, 960, 640), base_zoom=1.0, punch=1.5, title_px=104, oneliner_px=38),
    "9:16": dict(text=(72, 300, 920, 660), kicker_px=30, caption_px=(84, 56), caption_lines=3,
                 win=(40, 720, 1000, 940), base_zoom=1.0, punch=1.45, title_px=112, oneliner_px=46),
}


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
    """Keyframes [{t, x, y, scale, d, ease}] for one feature scene: open framed on the whole shot (or, on a
    narrow window, the first action), punch in on each action, pull back when the next one is far off."""
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


# ------------------------------------------------------------------------------------------------ plans
def shot_ids(feat):
    """A feature's shots in order: ``shot`` is one id or a list (one scene per shot, the caption stays up)."""
    sid = feat.get("shot") or feat["id"]
    return [str(x) for x in sid] if isinstance(sid, list) else [sid]


def xf_of(cfg):
    return float((cfg.get("motion") or {}).get("seconds", XF))


def _feature_scenes(cfg, shots, fid, lang, layout, dur_hint, cut, opening=False):
    """One scene per shot of the feature (``shot: [a, b]`` = two scenes sharing the caption, ``part`` 0, 1).
    ``opening``: the cut's first scene (no title card): its take plays from its first frame."""
    feat = C.feature(cfg, fid)
    sids = shot_ids(feat)
    out = []
    for k, sid in enumerate(sids):
        f = dict(feat, shot=sid)
        if k and isinstance(feat.get("trim"), list) and feat["trim"] and isinstance(feat["trim"][0], list):
            f["trim"] = feat["trim"][k]
        elif isinstance(feat.get("trim"), list) and feat["trim"] and isinstance(feat["trim"][0], list):
            f["trim"] = feat["trim"][0]
        sc = _feature_scene(cfg, shots, f, lang, layout, dur_hint, cut, share=len(sids),
                            anchor="start" if opening and k == 0 else "end")
        sc["part"], sc["parts"] = k, len(sids)
        out.append(sc)
    return out


def _feature_scene(cfg, shots, feat, lang, layout, dur_hint, cut, share=1, anchor="end"):
    shot = shot_for(feat, shots)
    rate = float(feat.get("rate") or cfg.get("pace") or 1.0)
    # idle stretches of a recording (waiting for the app) play fast unless the feature says ramp: false
    spans = TM.idle_spans(shot) if shot["kind"] == "video" and feat.get("ramp", True) else []
    want = float(feat["seconds"]) / share if feat.get("seconds") else None
    if feat.get("trim"):
        a, b = media_window(feat, shot)
    elif shot.get("clip") and shot["kind"] == "video":
        # a take she supplied is longer than its scene: play the stretch with the action at the cut's pace, not
        # the whole take squeezed into a few seconds
        target = want or dur_hint(5.0 if cut == "demo" else 1e9)
        a, b = TM.best_window(shot, target + xf_of(cfg), spans, rate, anchor=anchor)
    else:
        a, b = media_window(feat, shot)
    segs = TM.segments(a, b, spans, rate)
    natural = TM.length(segs)
    return dict(kind="feature", id=feat["id"], shot=shot["id"], media=dict(kind=shot["kind"], file=shot["file"],
                still=shot.get("still"), w=shot.get("w"), h=shot.get("h"), at=a, until=b, rate=rate, segs=segs),
                natural=natural, dur=round(want + xf_of(cfg), 3) if want else dur_hint(natural),
                fixed=bool(want), push=bool(shot.get("auto_focus")) and (cfg.get("motion") or {}).get("camera",
                                                                                                   "push") == "push",
                kicker=C.text(feat.get("kicker"), lang), caption=C.text(feat.get("caption"), lang),
                vo=C.text(feat.get("vo"), lang) if (cfg.get("voiceover") or {}).get("enabled") else "")


def push_camera(layout, shot, t0, t1, dur, tmap=None):
    """One slow push-in for a scene from a supplied recording: open on the window (on a narrow window: centred on
    where the action is), then ease in on the area where the screen changes most over the whole scene."""
    win = layout["win"]
    z0 = layout["base_zoom"]
    fit, sw, sh = _fit(win, shot)
    narrow = (win[2] / win[3]) < (sw / sh) * 0.8
    ev = [f for f in shot.get("focus") or [] if t0 <= f["t"] <= t1]
    if ev:
        x0 = min(f["x"] for f in ev)
        y0 = min(f["y"] for f in ev)
        x1 = max(f["x"] + f.get("w", 0) for f in ev)
        y1 = max(f["y"] + f.get("h", 0) for f in ev)
        cx, cy, bw, bh = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    else:
        cx, cy, bw, bh = 0.5, 0.5, 1.0, 1.0
    # zoom until the area of action fills ~85 % of the window; a calm move: 1.06x .. 1.4x
    vis_w, vis_h = win[2] / (sw * fit), win[3] / (sh * fit)          # the part of the shot the window shows at 1x
    z = clamp(0.85 / max(bw / vis_w, bh / vis_h, 1e-3), 1.06, 1.4)
    start = (cx, cy) if narrow else (0.5, 0.5)
    return [dict(t=0.0, d=0.0, ease="none", **cam_pose(win, shot, *start, z0)),
            dict(t=0.0, d=round(dur, 3), ease="sine.inOut", **cam_pose(win, shot, cx, cy, z0 * z))]


def _place(scenes, layout, shots, cfg, xf=XF):
    t = 0.0
    for i, s in enumerate(scenes):
        s["start"] = round(t, 3)
        if s["kind"] == "feature":
            shot = shots[s["shot"]]
            m = s["media"]
            m["segs"] = TM.fit(m["segs"], s["dur"])                    # a short scene plays the take faster
            s["play"] = round(min(s["dur"], TM.length(m["segs"])), 3)   # the rest holds the last frame
            segs = m["segs"]
            cam = push_camera if s.get("push") else camera
            s["cam"] = cam(layout, shot, m["at"], m["until"], s["dur"], lambda t, g=segs: TM.to_scene(g, t))
        t += s["dur"] - (xf if i < len(scenes) - 1 else 0.0)
    return round(t, 3)


def plan(cfg, shots, cut, lang, aspect, feature=None):
    """cut: demo | loop | clip (clip needs ``feature``)."""
    if aspect not in LAYOUTS:
        raise ValueError(f"aspect {aspect}: one of {', '.join(LAYOUTS)}")
    W, H = C.ASPECTS[aspect]
    layout = dict(LAYOUTS[aspect])
    xf = xf_of(cfg)
    scenes = []
    if cut == "demo":
        d = cfg["demo"]
        ids = C.cut_features(cfg, "demo")
        title = d.get("title_card", True)
        for k, fid in enumerate(ids):
            scenes += _feature_scenes(cfg, shots, fid, lang, layout, lambda n: clamp(n, 4.5, 9.0), cut,
                                      opening=k == 0 and not title)
        fixed = (d["title_seconds"] if title else 0.0) + d["end_seconds"] - xf * (len(scenes) - (0 if title else 1))
        body = sum(s["dur"] for s in scenes)
        if fixed + body > d["max_seconds"]:                  # squeeze every scene evenly, never under 4 s
            k = (d["max_seconds"] - fixed) / body
            for s in scenes:
                s["dur"] = round(max(min(4.0, s["dur"]) if s.get("fixed") else 4.0, s["dur"] * k), 3)
        elif fixed + body < d["min_seconds"]:                # hold each shot's last frame a little longer
            extra = (d["min_seconds"] - fixed - body) / max(1, len(scenes))
            for s in scenes:
                s["dur"] = round(s["dur"] + min(extra, 2.5), 3)
        scenes = (([dict(kind="title", dur=d["title_seconds"])] if title else []) + scenes
                  + [dict(kind="end", dur=d["end_seconds"])])
    elif cut == "loop":
        lp = cfg["loop"]
        ids = C.cut_features(cfg, "loop")
        each = (lp["seconds"] + xf * len(ids)) / len(ids)    # the closing crossfade back to frame 0 overlaps too
        for fid in ids:
            scenes += _feature_scenes(cfg, shots, fid, lang, layout, lambda n, e=each: e, cut)[:1]
        for s in scenes:
            s["dur"], s["fixed"] = round(each, 3), False
    elif cut == "clip":
        cp = cfg["clips"]
        if not feature:
            raise ValueError("clip needs a feature id")
        lo, hi = cp["min_seconds"] - cp["end_seconds"] + xf, cp["max_seconds"] - cp["end_seconds"] + xf
        scenes = _feature_scenes(cfg, shots, feature, lang, layout, lambda n: clamp(n + 1.2, lo, hi), cut)
        if len(scenes) > 1:
            for s in scenes:
                s["dur"] = round(max(s["dur"], lo / len(scenes) + xf), 3)
        scenes.append(dict(kind="end", dur=cp["end_seconds"]))
    else:
        raise ValueError(f"cut {cut}: demo | loop | clip")
    total = _place(scenes, layout, shots, cfg, xf)
    if cut == "loop":
        total = round(total - xf, 3)                         # last scene crossfades into the first frame
    tr = (cfg.get("motion") or {}).get("transition", "crossfade")
    return dict(cut=cut, lang=lang, aspect=aspect, W=W, H=H, duration=total, layout=layout, scenes=scenes,
                feature=feature, xf=xf, loop=cut == "loop", transition="crossfade" if cut == "loop" else tr)


def caption_cues(p):
    """[{start, end, text}] of the on-screen captions (firstpass checks their spelling / terms); a feature shown
    over two shots is one cue."""
    out = []
    for s in p["scenes"]:
        if s["kind"] == "feature" and s.get("caption"):
            if s.get("part") and out and out[-1]["text"] == C.plain(s["caption"]):
                out[-1]["end"] = round(s["start"] + s["dur"], 3)
                continue
            out.append(dict(start=s["start"], end=round(s["start"] + s["dur"], 3), text=C.plain(s["caption"])))
    return out


def frames(n, total):
    """n evenly spaced sample times inside (0, total) - used for snapshot checks."""
    return [round(total * (i + 0.5) / n, 2) for i in range(n)] if n > 0 and total > 0 else []
