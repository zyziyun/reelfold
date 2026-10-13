"""Local HTTP API for the desk (stdlib only).

Security model
  * listens on a Unix domain socket the desk names (DESK_SOCKET: a file in the app's own temp folder, mode 0600) -
    no TCP port, nothing another device or a web page can reach; Windows (no AF_UNIX in CPython) binds 127.0.0.1 on
    a random port instead. Printed once on stdout as a JSON ``ready`` line. The desk's main process is the only
    client: it forwards the UI's app://desk/api/* requests (src/main/engineTransport.ts);
  * every /api request needs ``Authorization: Bearer <DESK_TOKEN>`` (per-launch token from the Electron main
    process, compared in constant time);
  * over TCP the Host header must be 127.0.0.1:<port> (DNS-rebinding guard); a present Origin must be in
    DESK_ALLOWED_ORIGINS (the desk UI's own origin) - CORS headers are only sent to those origins;
  * JSON bodies are capped at 1 MB and validated per route.

Routes (JSON unless noted)
  GET  /api/health                         mode real|mock, engine path, background (answers being continued)
  GET  /api/recipes
  GET  /api/roots                          folders the desk may show media from (Electron media protocol)
  GET  /api/batches                        registry + state + counts
  POST /api/batches                        {name, recipe, source|folder, segments?, platforms[], budget?, out_dir?}
  POST /api/batches/import                 {dir}
  GET  /api/batches/<id>                   status (meta + job rows)
  GET  /api/batches/<id>/estimate
  POST /api/batches/<id>/run               {pilot?, confirm_pilot?, resume?, retry_failed?, jobs?[]}
  POST /api/batches/<id>/cancel
  GET  /api/batches/<id>/review            review items (contact sheet, snippet, QC, cleanup edits to confirm)
  POST /api/batches/<id>/review/apply      {decisions: {job: {decision, reason}}, cleanup: {job: reply}}
  POST /api/batches/<id>/package           {per_day?, start?, times?[]}
  GET  /api/batches/<id>/package           manifest + verify (recomputed confirmation code)
                                           work folders / projects: POST {clips[], platforms[], per_day?, start?,
                                           times?[], times_by_platform?} -> packages/<id> (workpkg.py)
  GET  /api/batches/<id>/events?n=50&job=
  GET  /api/batches/<id>/jobs/<job>        job detail (stages, QC, cleanup words + edits, media paths)
  GET  /api/stream                         text/event-stream: status | log | run-start | run-exit | batches
                                           | clients | plan | job-edit | live
v0.2 (studio.py; engine command when available, desk implementation otherwise)
  GET  /api/capabilities                   which v0.2 engine commands exist
  GET  /api/clients | POST /api/clients    client workspaces (client.yaml)
  GET  /api/clients/<slug> | POST ...      show (config + effective) / update
  POST /api/clients/<slug>/crm             funnel stage, revenue, 7-day post data, next price
  POST /api/plans                          AI segment planning (async) -> {id}; GET /api/plans/<id>
  POST /api/plans/<id>/batch               accepted + edited segments -> segments.yaml -> batch
  POST /api/batches/<id>/client            {client}
  POST /api/batches/<id>/jobs/<job>/edit   {op: caption (+reasr)|trim|cut {start,end,why}|notes {lines}|hook|cover|copy,
                                           ...}; /undo; /rerun
  POST /api/batches/<id>/timing            {job, event: start|stop, what: review, active_s?}
  POST /api/batches/<id>/deliver           {client?, zip, cleanup_days?}; GET; POST .../deliver/cleanup
  GET  /api/metrics?batch=|client=         dashboard numbers; GET|POST /api/metrics/weekly (weekly_metrics.csv)
  GET  /api/cleanup/due | POST /api/cleanup/done   source cleanup after delivery (the desk moves to Trash)
History (history.py; read-only discovery of past work: desk + engine registries, projects, watched folders)
  GET  /api/history?q=&status=&kind=       [{kind batch|project, id, dir, name, recipe, client, series, created,
                                           updated, counts, status, thumb, sources, opened, openable}]
  GET  /api/history/stamp                  {stamp}: changes when a project / batch registry changes (the desk polls it)
  GET  /api/history/config | POST {watch[]}   watched folders (default ~/Desktop/video-studio-demos)  (check-skill: allow)
  POST /api/history/open {dir}             put a found batch / project in the desk list -> {id, dir}
  GET  /api/history?archived=1             only the archived rows (+ archived: true, archived_at); the plain list
                                           leaves them out and counts them in ``archived``
  POST /api/history/archive {dir}|{dirs[]} archive (never deletes files; refused while a run is going)
  POST /api/history/restore {dir}|{dirs[]} back into All projects as before (desk list row too)
  POST /api/history/hide {dir}             old alias of archive; /unhide-one {dir} of restore; POST /api/history/unhide
                                           restores everything
  POST /api/history/client {dir, client}   agency mode: the client a project is for ('' = her own)
  POST /api/history/trash-plan {dirs[]}    Delete, step 1: what would go to the Trash per project folder (the desk's
                                           main process moves it after her confirm) {items [{dir, name, ok, reason?,
                                           target, files, bytes, keep[] (her footage: stays), inside[]}]}
  POST /api/history/forget {dirs[]}        Delete, step 2: folders now in the Trash leave the desk's notes
                                           (trash-plan / forget: older desks; the Delete dialog uses /api/delete)
Delete (purge.py: Reelfold-made files only - her footage / recordings never; running ones refused)
  POST /api/delete/plan {dirs[], clips[{item, clip}], requests[]}  -> {items [{key, kind, name, ok, reason?, targets[],
                                           files, bytes, keep[], other[]}], keep[], files, bytes, sig}
  POST /api/delete/stage {..., sig}        Move to Trash, step 1: out of every list now -> {id, targets[]}; the desk's
                                           main process moves the targets to the Trash once the Undo toast is gone;
                                           GET /api/delete/pending[/<id>]; POST .../<id>/undo; POST .../<id>/commit
                                           {trashed[], failed[]} (step 2: their notes go - calendar, goals, titles)
  POST /api/delete/hard {..., sig, confirm: true}   Delete permanently: removed from disk now, then their notes go
  POST /api/history/item/<id>/stop|resume  stop a project's run (pilot.stop: resumable) / run it on (Try again)
  POST /api/history/item/<id>/finish       its clips not made yet made (a pilot goes on to the rest) -> {started}
  GET  /api/history/item/<id>              one entry; work folders + detail {outputs, covers, sheets, posts, notes}
  POST /api/history/item/<id>/adopt        {recipe?: guess|name, title?} plain work folder -> .vstudio/work.json
  GET  /api/history/item/<id>/progress?n=  the run's last events as codes (「看过程」 in the control room)
  GET  /api/history/item/<id>/pieces       the making piece by piece (outputs.pieces: each stage's wip files while it
                                           runs, finished previews, a waiting checkpoint's options; media only)
  GET  /api/live/request/<id>?cursor=      the live pane (live.py): a request's / a project run's transcript - the
  GET  /api/live/project/<item>?cursor=    model CLIs' turns + the engine's stages and log, redacted - after the
                                           cursor; while watched, ``live {key}`` stream events say it grew
v0.4 (outputs.py, intake.py, inbox.py; engine command when available, desk implementation otherwise)
  GET  /api/outputs/<item>                 one clip per output {clips [{id, title, state, files, cover, post}], confirm}
  GET  /api/outputs/<item>/<clip>          player + editor document (words, captions, effects, caps, ops, version)
  POST /api/outputs/<item>/<clip>/pickup   {session_dir, at_word | replace [i0, i1], sig?} splice a recorded pickup in
                                           (one undo step) -> {step, pickup, doc}
  POST /api/outputs/<item>/<clip>/edit     {ops: [op...], by?, note?} (one undo step; a transcript cut {op: cut,
                                           words: [i0, i1], sig, why} also re-times captions / effects in that
                                           step);  /preview-edl {ops} -> kept ranges of pending cuts (live skip);
                                           /ask {prompt} -> proposals;
                                           /render {quality?, targets?, with_ops?};  /undo | /redo {steps?}
                                           /revert {step} (one earlier step, later ones kept); /chat {add} |
                                           {turn, set} (the clip's chat transcript; show returns it as chat);
                                           /export {targets, watermark?} -> {job} + output-render events
                                           (watermark true / false: this export, absent: her default);
                                           /export-stop {job};  /title {title|null} her title for the clip
                                           (null: back to the AI's; publish cards without their own title follow)
  POST /api/outputs/<item>/project-ask     {prompt, clips?, context?} project-level AI (every clip) -> {job};
                                           GET /api/project-ask/<job> {state, stages, notices, elapsed, result};
                                           POST /api/project-ask/<job>/stop (kills the engine + model CLI);
                                           POST /api/outputs/<item>/regenerate {items} (needs_rerender action)
  POST /api/outputs/<item>[/<clip>]/nle     {format xmeml|jianying|capcut|otio, media link|copy, to_app} the edit
                                           for editing software (engine output nle): one clip, or every clip
  GET  /api/outputs/<item>/<clip>/strip    timeline filmstrip sprite + audio peaks (timeline.py, cached);
                                           POST|GET .../transcribe 「听一遍」 -> output-transcribe events
  GET  /api/effects                        effects catalogue (zh labels, params, preview kind)
  GET|POST /api/ai/<item> {ai {provider, model?} | null, by? you|chat|group}   the project's AI (aichoice.py):
                                           every AI step of it uses it, a running one from its next step; null =
                                           the app's default; POST /api/intake/<id>/ai {ai} (a request);
                                           POST /api/goals/<id>/ai {ai, video?} (the group / one of its videos)
  POST /api/intake {prompt, inputs[], platforms?, lang?, mode? autopilot|ask, sample_name?, ai?}  -> {id};
                                           GET /api/intake/<id>; POST .../revise {prompt}; POST .../apply
                                           {plan?, run?}; POST .../stop (planning / revising); POST .../retry (a
                                           failed plan / revision / apply again); POST .../discard; GET
                                           /api/intake/recent; GET /api/intake/open (requests not projects yet)
                                           POST .../add {inputs?, text?} (what a ``needs`` request waited for);
                                           POST .../go-on (plan it without); GET /api/intake/open?archived=1 (the
                                           archived ones); POST /api/intake/archive | restore | delete {ids[]}
                                           (the Studio's row menu: delete = a request that never became a project
                                           is gone for good; her files are never touched)
  GET  /api/brain/<item>; POST .../refresh; POST .../template {id}; POST .../shot {id, set | reset};
       POST .../gen {id, action approve | skip | undo, code?}  the editor brain: template + why, the per-shot plan,
       "Could be generated" proposals; POST .../estimate {id} + .../generate {id, estimate_id, confirm_code,
       max_cny, code} (the Create spend gate: only her click spends), .../place {id, undo?}; GET .../shots?clip=
       (the clip's shots + why)   (brain.py)
  GET  /api/autopilot/<item>; POST .../reopen {checkpoint, item}; POST .../mode {on};
       POST .../change {checkpoint, item, answer}; POST .../remake {item, do {checkpoint: choice | null}}
       (a finished clip's vertical framing / post copy made again, older projects too)   (autopilot.py)
  POST /api/import/check {inputs[]}        finished videos vs footage in what was dropped (imports.py); POST
       /api/import {inputs[], sources?[], title?} -> {job} + ``import`` events; GET /api/import/job/<job>;
       GET /api/import/<item>; POST .../match {clip?} (``import-match``); POST .../copy {clip} (``import-copy``);
       POST .../sources {clip, sources[]} (footage linked afterwards, then matched);
       GET .../takes?clip=&shot= (other takes of a shot, with stills)
  GET  /api/home/suggestions               Home's chips from her own signals (homesuggest.py): requests sent more
                                           than once, fresh recordings in a watched folder no project uses yet
  GET  /api/sample                         the built-in sample recording (copied out of the app) -> {available, path, ...};
       POST /api/sample/remove {dir}       delete a project made from it (sample.py)
  POST /api/pilot/retry {item, provider?}  re-run a failed pilot (provider: every model task on it, e.g. codex)
  GET  /api/calendar?start=YYYY-MM-DD      {posts, queue}; POST /api/calendar {item, clip, platform, at};
                                           POST /api/calendar/<id> {at?, state?, remove?, caption?, platform?,
                                           enabled?, stats?}; POST .../confirm {start}; .../many {posts[]} (one
                                           undo); .../remove {ids} -> removed rows; .../restore {posts}; .../fill-week
                                           {start, platforms, times, clips?}; .../plan {text, start, platforms, times,
                                           clips?} (preview only, never written); .../shorten
                                           {text, platform, max?} (「为 X 缩短」, nothing saved)
  POST /api/weekplan {inputs[], text?, start, today, platforms, times, lang}  「一周的帖子」 -> plan (weekplan.py);
                                           GET /api/weekplan (still going) | /api/weekplan/<id>; POST .../run |
                                           .../reword {text} | .../confirm (scheduleMany, one undo) | .../dismiss
  GET  /api/share/<item>                   share for review (share.py): clips + versions + privacy warnings;
                                           POST {clips?, quality?, footer?, title?, expiry_note?, ack?} -> {job};
                                           GET /api/share-jobs/<job>; POST /api/feedback/import {text} -> Inbox items
  GET  /api/watermark                      Settings › Watermark (watermark.py): settings + previews over sample
                                           9:16 / 16:9 frames; POST {patch}; POST /api/watermark/logo {path}
  GET  /api/inbox                          every decision waiting for the creator; POST /api/inbox/answer {keys,
                                           answer?}; POST /api/inbox/undo {keys}; POST /api/inbox/open {key,
                                           which file|template|doc} (an author item's file in the default editor);
                                           POST /api/inbox/redraft {key, instruction?} (the engine drafts an author
                                           item again, in the background: "Draft it for me" / "ask in plain words")
"""
import hmac
import json
import os
import queue
import re
import threading
import traceback
import socketserver
import stat
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import metrics as MET
from .common import JOB_RE, NAME_RE, BadRequest, batch_id, need
from .v02store import CLIENT_RE

