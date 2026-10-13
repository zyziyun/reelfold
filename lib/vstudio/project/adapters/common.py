"""Shared adapters: the checkpoint payload / apply pairs most recipes use, candidate stages (hooks, cover frames)
and output collectors.

Checkpoints
  author      a file the human / agent writes (script, spec, edit list, timeline): payload = the path, whether it
              exists, its template + format doc; answer {done: true} or {content: "..."} (written for you). The
              digest is the file's hash, so a later edit (by the agent) asks again and re-runs what depends on it.
  publish     final look: exports, cover, post copy, QC; answer {approve: true} / {approve: false, reason}.
  filler      the cleanup CONFIRM rows of a speech recipe (vstudio.cleanup): answer {approve: [ids], keep: [ids],
              kinds: [kind...], all: bool} -> the item's ``cleanup_reply`` ("确认 3,5 / 保留 7").
  hook        ranked cold-open candidates from the transcript: answer {pick: k} (-1 = no hook) or
              {start, end, text} -> the item's ``hook``.
  cover       candidate frames of the composed master: answer {pick: k, text: "a|b"} or {t: s, text} -> a
              frame + text card -> the item's ``cover`` (export uses the file).
  keywords    the 3-8 highlight keywords drafted for a talkinghead vtrack clip (+ a few unticked candidates):
              answer {keywords: [...]} (free text) or the desk's ticks {approve: [...], keep: [...]} -> the item's
              ``keywords`` (they replace the drafted ones; [] = no highlight).
  choice      generic single-pick over options -> ``set`` param.
"""
import json
import os
import re
import shutil
import subprocess

from vstudio.batch.util import read_json, sha1_json, write_json

from .. import manifests as M
from ..build import file_sha, static_tctx
from ...oscompat import relpath as _relpath


# --------------------------------------------------------------------------- author
def _author_path(env_or_ctx, cp):
    m = env_or_ctx.m
    return M.fmt(cp["author"]["file"], static_tctx(m, env_or_ctx.params, env_or_ctx.job))


def dir_sha(path):
    """Hash of a folder's listing (names, sizes, mtimes) - an authored folder (scene compositions)."""
    rows = []
    for root, _, files in os.walk(path):
        for f in sorted(files):
            p = os.path.join(root, f)
            st = os.stat(p)
            rows.append([_relpath(p, path), st.st_size, int(st.st_mtime)])
    return sha1_json(sorted(rows))[:16] if rows else None


def author_payload(env, cp):
    """The file she would write - drafted by the engine first (``vstudio.project.drafts``: the recipe's drafter or
    the AI; never the seeded template / SYNTHETIC example). ``default`` ({done: true}) only for a real draft or her
    own file; ``review`` is the plain-language view the Inbox shows; ``draft_state`` missing | template | drafted |
    hers; ``draft_error`` why nothing could be drafted (``draft_error_code`` needs-model: the step needs an AI model
    and none answered); ``placeholders`` the "TODO"s still in it (never auto-approved)."""
    from .. import drafts as DR
    a = cp["author"]
    path = _author_path(env, cp)
    tpl = os.path.join(M.ROOT, a["template"]) if a.get("template") else None
    ctx = DR.Ctx.of_env(env)
    rec = DR.ensure(ctx, cp, path, tpl, echo=env.log)
    st = DR.state(path, tpl, cp, ctx.recipe)
    usable = st in ("drafted", "hers")
    extra = dict(review=DR.review(ctx, cp, path, tpl), draft_state=st, draft_by=(DR.read_side(path, cp["id"]) or
                                                                                  {}).get("by") if usable else None,
                 draft_error=(rec or {}).get("failed"), draft_error_code=(rec or {}).get("failed_code"),
                 draft_error_params=(rec or {}).get("failed_params"),
                 placeholders=DR.placeholders(path) if usable else 0)
    if a.get("needs_ai"):            # the step needs a model (the Inbox says so over a rules draft) and which one
        from .explainer_scenes import routed_provider
        extra.update(needs_ai=True, ai_provider=routed_provider())
    if os.path.isdir(path):
        sha = dir_sha(path)
        files = sorted(os.listdir(path))
        return dict(file=path, exists=usable, is_dir=True, files=files, format=a.get("format"),
                    doc=os.path.join(M.ROOT, a["doc"]) if a.get("doc") else None, content=None,
                    options=[dict(file=path, sha=sha)], digest=sha or "missing",
                    default=dict(done=True) if usable else None,
                    previews=[dict(kind=_kind_of(f), path=os.path.join(path, f)) for f in files[:24]], **extra)
    text = None
    if usable and os.path.getsize(path) < 200_000:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            text = None
    return dict(file=path, exists=usable, template=tpl, format=a.get("format"),
                doc=os.path.join(M.ROOT, a["doc"]) if a.get("doc") else None,
                content=text, options=[dict(file=path, sha=file_sha(path))], digest=file_sha(path) or "missing",
                default=dict(done=True) if usable else None,
                previews=[dict(kind="text", path=path)] if usable else [], **extra)


