"""Per-shot treatment: for every shot tile, how it is used in the cut - and why - under the template's policy.

    from vstudio.brain import treat
    plan = treat.plan(tiles, "travel-calm", target_s=60, out_aspect="9:16")
    plan["shots"]   # [{id, clip, use [a, b], hold_s, speed, speed_x, reframe, transition {kind, s}, grade {...},
                    #   text {ok, where}, punch_in, stabilize, skip, fit, why [{code, en, zh}], choices {...}, by}]
    plan["summary"] # counts per treatment + the budget checks (A4 / A7)

Restrained by default (AESTHETICS.md): a hard cut or a dissolve where the place / light changes, never a flash, a
whip or a glitch; slow motion only on a steady shot with movement in it and only where the frame cadence stays even
(60p at 0.5x, or RIFE frames when ``vstudio.rife`` is in the engine); one speed ramp at most in a beat short; a
punch-in only in talking heads; text only where the frame is steady and has room.

Every choice is an "effect fit": each candidate gets a 0-1 fit from the shot's numbers; the best wins, the others are
kept (``choices``) so the inspector can say "dissolve .82 vs cut .55: the light changes from dusk to night". When the
two best are within ``CLOSE`` the choice is ``ambiguous``; ``judge`` (the routed AI) may settle those; otherwise the
rules' pick stands. Her own change of a shot (``overrides``) is applied last and marked ``by: her``.
"""
import math

from . import presets as P

CLOSE = 0.08
MIN_SCORE = 0.32           # below this a shot is not used (unless nothing better is left)
DARK = 0.18                # mean brightness (0-1) under this = too dark to use as is
SHAKY = 0.35               # steadiness under this = shaky
LIGHT_JUMP = 0.12          # brightness change between neighbours that reads as a new light
COLOUR_JUMP = 9.0          # Lab distance between neighbours that reads as a new place / light
MATCH_LAB = 6.0            # neighbours this close in colour, both moving: a match cut
SUBJECT_SPREAD = 0.2       # the frame's interest gathered this tightly = one subject the crop can follow
CLIP_REPEAT = 0.08         # picking shots for the length: each shot already taken from a clip costs this much


def rife_available():
    try:
        from vstudio import rife  # noqa: F401
        return bool(getattr(rife, "available", lambda: True)())
    except Exception:  # noqa: BLE001  (RIFE not in this engine yet)
        return False


def _w(code, en, zh, **params):
    return dict(code=code, en=en, zh=zh, params=params)


def _aspect(w, h):
    if not w or not h:
        return None
    return w / h


def _ratio(s):
    if not s:
        return None
    a, _, b = str(s).partition(":")
    try:
        return float(a) / float(b)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _lab_d(a, b):
    if not a or not b:
        return None
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _same_framing(a, b):
    """Both sides frame the face the same way (size within 15 %, centre within 5 % of the frame): a jump cut that
    shows. A change of framing (a punch-in already in the edit, a new angle) is a clean cut and stays one."""
    fa, fb = a.get("face_area"), b.get("face_area")
    if not fa or not fb:
        return False
    if abs(fa - fb) / max(fa, fb) > 0.15:
        return False
    xa, xb = a.get("subject_xy"), b.get("subject_xy")
    return not (xa and xb and math.hypot(xa[0] - xb[0], xa[1] - xb[1]) > 0.05)


def _shot_of(tid):
    """'C1.S2.3' -> 'C1.S2' (the shot a moment belongs to)."""
    parts = str(tid).split(".")
    return ".".join(parts[:2])


def _pick(cands):
    """{name: (fit, why)} -> (name, fit, ambiguous, ranked [(name, fit)])."""
    ranked = sorted(((k, round(v[0], 2)) for k, v in cands.items()), key=lambda kv: -kv[1])
    best = ranked[0]
    amb = len(ranked) > 1 and best[1] - ranked[1][1] < CLOSE
    return best[0], best[1], amb, ranked


