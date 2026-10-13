"""The editor brain of one project: its template, the per-shot plan and the generation proposals, kept with the
project and changeable by her.

    from vstudio.brain import store
    doc = store.show(project)                     # computes what is missing (cached in state/brain/), -> the doc below
    store.set_template(project, "beat-short")     # her choice (same recipe), by: her
    store.set_shot(project, "C2.S1", transition="cut")
    store.decide_gen(project, "g1a2b3c4", "approve", code="9f3e1a")   # her OK at this price; nothing is spent here
    store.decide_gen(project, "g1a2b3c4", "skip")

project.yaml keeps what she decided (``brain: {template: {id, by, at}, shots: {id: {...}}, gen: {id: {status, ...}}}``);
``state/brain/`` keeps what is computed (tiles, signals, plan, proposals: re-made on ``refresh``).

doc = {template {template, recipe, label, reason, by, confidence, alternatives}, plan {shots, summary},
       proposals [... with status], cost {n, cny, unknown}, stage, decisions [...]}
"""
import json
import os
import re
import time

from . import genplan as G
from . import presets as P
from . import template as T
from . import treat as TR

MEDIA_EXT = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".heic", ".webp")
VERTICAL = ("douyin", "tiktok", "youtube-shorts", "wechat-channels", "instagram")


class BrainError(ValueError):
    pass


def _dir(project):
    d = os.path.join(project.state_dir, "brain")
    os.makedirs(d, exist_ok=True)
    return d


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)


def _paths(v):
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    return []


def media_of(project):
    """Every media file the project is made from (project + item inputs), in order, no repeats."""
    out = []
    for v in (project.data.get("inputs") or {}).values():
        out += _paths(v)
    for it in project.data.get("items") or []:
        for v in (it.get("inputs") or {}).values():
            out += _paths(v)
    out = [p for p in dict.fromkeys(out) if p.lower().endswith(MEDIA_EXT) and os.path.exists(p)]
    return out


def target_seconds(text, params=None):
    """'a 90-second film' / '2-minute' / '45 秒' / '两分钟' -> seconds, or None."""
    t = text or ""
    m = re.search(r"(\d{1,4})\s*[- ]?\s*(?:seconds?|secs?|s\b|秒)", t, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d{1,3}(?:\.\d)?)\s*[- ]?\s*(?:minutes?|mins?|分钟)", t, re.I)
    if m:
        return float(m.group(1)) * 60
    zh = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5}
    m = re.search(r"([一两二三四五])分钟", t)
    if m:
        return zh[m.group(1)] * 60.0
    v = (params or {}).get("length_s") or (params or {}).get("max_s")
    return float(v) if v else None


def out_aspect(project):
    plats = [str(p).split(":")[0] for p in (project.data.get("params") or {}).get("platforms") or []]
    text = (project.data.get("prompt") or "").lower()
    if (plats and plats[0] in VERTICAL) or re.search(r"vertical first|竖屏|9:16", text):
        return "9:16"
    return None


def _her(project):
    b = project.data.get("brain")
    return b if isinstance(b, dict) else {}


def _save_her(project, b):
    project.data["brain"] = b
    project.save()


def _light_analysis(paths):
    """The footage facts alone (length, shape, the DJI log) as an analysis: no listening, no faces - enough to pick
    a template inside a footage recipe."""
    from vstudio import footage, places
    files = []
    for k, p in enumerate(paths):
        if footage.is_video(p):
            f = footage.facts(p)
            files.append(dict(id=f"f{k + 1}", path=p, kind="video", duration=f.get("dur"), speech=None,
                              orientation=f.get("orientation")))
            if places.srt_for(p):
                files.append(dict(id=f"t{k + 1}", path=places.srt_for(p), kind="text", shape="telemetry"))
        elif p.lower().endswith((".jpg", ".jpeg", ".png", ".heic", ".webp")):
            files.append(dict(id=f"f{k + 1}", path=p, kind="image"))
    return dict(files=files)


def _signals(project, paths, refresh=False, light=False):
    d = _dir(project)
    sp = os.path.join(d, "signals.json")
    cached = None if refresh else _read(sp)
    if cached and cached.get("paths") == paths and (light or not cached.get("light")):
        return cached["signals"], cached.get("analysis_files") or []
    if light:
        analysis = _light_analysis(paths)
    else:
        from vstudio.intake import inventory as I
        analysis = I.analyze(paths, asr="sample")
    facts = {}
    try:
        from vstudio import footage
        for p in paths:
            if footage.is_video(p):
                facts[p] = footage.facts(p)
    except Exception:  # noqa: BLE001
        pass
    s = T.signals(analysis, project.data.get("prompt") or "", footage_facts=facts)
    files = [{k: f.get(k) for k in ("id", "path", "kind", "duration", "speech", "talking_head")} for f in analysis["files"]]
    _write(sp, dict(paths=paths, signals=s, analysis_files=files, light=light, at=time.strftime("%Y-%m-%dT%H:%M:%S")))
    return s, files