def author_apply(a):
    path = a.payload.get("file") or M.fmt(a.cp["author"]["file"], a.tctx())
    v = a.value or {}
    if v.get("content") is not None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(v["content"])
    if os.path.isdir(path):
        if not dir_sha(path):
            raise ValueError(f"{a.cp['id']}: {path} is empty - author it first")
        return dict(params={}, digest=dir_sha(path))
    if not os.path.exists(path):
        raise ValueError(f"{a.cp['id']}: {path} does not exist yet - write it (or answer with content)")
    from .. import drafts as DR
    ok = DR.format_check(a.m["id"], a.cp["id"])
    if ok and not ok(path):
        raise ValueError(f"{a.cp['id']}: {os.path.basename(path)} is not in the script format yet ('## Line N' "
                         "scenes with indented narration) - let Reelfold draft it from your notes, or write the lines")
    return dict(params={}, digest=file_sha(path))


# --------------------------------------------------------------------------- anchors
def prepare(env):
    """First stage of script recipes: the item workspace exists, author templates are seeded (at plan time);
    links the item's inputs into ``inputs/`` so the workflow configs can use short relative paths."""
    d = env.item_path("inputs")
    os.makedirs(d, exist_ok=True)
    linked = []
    for k, v in (env.params.get("_inputs") or {}).items():
        for src in (v if isinstance(v, list) else [v]):
            if isinstance(src, str) and os.path.isfile(src):
                dst = os.path.join(d, os.path.basename(src))
                if not os.path.exists(dst):
                    try:
                        os.symlink(src, dst)
                    except OSError:
                        shutil.copy2(src, dst)
                linked.append(dst)
    return dict(item_dir=env.item_dir, inputs=linked, files=[])


# --------------------------------------------------------------------------- publish
def _exports_of(env):
    ex = (env.inputs.get("export") or {}).get("exports") or []
    return [dict(platform=e.get("platform"), orientation=e.get("orientation"), file=e.get("file"),
                 cover=e.get("cover"), post=e.get("post"), duration=e.get("duration")) for e in ex]


def publish_copy(env):
    """The post copy the exports carry: the creator's, else the copy stage's draft from the captions - with what
    was drafted and from what (``llm:<provider>`` / ``transcript``) so the review shows it as a draft to edit
    (python -m vstudio.batch job edit --op copy)."""
    p = env.params
    cs = env.inputs.get("copy") or {}
    ex = env.inputs.get("export") or {}
    out = dict(title=p.get("title") or ex.get("title") or cs.get("title") or "",
               body=p.get("body") or ex.get("body") or cs.get("body") or "", tags=p.get("tags"))
    drafted = [k for k in ("title", "body") if not p.get(k) and out[k]
               and (k in (cs.get("drafted") or []) or ex.get(f"{k}_source") not in (None, "given"))]
    if drafted:
        out.update(drafted=drafted, source=cs.get("source") or ex.get("title_source") or ex.get("body_source"),
                   notes=list(cs.get("notes") or []),
                   edit="python -m vstudio.batch job edit --op copy --title ... --body ...")
    return out


def publish_payload(env, cp):
    files = []
    for dep, out in (env.inputs or {}).items():
        files += [f for f in (out or {}).get("files") or [] if os.path.exists(str(f))]
    exports = _exports_of(env)
    qc = env.inputs.get("qc") or {}
    previews = []
    for e in exports:
        previews += [dict(kind="video", path=e["file"], platform=e["platform"])]
        if e.get("cover"):
            previews.append(dict(kind="image", path=e["cover"], platform=e["platform"]))
    if not previews:
        previews = [dict(kind=_kind_of(f), path=f) for f in files[:12]]
    pv = env.inputs.get("preview") or {}
    for k in ("sheet", "snippet"):
        if pv.get(k):
            previews.append(dict(kind="image" if k == "sheet" else "video", path=pv[k]))
    return dict(options=[dict(file=x["path"], sha=file_sha(x["path"])) for x in previews],
                exports=exports, qc=dict(status=qc.get("status"), reasons=qc.get("reasons") or [],
                                         warnings=qc.get("warnings") or []),
                copy=publish_copy(env),
                default=dict(approve=True) if qc.get("status") != "red" else None, previews=previews)