MAX_BODY = 1 << 20
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
PLATFORM_RE = re.compile(r"^[a-z][a-z-]{0,30}(:[a-z]{3,12})?$")
ID_RE = re.compile(r"^[0-9a-f]{12}$")


def _num(v, lo, hi, name):
    need(isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi, f"{name} must be {lo}..{hi}")
    return v


def _abs_path(v, name, must_exist=True, kind=None):
    need(isinstance(v, str) and 0 < len(v) < 4096 and os.path.isabs(v) and "\0" not in v,
         f"{name} must be an absolute path")
    if must_exist:
        need(os.path.exists(v), f"{name} does not exist")
        if kind == "file":
            need(os.path.isfile(v), f"{name} must be a file")
        if kind == "dir":
            need(os.path.isdir(v), f"{name} must be a folder")
    return os.path.normpath(v)


def validate_create(b):
    need(isinstance(b, dict), "body must be an object")
    need(isinstance(b.get("name"), str) and NAME_RE.match(b["name"]), "name: letters (any language), digits, space . _ - (max 64)")
    need(b.get("recipe") in ("longform-slices", "talkinghead-clips") or
         (isinstance(b.get("recipe"), str) and NAME_RE.match(b["recipe"])), "recipe required")
    out = dict(name=b["name"], recipe=b["recipe"])
    if b.get("source"):
        out["source"] = _abs_path(b["source"], "source", kind="file")
    if b.get("folder"):
        out["folder"] = _abs_path(b["folder"], "folder", kind="dir")
    need(bool(out.get("source")) != bool(out.get("folder")), "give exactly one of source (file) or folder")
    if b.get("segments"):
        out["segments"] = _abs_path(b["segments"], "segments", kind="file")
        need(out["segments"].lower().endswith((".yaml", ".yml", ".csv", ".json")), "segments: .yaml/.csv/.json")
    if out["recipe"].startswith("longform"):
        need(out.get("source"), f"{out['recipe']} needs a source file (one long recording)")
    if out["recipe"] == "longform-slices":
        need(out.get("segments"), "longform-slices needs segments.yaml (the job list)")
    pl = b.get("platforms") or []
    need(isinstance(pl, list) and 0 < len(pl) <= 8 and all(isinstance(p, str) and PLATFORM_RE.match(p) for p in pl),
         "platforms: 1-8 entries like tiktok or xiaohongshu:full")
    out["platforms"] = pl
    if b.get("budget") is not None:
        bud = b["budget"]
        need(isinstance(bud, dict), "budget must be an object")
        out["budget"] = {}
        for k, hi in (("max_usd", 100000), ("max_hours", 1000), ("max_storage_gb", 100000)):
            if bud.get(k) is not None:
                out["budget"][k] = _num(bud[k], 0, hi, f"budget.{k}")
    if b.get("out_dir"):
        out["out_dir"] = _abs_path(b["out_dir"], "out_dir", must_exist=False)
    if b.get("planner"):
        need(b["planner"] in ("file", "claude"), "planner: file | claude")
        out["planner"] = b["planner"]
    if b.get("client"):
        out["client"] = _client(b["client"])
    return out


# ------------------------------------------------------------------ v0.2 validators
PID_RE = re.compile(r"^[0-9a-f]{12}$")
WEEK_RE = re.compile(r"^W\d{1,2}$")


def _client(v):
    need(isinstance(v, str) and CLIENT_RE.match(v), "client: a-z 0-9 _ - (max 40)")
    return v


def _str(v, name, lo=0, hi=200):
    need(isinstance(v, str) and lo <= len(v) <= hi, f"{name}: {lo}-{hi} chars")
    return v


def _strlist(v, name, n, ln):
    need(isinstance(v, list) and len(v) <= n and all(isinstance(x, str) and len(x) <= ln for x in v),
         f"{name}: up to {n} strings (max {ln} chars)")
    return v


def _platforms(v):
    need(isinstance(v, list) and 0 < len(v) <= 8 and all(isinstance(p, str) and PLATFORM_RE.match(p) for p in v),
         "platforms: 1-8 entries like tiktok or xiaohongshu:full")
    return v