# --------------------------------------------------------------------------- per-shot decisions
def _q(t, med):
    """A shot's quality inside this film: sharpness + steadiness + exposure measured against the film's own light
    (a night film's shots are dark on purpose; its brightest dusk shot is not its best)."""
    if t.get("sharp") is None or t.get("steady") is None or t.get("bright") is None or med is None:
        return float(t.get("score") or 0.5)
    rel = 1.0 - min(1.0, abs(float(t["bright"]) - med) / 0.25)
    q = 0.40 * float(t["sharp"]) + 0.35 * float(t["steady"]) + 0.25 * rel
    if t.get("aesthetic") is not None:        # LAION aesthetic 1-10 when the engine has the model (as in shots)
        q = 0.85 * q + 0.15 * max(0.0, min(1.0, (float(t["aesthetic"]) - 4.0) / 3.0))
    return round(q, 3)


def _usable(t, med=None):
    if (t.get("score") or 0) < MIN_SCORE and _q(t, med) < MIN_SCORE + 0.1:
        return False, _w("low-quality", f"soft / unsteady / badly exposed (quality {t.get('score')})",
                         f"画面虚、晃或曝光不好（质量 {t.get('score')}）")
    dark = DARK if med is None else min(DARK, 0.5 * med)        # dark relative to the film: night stays night
    if t.get("bright") is not None and t["bright"] < dark and (t.get("exposure") or 0) < 0.35:
        return False, _w("too-dark", "too dark to read", "太暗，看不清")
    return True, None


def _hold(t, pol, speechy, med=None):
    lo, hi = pol["hold"]
    length = max(0.1, float(t["end"]) - float(t["start"]))
    if speechy:
        return round(length, 2), _w("hold-speech", "held as long as the words", "按说话的长度保留")
    q = max(0.0, min(1.0, _q(t, med)))
    want = lo + (hi - lo) * q
    hold = min(want, length)
    why = _w("hold", f"held {hold:.1f} s (template {lo:g}-{hi:g} s; quality {q:.2f})",
             f"保留 {hold:.1f} 秒（模板 {lo:g}-{hi:g} 秒，质量 {q:.2f}）", lo=lo, hi=hi, q=q)
    return round(hold, 2), why


def _speed(t, pol, hold_needed, rife, ramp_left, peak):
    """-> (kind, x, fit, why, choices)."""
    allowed = pol["speed"]
    steady = float(t.get("steady") or 0)
    motion = t.get("motion")
    length = float(t["end"]) - float(t["start"])
    fps = float(t.get("src_fps") or 0)
    even = fps >= 50 or rife
    c = {"normal": (0.6, _w("speed-normal", "played at 1x", "原速"))}
    if "slowmo" in allowed:
        f = 0.0
        if even and steady >= 0.6 and motion is not None and motion >= 4:
            f = 0.45 + 0.25 * min(1.0, motion / 15) + (0.2 if length < hold_needed else 0) + 0.1 * (steady - 0.6) / 0.4
        how = "RIFE in-between frames" if (rife and fps < 50) else f"{fps:g}p played at half speed"
        why = _w("speed-slowmo", f"slow motion: steady shot with movement in it ({how})",
                 f"慢动作：画面稳，里面有运动（{'RIFE 补帧' if rife and fps < 50 else f'{fps:g}p 半速'}）",
                 motion=motion, steady=steady, fps=fps)
        if not even and steady >= 0.6 and motion is not None and motion >= 4:
            why = None                       # P2: 30p at 0.5x judders without in-between frames
        if why:
            c["slowmo"] = (f, why)
    if "ramp" in allowed and ramp_left > 0 and peak:
        c["ramp"] = (0.9, _w("speed-ramp", "one speed ramp on the busiest shot (once per video)",
                               "全片唯一一次变速，放在动作最强的镜头", motion=motion))
    k, fit, amb, ranked = _pick(c)
    x = 0.5 if k == "slowmo" else 1.0
    return k, x, fit, c[k][1], ranked, amb