def approve_apply(a):
    """A yes / no review that blocks on no (privacy check, layout check): a rejection never matches the payload,
    so the item stays waiting until a later yes."""
    v = a.value or {}
    if v.get("approve"):
        return dict(params={})
    return dict(params={}, digest="rejected", reason=v.get("reason"))


def publish_apply(a):
    return dict(params={}, review="approved" if (a.value or {}).get("approve") else "needs-replan",
                reason=(a.value or {}).get("reason"))


def _kind_of(path):
    ext = os.path.splitext(str(path))[1].lower()
    if ext in (".mp4", ".mov", ".m4v", ".webm", ".mkv"):
        return "video"
    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        return "image"
    if ext in (".wav", ".m4a", ".mp3", ".aac"):
        return "audio"
    if ext in (".md", ".txt", ".srt"):
        return "text"
    if ext == ".json":
        return "json"
    if ext == ".html":
        return "html"
    return "file"


# --------------------------------------------------------------------------- filler confirm (vstudio.cleanup)
def filler_payload(env, cp):
    out = env.inputs.get(cp["after"]) or {}
    cf = out.get("confirm_file")
    rows = read_json(cf, []) if cf else []
    opts = [dict(id=int(e["id"]), kind=e.get("kind"), part=e.get("part", "body"), text=e.get("text", ""),
                 t0=e.get("t0"), t1=e.get("t1"), before=e.get("before", ""), after=e.get("after", ""),
                 reason=e.get("reason", ""), confidence=e.get("confidence")) for e in rows or []]
    kinds = {}
    for o in opts:
        kinds.setdefault(o["kind"] or "?", []).append(o["id"])
    previews = [dict(kind="markdown", path=f) for f in (out.get("review"),) if f and os.path.exists(f)]
    for f in os.listdir(os.path.dirname(cf)) if cf and os.path.exists(cf) else []:
        if f.endswith("_review.md"):
            previews.append(dict(kind="markdown", path=os.path.join(os.path.dirname(cf), f)))
    return dict(options=opts, kinds=kinds, auto_cuts=out.get("auto"), saved_s=out.get("saved_s"),
                source=env.params.get("source"), default=dict(approve=[], keep=[]), previews=previews,
                skip=not opts, skip_reason="no CONFIRM edits (only AUTO cuts)")


def edl_filler_payload(env, cp):
    """The CONFIRM rows of a vstudio.cleanup EDL a workflow script wrote (the ``*cleanup.json`` file among the
    ``after`` stage's outputs: tight_cut.py --suggest, find_disfluencies.py, polish.py ...)."""
    out = env.inputs.get(cp["after"]) or {}
    edl = next((f for f in out.get("files") or [] if str(f).endswith("cleanup.json")), None)
    E = read_json(edl, {}) if edl else {}
    opts = [dict(id=int(e["id"]), kind=e.get("kind"), part="body", text=e.get("text", ""), t0=e.get("t0"),
                 t1=e.get("t1"), before=e.get("before", ""), after=e.get("after", ""), reason=e.get("reason", ""),
                 confidence=e.get("confidence")) for e in (E or {}).get("edits") or [] if e.get("action") == "confirm"]
    kinds = {}
    for o in opts:
        kinds.setdefault(o["kind"] or "?", []).append(o["id"])
    sheets = [f for f in out.get("files") or [] if str(f).endswith("review.md")]
    return dict(options=opts, kinds=kinds, edl=edl, default=dict(approve=[], keep=[]),
                previews=[dict(kind="markdown", path=f) for f in sheets], skip=not opts,
                skip_reason="no CONFIRM edits")


