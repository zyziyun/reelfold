"""Filmed performance editing: source-bound story plan -> original-frame cuts -> exports/QC."""
import os

from vstudio import media, performance as PE
from vstudio.batch.util import read_json, write_json


def _source(ctx):
    value = (ctx.params.get("_inputs") or {}).get("video")
    if isinstance(value, list):
        value = value[0] if len(value) == 1 else None
    if not isinstance(value, str) or not os.path.isfile(value):
        raise ValueError("performance edit: select one source performance per item")
    return value


def probe(env):
    source = _source(env)
    info = media.probe(source)
    return dict(source=source, duration=info["duration"], has_audio=info["has_audio"],
                w=info["display_w"], h=info["display_h"], files=[])


def format_ok(path):
    try:
        d = read_json(path, {})
        PE.validate(d, d.get("source_duration", 0))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _review(doc):
    return dict(kind="outline", lines=[dict(code="draft.line", params=dict(label=
                      f"{b['start']:.2f}–{b['end']:.2f}: {b['role']} · {b['evidence']}"))
                                       for b in doc["beats"]],
                summary=dict(code="draft.generic", params=dict(text=doc.get("summary") or doc["title"])))


def draft_edit(ctx, cp, path, template=None, instruction=None, complete=None):
    request = ctx.request() + ("\n" + instruction if instruction else "")
    doc = PE.plan(_source(ctx), request, os.path.dirname(path), speech=bool(ctx.params.get("speech")), complete=complete)
    write_json(path, doc)
    return dict(by="ai", provider=doc.get("provider"), model=doc.get("model"), review=_review(doc))


def review_edit(ctx, cp, path, side=None):
    return _review(read_json(path, {}))


def compose(env):
    path = os.path.join(env.item_dir, "work", "edit.json")
    doc = read_json(path, {})
    result = PE.render(_source(env), doc, os.path.join(env.item_dir, "work", "master.mp4"),
                       preset=env.params.get("preset") or "medium")
    result.update(plan=path, title=doc["title"], body=doc.get("summary") or "")
    return result


def native_profile(target, w, h):
    """Scale platform UI margins to the retained source canvas, including caption metadata."""
    from vstudio import platform as P
    name = str(target).split(":")[0]
    if P.canonical(name) == "youtube-shorts" and w > h:
        raise ValueError("performance edit: this landscape performance is not a Short; choose YouTube or create a deliberately reframed version")
    base = P.profile(name, P.best_orientation(name, w / h))
    sx, sy = w / base.w, h / base.h
    safe = {k: round(v * (sx if k in ("left", "right") else sy))
            for k, v in base.safe.items() if k != "right_lower"}
    if base.safe.get("right_lower"):
        rl = base.safe["right_lower"]
        safe["right_lower"] = dict(w=round(rl["w"] * sx), from_y=round(rl.get("from_y", base.h // 2) * sy))
    return P.profile(name, base.orientation, overrides=dict(w=w, h=h, aspect=f"{w}:{h}", safe=safe,
        caption=dict(band=[round(y * sy) for y in base.caption["band"]]),
        cover=dict(w=w, h=h, aspect=f"{w}:{h}", title_safe=[int(w*.05), int(h*.05), int(w*.95), int(h*.95)],
                   feed_crop=None, crops=[])))


def export(env):
    from vstudio import export as X
    c = env.inputs["compose"]
    info = media.probe(c["master"])
    w, h = int(info["display_w"]), int(info["display_h"])
    out = os.path.join(env.item_dir, "exports"); os.makedirs(out, exist_ok=True)
    entries = []
    for target in env.params.get("platforms") or ["youtube"]:
        # Preserve the staging; a new vertical composition needs separate review.
        prof = native_profile(target, w, h)
        e = X.export_one(c["master"], prof, out, captions=False, mode="letterbox",
                         preset=env.params.get("preset") or "medium",
                         post=dict(title=c["title"], body=c["body"], tags=[]))
        e["native_frame"] = True
        entries.append(e)
    manifest = os.path.join(out, "manifest.json")
    write_json(manifest, dict(master=c["master"], exports=entries, warnings=[]))
    exports = [dict(e, file=os.path.join(out, e["file"]),
                    cover=os.path.join(out, e["cover"]) if e.get("cover") else None,
                    post=os.path.join(out, e["post"]) if e.get("post") else None) for e in entries]
    return dict(manifest=manifest, exports=exports, files=[e["file"] for e in exports])


def qc(env):
    from vstudio import flicker
    reports, reasons = [], []
    source_audio = env.inputs["compose"]["source_has_audio"]
    for e in env.inputs["export"]["exports"]:
        info = media.probe(e["file"])
        if source_audio and not info["has_audio"]:
            reasons.append("The original performance audio is missing")
        r = flicker.analyze(e["file"], profile="calm")
        reports.append(r)
        if not r["ok"]:
            reasons.append(flicker.describe(r))
    from vstudio import audio_joins
    plan = read_json(env.inputs["compose"]["plan"], {})
    sound = audio_joins.inspect(_source(env), plan.get("segments", []))
    for join in sound["joins"]:
        if join["needs_review"]:
            reasons.append(f"Listen to the audio cut at {join['time']:.2f}s: {join['reason']}")
    path = os.path.join(env.item_dir, "work", "quality.json")
    write_json(path, dict(status="red" if reasons else "green", reasons=reasons, reports=reports, audio_joins=sound))
    return dict(status="red" if reasons else "green", reasons=reasons, files=[path],
                exports=env.inputs["export"]["exports"])