def _tiles(project, paths, refresh=False, echo=None):
    d = _dir(project)
    tp = os.path.join(d, "tiles.json")
    cached = None if refresh else _read(tp)
    if cached and cached.get("paths") == paths:
        return cached["tiles"]
    from . import tiles as TI
    ts = TI.for_clips(paths, echo=echo)
    _keep_thumbs(d, ts)
    _write(tp, dict(paths=paths, tiles=ts, at=time.strftime("%Y-%m-%dT%H:%M:%S")))
    return ts


def _keep_thumbs(d, ts):
    """Each tile's still in the project (``state/brain/thumbs/``): the app shows files inside the project only."""
    import shutil
    from . import tiles as TI
    td = os.path.join(d, "thumbs")
    os.makedirs(td, exist_ok=True)
    for t in ts:
        dst = os.path.join(td, re.sub(r"[^A-Za-z0-9._-]", "_", t["id"]) + ".jpg")
        try:
            if t.get("thumb") and os.path.exists(t["thumb"]):
                shutil.copy(t["thumb"], dst)
            else:
                img = TI._grab(t["clip"], float(t.get("t") or 0), 320)
                if img is None:
                    continue
                import cv2
                cv2.imwrite(dst, img, [cv2.IMWRITE_JPEG_QUALITY, 82])
            t["thumb"] = dst
        except Exception:  # noqa: BLE001  (a missing still never fails the plan)
            continue


def sentences_of(project):
    """The spoken sentences of the project's first recording, once its transcript exists (a speech recipe's asr
    stage: ``state/jobs/<item>/asr/a1.json``, whisper segments in the recording's seconds) -> [{start, end, text}]."""
    import glob
    for p in sorted(glob.glob(os.path.join(project.state_dir, "jobs", "*", "asr", "a1.json"))):
        d = _read(p, {}) or {}
        segs = [dict(start=float(x["start"]), end=float(x["end"]), text=str(x.get("text") or "").strip())
                for x in d.get("segments") or [] if isinstance(x, dict) and "start" in x and "end" in x]
        if segs:
            return segs
    return None


def stage_of(project, have_tiles):
    ex = os.path.join(project.dir, "exports")
    if os.path.isdir(ex) and any(os.scandir(ex)):
        return "review"
    return "cut" if have_tiles else "planned"


def template_of(project, s):
    """Her template if she chose one; else the one the plan carried (intake); else classified now."""
    her = _her(project).get("template") or {}
    if her.get("by") == "her" and her.get("id") in P.PRESETS:
        return T.classify(s, keep=her["id"])
    d = T.classify(s, fixed_recipe=project.data["recipe"])
    if d and her.get("id") in P.PRESETS and P.get(her["id"])["recipe"] == project.data["recipe"] and \
            her["id"] != d["template"]:
        # the plan's pick (made with her words, before the project existed) stands; today's top is an alternative
        planned = T.classify(s, keep=her["id"])
        top = dict(P.card(d["template"], "en"), label_zh=P.label(d["template"], "zh"), score=None)
        planned.update(by=her.get("by") or "rules", reason=her.get("reason") or d["reason"],
                       confidence=her.get("confidence") or d["confidence"],
                       alternatives=[top] + [a for a in d["alternatives"] if a["id"] != her["id"]][:2])
        return planned
    return d


def show(project, refresh=False, shots=True, judge=None, echo=None, light=False):
    """The brain doc of a project (module doc). ``shots=False``: the template only (no decoding). ``light``: signals
    from the footage facts only (a footage recipe's draft step: no listening pass)."""
    paths = media_of(project)
    s, _files = _signals(project, paths, refresh, light)
    tpl = template_of(project, s)
    if tpl:
        tpl = dict(tpl, alternatives=[a for a in tpl.get("alternatives") or [] if a["recipe"] == project.data["recipe"]])
    doc = dict(template=tpl, plan=None, proposals=[], cost=dict(n=0, cny=0.0, unknown=0), stage="planned",
               media=len(paths))
    if not tpl:
        return doc
    her = _her(project)
    target = target_seconds(project.data.get("prompt") or "", project.data.get("params"))
    tiles = []
    vids = [p for p in paths if not p.lower().endswith((".jpg", ".jpeg", ".png", ".heic", ".webp"))]
    if shots and vids:
        tiles = _tiles(project, vids, refresh, echo)
        pl = TR.plan(tiles, tpl["template"], target_s=target, out_aspect=out_aspect(project),
                     overrides=her.get("shots"), judge=judge)
        doc["plan"] = pl
    doc["stage"] = stage_of(project, bool(tiles))
    props = G.propose(tpl["template"], doc["plan"], s, stage=doc["stage"], target_s=target, tiles=tiles,
                      sentences=sentences_of(project) if tpl["recipe"] in G.SPEECH_RECIPES else None)
    st = her.get("gen") or {}
    for x in props:
        x["code"] = G.confirm_code(x)
        if x["id"] in st:
            x.update({k: v for k, v in st[x["id"]].items() if k in GEN_KEYS})
    # proposals she approved / skipped earlier stay listed even when the plan no longer raises them
    for pid, rec in st.items():
        if not any(x["id"] == pid for x in props) and rec.get("snapshot"):
            props.append(dict(rec["snapshot"], **{k: rec[k] for k in GEN_KEYS if k in rec}, stale=True))
    doc["proposals"] = props
    doc["cost"] = G.total([x for x in props if x.get("status") == "proposed"])
    doc["decisions"] = decisions(doc)
    _write(os.path.join(_dir(project), "brain.json"), doc)
    return doc