def _reframe(t, out_ratio, pol):
    src = _aspect(t.get("w"), t.get("h"))
    if not pol["reframe"] or not out_ratio or not src or abs(src - out_ratio) < 0.05:
        return "none", None
    if t.get("faces"):
        return "follow-face", _w("reframe-face", "the crop follows the face", "裁切跟随人脸")
    spread = t.get("subject_spread")
    if spread is not None and spread < SUBJECT_SPREAD and t.get("subject_xy"):
        x = t["subject_xy"][0]
        return "follow-subject", _w("reframe-subject", f"the crop follows the subject (at {int(x * 100)}% across)",
                                    f"裁切跟随主体（在画面 {int(x * 100)}% 处）", x=x)
    return "centre", _w("reframe-centre", "a wide scene with no single subject: a steady centre crop",
                        "大场景没有单一主体：居中稳定裁切")


def _transition(prev, t, pol, rife, beats):
    """The join into ``t`` from ``prev`` -> (kind, seconds, fit, why, ranked, ambiguous)."""
    allowed = pol["transitions"]
    if prev is None:
        return "open", 0.0, 1.0, _w("open", "opens the film", "开场"), [("open", 1.0)], False
    same_clip = prev["clip"] == t["clip"]
    db = abs((t.get("bright") or 0) - (prev.get("bright") or 0)) if t.get("bright") is not None and \
        prev.get("bright") is not None else None
    dl = _lab_d(prev.get("lab"), t.get("lab"))
    tod_change = bool(prev.get("time_of_day") and t.get("time_of_day") and prev["time_of_day"] != t["time_of_day"])
    place_change = bool(prev.get("city") and t.get("city") and prev["city"] != t["city"])
    c = {}
    if "cut" in allowed or "beat-cut" in allowed:
        f = 0.55
        if dl is not None and dl < COLOUR_JUMP:
            f += 0.15
        if same_clip:
            f += 0.1
        name = "beat-cut" if ("beat-cut" in allowed and beats) else "cut"
        c[name] = (min(f + (0.15 if name == "beat-cut" else 0), 0.95),
                   _w(name, "a hard cut on the music's beat" if name == "beat-cut" else "a hard cut: same light, same place",
                      "卡在音乐的拍点上硬切" if name == "beat-cut" else "硬切：光线和地点没变"))
    if "dissolve" in allowed:
        f = 0.6 if allowed[0] == "dissolve" else 0.35       # the template's own join (calm films: P1)
        bits_en, bits_zh = [], []
        if prev.get("aerial") and t.get("aerial") and not same_clip:
            f += 0.2
            bits_en.append("aerial to aerial")
            bits_zh.append("航拍接航拍")
        if db is not None and db >= LIGHT_JUMP:
            f += 0.25
            bits_en.append(f"the light changes ({prev.get('bright')}→{t.get('bright')})")
            bits_zh.append("光线变了")
        if dl is not None and dl >= COLOUR_JUMP:
            f += 0.2
            bits_en.append("the colour changes")
            bits_zh.append("色调变了")
        if tod_change:
            f += 0.2
            bits_en.append(f"{prev['time_of_day']} → {t['time_of_day']}")
            bits_zh.append("时间段变了")
        if place_change:
            f += 0.2
            bits_en.append(f"{prev['city']} → {t['city']}")
            bits_zh.append("换了地点")
        c["dissolve"] = (min(f, 0.95), _w("dissolve", f"a {pol['dissolve_s']:g} s dissolve: " +
                                          (", ".join(bits_en) or "a quiet join"),
                                          f"{pol['dissolve_s']:g} 秒叠化：" + ("，".join(bits_zh) or "安静地衔接"),
                                          tod=tod_change, place=place_change))
    if "match-cut" in allowed and dl is not None and not same_clip:
        both_move = (prev.get("pan_px_s") or 0) > 8 and (t.get("pan_px_s") or 0) > 8
        if dl < MATCH_LAB and both_move:
            c["match-cut"] = (0.8, _w("match-cut", "a match cut: the same colour and the camera keeps moving",
                                      "匹配剪辑：颜色一致，镜头运动连贯", lab_d=round(dl, 1)))
    pu, tu = prev.get("_use") or [prev["start"], prev["end"]], t.get("_use") or [t["start"], t["end"]]
    gap = same_clip and float(tu[0]) - float(pu[1]) > 0.05
    same_shot = same_clip and _shot_of(prev["id"]) == _shot_of(t["id"])
    # a cut inside one recording: time skipped (a gap), or the recording cuts there itself (a new shot) - a jump cut
    # when a face is on both sides; the same shot played on is no cut at all
    jump = gap or (same_clip and not same_shot)
    if same_clip and not jump:
        c = {"continuous": (0.95, _w("continuous", "the same take continues", "同一条镜头接着播"))}
    elif "morph" in allowed and jump and t.get("faces") and _same_framing(prev, t):
        if rife:
            c["morph"] = (0.85, _w("morph", "a morph cut hides the jump inside the same take (RIFE)",
                                   "同一条里的跳切用补帧平滑（RIFE）"))
        else:
            c["morph-fallback"] = (0.7, _w("punch-cover", "the jump cut is covered by a small punch-in (no RIFE yet)",
                                           "跳切用轻微推近遮住（还没有 RIFE）"))
    if not c:
        c["cut"] = (0.5, _w("cut", "a hard cut", "硬切"))
    if "morph" in c or "morph-fallback" in c:
        c = {k: v for k, v in c.items() if k in ("morph", "morph-fallback")}
    k, fit, amb, ranked = _pick(c)
    secs = pol["dissolve_s"] if k == "dissolve" else 0.3 if k == "morph" else 0.0
    return k, secs, fit, c[k][1], ranked, amb


