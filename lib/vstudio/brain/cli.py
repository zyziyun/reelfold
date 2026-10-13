"""CLI of vstudio.brain (see the package doc). Every command prints JSON with ``--json``; nothing here spends."""
import argparse
import json
import os
import sys

from . import genplan as G
from . import presets as P
from . import store as ST
from . import template as T
from . import treat as TR

MEDIA = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".heic", ".webp", ".srt", ".mp3", ".wav",
         ".m4a")


def expand(inputs):
    """Files and folders -> media files (folders one level deep + their subfolders, symlinks followed)."""
    out = []
    for x in inputs or []:
        x = os.path.expanduser(x)
        if os.path.isdir(x):
            for dp, dn, fn in os.walk(x, followlinks=True):
                dn[:] = sorted(d for d in dn if not d.startswith("."))
                out += [os.path.join(dp, f) for f in sorted(fn) if f.lower().endswith(MEDIA) and not f.startswith(".")]
        elif os.path.exists(x):
            out.append(x)
    return list(dict.fromkeys(out))


def _out(a, obj, text=None):
    if a.json or text is None:
        print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))
    else:
        print(text)
    return 0


def _signals(a):
    from vstudio import footage
    from vstudio.intake import inventory as I
    paths = expand(a.inputs)
    analysis = I.analyze(paths, asr=a.asr)
    facts = {p: footage.facts(p) for p in paths if footage.is_video(p)}
    return paths, analysis, T.signals(analysis, a.prompt or "", footage_facts=facts)


def _judge(a):
    return T.ai_judge() if getattr(a, "ai", False) else None


def cmd_classify(a):
    _paths, _an, s = _signals(a)
    d = T.classify(s, fixed_recipe=a.recipe, judge=_judge(a))
    return _out(a, d, d and f"{d['label']} ({d['by']}, {d['confidence']}): {d['reason']['en']}")


def _tiles(a, paths):
    from . import tiles as TI
    vids = [p for p in paths if p.lower().endswith((".mp4", ".mov", ".m4v", ".mkv", ".webm"))]
    return TI.for_clips(vids, echo=(lambda m: print(m, file=sys.stderr)) if not a.json else None)


def cmd_treat(a):
    paths = expand(a.inputs)
    ts = _tiles(a, paths)
    pl = TR.plan(ts, a.template, target_s=a.target, out_aspect=a.aspect,
                 judge=TR.ai_judge() if a.ai else None)
    return _out(a, pl, json.dumps(pl["summary"], ensure_ascii=False))


def cmd_gen(a):
    paths, _an, s = _signals(a)
    ts = _tiles(a, paths)
    pl = TR.plan(ts, a.template, target_s=a.target, out_aspect=a.aspect)
    props = G.propose(a.template, pl, s, stage=a.stage, target_s=a.target, tiles=ts)
    return _out(a, dict(proposals=props, cost=G.total(props)))


def _project(a):
    from vstudio.project.core import Project
    return Project(a.dir)


def cmd_show(a):
    pr = _project(a)
    doc = ST.show(pr, refresh=a.refresh, shots=not a.no_shots, judge=TR.ai_judge() if a.ai else None)
    return _out(a, doc)


def cmd_template(a):
    return _out(a, ST.set_template(_project(a), a.id))


def cmd_shot(a):
    pr = _project(a)
    if a.reset:
        return _out(a, ST.reset_shot(pr, a.id))
    ch = {}
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        ch[k] = {"true": True, "false": False}.get(v, v)
    return _out(a, ST.set_shot(pr, a.id, **ch))


def cmd_decide(a):
    act = "approve" if a.approve else "skip" if a.skip else "undo"
    return _out(a, ST.decide_gen(_project(a), a.id, act, code=a.code))


def cmd_presets(a):
    rows = [dict(P.card(k, a.lang), recipe=P.get(k)["recipe"]) for k in P.ids()]
    return _out(a, rows, "\n".join(f"{r['id']:20s} {r['recipe']:18s} {r['label']}" for r in rows))


def build_parser():
    ap = argparse.ArgumentParser(prog="python -m vstudio.brain")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(fn=fn)
        p.add_argument("--json", action="store_true")
        return p

    for name, fn, h in (("classify", cmd_classify, "inputs + request -> template"),
                        ("treat", cmd_treat, "per-shot treatment plan"),
                        ("gen", cmd_gen, "generation proposals (no spend)")):
        p = add(name, fn, h)
        p.add_argument("--inputs", nargs="+", required=True)
        p.add_argument("--prompt", default="")
        p.add_argument("--asr", default="sample", choices=("off", "sample", "full"))
        p.add_argument("--ai", action="store_true", help="ask the routed AI on close calls")
        if name == "classify":
            p.add_argument("--recipe", default=None, help="her explicit recipe: only its templates compete")
        else:
            p.add_argument("--template", required=True, choices=P.ids())
            p.add_argument("--target", type=float, default=None)
            p.add_argument("--aspect", default=None)
        if name == "gen":
            p.add_argument("--stage", default="cut", choices=G.STAGES)
    p = add("show", cmd_show, "a project's brain (computed when missing)")
    p.add_argument("--dir", required=True)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--no-shots", action="store_true")
    p.add_argument("--ai", action="store_true")
    p = add("template", cmd_template, "her template for a project")
    p.add_argument("--dir", required=True)
    p.add_argument("--id", required=True, choices=P.ids())
    p = add("shot", cmd_shot, "change one shot's treatment")
    p.add_argument("--dir", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--set", nargs="*", help="transition=cut speed=normal reframe=centre skip=true")
    p.add_argument("--reset", action="store_true")
    p = add("decide", cmd_decide, "approve / skip a generation proposal")
    p.add_argument("--dir", required=True)
    p.add_argument("--id", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", action="store_true")
    g.add_argument("--skip", action="store_true")
    g.add_argument("--undo", action="store_true")
    p.add_argument("--code", default=None, help="the proposal's confirm code (its price)")
    p = add("presets", cmd_presets, "the templates")
    p.add_argument("--lang", default="en", choices=("en", "zh"))
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except ST.BrainError as e:
        print(json.dumps(dict(ok=False, error=str(e)), ensure_ascii=False) if getattr(a, "json", False) else str(e),
              file=sys.stdout if getattr(a, "json", False) else sys.stderr)
        return 2
