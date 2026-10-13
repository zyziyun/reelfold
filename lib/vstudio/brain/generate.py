"""A "Could be generated" proposal she approves: priced in the Create spend gate, generated only after her confirm
there, and placed into the edit at the proposed spot - which she can take out again (Undo).

    from vstudio.brain import generate as GN
    est = GN.estimate(project, "g1a2b3c4")         # the gate's sheet: price, the most it can cost, month left,
                                                   # every reason it would be refused now (``codes``); nothing sent
    r = GN.generate(project, "g1a2b3c4", est["id"], est["confirm_code"], est["max_cny"], code=prop["code"])
    # her click: the approval at this price is recorded, ONE submit to the provider (Kling first), the take is
    # downloaded into state/brain/gen/ and placed in the edit -> {ok, status placed | generated | failed |
    # unknown-charge, file, placed}
    GN.unplace(project, "g1a2b3c4")                # Undo: out of the edit again (the paid take is kept)
    GN.place(project, "g1a2b3c4")                  # put it back

Only ``generate`` spends, and only with an estimate id + its confirm code + the max she saw (``vstudio.create.oneoff``:
the same gate as an episode's finals - one OK = one submit, month cap, the service ready, never retried). Nothing in
the autopilot, the brain's ``show`` or a stage calls it.

Where a take goes (``place``), by recipe:
    vlog (calm)    a segment in work/edit.json (``ai: true``, ``brain: <id>``) at the anchor: the opening, after the
                   shot it bridges from, where the weak shot was, or the end; the render watches the file
    vlog (fun)     a shot in work/edit.json's beat list (4 beats for an opening / a bridge, else 2)
    photo-story    a video shot in work/spec.py's SCRIPT, in the unit of the shot it follows
    talkinghead    a cut-away at the sentence it illustrates (``brain.gen.<id>.placed``; compose reads it)
A cover background is generated and kept (``status: generated``) for the cover step; it is not put in the video.
"""
import json
import os
import re
import subprocess
import time

from . import store as ST

PLACEABLE = ("establishing", "short", "bridge", "weak", "broll")


def owner(project):
    d = os.path.join(project.state_dir, "brain", "gen")
    os.makedirs(d, exist_ok=True)
    return d


def _doc(project):
    return ST._read(os.path.join(ST._dir(project), "brain.json")) or ST.show(project)


def proposal(project, pid):
    prop = next((x for x in _doc(project).get("proposals") or [] if x["id"] == pid), None)
    if not prop:
        raise ST.BrainError(f"no proposal {pid}")
    return prop