def _grade(t, median_bright, pol):
    g = dict(look=pol["grade"], match_exposure=False, colour_match=False, deflicker=False)
    why = []
    if t.get("bright") is not None and median_bright is not None and abs(t["bright"] - median_bright) > 0.06:
        g["match_exposure"] = True
        why.append(_w("grade-match", f"brightness pulled toward the film's ({t['bright']:.2f} vs {median_bright:.2f})",
                      f"亮度向全片靠拢（{t['bright']:.2f} 对 {median_bright:.2f}）"))
    if t.get("lab") and t.get("_lab_med") and _lab_d(t["lab"], t["_lab_med"]) > COLOUR_JUMP:
        g["colour_match"] = True
        why.append(_w("grade-colour", "colour matched to the hero shot", "颜色匹配主镜头"))
    if (t.get("exposure") or 1) < 0.5 and t.get("aerial"):
        g["deflicker"] = True
        why.append(_w("grade-deflicker", "the drone's exposure pumps: deflicker", "无人机曝光忽明忽暗：去闪烁"))
    return g, why


def _text(t, pol, hold):
    if pol["text"] == "none":
        return dict(ok=False, where=None), _w("text-none", "no text in this template", "这个模板不加字")
    steady = float(t.get("steady") or 0)
    if hold < 3.0 or steady < 0.5:
        return dict(ok=False, where=None), _w("text-no", "too short or moving for a line to be read",
                                              "太短或太晃，字读不清")
    xy = t.get("subject_xy")
    where = "upper" if xy and xy[1] > 0.58 else "lower"
    if t.get("faces") and pol["text"] != "captions":
        where = "lower"
    return dict(ok=True, where=where), _w("text-ok", f"room for a line in the {where} third",
                                          f"{'上' if where == 'upper' else '下'}三分之一有地方放字", where=where)