def reply_from(value, options):
    """{approve, keep, kinds, all} -> the vstudio.cleanup reply text ("确认 3,5 / 保留 7", "全部确认")."""
    v = value or {}
    if v.get("all"):
        keep = sorted(set(int(x) for x in v.get("keep") or []))
        return "全部确认" + (f" / 保留 {','.join(map(str, keep))}" if keep else "")
    ids = set(int(x) for x in v.get("approve") or [])
    kinds = set(v.get("kinds") or [])
    for o in options or []:
        k = o.get("kind") or ""
        if any(k == x or k.startswith(x + "/") or k.startswith(x + "-") for x in kinds):
            ids.add(int(o["id"]))
    keep = set(int(x) for x in v.get("keep") or []) - ids
    parts = []
    if ids:
        parts.append("确认 " + ",".join(map(str, sorted(ids))))
    if keep:
        parts.append("保留 " + ",".join(map(str, sorted(keep))))
    return " / ".join(parts)


def filler_apply(a):
    return dict(params=dict(cleanup_reply=reply_from(a.value, a.payload.get("options")) or None))


def cut_reply_apply(a):
    """Same answer, stored as ``cut_reply`` (the workflows whose config has its own reply key: promo cut.reply,
    vlog / photo-story cleanup.reply)."""
    return dict(params=dict(cut_reply=reply_from(a.value, a.payload.get("options")) or ""))


# --------------------------------------------------------------------------- keywords (talkinghead vtrack)
def keywords_payload(env, cp):
    out = env.inputs.get(cp["after"]) or {}
    if (env.spec.get("talkinghead") or {}).get("keywords"):
        return dict(options=[], skip=True, skip_reason="keywords set for the project")
    notes = read_json(out.get("notes"), {}) if out.get("notes") else {}
    kws, more = list(notes.get("keywords") or []), list(notes.get("keyword_candidates") or [])
    opts = [dict(id=k, label=k, text=k, checked=True) for k in kws] + \
           [dict(id=k, label=k, text=k, checked=False) for k in more if k not in kws]
    return dict(options=opts, default=dict(keywords=kws), chapters=notes.get("chapters") or [],
                panels=notes.get("panels") or [], warnings=notes.get("notes") or [],
                previews=[dict(kind="json", path=out["notes"])] if out.get("notes") else [],
                skip=not opts, skip_reason="; ".join(notes.get("notes") or []) or "no keywords drafted")


def keywords_apply(a):
    v = a.value or {}
    if "keywords" in v:
        picked = v.get("keywords") or []
    else:                                              # the desk's option ticks: ids are the keywords
        ids = {str(x) for x in v.get("approve") or []}
        picked = [o["id"] for o in a.payload.get("options") or [] if str(o["id"]) in ids]
    out = []
    for k in picked:
        k = re.sub(r"\s+", " ", str(k or "")).strip()
        if k and k not in out:
            out.append(k)
    return dict(params=dict(keywords=out))


# --------------------------------------------------------------------------- hooks (cold open candidates)
HOOK_CUES = ("其实", "但是", "千万", "一定", "为什么", "不是", "没想到", "关键", "核心", "最", "秘密", "错",
             "真相", "竟然", "因为", "所以", "you", "never", "why", "secret", "mistake", "actually")
OPENERS = ("然后", "所以", "那", "就是", "而且", "and ", "so ", "then ")


def _transcript_of(env):
    for dep in ("asr", "transcribe"):
        out = env.inputs.get(dep) or {}
        for k in ("transcript", "whisper"):
            if out.get(k) and os.path.exists(out[k]):
                return out[k]
    return None


def rank_hooks(transcript, n=6, min_s=1.8, max_s=9.0, rng=None):
    """Sentences of the transcript that work as a cold open: 2-9 s, no leading connective, a contrast / number /
    question cue scores up. -> [{index, start, end, text, dur, score}] best first."""
    from vstudio.batch.segplan import sentences_of
    from vstudio.cleanup import load_words
    W = load_words(transcript)
    if not W:
        return []
    sents = sentences_of(W, max_len=max_s)
    out = []
    for s in sents:
        d = s["te"] - s["t"]
        if not min_s <= d <= max_s:
            continue
        if rng and not (rng[0] - 0.05 <= s["t"] and s["te"] <= rng[1] + 0.05):
            continue
        txt = s["text"].strip()
        low = txt.lower()
        sc = 1.0 - abs(d - 4.5) / 9.0
        sc += 0.6 * sum(c in low for c in HOOK_CUES)
        sc += 0.5 if re.search(r"\d|[一二三四五六七八九十百千万两]+[个种点步年倍]", txt) else 0
        sc += 0.4 if re.search(r"[?？吗呢]$", txt) else 0
        sc -= 0.8 if low.startswith(OPENERS) else 0
        sc -= 0.3 * (s["k"] == 0)
        out.append(dict(start=round(s["t"], 3), end=round(s["te"], 3), text=txt, dur=round(d, 2),
                        score=round(sc, 3)))
    out.sort(key=lambda h: -h["score"])
    out = out[:n]
    for k, h in enumerate(out):
        h["index"] = k
    return out


