"""ai-video: plan (generate.py plan, the free dry run: credits per item) -> project budget approval -> generate
(paid, generate.py run --budget --yes) -> judge sheets per take -> take selection -> timeline (auto EDL from the
picks unless work/ai/timeline.yaml is authored) -> assemble.py -> vstudio.export."""
import glob
import os
import re

import yaml

from vstudio import take_review
from vstudio.batch.util import read_json, sha1_json, write_json

from ..build import file_sha
from ...oscompat import relpath as _relpath

_TOTAL = re.compile(r"Estimated total:\s*([\d.]+)\s*credits(?:\s*\(\+\d+% retry allowance = ([\d.]+)\))?")


def _proj(env):
    return os.path.join(env.item_dir, "work", "ai", "project.yaml")


def plan(env):
    proj = _proj(env)
    r = env.run([env.fmt("{python}"), os.path.join(env.workflow_dir, "scripts", "generate.py"), "plan", proj],
                log="plan.log")
    path = os.path.join(env.item_dir, "work", "ai", "plan.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(r.stdout or "")
    mo = _TOTAL.search(r.stdout or "")
    credits = float(mo.group(2) or mo.group(1)) if mo else None
    info = write_json(os.path.join(env.item_dir, "work", "ai", "plan.json"),
                      dict(credits=credits, base=float(mo.group(1)) if mo else None, unknown=mo is None))
    return dict(plan=path, credits=credits, info=info, files=[path, info], digest=file_sha(path))


def _all_plans(project_dir):
    out = []
    for p in sorted(glob.glob(os.path.join(project_dir, "items", "*", "work", "ai", "plan.json"))):
        d = read_json(p, {}) or {}
        out.append(dict(item=p.split(os.sep)[-4], credits=d.get("credits"), unknown=d.get("unknown")))
    return out


def budget_payload(env, cp):
    mine = env.inputs.get("plan") or {}
    plans = _all_plans(env.project_dir)
    known = [p["credits"] for p in plans if p["credits"] is not None]
    total = round(sum(known), 1)
    unknown = [p["item"] for p in plans if p["credits"] is None]
    ans = ((env.params.get("_answers") or {}).get(cp["id"]) or {}).get("value") or {}
    ok = bool(ans.get("approve")) and not unknown and total <= float(ans.get("budget") or 0) + 1e-6 \
        if not ans.get("allow_unknown") else bool(ans.get("approve"))
    return dict(options=plans, credits=mine.get("credits"), total_credits=total, unknown_items=unknown,
                digest="within-budget" if ok else f"need-{total}-{len(unknown)}",
                default=None, previews=[dict(kind="markdown", path=mine.get("plan"))] if mine.get("plan") else [])


def budget_apply(a):
    v = a.value or {}
    if not v.get("approve"):
        return dict(params={}, digest="declined")
    if v.get("budget") is None:
        raise ValueError("budget: give the approved credits (budget)")
    return dict(params={}, project_params=dict(budget_credits=float(v["budget"]),
                                              allow_unknown_cost=bool(v.get("allow_unknown"))),
                digest="within-budget")


def judge(env):
    takes = sorted(glob.glob(os.path.join(env.item_dir, "work", "ai", "takes", "*.mp4")))
    jd = os.path.join(env.item_dir, "work", "ai", "judge")
    os.makedirs(jd, exist_ok=True)
    with open(_proj(env), encoding="utf-8") as f:
        project = yaml.safe_load(f) or {}
    rows = []
    for t in takes:
        argv = [env.fmt("{python}"), os.path.join(env.workflow_dir, "scripts", "judge.py"), "sheet", t, "--out", jd]
        if not env.params.get("judge_asr"):
            argv.append("--no-asr")
        env.run(argv, log=f"judge_{os.path.basename(t)}.log")
        stem = os.path.splitext(os.path.basename(t))[0]
        unit = stem.rsplit("_v", 1)[0]
        card = os.path.join(jd, f"{stem}.card.json")
        existing = read_json(card, {}) or {}
        manual = isinstance(existing, dict) and existing.get("review_source") != "ai-sampled-visual" and any(
            value is not None for section in ("hard", "soft", "scores")
            for value in (existing.get(section) or {}).values())
        # Never replace a person's rejection or partial review with an AI approval.
        if not manual and take_review.inspect(t, card)[0] != "pass":
            from vstudio import take_review_ai
            review = take_review_ai.review(t, project, unit, os.path.join(jd, stem),
                                           os.path.dirname(_proj(env)))
            write_json(card, review)
        rows.append(dict(unit=unit, take=t, card=card, sheet=os.path.join(jd, f"{stem}.sheet.jpg")))
    path = write_json(os.path.join(jd, "takes.json"), dict(takes=rows))
    return dict(takes=path, n=len(rows), files=[path])


def takes_recheck(params):
    """Invalidate cached selection when footage or its review changes on disk."""
    root = os.path.join(params.get("_item_dir") or "", "work", "ai")
    paths = sorted(glob.glob(os.path.join(root, "takes", "*.mp4")) +
                   glob.glob(os.path.join(root, "judge", "*.card.json")))
    paths.append(os.path.join(root, "project.yaml"))
    for card in glob.glob(os.path.join(root, "judge", "*.card.json")):
        data = read_json(card, {}) or {}
        if isinstance(data, dict):
            paths.extend(r["path"] for r in data.get("references", []) if isinstance(r, dict) and r.get("path"))
    return {path: file_sha(path) for path in paths}


def takes_payload(env, cp):
    d = read_json((env.inputs.get(cp["after"]) or {}).get("takes"), {}) or {}
    units = {}
    for r in d.get("takes") or []:
        card = r.get("card") or os.path.splitext(r["sheet"])[0].removesuffix(".sheet") + ".card.json"
        decision, reasons = take_review.inspect(r["take"], card)
        units.setdefault(r["unit"], []).append(dict(file=r["take"], sheet=r["sheet"], card=card,
                                                   review=decision, reasons=reasons))
    opts = [dict(unit=u, takes=ts) for u, ts in sorted(units.items())]
    picks = {o["unit"]: next((t["file"] for t in reversed(o["takes"]) if t["review"] == "pass"), None)
             for o in opts}
    return dict(options=opts, default=dict(picks=picks) if picks and all(picks.values()) else None,
                previews=[dict(kind="image", path=t["sheet"]) for o in opts for t in o["takes"]
                          if os.path.exists(t["sheet"])], skip=False)


def takes_apply(a):
    picks = (a.value or {}).get("picks") or {}
    units = {o["unit"]: {t["file"]: t for t in o["takes"]} for o in a.payload.get("options") or []}
    if not units or set(picks) != set(units):
        raise ValueError("takes: select one reviewed take for every unit")
    reviews = {}
    for unit, path in picks.items():
        if path not in units[unit]:
            raise ValueError(f"takes: unknown take for {unit}")
        card = units[unit][path]["card"]
        take_review.require(path, card)
        reviews[path] = card
    return dict(params=dict(takes_pick=picks, takes_reviews=reviews))


def _check_timeline_reviews(path, reviews):
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    base = os.path.dirname(path)
    for entry in doc.get("edl") or []:
        if "take" in entry:
            video = os.path.abspath(os.path.join(base, doc.get("takes_dir", "takes"), entry["take"]))
            take_review.require(video, reviews.get(video, ""))


def timeline(env):
    """work/ai/timeline.yaml when authored (the locked EDL), else timeline.auto.yaml from the picked takes in unit
    order (each take whole), canvas from the project's aspect."""
    from vstudio import media
    d = os.path.join(env.item_dir, "work", "ai")
    hand = os.path.join(d, "timeline.yaml")
    reviews = {os.path.abspath(k): v for k, v in (env.params.get("takes_reviews") or {}).items()}
    if os.path.exists(hand):
        _check_timeline_reviews(hand, reviews)
        with open(hand, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        doc["review_cards"] = reviews
        checked = os.path.join(d, "timeline.reviewed.yaml")
        with open(checked, "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
        return dict(timeline=checked, authored=True, files=[checked], digest=file_sha(checked))
    picks = env.params.get("takes_pick") or {}
    if not picks:
        raise RuntimeError("timeline: no picked takes and no work/ai/timeline.yaml")
    with open(_proj(env), encoding="utf-8") as f:
        proj = yaml.safe_load(f) or {}
    w, h = (1080, 1920) if str(proj.get("aspect", "9:16")) in ("9:16", "3:4") else (1920, 1080)
    edl = []
    for unit in sorted(picks):
        f = picks[unit]
        take_review.require(f, reviews.get(os.path.abspath(f), ""))
        edl.append({"take": _relpath(f, os.path.join(d, "takes")), "in": 0.0,
                    "out": round(media.duration(f), 3)})
    tl = dict(review_cards=reviews, canvas=[w, h], fps=30, takes_dir="takes", out="master.mp4", grade=dict(saturation=0.88, grain=4),
              edl=edl, music=dict(path=None, duck_db=-10, carve=True),
              captions=dict(language=proj.get("language", "en"), max_chars=32, out="cues.json"))
    path = os.path.join(d, "timeline.auto.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(tl, f, allow_unicode=True, sort_keys=False)
    return dict(timeline=path, authored=False, files=[path], digest=sha1_json(tl)[:16])