# --------------------------------------------------------------------------- the plan
def plan(tiles, template, target_s=None, out_aspect=None, beats=False, overrides=None, judge=None, rife=None):
    """tiles (``brain.tiles``) + template id -> the per-shot treatment plan (module doc)."""
    pol = P.get(template)["policy"]
    rife = rife_available() if rife is None else rife
    out_ratio = _ratio(out_aspect)
    speechy_tpl = P.get(template)["recipe"] in ("talkinghead", "longform-to-short", "call-clips", "promo-recut")
    tiles = [dict(t) for t in tiles]
    brights = sorted(t["bright"] for t in tiles if t.get("bright") is not None)
    med_b = brights[len(brights) // 2] if brights else None
    usable_rank = sorted((t for t in tiles if _usable(t, med_b)[0]), key=lambda t: -_q(t, med_b))
    hero = usable_rank[0] if usable_rank else (tiles[0] if tiles else None)
    for t in tiles:
        t["_lab_med"] = hero.get("lab") if hero else None
    # which tiles go in: usable ones in time order until the target is met (best first when trimming)
    keep_ids = set()
    if target_s and not speechy_tpl:
        total, per_clip, left = 0.0, {}, list(usable_rank)
        while left and total < target_s * 1.05:
            # best shot first, but spread over the clips (a film of one take's ten moments is not a film)
            t = max(left, key=lambda x: _q(x, med_b) - CLIP_REPEAT * per_clip.get(x["clip"], 0))
            left.remove(t)
            h = min(pol["hold"][0] + (pol["hold"][1] - pol["hold"][0]) * _q(t, med_b),
                    float(t["end"]) - float(t["start"]))
            keep_ids.add(t["id"])
            per_clip[t["clip"]] = per_clip.get(t["clip"], 0) + 1
            total += h
    else:
        keep_ids = {t["id"] for t in usable_rank} or {t["id"] for t in tiles}
    motions = [t.get("motion") or 0 for t in tiles if t["id"] in keep_ids]
    peak_id = None
    if motions and pol["ramps"]:
        peak = max((t for t in tiles if t["id"] in keep_ids), key=lambda t: (t.get("motion") or 0) * (t.get("steady") or 0))
        peak_id = peak["id"]
    ramps_left, slowmo_used = pol["ramps"], 0
    slowmo_cap = max(1, len(keep_ids) // 4)
    out, prev = [], None
    ambiguous = []
    for t in tiles:
        ok, bad = _usable(t, med_b)
        row = dict(id=t["id"], clip=t["clip"], file=t.get("file"), start=t["start"], end=t["end"], thumb=t.get("thumb"),
                   t=t.get("t"), score=t.get("score"), faces=t.get("faces"), subject_frac=t.get("subject_frac"),
                   skip=False, why=[], choices={}, by="rules")
        if not ok or t["id"] not in keep_ids:
            row.update(skip=True, why=[bad or _w("not-needed", "not needed for the length", "时长够了，没用上")])
            out.append(row)
            continue
        speechy = speechy_tpl or (t.get("speech") or 0) >= 0.5
        hold, why_h = _hold(t, pol, speechy, med_b)
        best = t.get("best") or [t["start"], t["end"]]
        mid = (best[0] + best[1]) / 2
        a = max(float(t["start"]), mid - hold / 2)
        b = min(float(t["end"]), a + hold)
        if speechy:                                  # words are kept whole: the shot plays from start to end
            a, b = float(t["start"]), float(t["end"])
        sp, x, sfit, why_s, sranked, samb = _speed(t, pol, pol["hold"][0], rife, ramps_left,
                                                   t["id"] == peak_id)
        if sp == "slowmo":
            if slowmo_used >= slowmo_cap:
                sp, x, why_s = "normal", 1.0, _w("speed-normal", "1x (slow motion already used enough)",
                                                 "原速（慢动作已经够多）")
            else:
                slowmo_used += 1
                b = min(float(t["end"]), a + hold / 2)      # half the source time fills the hold at 0.5x
        if sp == "ramp":
            ramps_left -= 1
        rf, why_r = _reframe(t, out_ratio, pol)
        t["_use"] = [a, b]
        tk, ts, tfit, why_t, tranked, tamb = _transition(prev, t, pol, rife, beats)
        g, why_g = _grade(t, med_b, pol)
        tx, why_x = _text(t, pol, hold)
        stab = (t.get("steady") or 1) < SHAKY and (t.get("jitter_px") or 0) > 1.0
        punch = "none"
        if pol["punch_in"] and tk == "morph-fallback":
            punch = "jump-cover"
        row.update(use=[round(a, 2), round(b, 2)], hold_s=hold, speed=sp, speed_x=x, reframe=rf,
                   transition=dict(kind=tk, s=ts), grade=g, text=tx, punch_in=punch, stabilize=stab,
                   fit=round(min(sfit, tfit), 2),
                   why=[w for w in (why_t, why_h, why_s, why_r, why_x) if w] + why_g +
                   ([_w("stabilize", "a little shaky: stabilised", "有点晃：做稳定")] if stab else []),
                   choices=dict(transition=tranked, speed=sranked))
        if tamb or samb:
            row["ambiguous"] = [k for k, v in (("transition", tamb), ("speed", samb)) if v]
            ambiguous.append(row)
        out.append(row)
        prev = t
    if judge and ambiguous:
        try:
            calls = judge(ambiguous) or {}
        except Exception:  # noqa: BLE001  (no model: the rules' picks stand)
            calls = {}
        for row in ambiguous:
            c = calls.get(row["id"]) or {}
            for dim in row["ambiguous"]:
                pick = c.get(dim)
                if pick and pick in [k for k, _ in row["choices"].get(dim) or []]:
                    if dim == "transition":
                        row["transition"] = dict(kind=pick, s=pol["dissolve_s"] if pick == "dissolve" else 0.0)
                    else:
                        row["speed"], row["speed_x"] = pick, 0.5 if pick == "slowmo" else 1.0
                    row["by"] = "ai"
                    row["why"].insert(0, _w("ai", c.get("reason") or "the AI's call on a close one",
                                            c.get("reason") or "两种都合适，AI 选了这个"))
    for sid, ch in (overrides or {}).items():
        row = next((r for r in out if r["id"] == sid), None)
        if not row:
            continue
        for k, v in ch.items():
            if k == "transition":
                row["transition"] = dict(kind=v, s=pol["dissolve_s"] if v == "dissolve" else 0.0)
            elif k == "speed":
                row["speed"], row["speed_x"] = v, 0.5 if v == "slowmo" else 1.0
            elif k == "skip":
                row["skip"] = bool(v)
            elif k in ("reframe", "punch_in"):
                row[k] = v
        row["by"] = "her"
    used = [r for r in out if not r["skip"]]
    summary = dict(
        template=template, shots=len(out), used=len(used), seconds=round(sum(r["hold_s"] for r in used), 1),
        target_s=target_s, rife=rife,
        transitions={k: sum(1 for r in used if r["transition"]["kind"] == k)
                     for k in sorted({r["transition"]["kind"] for r in used})},
        speed={k: sum(1 for r in used if r["speed"] == k) for k in sorted({r["speed"] for r in used})},
        reframe={k: sum(1 for r in used if r["reframe"] == k) for k in sorted({r["reframe"] for r in used})},
        text_ok=sum(1 for r in used if r["text"]["ok"]), stabilize=sum(1 for r in used if r["stabilize"]),
        ambiguous=len(ambiguous), by_ai=sum(1 for r in out if r["by"] == "ai"),
        checks=dict(ramps=sum(1 for r in used if r["speed"] == "ramp") <= max(1, pol["ramps"]),
                    no_flash=all(r["transition"]["kind"] not in ("flash", "whip", "glitch", "light-leak") for r in used)))
    return dict(template=template, policy=_jsonable(pol), shots=out, summary=summary)


def _jsonable(pol):
    return {k: list(v) if isinstance(v, tuple) else v for k, v in pol.items()}


def ai_judge(complete=None, timeout=60):
    """A ``judge`` for ``plan``: the routed model settles the close calls from the numbers (text only)."""
    import json

    def run(rows):
        if complete is None:
            from vstudio import llm
            fn = llm.complete
        else:
            fn = complete
        brief = [dict(id=r["id"], choices=r["choices"], why=[w["en"] for w in r["why"]][:4]) for r in rows[:30]]
        prompt = ("Close calls in a premium edit (restraint first: hard cuts and dissolves, no gimmicks). For each "
                  f"shot pick from its choices.\n{json.dumps(brief)}\n\nReply "
                  '{"calls": {"<id>": {"transition": "<choice>", "speed": "<choice>", "reason": "short"}}}.')
        r = fn("planner", "You are a film editor.", prompt, schema=True, max_tokens=1500, timeout=timeout,
               cli_timeout=timeout, retries=0)
        if not isinstance(r, dict) or r.get("provider") == "none":
            return {}
        return ((r.get("json") or {}).get("calls")) or {}
    return run
