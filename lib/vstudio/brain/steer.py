"""The shot plan steering every footage builder: each builder's own edit decisions, made from the brain's plan
(``treat.plan`` with her per-shot changes applied), so what the project page says is what the render does.

    from vstudio.brain import steer
    doc = steer.plan_doc(project_dir)                       # the brain doc (cached; computed from the footage facts)
    steer.calm(doc, clips)       # calm vlog: [{clip, start, dur, speed?, xfade, stabilize?, brain}] (build_vlog)
    steer.fun(doc, clips)        # beat short: [{clip, start, beats 1|2|4, ramp? "fast-slow-fast" | "slowmo", brain}]
    steer.annotate(picks, doc, clips, fun=False)   # the AI's own windows get the plan's treatment where they overlap
    steer.photo_line(doc, by_id) / steer.photo_fix(text, doc, by_id)   # photo story: moments, stills, joins, text
    steer.talk(doc, source)      # talking head: [{a, b, join morph | cut | punch, brain, by}] source spans
    steer.restyle(project)       # her change of a shot -> the drafted edit files follow it (render goes stale)

``clips`` = {edit clip id: path}. A row of the plan carries ``by``: rules | ai | her; her rows always win over what a
drafter wrote, the rules' only where the drafter left the decision open.
"""
import ast
import json
import os

BEAT_S = 60.0 / 108          # the fun reel's built-in bed (vlog.FUN_BPM)
RAMP = "fast-slow-fast"       # the one speed ramp of a beat short (funvlog.frames.RAMPS)
HARD = ("cut", "beat-cut", "match-cut", "morph", "morph-fallback")
JOIN_PS = {"dissolve": "fade", "cut": "cut", "beat-cut": "cut", "match-cut": "cut"}


def plan_doc(project_dir, light=True):
    """The project's brain doc (its cache, else computed from the footage facts) or None."""
    try:
        from vstudio.project.core import Project
        from . import store as BS
        return BS.show(Project(project_dir), light=light)
    except Exception:  # noqa: BLE001  (no shot analysis here: the builders work from their own picks)
        return None