# what her record of a proposal adds to it in the doc: her answer, and once generated the take and where it went
GEN_KEYS = ("status", "at", "by", "approved_cny", "file", "placed", "run", "error")
SPENT = ("generating", "generated", "placed", "unknown-charge")


def decisions(doc):
    """The brain's decisions in one list (template + each used shot's treatment), with who made them."""
    out = []
    t = doc.get("template")
    if t:
        out.append(dict(kind="template", id="template", value=t["template"], by=t["by"], reason=t["reason"]))
    for r in ((doc.get("plan") or {}).get("shots") or []):
        if r.get("skip"):
            continue
        out.append(dict(kind="shot", id=r["id"], value=dict(transition=r["transition"]["kind"], speed=r["speed"],
                                                           reframe=r["reframe"], hold_s=r["hold_s"]),
                        by=r["by"], reason=dict(en="; ".join(w["en"] for w in r["why"][:3]),
                                                zh="；".join(w["zh"] for w in r["why"][:3]))))
    return out


def set_template(project, tid):
    if tid not in P.PRESETS:
        raise BrainError(f"unknown template {tid}: one of {', '.join(P.ids())}")
    p = P.get(tid)
    if p["recipe"] != project.data["recipe"]:
        raise BrainError(f"{tid} is made with {p['recipe']}; this project is a {project.data['recipe']} project "
                         f"(start a new one from the plan for that)")
    b = _her(project)
    b["template"] = dict(id=tid, by="her", at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    params = project.data.setdefault("params", {})
    for k, v in p["params"].items():
        params[k] = v
    _save_her(project, b)
    return dict(ok=True, template=tid, params=p["params"])


SHOT_FIELDS = dict(transition=("cut", "beat-cut", "dissolve", "match-cut", "morph"), speed=("normal", "slowmo", "ramp"),
                   reframe=("none", "centre", "follow-subject", "follow-face"), skip=(True, False),
                   punch_in=("none", "jump-cover", "emphasis"))


def set_shot(project, sid, **change):
    for k, v in change.items():
        if k not in SHOT_FIELDS or v not in SHOT_FIELDS[k]:
            raise BrainError(f"{k}={v!r}: one of {SHOT_FIELDS.get(k)}")
    b = _her(project)
    shots = b.setdefault("shots", {})
    shots.setdefault(sid, {}).update(change)
    _save_her(project, b)
    return dict(ok=True, shot=sid, change=shots[sid], edit=_restyle(project))


def reset_shot(project, sid):
    b = _her(project)
    (b.get("shots") or {}).pop(sid, None)
    _save_her(project, b)
    return dict(ok=True, shot=sid, edit=_restyle(project))


def _restyle(project):
    """Her change reaches the drafted edit files at once (``steer.restyle``; the render watches them)."""
    from . import steer
    try:
        return steer.restyle(project)
    except Exception as e:  # noqa: BLE001  (the plan keeps her change; the next draft reads it)
        return [dict(error=str(e)[:200])]


def decide_gen(project, pid, action, code=None):
    """Her answer on a proposal: ``approve`` (with the proposal's confirm ``code`` = this price) or ``skip``.
    Approving records her OK only; generating goes through the Create spend gate."""
    if action not in ("approve", "skip", "undo"):
        raise BrainError("action: approve | skip | undo")
    doc = _read(os.path.join(_dir(project), "brain.json")) or show(project)
    prop = next((x for x in doc.get("proposals") or [] if x["id"] == pid), None)
    if not prop:
        raise BrainError(f"no proposal {pid}")
    b = _her(project)
    gen = b.setdefault("gen", {})
    if (gen.get(pid) or {}).get("status") in SPENT:
        raise BrainError(f"{pid} is {gen[pid]['status']}: it was generated (paid); take it out of the edit instead")
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    snap = {k: prop[k] for k in ("id", "kind", "anchor", "title", "why", "mode", "prompt", "source", "seconds",
                                 "provider", "model", "estimate", "ai_label") if k in prop}
    if action == "undo":
        gen.pop(pid, None)
    elif action == "skip":
        gen[pid] = dict(status="skipped", by="her", at=now, snapshot=snap)
    else:
        if not code or code != G.confirm_code(prop):
            raise BrainError("the price changed or the code is wrong: look at the proposal again and approve it")
        gen[pid] = dict(status="approved", by="her", at=now, approved_cny=(prop.get("estimate") or {}).get("cny"),
                        snapshot=snap)
    _save_her(project, b)
    return dict(ok=True, id=pid, status=(gen.get(pid) or {}).get("status", "proposed"),
                next=("generate through Create (estimate + confirm)" if action == "approve" else None))
