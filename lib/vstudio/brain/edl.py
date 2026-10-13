"""The shot plan on a clip's timeline: the builder's per-shot source edit list (``<master>.edl.json``, written by
build_vlog / build_fun / the photo-story renderer / the talking-head compose stage) joined with the editor brain's
plan - each shot on the timeline says which take it plays, why this treatment, and the alternatives, exactly as the
project page's "How it's cut" does.

    from vstudio.brain import edl
    doc = edl.shots(project, output="item1/xiaohongshu-vertical")
    # {item, builder, duration, shots [{i, t0, t1, src, file, src_in, src_out, join, speed, role, ai,
    #   brain {id, by, transition, speed, hold_s, why, choices, thumb, effects} | None,
    #   gen {id, title, why, status} | None}], fresh}
"""
import glob
import os

from . import steer
from . import store as ST

ROW_KEYS = ("id", "by", "transition", "speed", "hold_s", "why", "choices", "thumb", "effects", "skip", "reframe",
            "punch_in", "stabilize", "text", "use", "clip", "file", "t")


def item_of(project, output):
    """The project item an output (``output list`` id or file) belongs to -> (job id, base item id) or (None, None)."""
    from vstudio.project import outputs as O
    try:
        rows = O.list_outputs(project.dir)["outputs"]
    except Exception:  # noqa: BLE001
        return None, None
    r = O._match(rows, output) if output else (rows[0] if rows else None)
    if not r or not r.get("item"):
        return None, None
    base = next((j.get("_base_item") or j["id"] for j in project.jobs_rows() if j["id"] == r["item"]), r["item"])
    return r["item"], base


def edl_file(project, job, base):
    """The newest edit list the item's builder wrote, or None."""
    pats = [os.path.join(project.dir, "items", base, "work", "*.edl.json"),
            os.path.join(project.dir, "items", base, "out", "*.edl.json"),
            os.path.join(project.state_dir, "jobs", job, "*", "edl.json"),
            os.path.join(project.state_dir, "jobs", job, "*", "*.edl.json")]
    hits = [p for pat in pats for p in glob.glob(pat)]
    return max(hits, key=os.path.getmtime) if hits else None


def shots(project, output=None, item=None):
    job, base = (item, item) if item else item_of(project, output)
    if not job:
        return dict(ok=True, item=None, shots=[], reason="no-item")
    path = edl_file(project, job, base)
    if not path:
        return dict(ok=True, item=job, shots=[], reason="no-edit-list")
    d = ST._read(path, {}) or {}
    doc = ST._read(os.path.join(ST._dir(project), "brain.json")) or {}
    rows = {r["id"]: r for r in ((doc.get("plan") or {}).get("shots") or [])}
    used = steer.used(doc)
    props = {p["id"]: p for p in doc.get("proposals") or []}
    out = []
    for s in d.get("shots") or []:
        s = dict(s)
        bid = s.get("brain")
        gen = props.get(bid) if bid else None
        r = rows.get(bid) if bid and not gen else None
        if r is None and not gen and s.get("src") and s.get("src_in") is not None and s.get("role") != "broll":
            r = steer._row_at(used, s["src"], float(s["src_in"]) + 0.5)     # an edit drafted before the plan
        s["file"] = os.path.basename(s["src"]) if s.get("src") else None
        s["brain"] = {k: r.get(k) for k in ROW_KEYS} if r else None
        s["gen"] = {k: gen.get(k) for k in ("id", "kind", "title", "why", "status", "mode", "provider", "ai_label")} \
            if gen else None
        out.append(s)
    return dict(ok=True, item=job, builder=d.get("builder"), duration=d.get("duration"), shots=out,
                edl=path, fresh=os.path.getmtime(path) >= os.path.getmtime(os.path.join(ST._dir(project), "brain.json"))
                if os.path.exists(os.path.join(ST._dir(project), "brain.json")) else True,
                template=(doc.get("template") or {}).get("template"))
