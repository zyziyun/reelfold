"""Where generated video would help this edit, as specific briefs with a price - proposed, never spent.

    from vstudio.brain import genplan
    props = genplan.propose(template, treatment, signals, stage="cut", place="Seattle")
    # [{id, kind, title {en, zh}, why {en, zh}, mode, prompt, source {clip, t, thumb} | None, seconds, provider,
    #   model, estimate {cny, unknown, verified, label}, anchor, status: proposed}]

What it looks for, by how far the edit has got (``stage``):

    planned   establishing   a footage film whose opening has no wide shot of the place
              short          the usable footage is well under the length she asked for
              cover          no frame clean enough for a cover background
    cut       bridge         two shots the cut joins across a big jump (place / day / light) in a narrated piece
              weak           a shot the cut needs (the only one of its clip) that is too short, shaky or dark:
                             a steady image-to-video take from its best still
              broll          a talking head on screen for a long stretch with nothing else (``sentences``): one
                             illustrative shot for what is said there
    review    (the planner runs again on the rendered cut's QC: a flicker / shake left after stabilising -> weak)

Prices come from the Create rate cards (``vstudio.create.costs.price_job``); the provider is the first one with a
rate card in ``PROVIDERS`` (Kling first). Nothing here calls a service: a proposal waits for her Approve, and even
then generation goes through the Create spend gate (estimate + confirm code). Autopilot only proposes.
Generated shots are marked AI-generated in the post (platform rules).
"""
import hashlib

from . import presets as P

PROVIDERS = (("kling-mcp", "kling-video-v3_0_omni", "720p"), ("minimax", "MiniMax-Hailuo-02", "768p"),
             ("veo", "veo-3.1-fast", "720p"))
IMAGE = ("kling-mcp", "kling-image-v3_0_omni")
STAGES = ("planned", "cut", "review")
FOOTAGE_RECIPES = ("vlog", "photo-story")
SPEECH_RECIPES = ("talkinghead", "longform-to-short", "promo-recut", "call-clips")
BROLL_AFTER_S = 30.0       # a talking head alone on screen this long gets one illustrative shot
BROLL_MAX = 3              # at most this many per video (restraint: the talk is the film)
SHORT_SHARE = 0.8          # usable footage under this share of the target length -> extra shots


def _id(kind, anchor):
    return "g" + hashlib.sha1(f"{kind}\0{anchor}".encode()).hexdigest()[:8]


def price(seconds, kind="video"):
    """-> (provider, model, estimate) for the first provider with a rate card."""
    from vstudio.create import costs
    if kind == "image":
        e = costs.price_job(IMAGE[0], IMAGE[1], 1, kind="image")
        return IMAGE[0], IMAGE[1], dict(cny=e.get("cny"), unknown=e.get("unknown"), verified=e.get("verified"),
                                        label=e.get("label"))
    for prov, model, res in PROVIDERS:
        try:
            e = costs.price_job(prov, model, seconds, res)
        except Exception:  # noqa: BLE001  (a rate card that does not parse: next provider)
            continue
        if not e.get("unknown"):
            return prov, model, dict(cny=e.get("cny"), unknown=False, verified=e.get("verified"), label=e.get("label"),
                                     seconds_billed=e.get("seconds_billed"), resolution=res)
    prov, model, res = PROVIDERS[0]
    return prov, model, dict(cny=None, unknown=True, verified=False, label=None, resolution=res)


def _src(row):
    if not row:
        return None
    return dict(clip=row.get("clip"), t=row.get("t"), thumb=row.get("thumb"), shot=row.get("id"))


def _mk(kind, anchor, title, why, mode, prompt, seconds, source=None, img=False):
    prov, model, est = price(seconds, "image" if img else "video")
    return dict(id=_id(kind, anchor), kind=kind, anchor=anchor, title=title, why=why, mode=mode, prompt=prompt,
                source=source, seconds=seconds, provider=prov, model=model, estimate=est, status="proposed",
                ai_label=True)