def hook_candidates(env):
    tr = _transcript_of(env)
    if not tr:
        raise RuntimeError("hook candidates: no transcript from the asr stage")
    hooks = rank_hooks(tr, n=int(env.params.get("hook_count") or 6), rng=env.params.get("range"))
    path = write_json(env.path("hooks.json"), dict(candidates=hooks, transcript=tr))
    return dict(candidates=path, n=len(hooks), files=[path])


def hook_payload(env, cp):
    out = env.inputs.get(cp["after"]) or {}
    c = (read_json(out.get("candidates"), {}) or {}).get("candidates") if out.get("candidates") else []
    pick = env.params.get("hook_default", -1)
    return dict(options=c or [], default=dict(pick=int(pick) if c else -1),
                previews=[dict(kind="json", path=out.get("candidates"))] if out.get("candidates") else [],
                skip=not c, skip_reason="no hook-worthy sentence")


def hook_apply(a):
    v = a.value or {}
    if "start" in v and "end" in v:
        h = dict(src=[float(v["start"]), float(v["end"])], lines=[v["text"]] if v.get("text") else [])
        return dict(params=dict(hook=h))
    k = int(v.get("pick", -1))
    if k < 0:
        return dict(params=dict(hook=None))
    opts = a.payload.get("options") or []
    if k >= len(opts):
        raise ValueError(f"hook: pick {k} out of range (0..{len(opts) - 1})")
    o = opts[k]
    return dict(params=dict(hook=dict(src=[o["start"], o["end"]], lines=[v.get("text") or o["text"]])))


# --------------------------------------------------------------------------- cover frames
def grab_frame(video, t, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", video, "-frames:v", "1",
                    "-q:v", "2", out], check=True)
    return out


def cover_frames(env):
    """Candidate cover frames of the composed (caption-free) master, ranked by ``vstudio.cover.score_frames``
    (sharpness, exposure, subject, faces, LAION aesthetic; crossfades skipped), else evenly spaced; + a sheet."""
    from vstudio import media
    video = None
    for dep in ["compose"] + [d for d in env.inputs if d != "compose"]:
        o = env.inputs.get(dep) or {}
        video = o.get("master") or o.get("final") or o.get("video")
        if video:
            break
    video = video or env.params.get("source")
    if not video or not os.path.exists(video):
        raise RuntimeError("cover frames: no composed master")
    dur = media.duration(video)
    n = int(env.params.get("cover_candidates") or 6)
    ts = []
    if env.params.get("cover_face_rank", True):
        try:
            from vstudio.cover import score_frames
            ts = [p["t"] for p in score_frames(video, top_n=n, step=6, min_gap=max(1.0, dur / (2 * n)),
                                               avoid=_transitions_of(env), log=env.log)]
        except Exception as e:  # noqa: BLE001  (no face model / no face: evenly spaced frames)
            env.log(f"face ranking skipped: {str(e)[:120]}")
    if not ts:
        ts = [dur * (k + 0.5) / n for k in range(n)]
    ts = clear_of_transitions(ts, _transitions_of(env), dur)
    cands = []
    for k, t in enumerate(ts):
        f = grab_frame(video, t, env.path(f"cand_{k}.jpg"))
        cands.append(dict(index=k, t=round(t, 3), image=f))
    sheet = env.path("sheet.jpg")
    try:
        media.contact_sheet(video, sheet, every=max(0.5, dur / 8), cols=4, thumb_w=200, max_frames=8)
    except Exception:  # noqa: BLE001
        sheet = None
    path = write_json(env.path("cover_candidates.json"), dict(video=video, candidates=cands))
    return dict(candidates=path, video=video, sheet=sheet, files=[path] + [c["image"] for c in cands])


def _transitions_of(env):
    """[[t0, t1], ...] crossfades of the master (a vlog render's ``shots`` file), else []."""
    for o in env.inputs.values():
        sp = (o or {}).get("shots") if isinstance(o, dict) else None
        if sp and os.path.exists(sp):
            return [list(x) for x in (read_json(sp, {}) or {}).get("transitions") or [] if len(x) == 2]
    return []