def cached_doc(project_dir):
    """The brain doc as last computed (``state/brain/brain.json``), never computing - for stage keys and stages that
    must stay quick."""
    try:
        with open(os.path.join(project_dir, "state", "brain", "brain.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def used(doc):
    return [r for r in (((doc or {}).get("plan") or {}).get("shots") or []) if not r.get("skip") and r.get("use")]


def _real(p):
    try:
        return os.path.realpath(p)
    except (TypeError, ValueError):
        return p


def _by_real(clips):
    return {_real(p): k for k, p in clips.items()}


def _join_s(r, doc):
    """Seconds of the join INTO this shot: a dissolve's length, 0 for a hard cut."""
    k = (r.get("transition") or {}).get("kind")
    if k == "dissolve":
        pol = ((doc or {}).get("plan") or {}).get("policy") or {}
        return float((r.get("transition") or {}).get("s") or pol.get("dissolve_s") or 0.8)
    return 0.0 if k in HARD else None


# --------------------------------------------------------------------------- calm vlog (build_vlog.py)
def calm(doc, clips):
    """The plan's used shots as build_vlog segments: the window, slow motion at 0.5x, the join into it (``xfade``:
    a dissolve's seconds, 0 = a hard cut) and stabilise - each tagged with its shot id (``brain``)."""
    by_real = _by_real(clips)
    out = []
    for r in used(doc):
        cid = by_real.get(_real(r["clip"]))
        if cid is None:
            continue
        a, b = r["use"]
        seg = dict(clip=cid, start=round(float(a), 2), dur=round(max(1.0, float(b) - float(a)), 2), brain=r["id"])
        if r.get("speed") == "slowmo":
            seg["speed"] = 0.5
        j = _join_s(r, doc)
        if j is not None and out:
            seg["xfade"] = round(j, 2)
        if r.get("stabilize"):
            seg["stabilize"] = True
        out.append(seg)
    return out


# --------------------------------------------------------------------------- beat short (build_fun.py)
def beats_of(hold_s, beat_s=BEAT_S):
    """A hold -> the beat count it lands on (1, 2 or 4: the grid build_fun cuts on)."""
    n = float(hold_s or 0) / beat_s
    return min((1, 2, 4), key=lambda k: abs(k - n))


def fun(doc, clips, beat_s=BEAT_S):
    """The plan's used shots as build_fun shots: beat-aligned holds, the single ramp (4 beats), slow motion where
    planned (``ramp: "slowmo"``: RIFE in-betweens when the source is under 50p and RIFE is downloaded)."""
    by_real = _by_real(clips)
    out = []
    for r in used(doc):
        cid = by_real.get(_real(r["clip"]))
        if cid is None:
            continue
        shot = dict(clip=cid, start=round(float(r["use"][0]), 2), beats=beats_of(r.get("hold_s"), beat_s),
                    brain=r["id"])
        if r.get("speed") == "ramp":
            shot.update(ramp=RAMP, beats=4)
        elif r.get("speed") == "slowmo":
            shot.update(ramp="slowmo", beats=max(2, shot["beats"]))
        out.append(shot)
    return out


def _row_at(rows, path, t):
    """The plan row of ``path`` whose window holds ``t`` (else the nearest one of that clip) or None."""
    rp = _real(path)
    mine = [r for r in rows if _real(r["clip"]) == rp]
    if not mine:
        return None
    hit = [r for r in mine if float(r["use"][0]) - 0.5 <= t <= float(r["use"][1]) + 0.5]
    if hit:
        return hit[0]
    return min(mine, key=lambda r: min(abs(t - float(r["use"][0])), abs(t - float(r["use"][1]))))


def annotate(picks, doc, clips, fun_style=False):
    """The drafter's own windows (``picks``: [{clip, start, ...}]) get the plan's treatment of the shot they fall in:
    its id, slow motion / the ramp, the join, stabilise. What the drafter set itself stays, unless she changed that
    shot (``by: her``)."""
    rows = used(doc)
    if not rows:
        return picks
    out = []
    for p in picks:
        p = dict(p)
        path = clips.get(p.get("clip"))
        r = _row_at(rows, path, float(p.get("start") or 0) + 0.5) if path else None
        if r is None:
            out.append(p)
            continue
        hers = r.get("by") == "her"
        p.setdefault("brain", r["id"])
        if fun_style:
            if r.get("speed") == "ramp" and (hers or "ramp" not in p):
                p.update(ramp=RAMP, beats=4)
            elif r.get("speed") == "slowmo" and (hers or "ramp" not in p):
                p["ramp"] = "slowmo"
                p["beats"] = max(2, int(p.get("beats") or 2))
            elif hers and r.get("speed") == "normal":
                p.pop("ramp", None)
        else:
            if r.get("speed") == "slowmo" and (hers or "speed" not in p):
                p["speed"] = 0.5
            elif hers and r.get("speed") == "normal":
                p.pop("speed", None)
            j = _join_s(r, doc)
            if j is not None and out and (hers or "xfade" not in p):
                p["xfade"] = round(j, 2)
            if r.get("stabilize") and "stabilize" not in p:
                p["stabilize"] = True
        out.append(p)
    return out


def prompt_line(doc, clips, fun_style=False):
    """One line for the drafter's prompt: the plan's windows with their treatment and why."""
    by_real = _by_real(clips)
    bits = []
    for r in used(doc):
        cid = by_real.get(_real(r["clip"]))
        if cid is None:
            continue
        a, b = r["use"]
        why = next((w["en"] for w in r.get("why") or [] if w.get("code") not in ("hold", "open")), "")
        extra = {"slowmo": ", slow motion", "ramp": ", the one speed ramp"}.get(r.get("speed"), "")
        her = ", her choice" if r.get("by") == "her" else ""
        bits.append(f"{cid} {a:.1f}-{b:.1f}s ({(r.get('transition') or {}).get('kind')}{extra}{her}"
                    f"{': ' + why if why else ''})")
    if not bits:
        return ""
    t = (doc or {}).get("template") or {}
    what = "beat short" if fun_style else "calm film"
    return (f"Editor's shot plan ({t.get('label') or what}, from the shot analysis - follow it unless the sheets show "
            f"a better moment; the shots marked 'her choice' are hers, keep them): " + "; ".join(bits[:24]))


# --------------------------------------------------------------------------- photo story (photostory spec.py)
def _vid_id(src, by_id):
    """'v<clip>' / 'video:<clip>' -> the clip id in ``by_id`` (exact, else the id that ends with it) or None."""
    if not isinstance(src, str):
        return None
    if src.startswith("video:"):
        k = src[6:]
    elif src.startswith("v"):
        k = src[1:]
    else:
        return None
    if k in by_id:
        return k
    hit = [c for c in by_id if c.endswith(k) or os.path.splitext(os.path.basename(by_id[c]["path"]))[0] == k]
    return hit[0] if len(hit) == 1 else None


def photo_line(doc, by_id):
    """The plan for the photo-story drafter: which moments (clip, in-point, hold), how they join, where a label may
    sit, and the stills worth cutting for the cover."""
    by_path = {_real(f["path"]): k for k, f in by_id.items()}
    bits, stills = [], []
    for r in used(doc):
        cid = by_path.get(_real(r["clip"]))
        if cid is None:
            continue
        a = float(r["use"][0])
        kind = (r.get("transition") or {}).get("kind")
        tr = JOIN_PS.get(kind)
        txt = r.get("text") or {}
        room = f", text room in the {txt['where']} third" if txt.get("ok") else ", no room for a label"
        bits.append(f"v{cid} off={a:.1f} (~{float(r.get('hold_s') or 0):.0f} s{', tr=' + repr(tr) if tr else ''}"
                    f"{room}{', her choice' if r.get('by') == 'her' else ''})")
    best = sorted(used(doc), key=lambda r: -(r.get("score") or 0))[:4]
    for r in best:
        cid = by_path.get(_real(r["clip"]))
        if cid is not None and r.get("t") is not None:
            stills.append(f"{cid} t={float(r['t']):.1f}")
    if not bits:
        return ""
    line = ("Editor's shot plan (from the shot analysis; use these moments as the video shots' sources and in-points, "
            "their joins and label places; shots marked 'her choice' are hers): " + "; ".join(bits[:24]))
    if stills:
        line += ". Stills worth cutting for the cover (frames): " + ", ".join(stills)
    return line


def _kw_names(node):
    if isinstance(node, ast.Call):
        return {k.arg for k in node.keywords if k.arg}
    if isinstance(node, ast.Dict):
        return {k.value for k in node.keys if isinstance(k, ast.Constant)}
    return set()


def _kw_value(node, name):
    if isinstance(node, ast.Call):
        for k in node.keywords:
            if k.arg == name and isinstance(k.value, ast.Constant):
                return k.value.value
    if isinstance(node, ast.Dict):
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and k.value == name and isinstance(v, ast.Constant):
                return v.value
    return None


def _offset(lines, lineno, col):
    """ast's (line, UTF-8 byte column) -> a character offset into the text (a 中文 cue before it on the line counts
    once per character)."""
    head = lines[lineno - 1].encode("utf-8")[:col].decode("utf-8", "ignore") if lineno - 1 < len(lines) else ""
    return sum(len(x) for x in lines[:lineno - 1]) + len(head)


def _set_keys(text, lines, node, kv, force):
    """-> [(start, end, replacement)] that put ``kv`` into the shot's options (a dict(...) call, a {...} literal
    or None)."""
    have = _kw_names(node)
    edits = []
    if isinstance(node, ast.Constant) and node.value is None:
        s = _offset(lines, node.lineno, node.col_offset)
        e = _offset(lines, node.end_lineno, node.end_col_offset)
        return [(s, e, "dict(" + ", ".join(f"{k}={v!r}" for k, v in kv.items()) + ")")]
    if not isinstance(node, (ast.Call, ast.Dict)):
        return []
    for k, v in kv.items():
        if k in have:
            if not force:
                continue
            if isinstance(node, ast.Call):
                kw = next(x for x in node.keywords if x.arg == k)
                s = _offset(lines, kw.value.lineno, kw.value.col_offset)
                e = _offset(lines, kw.value.end_lineno, kw.value.end_col_offset)
            else:
                i = [isinstance(x, ast.Constant) and x.value == k for x in node.keys].index(True)
                s = _offset(lines, node.values[i].lineno, node.values[i].col_offset)
                e = _offset(lines, node.values[i].end_lineno, node.values[i].end_col_offset)
            edits.append((s, e, repr(v)))
            continue
        end = _offset(lines, node.end_lineno, node.end_col_offset) - 1          # the closing ) or }
        empty = not (node.keywords or node.args) if isinstance(node, ast.Call) else not node.keys
        sep = "" if empty else ", "
        edits.append((end, end, sep + (f"{k}={v!r}" if isinstance(node, ast.Call) else f"{k!r}: {v!r}")))
    return edits


def _script_shots(tree):
    """The SCRIPT's shot tuples: [(unit index, shot list node, tuple node)]."""
    out = []
    for st in tree.body:
        if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SCRIPT" for t in st.targets) \
                and isinstance(st.value, (ast.List, ast.Tuple)):
            for ui, unit in enumerate(st.value.elts):
                if isinstance(unit, (ast.Tuple, ast.List)) and len(unit.elts) >= 3 and \
                        isinstance(unit.elts[2], (ast.List, ast.Tuple)):
                    for sh in unit.elts[2].elts:
                        if isinstance(sh, (ast.Tuple, ast.List)) and len(sh.elts) >= 4:
                            out.append((ui, unit.elts[2], sh))
    return out


def photo_fix(text, doc, by_id):
    """The spec's video shots follow the plan: the join into each (``tr``: "fade" for a dissolve, "cut") where the
    drafter left it open - always where she chose it - and the label's place (``label_at``: upper | lower, the
    plan's text-safe third). -> (text, [what changed]). The text stays a plain data module."""
    rows = used(doc)
    if not rows or not text:
        return text, []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text, []
    lines = text.splitlines(keepends=True)
    edits, notes = [], []
    first = True
    for _ui, _lst, sh in _script_shots(tree):
        src = sh.elts[0].value if isinstance(sh.elts[0], ast.Constant) else None
        cid = _vid_id(src, by_id)
        opt = sh.elts[3]
        if cid is None:
            first = False
            continue
        off = _kw_value(opt, "off") or 0.0
        r = _row_at(rows, by_id[cid]["path"], float(off) + 0.5)
        if r is None:
            first = False
            continue
        hers = r.get("by") == "her"
        kv = {}
        tr = JOIN_PS.get((r.get("transition") or {}).get("kind"))
        if tr and not first:
            kv["tr"] = tr
        txt = r.get("text") or {}
        if txt.get("ok") and txt.get("where") in ("upper", "lower") and _kw_value(opt, "label") is not None:
            kv["label_at"] = txt["where"]
        kv["brain"] = r["id"]
        got = _set_keys(text, lines, opt, kv, force=hers)
        if got:
            edits += got
            notes.append(f"{r['id']}: " + ", ".join(f"{k}={v}" for k, v in kv.items() if k != "brain"))
        first = False
    if not edits:
        return text, []
    out = text
    for s, e, rep in sorted(edits, key=lambda x: (x[0], x[1]), reverse=True):
        out = out[:s] + rep + out[e:]
    try:
        ast.parse(out)
    except SyntaxError:
        return text, []
    return out, notes


def photo_shot(text, path, after_clip=None, by_id=None, tr="fade", brain=None):
    """Put a video shot (``path``: a generated clip) into the spec: in the unit where ``after_clip`` plays (after it),
    else the first unit -> the new text, or None when the spec has no SCRIPT."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    lines = text.splitlines(keepends=True)
    shots = _script_shots(tree)
    if not shots:
        return None
    target = None
    if after_clip and by_id:
        for ui, lst, sh in shots:
            src = sh.elts[0].value if isinstance(sh.elts[0], ast.Constant) else None
            if _vid_id(src, by_id) == after_clip:
                target = (lst, sh)
    if target is None:
        target = (shots[0][1], None)
    lst, after = target
    opts = dict(off=0.0, audio="mute", tr=tr, **({"brain": brain} if brain else {}))
    new = f'("v{path}", 1, "still", dict(' + ", ".join(f"{k}={v!r}" for k, v in opts.items()) + "))"
    if after is not None:
        at = _offset(lines, after.end_lineno, after.end_col_offset)
        out = text[:at] + ", " + new + text[at:]
    else:
        at = _offset(lines, lst.lineno, lst.col_offset) + 1                     # right after the [ / (
        out = text[:at] + new + (", " if lst.elts else "") + text[at:]
    try:
        ast.parse(out)
    except SyntaxError:
        return None
    return out


# --------------------------------------------------------------------------- talking head (thfolder + compose)
def talk(doc, source):
    """The plan's spans of the recording ``source``: [{a, b, join, punch, brain, by}] - ``join`` how a jump cut
    inside the span is smoothed: morph (RIFE in-betweens), punch (a small punch-in hides it) or cut (a clean cut,
    e.g. a change of framing, or her choice)."""
    out = []
    rp = _real(source)
    for r in used(doc):
        if _real(r["clip"]) != rp:
            continue
        k = (r.get("transition") or {}).get("kind")
        join = {"morph": "morph", "morph-fallback": "punch", "cut": "cut", "match-cut": "cut"}.get(k)
        if r.get("punch_in") == "jump-cover":
            join = "punch"
        elif r.get("punch_in") == "none" and join == "punch" and r.get("by") == "her":
            join = "cut"
        out.append(dict(a=float(r.get("start", r["use"][0])), b=float(r.get("end", r["use"][1])), join=join,
                        punch=r.get("punch_in") or "none", brain=r["id"], by=r.get("by")))
    return out


def joint_policy(spans, t_src, default):
    """How the jump cut at source second ``t_src`` is smoothed (``spans`` from ``talk``) -> morph | punch | cut."""
    for s in spans:
        if s["a"] - 1e-3 <= t_src <= s["b"] + 1e-3:
            return s["join"] or default
    return default


# --------------------------------------------------------------------------- her change of a shot -> the edit
def restyle(project):
    """Her per-shot change reaches the drafted edit files at once (the render watches them): a calm vlog's segments
    / a beat short's shots carrying that shot's id (``brain``) get its speed, join, ramp; a left-out shot leaves the
    edit; a photo story's shots get their join. -> [{item, file, changed}]."""
    doc = plan_doc(project.dir)
    if not doc or not doc.get("plan"):
        return []
    rows = {r["id"]: r for r in doc["plan"]["shots"]}
    out = []
    for it in project.data.get("items") or []:
        d = os.path.join(project.dir, "items", it["id"], "work")
        ep = os.path.join(d, "edit.json")
        if os.path.isfile(ep):
            n = _restyle_edit(ep, rows, doc)
            if n:
                out.append(dict(item=it["id"], file=ep, changed=n))
        sp = os.path.join(d, "spec.py")
        if os.path.isfile(sp):
            n = _restyle_spec(sp, doc, project)
            if n:
                out.append(dict(item=it["id"], file=sp, changed=n))
    return out


def _restyle_edit(path, rows, doc):
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return 0
    if cfg.get("starter"):
        return 0                                    # not drafted yet: the draft reads the plan itself
    fun_style = cfg.get("style") == "fun"
    key = "shots" if fun_style else "segments"
    lst = cfg.get(key) or []
    changed, keep = 0, []
    for s in lst:
        r = rows.get(s.get("brain"))
        if r is None or r.get("by") != "her":
            keep.append(s)
            continue
        if r.get("skip"):
            changed += 1
            continue
        new = dict(s)
        if fun_style:
            new.pop("ramp", None)
            if r.get("speed") == "ramp":
                new.update(ramp=RAMP, beats=4)
            elif r.get("speed") == "slowmo":
                new.update(ramp="slowmo", beats=max(2, int(new.get("beats") or 2)))
        else:
            if r.get("speed") == "normal" and new.get("speed") == 0.5:
                new.pop("speed")
            if r.get("speed") == "slowmo":
                new["speed"] = 0.5
            j = _join_s(r, doc)
            if j is not None and keep:
                new["xfade"] = round(j, 2)
        if new != s:
            changed += 1
        keep.append(new)
    if changed:
        cfg[key] = keep
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return changed


def _restyle_spec(path, doc, project):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return 0
    if "SYNTHETIC" in text[:600]:
        return 0
    from . import store as BS
    by_id = {os.path.splitext(os.path.basename(p))[0]: dict(path=p) for p in BS.media_of(project)}
    new, notes = photo_fix(text, dict(doc, plan=dict(doc["plan"], shots=[r for r in doc["plan"]["shots"]
                                                                         if r.get("by") == "her"])), by_id)
    if new != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
    return len(notes)