def propose(template, treatment=None, signals=None, stage="cut", place=None, target_s=None, sentences=None,
            tiles=None):
    """-> proposals (module doc), most useful first. ``treatment``: ``treat.plan`` output (None at ``planned``)."""
    p = P.get(template)
    recipe = p["recipe"]
    s = signals or {}
    shots = (treatment or {}).get("shots") or []
    used = [r for r in shots if not r.get("skip")]
    out = []
    where = place or next((t.get("city") for t in tiles or [] if t.get("city")), None)
    where_txt = f" over {where}" if where else ""
    stage_n = STAGES.index(stage) if stage in STAGES else 1
    # ---- planned: the film as a whole
    if recipe in FOOTAGE_RECIPES and (s.get("videos") or tiles):
        first = used[0] if used else None
        wide = [r for r in used if (r.get("reframe") in ("none", "centre")) and not r.get("faces")]
        aerial = bool(s.get("aerial")) or any(t.get("aerial") for t in tiles or [])
        if first is not None and not aerial and not wide:
            out.append(_mk("establishing", "open", dict(en="An establishing shot to open", zh="开场的全景镜头"),
                           dict(en="the film opens close: nothing shows where we are",
                                zh="开场就是近景，看不出在哪里"),
                           "text-to-video", f"A slow, wide establishing aerial shot{where_txt} at the same time of day "
                           f"as the footage, gentle forward drift, natural colour, no text, no people in focus.", 5))
        have = sum(r.get("hold_s") or 0 for r in used)
        if target_s and used and have < target_s * SHORT_SHARE:
            missing = target_s - have
            best = max(used, key=lambda r: r.get("score") or 0)
            n = max(1, min(3, int(round(missing / 5))))
            out.append(_mk("short", "length", dict(en=f"{n} more shot{'s' if n > 1 else ''} to reach {int(target_s)} s",
                                                   zh=f"再补 {n} 个镜头，凑够 {int(target_s)} 秒"),
                           dict(en=f"the usable footage gives {have:.0f} s of the {int(target_s)} s asked",
                                zh=f"能用的素材只有 {have:.0f} 秒，要求 {int(target_s)} 秒"),
                           "image-to-video", "Continue this exact scene with a slow, steady camera move in the same "
                           "light; keep every detail of the place; no new objects; no text.", 5 * n, _src(best)))
    if tiles and not any((t.get("score") or 0) >= 0.6 and 0.3 <= (t.get("bright") or 0) <= 0.8 for t in tiles):
        out.append(_mk("cover", "cover", dict(en="A cover background", zh="封面背景图"),
                       dict(en="no frame is sharp and well lit enough for a cover", zh="没有足够清晰、亮度合适的帧做封面"),
                       "text-to-image", f"A calm, premium photograph{where_txt} matching the film's light, room at the "
                       "bottom third for a title, no text.", 1, img=True))
    # ---- cut: shot by shot
    if stage_n >= 1 and used:
        narrated = recipe == "photo-story" and p["params"].get("mode") == "narration"
        for a, b in zip(used, used[1:]):
            kind = (b.get("transition") or {}).get("kind")
            big = kind == "dissolve" and any(w.get("code") == "dissolve" and ((w.get("params") or {}).get("tod") or
                                                                             (w.get("params") or {}).get("place"))
                                             for w in b["why"])
            if narrated and big:
                out.append(_mk("bridge", f"{a['id']}>{b['id']}",
                               dict(en=f"A bridge between {a['id']} and {b['id']}", zh=f"{a['id']} 和 {b['id']} 之间的过渡镜头"),
                               dict(en="the story jumps in place or time here; a short bridge carries the voice over it",
                                    zh="这里地点或时间跳得大，一个过渡镜头让旁白接得上"),
                               "first-last-frame", "A smooth 4-second camera move that starts on the first frame and "
                               "ends on the second, same light as both, no new objects, no text.", 5,
                               dict(_src(a), end=_src(b))))
        clips = {}
        for r in shots:
            clips.setdefault(r["clip"], []).append(r)
        for clip, rows in clips.items():
            if any(not r.get("skip") for r in rows):
                continue
            bad = [r for r in rows if any(w.get("code") in ("low-quality", "too-dark") for w in r.get("why") or [])]
            if not bad:
                continue
            r = max(bad, key=lambda x: x.get("score") or 0)
            dark = any(w.get("code") == "too-dark" for w in r["why"])
            out.append(_mk("weak", r["id"], dict(en=f"A steady take of {r.get('file') or r['id']}",
                                                 zh=f"{r.get('file') or r['id']} 的稳定版本"),
                           dict(en="the only shot of this moment is too dark to use" if dark else
                                "the only shot of this moment is too shaky or soft to use",
                                zh="这个时刻只有这一条，太暗了" if dark else "这个时刻只有这一条，太晃或太虚"),
                           "image-to-video", "Animate this still with a slow, steady camera move; keep the scene and "
                           "its light exactly; " + ("lift the shadows naturally; " if dark else "") + "no new objects; "
                           "no text.", 5, _src(r)))
    if stage_n >= 1 and recipe in SPEECH_RECIPES and sentences:
        run_s, run = 0.0, []
        for snt in sentences:
            run.append(snt)
            run_s = float(snt["end"]) - float(run[0]["start"])
            if run_s >= BROLL_AFTER_S:
                k = len(run) // 2
                mid = run[k]
                text = " ".join(str(x.get("text") or "").strip() for x in run[max(0, k - 1):k + 2])[:160]
                out.append(_mk("broll", f"{run[0]['start']:.0f}",
                               dict(en=f"One illustrative shot at {int(float(mid['start']))} s",
                                    zh=f"{int(float(mid['start']))} 秒处加一个示意镜头"),
                               dict(en=f"{int(run_s)} s of talking head with nothing else on screen",
                                    zh=f"连续 {int(run_s)} 秒只有人在说话"),
                               "text-to-video", f"A calm, realistic 5-second shot that illustrates: \"{text}\". "
                               "Natural light, no text, no faces.", 5,
                               dict(t=float(mid["start"]), sentence=text)))
                run, run_s = [], 0.0
    brolls = [x for x in out if x["kind"] == "broll"]
    if len(brolls) > BROLL_MAX:                    # spread the few kept over the talk
        step = len(brolls) / BROLL_MAX
        keep = {brolls[int(i * step + step / 2)]["id"] for i in range(BROLL_MAX)}
        out = [x for x in out if x["kind"] != "broll" or x["id"] in keep]
    order = dict(weak=0, establishing=1, bridge=2, short=3, broll=4, cover=5)
    out.sort(key=lambda x: order.get(x["kind"], 9))
    return out


def total(props, statuses=None):
    st = statuses or {}
    live = [x for x in props if (st.get(x["id"]) or {}).get("status", x["status"]) != "skipped"]
    known = [x["estimate"]["cny"] for x in live if x["estimate"].get("cny") is not None]
    return dict(n=len(live), cny=round(sum(known), 2), unknown=sum(1 for x in live if x["estimate"].get("cny") is None))


def confirm_code(prop):
    """The code an Approve must carry: the proposal at this price (a changed price needs a new Approve)."""
    e = prop.get("estimate") or {}
    return hashlib.sha1(f"{prop['id']}\0{prop['provider']}\0{prop['model']}\0{e.get('cny')}\0{prop['seconds']}".encode()
                        ).hexdigest()[:6]