def _frame(src, t, out):
    from vstudio import media
    try:
        subprocess.run([media.ffmpeg_bin(), "-v", "error", "-y", "-ss", f"{max(0.0, float(t or 0)):.3f}", "-i", src,
                        "-frames:v", "1", "-vf", "scale='min(1920,iw)':-2", "-q:v", "2", out], capture_output=True,
                       timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return out if os.path.exists(out) else None


def _aspect(project, prop):
    a = ST.out_aspect(project)
    if a:
        return a
    src = (prop.get("source") or {}).get("clip") or next(iter(ST.media_of(project)), None)
    try:
        from vstudio import media
        info = media.probe(src)
        return "9:16" if info["display_h"] > info["display_w"] else "16:9"
    except Exception:  # noqa: BLE001
        return "16:9"


def job_of(project, prop):
    """The proposal as a generation job (``oneoff`` shape): the brief, its price's provider / model, and the stills
    it starts from cut at full size from her footage (image-to-video: the shot's best second; first-last-frame:
    both ends of the jump)."""
    d = owner(project)
    kind = "image" if prop["mode"] == "text-to-image" else "video"
    refs = {}
    src = prop.get("source") or {}
    kling = prop["provider"] == "kling-mcp"
    if prop["mode"] in ("image-to-video", "first-last-frame") and src.get("clip"):
        a = _frame(src["clip"], src.get("t"), os.path.join(d, f"{prop['id']}_first.jpg"))
        if a:
            refs["image_1" if kling else "first_frame"] = a
        end = src.get("end") or {}
        if prop["mode"] == "first-last-frame" and end.get("clip"):
            b = _frame(end["clip"], end.get("t"), os.path.join(d, f"{prop['id']}_last.jpg"))
            if b:
                refs["image_2" if kling else "last_frame"] = b
    est = prop.get("estimate") or {}
    prompt = prop["prompt"]
    if kling and "image_2" in refs:
        prompt = "Start exactly on 图片1 and end exactly on 图片2. " + prompt
    elif kling and refs:
        prompt = "Start exactly on 图片1. " + prompt
    return dict(id=prop["id"], kind=kind, provider=prop["provider"], model=prop["model"], seconds=prop["seconds"],
                resolution=est.get("resolution"), aspect=_aspect(project, prop), prompt=prompt, refs=refs)


def estimate(project, pid):
    """The spend gate's sheet for one proposal (nothing is sent): {id, confirm_code, max_cny, subtotal_cny, lines,
    codes [refusals now], month {cap, used, left_after}, expires_at, proposal {id, code, title, mode, seconds}}."""
    from vstudio.create import oneoff
    prop = proposal(project, pid)
    if prop.get("status") not in (None, "proposed", "approved", "failed"):
        raise ST.BrainError(f"{pid} is {prop.get('status')}: nothing to generate")
    est = oneoff.estimate(owner(project), job_of(project, prop))
    est["proposal"] = {k: prop.get(k) for k in ("id", "code", "kind", "title", "why", "mode", "seconds", "provider",
                                                "model", "estimate")}
    return est


def _save(project, pid, **fields):
    b = ST._her(project)
    rec = b.setdefault("gen", {}).setdefault(pid, {})
    rec.update(fields)
    ST._save_her(project, b)
    _refresh_doc(project)
    return rec


def _refresh_doc(project):
    """The cached doc the desk reads (state/brain/brain.json) follows her record at once (computed parts cached)."""
    try:
        from vstudio.project.core import Project
        ST.show(Project(project.dir), light=True)
    except Exception:  # noqa: BLE001  (the record in project.yaml is the truth; the next show catches up)
        pass


def check(project, pid, estimate_id, confirm_code, max_cny, code=None):
    """Everything ``generate`` checks before the paid submit, with no side effect -> {ok} or the refusal
    (BrainError / CreateError)."""
    from vstudio.create import oneoff
    from . import genplan as G
    prop = proposal(project, pid)
    if prop.get("status") not in (None, "proposed", "approved", "failed"):
        raise ST.BrainError(f"{pid} is {prop.get('status')}: nothing to generate")
    if (code or prop.get("code")) != G.confirm_code(prop):
        raise ST.BrainError("the price changed or the code is wrong: look at the proposal again and approve it")
    oneoff.gate(owner(project), job_of(project, prop), estimate_id, confirm_code, max_cny)
    return dict(ok=True, id=pid)


def generate(project, pid, estimate_id, confirm_code, max_cny, code=None, on_event=None, place_it=True):
    """Her confirm in the gate: approve at this price (``code`` = the proposal's), then the one paid submit, the
    download, the placement. -> {ok, id, status, file?, placed?, cny?, error?}."""
    from vstudio.create import oneoff
    from vstudio.create.i18n import CreateError
    from vstudio.project.core import Project
    prop = proposal(project, pid)
    if prop.get("status") not in (None, "proposed", "approved", "failed"):
        raise ST.BrainError(f"{pid} is {prop.get('status')}: nothing to generate")
    if prop.get("status") == "approved" and not code:
        code = prop.get("code")
    job = job_of(project, prop)
    oneoff.gate(owner(project), job, estimate_id, confirm_code, max_cny)     # refused here: nothing recorded
    ST.decide_gen(project, pid, "approve", code=code)          # the code = this price; a changed price is refused
    project = Project(project.dir)
    _save(project, pid, status="generating", at=time.strftime("%Y-%m-%dT%H:%M:%S"), estimate=estimate_id)
    try:
        res = oneoff.run(owner(project), job, estimate_id, confirm_code, max_cny, on_event=on_event)
    except CreateError as e:                                   # refused at the last moment: nothing was sent
        _save(Project(project.dir), pid, status="approved", error=e.code)
        raise
    project = Project(project.dir)
    run = dict(task=res.get("task"), state=res["state"], cny=res.get("cny"), provider=res.get("provider"),
               model=res.get("model"), at=time.strftime("%Y-%m-%dT%H:%M:%S"), code=res.get("code"))
    if res["state"] != "done":
        _save(project, pid, status="failed" if res["state"] == "failed" else "unknown-charge", run=run,
              error=res.get("error"))
        return dict(ok=False, id=pid, status=res["state"], code=res.get("code"), error=res.get("error"))
    _save(project, pid, status="generated", run=run, file=res["files"][0], files=res["files"])
    out = dict(ok=True, id=pid, status="generated", file=res["files"][0], cny=res.get("cny"))
    if place_it and prop["kind"] in PLACEABLE:
        out.update(place(Project(project.dir), pid))
    return out


# --------------------------------------------------------------------------- placing a take in the edit
def _rec(project, pid):
    rec = (ST._her(project).get("gen") or {}).get(pid)
    if not rec or not rec.get("file") or not os.path.exists(rec["file"]):
        raise ST.BrainError(f"{pid} has no generated take to place")
    return rec


def _dur(path):
    from vstudio import media
    try:
        return float(media.probe(path)["duration"])
    except Exception:  # noqa: BLE001
        return 5.0


def _anchor_index(lst, snap, doc):
    """Where in an edit list (segments / shots carrying ``brain`` ids, in order) the take goes."""
    kind, anchor = snap.get("kind"), str(snap.get("anchor") or "")
    if kind == "establishing" or anchor == "open":
        return 0
    if kind == "short" or anchor == "length":
        return len(lst)
    ids = [s.get("brain") for s in lst]
    if kind == "bridge" and ">" in anchor:
        a = anchor.split(">")[0]
        if a in ids:
            return ids.index(a) + 1
    order = [r["id"] for r in (((doc or {}).get("plan") or {}).get("shots") or [])]
    if anchor in order:                              # a weak shot: after the last used shot planned before it
        k = order.index(anchor)
        best = 0
        for i, sid in enumerate(ids):
            if sid in order and order.index(sid) < k:
                best = i + 1
        return best
    return len(lst)


def _items(project):
    return [it["id"] for it in project.data.get("items") or []]


def place(project, pid):
    """Put her generated take into every item's edit at the proposal's spot -> {status: placed, placed {...}}.
    Placing twice is a no-op."""
    rec = _rec(project, pid)
    snap = rec.get("snapshot") or {}
    if rec.get("status") == "placed":
        return dict(status="placed", placed=rec.get("placed"))
    doc = _doc(project)
    file = os.path.realpath(rec["file"])
    secs = _dur(file)
    recipe = project.data["recipe"]
    done = []
    if recipe == "vlog":
        for item in _items(project):
            p = os.path.join(project.dir, "items", item, "work", "edit.json")
            if _place_edit(p, pid, file, secs, snap, doc):
                done.append(dict(item=item, file=p))
    elif recipe == "photo-story":
        for item in _items(project):
            p = os.path.join(project.dir, "items", item, "work", "spec.py")
            if _place_spec(p, pid, file, snap, doc, project):
                done.append(dict(item=item, file=p))
    elif recipe in ("talkinghead",) and snap.get("kind") == "broll":
        done = [dict(item=item, file=None) for item in _items(project)]
    if not done:
        raise ST.BrainError(f"{pid}: this project's edit has no place for it yet (draft the edit first)")
    placed = dict(items=done, file=file, seconds=round(secs, 2), at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    _save(project, pid, status="placed", placed=placed)
    return dict(status="placed", placed=placed)


def _clip_id(pid):
    return f"ai_{pid}"


def _place_edit(path, pid, file, secs, snap, doc):
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return False
    if cfg.get("starter"):
        return False
    fun = cfg.get("style") == "fun"
    key = "shots" if fun else "segments"
    lst = list(cfg.get(key) or [])
    if any(s.get("clip") == _clip_id(pid) for s in lst):
        return True
    cfg.setdefault("clips", {})[_clip_id(pid)] = file
    k = _anchor_index(lst, snap, doc)
    if fun:
        new = dict(clip=_clip_id(pid), start=0.0, beats=4 if snap.get("kind") in ("establishing", "bridge") else 2,
                   ai=True, brain=pid)
    else:
        new = dict(clip=_clip_id(pid), start=0.0, dur=round(max(1.0, secs - 0.1), 2), ai=True, brain=pid)
    lst.insert(k, new)
    cfg[key] = lst
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return True


def _place_spec(path, pid, file, snap, doc, project):
    from . import steer
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    if "SYNTHETIC" in text[:600]:
        return False
    if f'"v{file}"' in text:
        return True
    by_id = {os.path.splitext(os.path.basename(p))[0]: dict(path=p) for p in ST.media_of(project)}
    rows = {r["id"]: r for r in (((doc or {}).get("plan") or {}).get("shots") or [])}
    anchor = str(snap.get("anchor") or "")
    after = None
    if snap.get("kind") == "bridge" and ">" in anchor:
        after = rows.get(anchor.split(">")[0])
    elif anchor in rows:
        after = rows[anchor]
    elif snap.get("kind") == "short":
        used = steer.used(doc)
        after = used[-1] if used else None
    after_clip = None
    if after is not None:
        after_clip = next((k for k, v in by_id.items() if os.path.realpath(v["path"]) == os.path.realpath(after["clip"])),
                          None)
    new = steer.photo_shot(text, file, after_clip=after_clip, by_id=by_id, brain=pid)
    if not new:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return True


def unplace(project, pid):
    """Undo: take her generated take out of every item's edit again (the paid take is kept in state/brain/gen and
    can be put back) -> {status: generated}."""
    rec = (ST._her(project).get("gen") or {}).get(pid) or {}
    if rec.get("status") != "placed":
        raise ST.BrainError(f"{pid} is not in the edit")
    for it in (rec.get("placed") or {}).get("items") or []:
        p = it.get("file")
        if not p or not os.path.exists(p):
            continue
        if p.endswith(".json"):
            _unplace_edit(p, pid)
        elif p.endswith(".py"):
            _unplace_spec(p, rec.get("file"))
    _save(project, pid, status="generated", placed=None, unplaced_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    return dict(status="generated")


def _unplace_edit(path, pid):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    key = "shots" if cfg.get("style") == "fun" else "segments"
    cfg[key] = [s for s in cfg.get(key) or [] if s.get("clip") != _clip_id(pid)]
    (cfg.get("clips") or {}).pop(_clip_id(pid), None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _unplace_spec(path, file):
    import ast
    from . import steer
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    lines = text.splitlines(keepends=True)
    for _ui, lst, sh in steer._script_shots(tree):
        src = sh.elts[0].value if isinstance(sh.elts[0], ast.Constant) else None
        if src != f"v{os.path.realpath(file)}" and src != f"v{file}":
            continue
        s = steer._offset(lines, sh.lineno, sh.col_offset)
        e = steer._offset(lines, sh.end_lineno, sh.end_col_offset)
        m = re.match(r"\s*,\s*", text[e:])
        if m:
            e += m.end()
        else:
            m2 = re.search(r",\s*$", text[:s])
            if m2:
                s = m2.start()
        new = text[:s] + text[e:]
        try:
            ast.parse(new)
        except SyntaxError:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        return