def _hook(h, name):
    need(isinstance(h, dict), f"{name} must be an object")
    out = dict(start=_num(h.get("start"), 0, 1e6, f"{name}.start"), end=_num(h.get("end"), 0, 1e6, f"{name}.end"),
               text=_str(h.get("text") or "", f"{name}.text", 0, 200))
    need(out["end"] > out["start"], f"{name}: end must be after start")
    return out


def validate_client_create(b):
    need(isinstance(b, dict), "body must be an object")
    _client(b.get("slug"))
    return b


def validate_plan(b):
    need(isinstance(b, dict), "body must be an object")
    out = dict(source=_abs_path(b.get("source"), "source", kind="file"))
    out["count"] = int(_num(b.get("count", 6), 1, 50, "count"))
    out["min"] = float(_num(b.get("min", 30), 5, 600, "min"))
    out["max"] = float(_num(b.get("max", 90), out["min"], 900, "max"))
    need(b.get("provider", "none") in ("claude", "openai", "none"), "provider: claude | openai | none")
    out["provider"] = b.get("provider", "none")
    if b.get("platforms"):
        out["platforms"] = _platforms(b["platforms"])
    if b.get("client"):
        out["client"] = _client(b["client"])
    return out


def validate_plan_batch(b):
    need(isinstance(b, dict), "body must be an object")
    need(isinstance(b.get("name"), str) and NAME_RE.match(b["name"]), "name: letters (any language), digits, space . _ - (max 64)")
    segs = b.get("segments")
    need(isinstance(segs, list) and 0 < len(segs) <= 200, "segments: 1-200 accepted segments")
    rows = []
    for i, s in enumerate(segs):
        n = f"segments[{i}]"
        need(isinstance(s, dict), f"{n} must be an object")
        r = dict(start=_num(s.get("start"), 0, 1e6, f"{n}.start"), end=_num(s.get("end"), 0, 1e6, f"{n}.end"),
                 title=_str(s.get("title"), f"{n}.title", 1, 100))
        for k, hi in (("chapter", 60), ("why", 500), ("risk", 500), ("body", 2000)):
            if s.get(k):
                r[k] = _str(s[k], f"{n}.{k}", 0, hi)
        if s.get("notes"):
            r["notes"] = _strlist(s["notes"], f"{n}.notes", 10, 200)
        if s.get("tags"):
            r["tags"] = _strlist(s["tags"], f"{n}.tags", 20, 30)
        if s.get("hook"):
            r["hook"] = _hook(s["hook"], f"{n}.hook")
        if s.get("hook_candidates"):
            need(isinstance(s["hook_candidates"], list) and len(s["hook_candidates"]) <= 10, f"{n}.hook_candidates")
            r["hook_candidates"] = [_hook(h, f"{n}.hook_candidates") for h in s["hook_candidates"]]
        rows.append(r)
    out = dict(name=b["name"], segments=rows, platforms=_platforms(b.get("platforms")))
    if b.get("client"):
        out["client"] = _client(b["client"])
    if b.get("budget") is not None:
        out["budget"] = validate_create(dict(name="x", recipe="talkinghead-clips", folder="/", platforms=["tiktok"],
                                             budget=b["budget"]))["budget"]
    if b.get("out_dir"):
        out["out_dir"] = _abs_path(b["out_dir"], "out_dir", must_exist=False)
    return out


def validate_edit(b):
    need(isinstance(b, dict), "body must be an object")
    op = b.get("op")
    need(op in ("caption", "trim", "cut", "notes", "hook", "cover", "copy"),
         "op: caption | trim | cut | notes | hook | cover | copy")
    if op == "caption":
        cue = b.get("cue")
        need(isinstance(cue, int) and not isinstance(cue, bool) and 0 <= cue <= 100000, "cue: caption index")
        need(b.get("reasr") in (None, True, False), "reasr must be a boolean")
        out = dict(cue=cue, text=_str(b.get("text"), "text", 1, 200))
        if b.get("reasr"):
            out["reasr"] = True
        return op, out
    if op == "cut":
        a, z = _num(b.get("start"), 0, 1e6, "start"), _num(b.get("end"), 0, 1e6, "end")
        need(z > a, "end must be after start")
        return op, dict(start=float(a), end=float(z), why=_str(b.get("why") or "", "why", 0, 200))
    if op == "notes":
        lines = _strlist(b.get("lines") if b.get("lines") is not None else [], "lines", 12, 80)
        need(all("|" not in x for x in lines), "notes lines cannot contain |")
        return op, dict(lines=[x.strip() for x in lines if x.strip()])
    if op == "trim":
        a, z = _num(b.get("start"), 0, 1e6, "start"), _num(b.get("end"), 0, 1e6, "end")
        need(z > a, "end must be after start")
        return op, dict(start=float(a), end=float(z))
    if op == "hook":
        k = b.get("pick")
        need(isinstance(k, int) and not isinstance(k, bool) and 0 <= k < 20, "pick: hook candidate index")
        return op, dict(pick=k)
    if op == "cover":
        t = b.get("t")
        return op, dict(t=None if t is None else float(_num(t, 0, 36000, "t")), text=_str(b.get("text") or "", "text", 0, 60))
    return op, dict(title=_str(b.get("title"), "title", 1, 100), body=_str(b.get("body") or "", "body", 0, 2000),
                    tags=[t.strip().lstrip("#") for t in _strlist(b.get("tags") or [], "tags", 30, 30) if t.strip()])


def validate_timing(b):
    need(isinstance(b, dict), "body must be an object")
    need(isinstance(b.get("job"), str) and JOB_RE.match(b["job"]), "bad job id")
    need(b.get("event") in ("start", "stop"), "event: start | stop")
    need(b.get("what", "review") == "review", "what: review")
    out = dict(job=b["job"], event=b["event"], what="review")
    if b["event"] == "stop":
        out["active_s"] = float(_num(b.get("active_s", 0), 0, 86400, "active_s"))
    return out


def validate_deliver(b):
    need(isinstance(b, dict), "body must be an object")
    out = dict(zip=True)
    if b.get("client"):
        out["client"] = _client(b["client"])
    if "zip" in b:
        need(isinstance(b["zip"], bool), "zip must be a boolean")
        out["zip"] = b["zip"]
    if b.get("cleanup_days") is not None:              # 0 = never delete the sources (engine --cleanup-days 0)
        out["cleanup_days"] = int(_num(b["cleanup_days"], 0, 365, "cleanup_days"))
    return out


def validate_cleanup_set(b):
    need(isinstance(b, dict) and isinstance(b.get("enabled"), bool), "enabled must be a boolean")
    out = dict(enabled=b["enabled"], days=None)
    if b.get("days") is not None:
        out["days"] = int(_num(b["days"], 1, 365, "days"))
    need(not out["enabled"] or out["days"], "days required when enabled")
    return out


def validate_crm(b):
    need(isinstance(b, dict), "body must be an object")
    out = {}
    if b.get("stage"):
        need(b["stage"] in MET.FUNNEL + ("lost",), f"stage: {' | '.join(MET.FUNNEL)} | lost")
        out["stage"] = b["stage"]
    if b.get("revenue") is not None:
        out["revenue"] = float(_num(b["revenue"], 0, 1e7, "revenue"))
    if b.get("price_next") is not None:
        out["price_next"] = float(_num(b["price_next"], 0, 1e7, "price_next"))
    if b.get("note") is not None:
        out["note"] = _str(b["note"], "note", 0, 2000)
    if b.get("date"):
        need(isinstance(b["date"], str) and DATE_RE.match(b["date"]), "date: YYYY-MM-DD")
        out["date"] = b["date"]
    if b.get("post"):
        p = b["post"]
        need(isinstance(p, dict), "post must be an object")
        post = dict(platform=_str(p.get("platform") or "", "post.platform", 1, 40))
        for k in ("plays", "saves", "likes", "comments", "followers"):
            if p.get(k) is not None:
                post[k] = int(_num(p[k], 0, 1e10, f"post.{k}"))
        if p.get("url"):
            need(isinstance(p["url"], str) and p["url"].startswith("https://") and len(p["url"]) < 2048, "post.url: https")
            post["url"] = p["url"]
        if p.get("batch"):
            need(isinstance(p["batch"], str) and ID_RE.match(p["batch"]), "post.batch: batch id")
            post["batch"] = p["batch"]
        if p.get("posted"):
            need(isinstance(p["posted"], str) and DATE_RE.match(p["posted"]), "post.posted: YYYY-MM-DD")
            post["posted"] = p["posted"]
        out["post"] = post
    need(out, "nothing to update")
    return out


def validate_weekly(b):
    need(isinstance(b, dict) and isinstance(b.get("week"), str) and WEEK_RE.match(b["week"]), "week: W1..W99")
    v = b.get("values")
    need(isinstance(v, dict) and set(v) <= set(MET.MANUAL_COLUMNS), f"values: {', '.join(MET.MANUAL_COLUMNS)}")
    for k, x in v.items():
        need(x is None or (isinstance(x, (int, float)) and not isinstance(x, bool)) or (isinstance(x, str) and len(x) <= 20),
             f"{k}: number")
    return dict(week=b["week"], values=v)