def clear_of_transitions(ts, transitions, dur, pad=0.35):
    """Cover candidates never sit in a crossfade (two shots on top of each other made a ghosted cover): a time
    inside one moves to the middle of the shot after it."""
    if not transitions:
        return ts
    tr = sorted(transitions)
    out = []
    for t in ts:
        hit = next((x for x in tr if x[0] - pad <= t <= x[1] + pad), None)
        if hit:
            nxt = next((x[0] for x in tr if x[0] > hit[1]), dur)
            t = min(dur - 0.1, (hit[1] + nxt) / 2)
        if all(abs(t - u) > 0.5 for u in out):
            out.append(round(t, 3))
    return out


def cover_payload(env, cp):
    out = env.inputs.get(cp["after"]) or {}
    d = read_json(out.get("candidates"), {}) or {}
    c = d.get("candidates") or []
    title = env.params.get("cover_text") or env.params.get("title") or ""
    return dict(options=[dict(index=x["index"], t=x["t"], image=x["image"]) for x in c], video=d.get("video"),
                default=dict(pick=0, text=title) if c else None,
                previews=[dict(kind="image", path=x["image"]) for x in c], skip=not c)


def cover_apply(a):
    v = a.value or {}
    opts = a.payload.get("options") or []
    if "t" in v:
        frame = grab_frame(a.payload["video"], float(v["t"]), a.answer_path(f"cover_frame_{int(float(v['t']) * 1000)}.jpg"))
        t = float(v["t"])
    else:
        k = int(v.get("pick", 0))
        if not 0 <= k < len(opts):
            raise ValueError(f"cover: pick {k} out of range")
        frame, t = opts[k]["image"], opts[k]["t"]
    text = v.get("text") or ""
    retouched = None
    if a.params.get("cover_retouch"):                 # the format's cover rule: her face slimmed + light makeup
        frame, retouched = retouch_cover_frame(frame, a.answer_path(f"cover_frame_{int(t * 1000)}.retouched.jpg"))
    try:
        cv = designed_covers(frame, text, a, t, retouched)
    except Exception as e:  # noqa: BLE001  (engine 2.0 failed: the classic covers, said in the record)
        cv = classic_covers(frame, text, a, t, retouched)
        cv["engine_error"] = str(e)[:200]
    cv.update(file=cv.get("file"), t=t, text=text)
    if retouched is not None:
        cv["retouched"] = retouched
    return dict(params=dict(cover=cv))


# generic canvases (the export picks the closest aspect for any platform without its own cover) and the platforms
# with a cover of their own (exact size, keep-outs, their language): vstudio.cover_engine
GENERIC_COVERS = {"file": ((1920, 1080), (160, 80, 1760, 1000)), "v916": ((1080, 1920), (60, 300, 1020, 1620)),
                  "v34": ((1080, 1440), (60, 120, 1020, 1240))}
OWN_COVERS = {"en": "youtube", "en_v916": "youtube-shorts", "bili": "bilibili"}


def designed_covers(frame, text, a, t, retouched):
    """Cover engine 2.0 (``vstudio.cover_engine``): the generic canvases in the Chinese text when a Chinese
    platform is targeted (else English), YouTube / Shorts in English, B站 in Chinese, + the YouTube A/B pack."""
    from vstudio import cover_engine as CE
    from vstudio import platform as P
    plats = a.params.get("platforms")
    plats = [x.strip() for x in (plats if isinstance(plats, (list, tuple)) else str(plats or "").split(","))
             if str(x).strip()]
    langs = {P.lang_for(p, "en") for p in plats} or {"zh" if _has_cjk(text) else "en"}
    title = a.params.get("title") or ""
    texts = {"zh": CE.mono_text(text, "zh") or CE.mono_text(title, "zh"),
             "en": CE.mono_text(text, "en") or CE.mono_text(title, "en")}
    gen_lang = "zh" if "zh" in langs and texts["zh"] else "en"
    tag = sha1_json([text, retouched, sorted(plats)])[:8]
    out_dir = os.path.dirname(a.answer_path(f"covers_{int(t * 1000)}_{tag}/x"))
    targets = {k: dict(name="generic", key=f"generic:{k}", size=sz, safe=safe, keepouts=[], lang=gen_lang,
                       max_bytes=None) for k, (sz, safe) in GENERIC_COVERS.items()}
    base = {P.canonical(p.split(":")[0]) for p in plats}
    for key, plat in OWN_COVERS.items():
        if plat in base:
            targets[key] = plat
    res = CE.make_covers(frame, texts, list(targets.values()), out_dir, stem=f"cover_{int(t * 1000)}",
                         log=lambda m: print(m))
    cv = dict(engine="cover-2", analysis=res.get("_analysis"))
    for key, tg in targets.items():
        r = res.get(tg if isinstance(tg, str) else tg["key"])
        if r:
            cv[key] = r["file"]
            cv.setdefault("legibility", {})[key] = r.get("ok")
    yt = res.get("youtube") or {}
    if len(yt.get("variants") or []) >= 2:
        cv["youtube_ab"] = ",".join(x["file"] for x in yt["variants"])
    if texts["en"]:
        cv["text_en"] = texts["en"]
    return cv