def validate_run(b):
    need(isinstance(b, dict), "body must be an object")
    out = {}
    if b.get("pilot") is not None:
        out["pilot"] = int(_num(b["pilot"], 1, 50, "pilot"))
    for k in ("confirm_pilot", "resume", "retry_failed"):
        if b.get(k) is not None:
            need(isinstance(b[k], bool), f"{k} must be a boolean")
            out[k] = b[k]
    if b.get("jobs"):
        need(isinstance(b["jobs"], list) and len(b["jobs"]) <= 1000 and
             all(isinstance(j, str) and JOB_RE.match(j) for j in b["jobs"]), "jobs: list of job ids")
        out["jobs"] = b["jobs"]
    return out


def validate_decisions(b):
    need(isinstance(b, dict), "body must be an object")
    dec, cl = b.get("decisions") or {}, b.get("cleanup") or {}
    need(isinstance(dec, dict) and isinstance(cl, dict), "decisions / cleanup must be objects")
    need(len(dec) + len(cl) <= 5000, "too many decisions")
    out = dict(decisions={}, cleanup={})
    for jid, d in dec.items():
        need(JOB_RE.match(jid or ""), f"bad job id {jid!r}")
        need(isinstance(d, dict) and d.get("decision") in ("approve", "reject"), f"{jid}: decision approve|reject")
        r = d.get("reason") or ""
        need(isinstance(r, str) and len(r) <= 500, f"{jid}: reason max 500 chars")
        out["decisions"][jid] = dict(decision=d["decision"], reason=r)
    for jid, reply in cl.items():
        need(JOB_RE.match(jid or ""), f"bad job id {jid!r}")
        need(isinstance(reply, str) and len(reply) <= 2000, f"{jid}: cleanup reply must be text")
        out["cleanup"][jid] = reply
    return out


def validate_package(b):
    need(isinstance(b, dict), "body must be an object")
    out = {}
    if b.get("per_day") is not None:
        out["per_day"] = int(_num(b["per_day"], 1, 20, "per_day"))
    if b.get("start"):
        need(isinstance(b["start"], str) and DATE_RE.match(b["start"]), "start: YYYY-MM-DD")
        out["start"] = b["start"]
    if b.get("times"):
        need(isinstance(b["times"], list) and all(isinstance(t, str) and TIME_RE.match(t) for t in b["times"]),
             "times: [HH:MM, ...]")
        out["times"] = b["times"]
    return out


class Api:
    def __init__(self, engine, bus, token, origins, studio=None, kinds=None):
        """``kinds``: {History | Intake | Strips | CreateApi: class} replacing the built-in part (the test engine in
        engine/tests/fixtures passes its in-memory versions; the product never does)."""
        self.engine, self.bus, self.token, self.origins = engine, bus, token, set(origins)
        if studio is None:
            from .caps import Capabilities
            from .studio import Studio
            studio = Studio(engine, engine.data_dir, bus, Capabilities(fixed=set()))
        self.studio = studio
        from .common import Registry
        from .create import CreateApi
        from .history import History
        from .intake import Intake
        from .timeline import Strips
        from .autopilot import Autopilot
        K = {**dict(History=History, Intake=Intake, Strips=Strips, CreateApi=CreateApi, Autopilot=Autopilot),
             **(kinds or {})}
        self.history = K["History"](engine.data_dir, getattr(engine, "reg", None) or Registry(engine.data_dir), engine)
        from .inbox import Inbox
        from .outputs import Outputs, probe
        runner = getattr(studio, "runner", None)
        real = engine.mode == "real"
        self.outputs = Outputs(engine.data_dir, self.history, runner if real else None, bus)
        from .projask import ProjectAsk
        self.project_ask = ProjectAsk(self.outputs, bus)
        self.strips = K["Strips"](engine.data_dir, self.outputs, self.history, bus)
        from .history import vstudio_home
        from .sample import Sample
        self.sample = Sample(engine.data_dir, vstudio_home)
        self.intake = K["Intake"](engine.data_dir, bus, runner, engine.mode, probe=probe, sample=self.sample)
        from .goals import Goals                   # goal mode: one request -> several videos, made as a group
        self.goals = Goals(engine.data_dir, bus, self.intake, self.history, runner if real else None, engine.mode)
        self.inbox = Inbox(engine.data_dir, self.history, runner, engine.mode, bus)
        self.inbox.outputs = self.outputs
        self.autopilot = K["Autopilot"](self.history, runner if real else None, bus, intake=self.intake)
        self.project_ask.autopilot = self.autopilot
        from .brain import Brain                    # the editor brain: template, per-shot plan, generation proposals
        self.brain = Brain(self.history, runner if real else None, bus, outputs=self.outputs)
        self.outputs.autopilot = self.autopilot        # the clip chat's "follow the subject" / "rewrite the copy"
        from .imports import Imports                # finished videos made elsewhere -> second-pass editing
        self.imports = Imports(engine.data_dir, self.history, self.outputs, self.strips, bus, runner if real else None)
        if real and runner is not None:            # runs that waited in line when the app quit go back in line
            import threading

            def requeue():
                from . import pilot
                try:
                    dirs = [r["dir"] for r in self.history.list()["items"] if r.get("kind") in ("project", "work")]
                    pilot.requeue(runner.python, runner.env, dirs, bus)
                except Exception:  # noqa: BLE001  (the history is read again on the next list)
                    pass
            threading.Thread(target=requeue, daemon=True).start()
        from .calendar import Calendar
        self.calendar = Calendar(engine.data_dir, self.history, self.outputs, bus, mode=engine.mode)
        from .purge import Purge                   # Delete: Move to Trash (undo) / Delete permanently; never her footage
        self.purge = Purge(engine.data_dir, self.history, self.intake, self.calendar, self.outputs, self.goals, bus)
        from .workpkg import WorkPackages
        self.workpkg = WorkPackages(engine.data_dir, self.history, self.outputs)
        from .weekplan import WeekPlans            # 「这周的素材 → 一周的帖子」 (intake + run + calendar.plan)
        self.weekplans = WeekPlans(engine.data_dir, bus, self.intake, self.calendar, self.history,
                                   runner if real else None)
        # Create page: idle until the desk calls /api/create (flag)
        self.create = K["CreateApi"](engine.data_dir, bus, runner if real else None, engine.mode,
                                     history=self.history, calendar=self.calendar, outputs=self.outputs)
        self.inbox.extra.append(self.create.inbox_items)
        # a goal's own requests are its business (it retries or drops them): not Inbox items of their own
        self.inbox.extra.append(lambda: self.goals.without_owned(self.intake.inbox_items()))
        self.inbox.extra.append(self.goals.inbox_items)
        if hasattr(self.inbox, "post"):            # the group decides what of its projects needs her (goals.py)
            self.inbox.post.append(self.goals.filter_inbox)
        from .share import Share                   # share for review: static page + feedback -> Inbox
        self.share = Share(engine.data_dir, self.history, self.outputs, self.inbox, bus)
        from .watermark import Watermark           # Settings › Watermark (vstudio.watermark settings + previews)
        self.watermark = Watermark()
        from .live import LiveHub                  # the live pane: a job's transcript + a nudge when it grows
        self.live = LiveHub(bus)
        self.port = None
        self.socket_path = None

    def roots(self):
        out = list(self.engine.roots())
        for p in self.studio.plans.values():
            out.append(os.path.dirname(p["request"]["source"]))
        out += self.history.roots()
        for j in list(self.intake.jobs.values()):
            for p in j.get("inputs") or []:
                out.append(p if os.path.isdir(p) else os.path.dirname(p))
            for p in j.get("applied") or []:
                out.append(p["dir"])
        out += self.create.roots()
        out += self.goals.roots()
        return sorted(set(out))

    def _route_import(self, method, parts, query, b):
        def paths(v, name, n=200):
            need(isinstance(v, list) and len(v) <= n, f"{name}: up to {n} files / folders")
            return [_abs_path(p, f"{name}[]") for p in v]
        if parts == ["import", "check"] and method == "POST":
            ins = paths(b.get("inputs") or [], "inputs")
            need(ins, "inputs: the files / folders to look at")
            return self.imports.check(ins)
        if parts == ["import"] and method == "POST":
            ins = paths(b.get("inputs") or [], "inputs")
            need(ins, "inputs: the finished videos (files / folders)")
            src = paths(b.get("sources") or [], "sources")
            t = b.get("title")
            need(t is None or (isinstance(t, str) and len(t) <= 200), "title: up to 200 chars")
            return self.imports.start(ins, src, t.strip() if t else None)
        if len(parts) == 3 and parts[1] == "job" and method == "GET":
            return self.imports.get(parts[2])
        need(len(parts) >= 2 and ID_RE.match(parts[1]), "bad item id")
        if len(parts) == 2 and method == "GET":
            return self.imports.info(parts[1])
        if parts[2:] == ["match"] and method == "POST":
            c = b.get("clip")
            need(c is None or (isinstance(c, str) and len(c) <= 200), "clip: a clip id")
            return self.imports.match(parts[1], c)
        if parts[2:] == ["sources"] and method == "POST":
            need(isinstance(b.get("clip"), str) and 0 < len(b["clip"]) <= 200, "clip: a clip id")
            src = paths(b.get("sources") or [], "sources")
            need(src, "sources: footage files / folders")
            return self.imports.link(parts[1], b["clip"], src)
        if parts[2:] == ["copy"] and method == "POST":
            need(isinstance(b.get("clip"), str) and 0 < len(b["clip"]) <= 200, "clip: a clip id")
            return self.imports.copy(parts[1], b["clip"])
        if parts[2:] == ["takes"] and method == "GET":
            clip = (query.get("clip") or [""])[0]
            shot = (query.get("shot") or [""])[0]
            need(clip and shot.isdigit(), "clip and shot")
            return self.imports.takes(parts[1], clip, int(shot))
        raise KeyError("no such import route")

    def _route_delete(self, method, parts, b):
        """Delete (purge.py): plan -> Move to Trash (stage; the desk's main process moves the paths after the Undo
        toast, then commit) or Delete permanently (hard)."""
        p = self.purge
        if parts == ["plan"] and method == "POST":
            return p.plan(b)
        if parts == ["stage"] and method == "POST":
            return p.stage(b, b.get("sig"))
        if parts == ["hard"] and method == "POST":
            need(b.get("confirm") is True, "confirm: true (Delete permanently asks twice)")
            return p.hard(b, b.get("sig"))
        if parts == ["pending"] and method == "GET":
            return p.pending()
        if len(parts) >= 2 and parts[0] == "pending" and re.match(r"^[0-9a-f]{12}$", parts[1]):
            if len(parts) == 2 and method == "GET":
                return p.pending_one(parts[1])
            if parts[2:] == ["undo"] and method == "POST":
                return p.undo(parts[1])
            if parts[2:] == ["commit"] and method == "POST":
                tr, fl = b.get("trashed") or [], b.get("failed") or []
                need(isinstance(tr, list) and isinstance(fl, list) and len(tr) + len(fl) <= 5000 and
                     all(isinstance(x, str) and os.path.isabs(x) for x in tr + fl), "trashed / failed: absolute paths")
                return p.commit(parts[1], tr, fl)
        raise KeyError("no such delete route")

    def route_v04(self, method, parts, query, body):
        """v0.4: outputs (player + second-pass editor), intake (composer -> plan card), inbox. None = not mine."""
        from urllib.parse import unquote
        b = body if isinstance(body, dict) else {}
        if parts[:1] == ["effects"] and method == "GET":
            return self.outputs.effects()
        if parts[:1] == ["delete"]:
            return self._route_delete(method, parts[1:], b)
        if parts[:1] == ["import"]:
            return self._route_import(method, parts, query, b)
        if parts[:1] == ["project-ask"] and len(parts) >= 2:
            if len(parts) == 2 and method == "GET":
                return self.project_ask.get(parts[1])
            if len(parts) == 3 and parts[2] == "stop" and method == "POST":
                return self.project_ask.stop(parts[1])
        if parts[:1] == ["outputs"] and len(parts) == 3 and method == "POST" and parts[2] in ("project-ask", "regenerate",
                                                                                              "nle"):
            need(ID_RE.match(parts[1]), "bad item id")
            if parts[2] == "nle":
                return self.outputs.nle_all(parts[1], b.get("format"), media=b.get("media") or "link",
                                            to_app=b.get("to_app"))
            if parts[2] == "regenerate":
                return self.project_ask.regenerate(parts[1], b.get("items"))
            return self.project_ask.start(parts[1], b.get("prompt"), clips=b.get("clips"), context=b.get("context"))
        if parts[:1] == ["outputs"] and len(parts) == 4 and parts[3] in ("strip", "transcribe"):
            need(ID_RE.match(parts[1]), "bad item id")
            return self.strips.route(method, parts[1], unquote(parts[2]), parts[3])
        if parts[:1] == ["outputs"] and len(parts) >= 2:
            need(ID_RE.match(parts[1]), "bad item id")
            if len(parts) == 2 and method == "GET":
                return self.outputs.clips(parts[1])
            clip = unquote(parts[2])
            if len(parts) == 3 and method == "GET":
                return self.outputs.show(parts[1], clip)
            if len(parts) == 4 and method == "POST":
                verb = parts[3]
                if verb == "edit":
                    return self.outputs.edit(parts[1], clip, b.get("ops"), by=b.get("by") or "user", turn=b.get("turn"),
                                             note=b.get("note"))
                if verb == "preview-edl":
                    return self.outputs.preview_edl(parts[1], clip, b.get("ops"))
                if verb == "pickup":
                    return self.outputs.pickup(parts[1], clip, b.get("session_dir"), at_word=b.get("at_word"),
                                               replace=b.get("replace"), sig=b.get("sig"))
                if verb == "ask":
                    return self.outputs.ask(parts[1], clip, b.get("prompt"), context=b.get("context"))
                if verb == "render":
                    return self.outputs.render(parts[1], clip, b.get("quality") or "preview", b.get("targets") or "primary",
                                               with_ops=b.get("with_ops"))
                if verb == "export":
                    wm = b.get("watermark")
                    need(wm in (None, True, False), "watermark must be true, false or absent")
                    return self.outputs.export(parts[1], clip, b.get("targets"), watermark=wm)
                if verb == "export-stop":
                    return self.outputs.export_stop(b.get("job"))
                if verb == "revert":
                    return self.outputs.revert(parts[1], clip, b.get("step"))
                if verb == "nle":
                    return self.outputs.nle(parts[1], clip, b.get("format"), media=b.get("media") or "link",
                                            to_app=b.get("to_app"))
                if verb == "chat":
                    if b.get("turn") is not None:
                        return self.outputs.chat_update(parts[1], clip, b.get("turn"), b.get("set"))
                    return self.outputs.chat_add(parts[1], clip, b.get("add"))
                if verb in ("undo", "redo"):
                    return self.outputs.undo(parts[1], clip, b.get("steps", 1), redo=verb == "redo")
                if verb == "title":
                    return self.outputs.set_title(parts[1], clip, b.get("title"))
        if parts == ["home", "suggestions"] and method == "GET":
            from .homesuggest import suggestions
            return suggestions(self.history, self.intake)
        if parts[:1] == ["goals"]:
            return self.route_goals(method, parts[1:], b)
        if parts[:1] == ["intake"]:
            if parts == ["intake"] and method == "POST":
                prompt = b.get("prompt") or ""
                need(isinstance(prompt, str) and len(prompt) <= 2000, "prompt: max 2000 chars")
                inputs = b.get("inputs") or []
                need(isinstance(inputs, list) and len(inputs) <= 200, "inputs: up to 200 files / folders")
                inputs = [_abs_path(p, "inputs[]") for p in inputs]
                need(prompt.strip() or inputs, "say what to make or add files")
                need(b.get("goal") in (None, True, False), "goal must be a boolean")
                # a goal-style request ("several videos from this card"), or 「Make several videos」 in the composer:
                # a survey + a plan of videos, made as a group (goals.py)
                if b.get("goal") is True or (b.get("goal") is None and not b.get("recipe") and not b.get("sample_name")
                                             and self.goals.detect(prompt, inputs)):
                    g = self.goals.start(prompt.strip(), inputs, b.get("platforms"), b.get("lang"),
                                         "ask" if b.get("mode") == "ask" else "autopilot",
                                         **({"ai": b["ai"]} if b.get("ai") else {}))
                    return dict(id=g["id"], goal=True)
                return self.intake.start(prompt.strip(), inputs, b.get("platforms"), b.get("lang"), b.get("mode"),
                                         b.get("sample_name"), **({"recipe": b["recipe"]} if b.get("recipe") else {}),
                                         **({"ai": b["ai"]} if b.get("ai") else {}))
            if parts == ["intake", "recent"] and method == "GET":
                return self.intake.recent()
            if parts == ["intake", "open"] and method == "GET":
                ar = (query.get("archived") or [None])[0]
                need(ar in (None, "", "0", "1"), "archived: 0|1")
                res = self.intake.open(archived=ar == "1")
                self.goals.mark(res.get("items"), "id")         # a goal's requests sit under its group
                return res
            if parts[1:] in (["archive"], ["restore"], ["delete"]) and len(parts) == 2 and method == "POST":
                ids = b.get("ids")
                need(isinstance(ids, list) and 0 < len(ids) <= 200 and all(isinstance(x, str) and PID_RE.match(x) for x in ids),
                     "ids: 1-200 request ids")
                return getattr(self.intake, parts[1])(ids)
            need(len(parts) >= 2 and PID_RE.match(parts[1]), "bad plan id")
            if len(parts) == 2 and method == "GET":
                return self.intake.get(parts[1])
            if parts[2:] == ["revise"] and method == "POST":
                need(isinstance(b.get("prompt"), str) and 0 < len(b["prompt"].strip()) <= 500, "prompt: 1-500 chars")
                return self.intake.revise(parts[1], b["prompt"].strip(), b.get("lang"))
            if parts[2:] == ["apply"] and method == "POST":
                need(b.get("run") in (None, True, False), "run must be a boolean")
                return self.intake.apply(parts[1], b.get("plan"), run=b.get("run", True) is not False)
            if parts[2:] == ["stop"] and method == "POST":
                return self.intake.stop(parts[1])
            if parts[2:] == ["retry"] and method == "POST":
                return self.intake.retry(parts[1])
            if parts[2:] == ["discard"] and method == "POST":
                return self.intake.discard(parts[1])
            if parts[2:] == ["add"] and method == "POST":
                inputs = b.get("inputs") or []
                need(isinstance(inputs, list) and len(inputs) <= 200, "inputs: up to 200 files / folders")
                need(b.get("text") is None or isinstance(b.get("text"), str), "text: links / words")
                return self.intake.add(parts[1], [_abs_path(p, "inputs[]") for p in inputs], b.get("text"))
            if parts[2:] == ["go-on"] and method == "POST":
                return self.intake.go_on(parts[1])
            if parts[2:] == ["ai"] and method == "POST":
                return self.intake.set_ai(parts[1], b.get("ai"), b.get("by") or "you")
        if parts[:1] == ["ai"] and len(parts) == 2:
            need(ID_RE.match(parts[1]), "bad item id")
            return self.project_ai(parts[1], method, b)
        if parts[:1] == ["autopilot"] and len(parts) >= 2:
            need(ID_RE.match(parts[1]), "bad item id")
            if len(parts) == 2 and method == "GET":
                return self.autopilot.get(parts[1])
            if parts[2:] == ["reopen"] and method == "POST":
                return self.autopilot.reopen(parts[1], b.get("checkpoint"), b.get("item") or "*")
            if parts[2:] == ["mode"] and method == "POST":
                return self.autopilot.mode(parts[1], b.get("on"))
            if parts[2:] == ["change"] and method == "POST":
                return self.autopilot.change(parts[1], b.get("checkpoint"), b.get("item"), b.get("answer"))
            if parts[2:] == ["remake"] and method == "POST":
                return self.autopilot.remake(parts[1], b.get("item"), b.get("do"))
        if parts[:1] == ["brain"] and len(parts) >= 2:
            need(ID_RE.match(parts[1]), "bad item id")
            if len(parts) == 2 and method == "GET":
                return self.brain.get(parts[1])
            if parts[2:] == ["refresh"] and method == "POST":
                return self.brain.refresh(parts[1])
            if parts[2:] == ["template"] and method == "POST":
                return self.brain.template(parts[1], b.get("id"))
            if parts[2:] == ["shot"] and method == "POST":
                return self.brain.shot(parts[1], b.get("id"), b.get("set"), reset=b.get("reset") is True)
            if parts[2:] == ["gen"] and method == "POST":
                return self.brain.gen(parts[1], b.get("id"), b.get("action"), b.get("code"))
            if parts[2:] == ["estimate"] and method == "POST":
                return self.brain.estimate(parts[1], b.get("id"))
            if parts[2:] == ["generate"] and method == "POST":
                return self.brain.generate(parts[1], b.get("id"), b.get("estimate_id"), b.get("confirm_code"),
                                           b.get("max_cny"), b.get("code"))
            if parts[2:] == ["place"] and method == "POST":
                return self.brain.place(parts[1], b.get("id"), undo=b.get("undo") is True)
            if parts[2:] == ["shots"] and method == "GET":
                return self.brain.shots(parts[1], (query.get("clip") or [""])[0])
        if parts == ["sample"] and method == "GET":
            return self.sample.info()
        if parts == ["sample", "remove"] and method == "POST":
            r = self.sample.remove(b.get("dir"))
            if self.bus:
                self.bus.publish("batches")
            return r
        if parts == ["pilot", "retry"] and method == "POST":
            e = self.history.find(b.get("item"))
            need(e["kind"] in ("project", "work"), "only a project's pilot can be retried")
            return self.intake.retry_pilot(e["dir"], b.get("provider"))
        if parts[:1] == ["calendar"]:
            if parts == ["calendar"] and method == "GET":
                st = (query.get("start") or [None])[0]
                # queue=0: the posts only (the desk's publish clock reads them every 30 s; the queue scans projects)
                return self.calendar.list(start=st, queue=(query.get("queue") or ["1"])[0] != "0")
            if parts == ["calendar"] and method == "POST":
                return self.calendar.add(b)
            if parts == ["calendar", "confirm"] and method == "POST":
                return self.calendar.confirm_week(b.get("start"))
            if parts == ["calendar", "many"] and method == "POST":
                return self.calendar.add_many(b.get("posts"))
            if parts == ["calendar", "schedule-clips"] and method == "POST":
                return self.calendar.schedule_clips(b)
            if parts == ["calendar", "remove"] and method == "POST":
                return self.calendar.remove_many(b.get("ids"))
            if parts == ["calendar", "restore"] and method == "POST":
                return self.calendar.restore(b.get("posts"))
            if parts == ["calendar", "fill-week"] and method == "POST":
                return self.calendar.fill_week(b)
            if parts == ["calendar", "plan"] and method == "POST":
                return self.calendar.plan(b)
            if parts == ["calendar", "shorten"] and method == "POST":
                return self.calendar.shorten(b)
            if len(parts) == 2 and method == "POST":
                need(ID_RE.match(parts[1]), "bad post id")
                return self.calendar.update(parts[1], b)
        if parts[:1] == ["weekplan"]:
            w = self.weekplans
            if parts == ["weekplan"] and method == "GET":
                return w.active()
            if parts == ["weekplan"] and method == "POST":
                need(isinstance(b.get("inputs"), list) and len(b["inputs"]) <= 200, "inputs: up to 200 files / folders")
                return w.start(dict(b, inputs=[_abs_path(p, "inputs[]") for p in b["inputs"]]))
            need(len(parts) >= 2 and ID_RE.match(parts[1]), "bad week plan id")
            if len(parts) == 2 and method == "GET":
                return w.get(parts[1])
            if parts[2:] == ["run"] and method == "POST":
                return w.run(parts[1])
            if parts[2:] == ["reword"] and method == "POST":
                return w.reword(parts[1], b.get("text") or "", today=b.get("today"), start=b.get("start"))
            if parts[2:] == ["confirm"] and method == "POST":
                return w.confirm(parts[1])
            if parts[2:] == ["dismiss"] and method == "POST":
                return w.dismiss(parts[1])
        if parts[:1] == ["share"] and len(parts) == 2:
            need(ID_RE.match(parts[1]), "bad item id")
            return self.share.options(parts[1]) if method == "GET" else self.share.start(parts[1], b)
        if parts[:1] == ["share-jobs"] and len(parts) == 2 and method == "GET":
            return self.share.job(parts[1])
        if parts == ["feedback", "import"] and method == "POST":
            return self.share.import_feedback(b)
        if parts[:1] == ["inbox"]:
            if parts == ["inbox"] and method == "GET":
                return self.inbox.list()
            if parts == ["inbox", "answer"] and method == "POST":
                return self.inbox.answer(b.get("keys"), b.get("answer"))
            if parts == ["inbox", "undo"] and method == "POST":
                return self.inbox.undo(b.get("keys"))
            if parts == ["inbox", "open"] and method == "POST":
                return self.inbox.open_file(b.get("key"), b.get("which") or "file")
            if parts == ["inbox", "redraft"] and method == "POST":
                return self.inbox.redraft(b.get("key"), b.get("instruction"))
        return None

    def project_ai(self, item, method, b):
        """GET|POST /api/ai/<item>: the project's AI (aichoice.py)."""
        from . import aichoice
        e = self.history.find(item)
        d = e.get("dir") or ""
        ok = e.get("kind") == "project" and os.path.isfile(os.path.join(d, "project.yaml"))
        if method == "GET":
            return dict(item=item, supported=ok, ai=aichoice.read_project(d) if ok else None)
        need(method == "POST", "GET or POST")
        need(ok, "only a recipe project has an AI of its own")
        r = aichoice.set_project(getattr(self.autopilot, "runner", None), d, aichoice.clean(b.get("ai")), b.get("by") or "you")
        if self.bus:
            self.bus.publish("batches")
        return dict(ok=True, item=item, **r)

    def route_goals(self, method, parts, b):
        """/api/goals[/<id>[/<verb>]] (goals.py)."""
        G = self.goals
        if not parts:
            if method == "GET":
                return G.list()
            if method == "POST":
                prompt = b.get("prompt") or ""
                inputs = b.get("inputs") or []
                need(isinstance(inputs, list) and len(inputs) <= 200, "inputs: up to 200 files / folders")
                need(b.get("mode") in (None, "autopilot", "ask"), "mode: autopilot | ask")
                return G.start(prompt, [_abs_path(p, "inputs[]") for p in inputs], b.get("platforms"), b.get("lang"),
                               b.get("mode") or "autopilot")
        need(len(parts) >= 1 and PID_RE.match(parts[0]), "bad goal id")
        gid = parts[0]
        if parts[1:] == ["ai"] and method == "POST":
            return G.set_ai(gid, b.get("ai"), b.get("video"))
        if len(parts) == 1 and method == "GET":
            return G.view(gid)
        if len(parts) == 2 and method == "POST":
            verb = parts[1]
            if verb == "edit":
                return G.edit(gid, b.get("ops"))
            if verb == "video":
                return G.video(gid, b.get("video"), b.get("action"))
            if verb in ("approve", "stop", "retry", "clear", "dismiss"):
                return getattr(G, verb)(gid)
        return None

    def route_v02(self, method, parts, query, body):
        s = self.studio
        q = lambda k: (query.get(k) or [None])[0]  # noqa: E731
        if parts == ["capabilities"] and method == "GET":
            return s.capabilities()
        if parts[:1] == ["clients"]:
            if len(parts) == 1:
                if method == "GET":
                    return s.list_clients()
                if method == "POST":
                    return s.create_client(validate_client_create(body))
            slug = _client(parts[1])
            if len(parts) == 2:
                if method == "GET":
                    return s.get_client(slug)
                if method == "POST":
                    need(isinstance(body, dict), "body must be an object")
                    return s.update_client(slug, body)
            if parts[2:] == ["crm"] and method == "POST":
                s._read_client(slug)
                return s.set_crm(slug, validate_crm(body))
        if parts[:1] == ["plans"]:
            if len(parts) == 1 and method == "POST":
                return s.start_plan(validate_plan(body))
            need(len(parts) >= 2 and PID_RE.match(parts[1]), "bad plan id")
            if len(parts) == 2 and method == "GET":
                return s.get_plan(parts[1])
            if parts[2:] == ["batch"] and method == "POST":
                return s.plan_to_batch(parts[1], validate_plan_batch(body))
        if parts[:1] == ["metrics"]:
            if len(parts) == 1 and method == "GET":
                b, c = q("batch"), q("client")
                need(b is None or ID_RE.match(b), "bad batch id")
                return s.metrics(batch=b, client=_client(c) if c else None)
            if parts[1:] == ["weekly"]:
                if method == "GET":
                    return s.weekly()
                if method == "POST":
                    return s.set_weekly_manual(validate_weekly(body))
        if parts[:1] == ["history"]:
            h = self.history
            if parts == ["history"] and method == "GET":
                st, kind = q("status"), q("kind")
                need(st is None or re.match(r"^[a-z-]{1,20}$", st), "bad status")
                qq, ty, cl = q("q"), q("type"), q("client")
                need(qq is None or len(qq) <= 200, "q: max 200 chars")
                need(kind in (None, "batch", "project", "work"), "kind: batch|project|work")
                need(ty is None or re.match(r"^[a-z-]{1,20}$", ty), "bad type")
                need(cl is None or len(cl) <= 200, "bad client")
                ar = q("archived")
                need(ar in (None, "", "0", "1", "true", "false"), "archived: 0|1")
                res = h.list(q=qq, status=st, kind=kind, type_=ty, client=cl, archived=ar in ("1", "true"))
                self.goals.mark(res.get("items"), "dir")       # a goal's projects sit under its group
                return res
            if len(parts) >= 3 and parts[1] == "item":
                need(ID_RE.match(parts[2]), "bad item id")
                if len(parts) == 3 and method == "GET":
                    return h.item(parts[2])
                if parts[3:] == ["progress"] and method == "GET":
                    from .pilot import progress_feed
                    n = q("n") or "30"
                    need(n.isdigit(), "n: a number")
                    return progress_feed(h.find(parts[2])["dir"], int(n))
                if parts[3:] == ["pieces"] and method == "GET":
                    return self.outputs.pieces(parts[2])
                if parts[3:] == ["finish"] and method == "POST":
                    # Home's "Finish <project> · N clips left": the project run on to its clips not made yet (a pilot
                    # that stopped after its first clip goes on to the rest); nothing to run while a question of the
                    # project waits for her (started: false - the desk opens the project, the question is there)
                    e = h.find(parts[2])
                    need(e["kind"] == "project", "only a project can be finished")
                    from . import pilot
                    rec = pilot.resume_after_answer(self.inbox.runner, e["dir"], bus=self.bus)
                    if rec and self.bus:
                        self.bus.publish("batches")
                    return dict(ok=True, started=bool(rec))
                if parts[3:] in (["stop"], ["resume"]) and method == "POST":
                    e = h.find(parts[2])
                    need(e["kind"] in ("project", "work"), "only a project's run can be stopped / tried again")
                    if parts[3] == "stop":
                        from . import pilot
                        return pilot.stop(e["dir"], self.bus)
                    return self.intake.resume_pilot(e["dir"])
                if parts[3:] == ["adopt"] and method == "POST":
                    b = body if isinstance(body, dict) else {}
                    rec = b.get("recipe") or "guess"
                    need(isinstance(rec, str) and re.match(r"^[a-z][a-z0-9-]{0,40}$", rec), "bad recipe")
                    title = b.get("title")
                    need(title is None or (isinstance(title, str) and len(title) <= 200), "title: max 200 chars")
                    r = h.adopt(parts[2], recipe=rec, title=title)
                    self.bus.publish("batches")
                    return r
            if parts == ["history", "stamp"] and method == "GET":
                return h.stamp()
            if parts == ["history", "config"]:
                if method == "GET":
                    return h.config()
                if method == "POST":
                    need(isinstance(body, dict), "body must be an object")
                    return h.set_watch(body.get("watch"))
            if parts == ["history", "unhide"] and method == "POST":
                r = h.unhide_all()
                self.bus.publish("batches")
                return r
            if parts[1:] in (["archive"], ["restore"]) and method == "POST":
                need(isinstance(body, dict), "body must be an object")
                raw = body.get("dirs") if "dirs" in body else [body.get("dir")]
                need(isinstance(raw, list) and 0 < len(raw) <= 500, "dir or dirs[] (1-500) required")
                dirs = [_abs_path(d, "dir", must_exist=False) for d in raw]
                r = h.archive(dirs) if parts[1] == "archive" else h.restore(dirs)
                self.bus.publish("batches")
                return r
            if parts[1:] in (["trash-plan"], ["forget"]) and method == "POST":
                need(isinstance(body, dict), "body must be an object")
                raw = body.get("dirs")
                need(isinstance(raw, list) and 0 < len(raw) <= 200, "dirs[] (1-200) required")
                dirs = [_abs_path(d, "dir", must_exist=False) for d in raw]
                if parts[1] == "trash-plan":
                    return h.trash_plan(dirs)
                gone = [d for d in dirs if not os.path.exists(d)]
                need(gone, "nothing to forget: the folders are still there")
                r = h.forget(gone)
                # its posts still waiting to go out go too (posted ones stay: they are her history)
                items = {batch_id(x) for d in gone for x in (d, os.path.join(d, "state"))}
                drop = [p["id"] for p in self.calendar._rows() if p.get("item") in items and p.get("state") != "posted"]
                if drop:
                    self.calendar.remove_many(drop[:200])
                r["posts_removed"] = len(drop)
                self.bus.publish("batches")
                self.bus.publish("calendar")
                return r
            if parts[1:] == ["client"] and method == "POST":
                need(isinstance(body, dict), "body must be an object")
                r = h.set_client(_abs_path(body.get("dir"), "dir", must_exist=False), body.get("client"))
                self.bus.publish("batches")
                return r
            if parts[1:] in (["unhide-one"], ["rename"]) and method == "POST":
                need(isinstance(body, dict), "body must be an object")
                d = _abs_path(body.get("dir"), "dir", must_exist=False)
                r = h.unhide(d) if parts[1] == "unhide-one" else h.rename(d, body.get("name"))
                self.bus.publish("batches")
                return r
            if parts[1:] in (["open"], ["hide"]) and method == "POST":
                need(isinstance(body, dict), "body must be an object")
                d = _abs_path(body.get("dir"), "dir", must_exist=parts[1] == "open", kind="dir")
                if parts[1] == "hide":
                    r = h.hide(d)
                else:
                    need(self.engine.mode == "real", "opening a found batch needs the real engine")
                    r = h.open(d)
                self.bus.publish("batches")
                return r
        if parts[:1] == ["cleanup"]:
            if parts[1:] == ["due"] and method == "GET":
                return s.cleanup_due()
            if parts[1:] == ["done"] and method == "POST":
                need(isinstance(body, dict) and ID_RE.match(body.get("batch") or ""), "batch id required")
                paths = body.get("paths") or []
                need(isinstance(paths, list) and len(paths) <= 100, "paths: list")
                return s.cleanup_done(body["batch"], [_abs_path(p, "path", must_exist=False) for p in paths])
        raise KeyError("not found")

    def route_batch_v02(self, method, bid, rest, body):
        s = self.studio
        if rest == ["client"] and method == "POST":
            need(isinstance(body, dict), "body must be an object")
            return s.set_batch_client(bid, _client(body["client"]) if body.get("client") else None)
        if rest == ["timing"] and method == "POST":
            return s.timing(bid, validate_timing(body))
        if rest == ["deliver"]:
            if method == "POST":
                return s.deliver(bid, validate_deliver(body or {}))
            if method == "GET":
                return dict(delivery=s.delivery(bid))
        if rest == ["deliver", "cleanup"] and method == "POST":
            return s.set_cleanup(bid, validate_cleanup_set(body))
        if len(rest) == 3 and rest[0] == "jobs" and method == "POST":
            need(JOB_RE.match(rest[1]), "bad job id")
            if rest[2] == "edit":
                op, args = validate_edit(body)
                return s.edit(bid, rest[1], op, args)
            if rest[2] == "undo":
                return s.undo(bid, rest[1])
            if rest[2] == "rerun":
                return s.rerun(bid, rest[1])
        return None

    def route_live(self, parts, query):
        """GET /api/live/request/<id> | /api/live/project/<item> ?cursor= -> the job's transcript after the cursor
        (``desk_engine.live``); each call keeps the job watched (``live`` events while its files grow)."""
        from . import live as L
        need(len(parts) == 2 and parts[0] in ("request", "project"), "live/request/<id> | live/project/<item>")
        cursor = (query.get("cursor") or [None])[0]
        need(cursor is None or re.match(r"^[0-9:,]{0,80}$", cursor), "bad cursor")
        if parts[0] == "request":
            need(re.match(r"^[0-9a-f]{12}$", parts[1]), "bad request id")
            src = L.request_sources(self.engine.data_dir, parts[1])
            j = self.intake.jobs.get(parts[1]) or {}
            running = j.get("state") == "running"
        else:
            need(ID_RE.match(parts[1]), "bad item id")
            d = self.history.find(parts[1])["dir"]
            src = L.project_sources(d)
            from .pilot import running as run_of
            running = bool(run_of(d))
        key = f"{parts[0]}:{parts[1]}"
        self.live.watch(key, src)
        return dict(L.read(src, cursor), key=key, running=running)

    def route(self, method, path, query, body):
        e = self.engine
        parts = [p for p in path.split("/") if p][1:]          # drop "api"
        if method == "GET" and parts == ["health"]:
            from .inbox import background
            return dict(ok=True, **e.health(), background=background())
        if method == "GET" and parts == ["recipes"]:
            return e.recipes()
        if method == "GET" and parts == ["roots"]:
            return self.roots()
        if parts[:1] == ["create"]:
            return self.create.route(method, parts[1:], query, body)
        if parts[:1] == ["watermark"]:
            r = self.watermark.route(method, parts, body, query)
            if r is not None:
                return r
        if parts[:1] == ["live"] and method == "GET":
            return self.route_live(parts[1:], query)
        if parts[:1] != ["batches"]:
            r = self.route_v04(method, parts, query, body)
            if r is not None:
                return r
            return self.route_v02(method, parts, query, body)
        if len(parts) == 1:
            if method == "GET":
                return self.studio.list_batches()
            if method == "POST":
                return self.studio.create_batch(validate_create(body))
        if parts[1:] == ["import"] and method == "POST":
            need(isinstance(body, dict), "body must be an object")
            return e.import_batch(_abs_path(body.get("dir"), "dir", kind="dir"))
        bid = parts[1]
        need(ID_RE.match(bid), "bad batch id")
        rest = parts[2:]
        if method == "GET" and not rest:
            return e.status(bid)
        if method == "GET" and rest == ["estimate"]:
            return e.estimate(bid)
        if method == "POST" and rest == ["run"]:
            return e.run(bid, validate_run(body or {}))
        if method == "POST" and rest == ["cancel"]:
            return e.cancel(bid)
        if method == "GET" and rest == ["review"]:
            return e.review_items(bid)
        if method == "POST" and rest == ["review", "apply"]:
            r = e.apply_review(bid, validate_decisions(body))
            self.inbox.resume(r.pop("resume", None) or [])   # a project's publish check answered: its run goes on
            if self.bus:
                self.bus.publish("inbox")
            return r
        if rest == ["package"] and method in ("GET", "POST") and self.workpkg.owns(bid):
            # a work folder / project: clips x platforms -> per-platform package (workpkg.py)
            return self.workpkg.package(bid, body or {}) if method == "POST" else self.workpkg.manifest(bid)
        if method == "POST" and rest == ["package"]:
            return e.package(bid, validate_package(body or {}))
        if method == "GET" and rest == ["package"]:
            return e.manifest(bid)
        if method == "GET" and rest == ["events"]:
            n = int((query.get("n") or ["50"])[0])
            job = (query.get("job") or [None])[0]
            need(1 <= n <= 1000, "n: 1..1000")
            need(job is None or JOB_RE.match(job), "bad job id")
            return e.events(bid, n, job)
        if method == "GET" and len(rest) == 2 and rest[0] == "jobs":
            need(JOB_RE.match(rest[1]), "bad job id")
            return self.studio.job_detail(bid, rest[1])
        r = self.route_batch_v02(method, bid, rest, body)
        if r is not None:
            return r
        raise KeyError("not found")