def classic_covers(frame, text, a, t, retouched):
    """The pre-2.0 covers: the frame + the text (``_text_cover``), subject crops for 9:16 / 3:4, an English twin."""
    from vstudio.batch.edits import _text_cover
    out = a.answer_path(f"cover_{int(t * 1000)}_{sha1_json([text, retouched])[:8]}.jpg")
    _text_cover(frame, text, out)
    cv = dict(file=out)
    # a landscape frame on a portrait cover: its own crop around the subject, with the same text (the export used
    # to fit the landscape cover on a blurred pad - a small picture in a grey band on 小红书 / Shorts)
    for key, (aw, ah) in (("v916", (9, 16)), ("v34", (3, 4))):
        try:
            crop = subject_crop(frame, aw / ah, a.answer_path(f"cover_frame_{int(t * 1000)}_{key}.jpg"))
        except Exception:  # noqa: BLE001  (no crop: the export pads the landscape cover as before)
            crop = None
        if crop:
            cv[key] = _text_cover(crop, text, a.answer_path(f"cover_{int(t * 1000)}_{key}_"
                                                            f"{sha1_json([text, retouched])[:8]}.jpg"))
    # YouTube / Shorts is always English (vstudio.platform.lang_for): a cover text with Chinese in it gets an English
    # twin for those targets ("Golden Hour · 黄金时刻 | Elliott Bay" -> "Golden Hour | Elliott Bay"; none: no text)
    if _has_cjk(text) and _goes_to_youtube(a.params.get("platforms")):
        en = english_cover_text(text)
        tag = sha1_json([en, retouched])[:8]
        cv["en"] = _text_cover(frame, en, a.answer_path(f"cover_{int(t * 1000)}_en_{tag}.jpg"))
        src916 = _crop_of(cv, a, t, "v916") or frame
        cv["en_v916"] = _text_cover(src916, en, a.answer_path(f"cover_{int(t * 1000)}_v916_en_{tag}.jpg"))
        cv["text_en"] = en
    return cv


def _crop_of(cv, a, t, key):
    """The subject crop ``cover_apply`` cut for ``key`` (v916 / v34), when it cut one."""
    p = a.answer_path(f"cover_frame_{int(t * 1000)}_{key}.jpg")
    return p if cv.get(key) and os.path.exists(p) else None


def _has_cjk(text):
    return bool(re.search(r"[\u3400-\u9fff]", str(text or "")))


def _goes_to_youtube(platforms):
    from vstudio import platform as P
    plats = platforms if isinstance(platforms, (list, tuple)) else str(platforms or "").split(",")
    return any(P.lang_fixed(p) for p in plats if str(p).strip())


def english_cover_text(text):
    """A bilingual cover text in English only: per line ("|" / newline), the parts ("·" / "/" / "—") with no Chinese;
    a line with nothing English left is dropped. "" when nothing is English."""
    out = []
    for line in re.split(r"\s*[|｜\n]\s*", str(text or "")):
        parts = [x.strip() for x in re.split(r"\s*[·•/／—]\s*", line) if x.strip() and not _has_cjk(x)]
        if parts:
            out.append(" · ".join(parts))
    return " | ".join(out)