def make_handler(api):
    class H(BaseHTTPRequestHandler):
        server_version = "vstudio-desk-engine"
        sys_version = ""

        def log_message(self, fmt, *args):  # quiet; never log headers (token)
            pass

        # ------------------------------------------------------------ guards
        def _origin_ok(self):
            o = self.headers.get("Origin")
            return o is None or o in api.origins

        def _host_ok(self):
            if api.socket_path:                  # a Unix socket: no TCP, so no DNS rebinding to guard against
                return True
            return self.headers.get("Host") in (f"127.0.0.1:{api.port}", f"localhost:{api.port}")

        def _auth_ok(self):
            h = self.headers.get("Authorization") or ""
            return h.startswith("Bearer ") and hmac.compare_digest(h[7:].encode(), api.token.encode())

        def _cors(self):
            o = self.headers.get("Origin")
            if o and o in api.origins:
                self.send_header("Access-Control-Allow-Origin", o)
                self.send_header("Vary", "Origin")

        def _send(self, code, obj):
            data = json.dumps(obj, ensure_ascii=False, default=lambda x: sorted(x) if isinstance(x, set) else str(x)
                              ).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        def _guard(self):
            if not self._host_ok():
                self._send(421, dict(error="bad host"))
                return False
            if not self._origin_ok():
                self._send(403, dict(error="origin not allowed"))
                return False
            if not self._auth_ok():
                self._send(401, dict(error="unauthorized"))
                return False
            return True

        # ------------------------------------------------------------ verbs
        def do_OPTIONS(self):
            if not self._host_ok() or not self._origin_ok() or not self.headers.get("Origin"):
                self.send_response(403)
                self.end_headers()
                return
            self.send_response(204)
            self._cors()
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.end_headers()

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def _handle(self, method):
            if not self._guard():
                return
            u = urlparse(self.path)
            if not u.path.startswith("/api/"):
                return self._send(404, dict(error="not found"))
            if method == "GET" and u.path == "/api/stream":
                return self._stream()
            body = None
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    return self._send(413, dict(error="body too large"))
                if n:
                    ctype = self.headers.get("Content-Type") or ""
                    if not ctype.startswith("application/json"):
                        return self._send(415, dict(error="json only"))
                    try:
                        body = json.loads(self.rfile.read(n).decode("utf-8"))
                    except ValueError:
                        return self._send(400, dict(error="invalid json"))
            try:
                res = api.route(method, u.path, parse_qs(u.query), body)
                self._send(200, res)
            except BadRequest as e:
                doc = getattr(e, "doc", None)        # engine refusals keep their code for the UI's own words
                self._send(getattr(e, "status", None) or (422 if doc else 400), dict(error=str(e), **(doc or {})))
            except KeyError as e:
                self._send(404, dict(error=str(e).strip("'\"")))
            except (FileNotFoundError, ValueError) as e:
                self._send(422, dict(error=str(e)))
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._send(500, dict(error=f"{type(e).__name__}: {e}"))

        def _stream(self):
            q = api.bus.subscribe()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self._cors()
                self.end_headers()
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        ev = q.get(timeout=15)
                        data = json.dumps(ev, ensure_ascii=False, default=str)
                        self.wfile.write(f"event: {ev['type']}\ndata: {data}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                api.bus.unsubscribe(q)

    return H


# Windows CPython has no AF_UNIX server class: there the engine binds 127.0.0.1 (serve() below)
if hasattr(socketserver, "UnixStreamServer"):
    class UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        """The HTTP API on a Unix domain socket (one thread per connection, like ThreadingHTTPServer). Not HTTPServer:
        its server_bind() looks up a host name, which a socket path is not."""
        daemon_threads = True
        # a full backlog refuses a Unix-socket connect at once (TCP would retry): the UI opens many requests at start-up
        request_queue_size = 128

        bound_ino = None

        def server_bind(self):
            try:
                os.unlink(self.server_address)            # a socket left behind by an engine that was killed
            except FileNotFoundError:
                pass
            super().server_bind()
            # 0600: only this user (the folder - the per-user temp dir / the app's container - is private already)
            os.chmod(self.server_address, 0o600)
            self.bound_ino = os.lstat(self.server_address).st_ino

        def server_close(self):
            super().server_close()
            try:                                          # ours only: a successor may have bound the same path
                st = os.lstat(self.server_address)
                if stat.S_ISSOCK(st.st_mode) and st.st_ino == self.bound_ino:
                    os.unlink(self.server_address)
            except OSError:
                pass


class TcpHTTPServer(ThreadingHTTPServer):
    """127.0.0.1 (Windows). A full backlog refuses a connect on Windows TCP too (WSAECONNREFUSED, no SYN retry as on
    macOS / Linux), and the default backlog is 5: the editor opens more requests than that at once, All projects
    200+ (main also tries a refused connect again). Windows clamps the number to what it allows."""
    daemon_threads = True
    request_queue_size = 1024


def serve(api, host="127.0.0.1", port=0, socket_path=None):
    """Serve the API in a background thread: on a Unix socket when `socket_path` is given (macOS / Linux), else on
    host:port (Windows)."""
    if socket_path:
        httpd = UnixHTTPServer(socket_path, make_handler(api))
        api.socket_path = socket_path
    else:
        httpd = TcpHTTPServer((host, port), make_handler(api))
        api.port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