def subject_crop(frame, aspect, out):
    """A crop of ``frame`` at ``aspect`` (w/h) centred on its most salient column band -> out, or None when the frame
    is already that narrow."""
    import numpy as np
    from PIL import Image
    im = Image.open(frame).convert("RGB")
    W, H = im.size
    cw = int(round(H * aspect))
    if cw >= W * 0.98:
        return None
    from vstudio import saliency
    small = im.resize((480, int(480 * H / W)))
    col = saliency.Analyzer(person=False)(np.asarray(small)[..., ::-1].copy())["map"].sum(0)
    G = len(col)
    k = max(1, int(round(G * cw / W)))
    sums = np.convolve(col, np.ones(k), "valid")
    x = int(np.argmax(sums)) / G * W
    x = int(min(max(0, x), W - cw))
    im.crop((x, 0, x + cw, H)).save(out, quality=92)
    return out


def retouch_cover_frame(frame, out):
    """vstudio.retouch on the picked cover frame (persona ``retouch.cover`` knobs over slim .05 / eye .04 /
    makeup .5) -> (path, True) or (frame, False) when no face is found - said in the cover record, not hidden."""
    from PIL import Image
    from vstudio.config import persona
    from vstudio.cover import _face_and_retouch
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(frame):
        return out, True
    knobs = dict(((persona().get("retouch") or {}).get("cover")) or {}) or True
    with Image.open(frame) as im:
        photo = im.convert("RGB")
    res, _fx = _face_and_retouch(photo, knobs, "auto")
    if res is photo:                                  # no face / no face model: the frame as it is
        return frame, False
    res.save(out, quality=94)
    return out, True


# --------------------------------------------------------------------------- generic choice
def choice_payload(env, cp):
    out = env.inputs.get(cp["after"]) or {}
    opts = out.get("options") or []
    if out.get("options_file"):
        opts = read_json(out["options_file"], []) or []
    return dict(options=opts, default=dict(pick=0) if opts else None,
                previews=[dict(kind=_kind_of(o.get("path")), path=o.get("path")) for o in opts if o.get("path")],
                skip=not opts)


def choice_apply(a):
    k = int((a.value or {}).get("pick", 0))
    opts = a.payload.get("options") or []
    if not 0 <= k < len(opts):
        raise ValueError("pick out of range")
    o = opts[k]
    return dict(params=dict(o.get("set") or {}))


# --------------------------------------------------------------------------- collectors
def collect_batch_exports(project, job, rows):
    ex = ((rows.get("export") or {}).get("out") or {}).get("exports") or []
    return [dict(platform=e.get("platform"), orientation=e.get("orientation"), kind="video", file=e.get("file"),
                 cover=e.get("cover"), post=e.get("post"), duration=e.get("duration"), **_geometry(e)) for e in ex]


def _geometry(e):
    """The export manifest's frame facts the players and the editor read (size, fps, safe / caption boxes)."""
    return {k: e[k] for k in ("w", "h", "fps", "safe_box", "caption_box") if e.get(k) is not None}


def collect_files(project, job, rows):
    """``outputs.files`` templates of the manifest (item dir relative), the ones that exist."""
    m = project.manifest
    t = static_tctx(m, job["params"], job["id"])
    out = []
    for tpl in m["outputs"].get("files") or []:
        try:
            p = M.fmt(tpl, t)
        except M.Missing:
            continue
        for f in sorted(_glob(p)):
            out.append(dict(platform=None, orientation=None, kind=_kind_of(f), file=f))
    return out


def _glob(p):
    import glob as G
    return [x for x in G.glob(p) if os.path.isfile(x)] if any(c in p for c in "*?[") else ([p] if os.path.isfile(p) else [])


def collect_vstudio_exports(project, job, rows):
    """``python -m vstudio.export`` folders of the item (``exports/manifest.json`` anywhere under the item dir)
    + the manifest's ``outputs.files``."""
    import glob as G
    out = []
    for man in sorted(G.glob(os.path.join(job["params"]["_item_dir"], "**", "manifest.json"), recursive=True)):
        d = read_json(man, {}) or {}
        base = os.path.dirname(man)
        for e in d.get("exports") or []:
            if not e.get("file"):
                continue
            j = lambda x: x and (x if os.path.isabs(x) else os.path.join(base, x))  # noqa: E731
            out.append(dict(platform=e.get("platform"), orientation=e.get("orientation"), kind="video",
                            file=j(e["file"]), cover=j(e.get("cover")), post=j(e.get("post")),
                            duration=e.get("duration"), **_geometry(e)))
    return out + collect_files(project, job, rows)


def collect_all(project, job, rows):
    return collect_batch_exports(project, job, rows) + collect_files(project, job, rows)


def copy_into(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)
    return dst


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, default=str)
