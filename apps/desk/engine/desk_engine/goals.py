"""Goal mode: one request that asks for SEVERAL videos ("make as many videos as you can from my DJI card, each with
its own theme") -> a survey, a plan of videos, and a group that makes them and keeps the goal until every video is
made or dropped.

  surveying  ``vstudio.intake goal`` reads the folder (stories by time + place + light, contact sheets) and the
             routed AI proposes the videos (the rules when no model answers)          progress: the engine's events
  planned    the plan card: she renames / drops / merges / changes a video's kind or length (``edit``:
             ``vstudio.intake.goal.edit_goal``, which rebuilds each video's request), then 「Make these videos」
             (``approve``). On autopilot the plan is approved the moment it is ready.
  running    each video is an ordinary request from Home (``Intake.start(request, its clips, mode autopilot)``):
             planned, made into its project(s) and run whole on autopilot. At most ``PARALLEL`` videos are in flight
             at once (planning or making); the runs themselves also wait for a free run slot (pilot.RunQueue).
  done       every video is made or dropped: the summary card lists what was made (files per platform + post copy
             come from the clips) and what was dropped and why. | failed (the survey failed) | stopped (she stopped it)

A video's own state: waiting -> planning -> making -> made, or ``you`` (its project waits for her answer: the Inbox
has the question), or dropped. When a video fails (its plan or its run) or stalls (no sign of life for ``STALL_S``),
it is tried once more (``attempts``); a second failure drops it with the reason (``reason_code``: the engine's own
failure code, ``stalled``, ``stopped``, ``by-you``). ``clear(id)``: the unfinished ones go - a request that never
became a project is deleted, a project is archived (hidden, files kept; Restore brings it back) - her words: "可以根据
情况删掉没有剪辑完成的".

Store: ``<DESK_DATA_DIR>/goals/<id>.json`` (the record) + ``<id>.plan.json`` (the engine's goal document). A goal
that was surveying when the desk quit is a failure she can try again; a running one goes on after a restart.
"""
import hashlib
import os
import re
import threading
import time

from .common import batch_id, need, read_json, write_json

ID_RE = re.compile(r"^[0-9a-f]{12}$")
VID_RE = re.compile(r"^v\d{1,2}$")
PARALLEL = 3                 # videos in flight at once (planning or making); env DESK_GOAL_PARALLEL
STALL_S = 45 * 60            # no sign of life this long while planning / making: stalled
TICK_S = 4.0
MAX_TRIES = 2                # the first try + one retry
RECENT_S = 14 * 86400        # a finished goal stays in the lists this long (unless she dismissed it)
ACTIVE = ("planning", "making")
SETTLED = ("made", "dropped")
# autopilot stopped because nothing could be drafted / no model drew a step: a failure of the run, tried once more
# (then dropped); every other blocker (consent, a budget, a question she took back, a red QC, a key) is hers
RETRY_BLOCKERS = ("needs-input", "needs-model")


FANOUT_KEEP = 6              # the edits across the group the page keeps (newest last)
FANOUT_PARALLEL = 2          # clips asked / edited at once in one edit across the group
RECUT_AI_PICK = 6            # 「Let AI pick」: this many unused clips of the video's own stories go in for its planner
MORE_MAX = 10


def _wanted(prompt):
    try:
        from vstudio.intake.goal import wanted_range
        return wanted_range(prompt or "")
    except Exception:  # noqa: BLE001  (an engine without goal mode)
        return None


def _agg(states):
    """One video's state in an edit across the group, from its clips' rows."""
    for st in ("asking", "applying", "rendering", "waiting", "proposed", "done", "undone"):
        if st in states:
            return st
    return "failed" if states and all(x == "failed" for x in states) else "nothing"


def _public_fanout(f, g):
    """An edit across the group for the page: per video (its title) its versions' clips, what changed, the state."""
    titles = {v["id"]: (v.get("title"), v.get("title_zh")) for v in g.get("videos") or []}
    vids = {}
    for r in f.get("rows") or []:
        x = vids.setdefault(r["video"], dict(video=r["video"], title=titles.get(r["video"], (None, None))[0],
                                             title_zh=titles.get(r["video"], (None, None))[1], rows=[]))
        x["rows"].append({k: r.get(k) for k in ("item", "clip", "lang", "state", "describe", "summary", "error",
                                               "step", "hold", "provider")})
    for x in vids.values():
        x["state"] = _agg([r["state"] for r in x["rows"]])
    out = {k: f.get(k) for k in ("id", "prompt", "scope", "at", "state", "mode")}
    out["videos"] = list(vids.values())
    out["counts"] = dict(done=sum(1 for x in vids.values() if x["state"] == "done"),
                         nothing=sum(1 for x in vids.values() if x["state"] == "nothing"),
                         failed=sum(1 for x in vids.values() if x["state"] == "failed"),
                         proposed=sum(1 for x in vids.values() if x["state"] == "proposed"),
                         undone=sum(1 for x in vids.values() if x["state"] == "undone"), total=len(vids))
    return out


def _parallel():
    try:
        return max(1, min(8, int(os.environ.get("DESK_GOAL_PARALLEL") or PARALLEL)))
    except ValueError:
        return PARALLEL


def detect(prompt, inputs=()):
    """A goal-style request (several videos from a folder / card): the engine's own test (``vstudio.intake.goal``)."""
    try:
        from vstudio.intake.goal import is_goal
    except Exception:  # noqa: BLE001  (an engine without goal mode: every request stays one request)
        return False
    try:
        return bool(is_goal(prompt or "", list(inputs or [])))
    except Exception:  # noqa: BLE001
        return False


def paths_in(prompt):
    try:
        from vstudio.intake.goal import paths_in as f
        return f(prompt or "")
    except Exception:  # noqa: BLE001
        return []


def _ui(g):
    return {"en": "en", "zh-CN": "zh", "zh": "zh", "fr": "fr"}.get((g or {}).get("lang") or "")


def _sig(progress):
    """What a request's planning is doing right now (no change for ``STALL_S``: stalled)."""
    return repr((progress.get("stage"), progress.get("i"), progress.get("done_s")))


def _lang_of(p):
    """A video's language version from its project's name ("… (English)" / "… (中文)"), else None."""
    n = str((p or {}).get("name") or "")
    if re.search(r"[(（]\s*(English|EN)\s*[)）]", n, re.I):
        return "en"
    if re.search(r"[(（]\s*(中文|Chinese|ZH)\s*[)）]", n, re.I):
        return "zh"
    if re.search(r"[(（]\s*(Français|French|FR)\s*[)）]", n, re.I):
        return "fr"
    return None


def _retire(v):
    """The video's request / projects are left behind for a fresh try: they stay the group's (``past``), so the lists
    never show them as loose rows of their own."""
    past = v.setdefault("past", dict(intakes=[], dirs=[]))
    if v.get("intake") and v["intake"] not in past["intakes"]:
        past["intakes"].append(v["intake"])
    for p in v.get("projects") or []:
        if p.get("dir") and p["dir"] not in past["dirs"]:
            past["dirs"].append(p["dir"])


def _blocker(d):
    """Why autopilot left the project's last run to her (its ``autopilot-blocked`` event), or None."""
    from . import pilot
    rec = read_json(os.path.join(d, pilot.REC), None)
    rec = rec if isinstance(rec, dict) else {}
    lines = pilot._tail(os.path.join(d, pilot.LOG), int(rec.get("offset") or 0))
    ev = next((e for e in reversed(pilot._events(lines)) if e.get("event") == "autopilot-blocked"), None)
    return ev.get("blocker") if ev else None


def _goal_code(line):
    """"default" when the goal line is the rule planner's stock line (in any language): the UI shows it in its own
    language at render time (a goal planned in Chinese kept its Chinese line after she switched the UI to English)."""
    if not line:
        return None
    try:
        from vstudio.intake.goal import GOAL_LINE
    except Exception:  # noqa: BLE001  (an engine without goal mode)
        return None
    return "default" if line in GOAL_LINE.values() else None


def project_state(d):
    """A project folder -> (made | running | you | failed | stopped, detail). Read-only, cheap (no history scan)."""
    from . import pilot
    from .common import live_status
    from .history import summarize_project
    if not d or not os.path.isdir(d):
        return "failed", dict(code="missing")
    fail = pilot.failure(d)
    live = live_status(d)
    if fail and not fail.get("remake"):
        if not (live and live.get("state") in ("running", "waiting") and
                (live.get("heartbeat") or 0) > (fail.get("at") or 0) + 5):
            return "failed", dict(code=fail.get("code") or "unknown", stage=fail.get("stage"), error=fail.get("error"))
    if pilot.running(d) or pilot.queued(d) or (live and live.get("state") == "running"):
        return "running", dict(live=live, queued=pilot.queued(d))
    if live and live.get("state") in ("interrupted", "failed"):
        return "failed", dict(code="stalled" if live["state"] == "interrupted" else "unknown")
    if pilot.stopped(d):
        return "stopped", {}
    s = summarize_project(d)
    st = s.get("status")
    if st in ("done", "delivered", "packaged"):
        return "made", dict(counts=s.get("counts"))
    if live and live.get("state") == "waiting":
        return "you", dict(live=live, blocker=_blocker(d))
    if st == "in-progress":
        c = s.get("counts") or {}
        return ("failed", dict(code="items-failed")) if c.get("failed") and not c.get("done") else \
            ("you", dict(blocker=_blocker(d)))
    return "running", dict(live=live)             # planned, its first run not started yet


class Goals:
    def __init__(self, data_dir, bus, intake, history=None, runner=None, mode="real", survey=None, ticker=True,
                 extend=None, outputs=None):
        """``survey``: fn(goal record, on_event) -> the engine's goal document (tests pass one; the product runs
        ``vstudio.intake goal``); ``extend``: fn(goal record, doc, n, used, about) -> (doc, new ids, planner) for more
        videos (the product runs ``vstudio.intake goal-more``). ``outputs``: the clip editor (an edit across the
        group goes through each clip's own AI). ``ticker``: a background thread moves running goals along."""
        self.dir = os.path.join(data_dir, "goals")
        self.bus, self.intake, self.history, self.runner, self.mode = bus, intake, history, runner, mode
        self.outputs = outputs
        self._survey = survey or self._engine_survey
        self._extend = extend or self._engine_extend
        self._lock = threading.RLock()
        self._procs = {}
        self._stop = threading.Event()
        self._thread = None
        self._ticker = ticker
        self._load()
        self._adopt()
        if ticker and any(g.get("state") == "running" for g in self._all()):
            self._ensure_ticker()

    # ------------------------------------------------------------------ store
    def _path(self, gid, plan=False):
        need(isinstance(gid, str) and ID_RE.match(gid), "bad goal id")
        return os.path.join(self.dir, f"{gid}{'.plan' if plan else ''}.json")

    def _load(self):
        self.goals = {}
        if not os.path.isdir(self.dir):
            return
        for f in os.listdir(self.dir):
            if not f.endswith(".json") or f.endswith(".plan.json") or not ID_RE.match(f[:-5]):
                continue
            g = read_json(os.path.join(self.dir, f), None)
            if not isinstance(g, dict):
                continue
            if g.get("state") == "surveying":     # the desk quit while it read the footage: say so, offer Try again
                g.update(state="failed", error_code="stopped", error="the app was closed while this was being planned")
            if (g.get("more") or {}).get("state") == "planning":     # ... or planned more videos: she asks again
                g["more"].update(state="failed", error_code="stopped")
            for f in g.get("fanouts") or []:                          # an edit across the group it was making
                for r in f.get("rows") or []:
                    if r.get("state") in ("waiting", "asking", "applying", "rendering"):
                        r.update(state="failed", error="the app was closed")
                if f.get("state") == "running":
                    f["state"] = "done"
            self.goals[g["id"]] = g

    def _adopt(self):
        """A goal's requests from before ``past`` was kept (a Try again left the old one behind as a loose "Stopped by
        you" row): a request with a video's own words, sent after the goal began, is that video's."""
        jobs = getattr(self.intake, "jobs", None)
        if not isinstance(jobs, dict):
            return
        for g in list(self.goals.values()):
            by_req = {v.get("request"): v for v in g.get("videos") or [] if v.get("request")}
            changed = False
            for rid, j in list(jobs.items()):
                v = by_req.get((j or {}).get("prompt"))
                if not v or rid == v.get("intake") or (j.get("started") or 0) < (g.get("created") or 0):
                    continue
                past = v.setdefault("past", dict(intakes=[], dirs=[]))
                if rid not in past["intakes"]:
                    past["intakes"].append(rid)
                    changed = True
            if changed:
                self._save(g, quiet=True)

    def _all(self):
        with self._lock:
            return [dict(g) for g in self.goals.values()]

    def _save(self, g, quiet=False):
        g["updated"] = time.time()
        with self._lock:
            self.goals[g["id"]] = g
            os.makedirs(self.dir, exist_ok=True)
            write_json(self._path(g["id"]), {k: v for k, v in g.items() if k != "progress" or g.get("state") == "surveying"})
        if self.bus and not quiet:
            self.bus.publish("goals", id=g["id"], state=g.get("state"))
        return g

    def _get(self, gid):
        need(isinstance(gid, str) and ID_RE.match(gid), "bad goal id")
        with self._lock:
            g = self.goals.get(gid)
        if not g:
            raise KeyError(f"no goal {gid}")
        return g

    def plan_doc(self, gid):
        return read_json(self._path(gid, plan=True), None)

    # ------------------------------------------------------------------ start / survey
    def start(self, prompt, inputs, platforms=None, lang=None, mode="autopilot", ai=None):
        """``ai``: the composer's AI for the group ({provider, model}; aichoice): the survey and every video use it."""
        from .aichoice import clean
        ai = clean(ai)
        from .intake import review_first
        if review_first(prompt):
            mode = "ask"
        need(isinstance(prompt, str) and len(prompt) <= 2000, "prompt: max 2000 chars")
        need(mode in ("autopilot", "ask"), "mode: autopilot | ask")
        named = [p for p in paths_in(prompt) if p not in (inputs or [])]
        inputs = list(dict.fromkeys([*(inputs or []), *named]))
        need(inputs, "drop the folder with the footage, or name it in the request")
        gid = hashlib.sha1(f"{prompt}\0{inputs}\0{time.time()}\0{os.urandom(4).hex()}".encode()).hexdigest()[:12]
        g = dict(id=gid, prompt=prompt.strip(), inputs=inputs, platforms=platforms or None, lang=lang, mode=mode,
                 state="surveying", step="scan", created=time.time(), videos=[], goal=None, survey=None,
                 error=None, error_code=None, progress=None, ai=ai)
        self._save(g)
        if self.bus:
            self.bus.publish("batches")
        threading.Thread(target=self._run_survey, args=(gid,), daemon=True).start()
        return self.view(gid)

    def retry(self, gid):
        g = self._get(gid)
        if g["state"] == "running":
            return self._retry_dropped(gid)
        need(g["state"] in ("failed", "stopped"), "only a failed or stopped goal can be tried again")
        g.update(state="surveying", step="scan", error=None, error_code=None, progress=None)
        self._save(g)
        threading.Thread(target=self._run_survey, args=(gid,), daemon=True).start()
        return self.view(gid)

    def _engine_survey(self, g, on_event):
        if self.runner is None or self.mode != "real":
            raise RuntimeError("goal mode needs the Reelfold engine (vstudio.intake goal)")
        out = self._path(g["id"], plan=True)
        args = ["goal", "--prompt", g["prompt"], "--out", out, "--json"]
        if g.get("inputs"):
            args += ["--inputs", *g["inputs"]]
        if g.get("platforms"):
            args += ["--platforms", *[p.split(":")[0] for p in g["platforms"]]]
        lang = {"en": "en", "zh-CN": "zh", "zh": "zh", "fr": "fr"}.get(g.get("lang") or "")
        if lang:
            args += ["--ui-lang", lang]
        track = self._procs.setdefault(g["id"], [])
        r = self.runner.sibling("vstudio.intake")
        from .aichoice import env as ai_env
        done = r.events([*args, "--json-events"], on_event, timeout=3600, track=track, env_extra=ai_env(g.get("ai")))
        return done.get("plan") or read_json(out, None) or {}

    def _run_survey(self, gid):
        def on_event(ev):
            if ev.get("event") != "stage":
                return
            with self._lock:
                g = self.goals.get(gid)
                if not g or g.get("state") != "surveying":
                    return
                seen = list((g.get("progress") or {}).get("seen") or [])
                if ev.get("stage") and ev["stage"] not in seen:
                    seen.append(ev["stage"])
                g["progress"] = dict({k: ev.get(k) for k in ("stage", "file", "i", "n", "kind", "files", "provider")
                                      if ev.get(k) is not None}, seen=seen, at=time.time())
                g["step"] = ev.get("stage") or g.get("step")
            if self.bus:
                self.bus.publish("goals", id=gid, state="surveying")
        try:
            doc = self._survey(dict(self._get(gid)), on_event)
            need(isinstance(doc, dict) and doc.get("kind") == "vstudio.intake.goal", "the survey returned no plan")
        except Exception as e:  # noqa: BLE001
            g = self._get(gid)
            if g.get("state") != "surveying":
                return                               # she stopped it
            from . import pilot
            txt = str(e)
            g.update(state="failed", error=pilot.scrub(txt, 400), progress=None,
                     error_code="plan-empty" if "no folder" in txt or "plan-empty" in txt else pilot.classify(txt))
            self._save(g)
            return
        g = self._get(gid)
        if g.get("state") != "surveying":
            return
        write_json(self._path(gid, plan=True), doc)
        self._take_plan(g, doc)
        g.update(state="planned", step="planned", progress=None)
        if not g["videos"]:
            g.update(state="failed", error_code="plan-empty", error="no footage to make a video from")
        self._save(g)
        if g["state"] == "planned" and g.get("mode") == "autopilot":
            self.approve(gid)

    def _take_plan(self, g, doc):
        g["goal"], g["goal_code"] = doc.get("goal"), doc.get("goal_code")
        g["planner"] = {k: (doc.get("planner") or {}).get(k) for k in ("provider", "model", "fallback", "reason")}
        g["count"] = doc.get("count") if isinstance(doc.get("count"), dict) else None
        sv = doc.get("survey") or {}
        g["survey"] = dict(totals=sv.get("totals"), notes=sv.get("notes"), unused=sv.get("unused"),
                           stories=[{k: s.get(k) for k in ("id", "place", "date", "start", "end", "time_of_day", "videos",
                                                          "photos", "panoramas", "seconds", "aerial", "thumbs", "sheet", "folder")}
                                    for s in sv.get("stories") or []])
        old = {v["id"]: v for v in g.get("videos") or []}
        g["videos"] = [dict(old.get(v["id"]) or {}, **{k: v.get(k) for k in (
            "id", "title", "title_zh", "kind", "theme", "why", "length_s", "clips", "stills", "stories", "platforms",
            "request", "inputs", "merged_into", "recipe", "lengths", "lengths_own", "cuts", "possible_s",
            "over_footage")}, planned_out=bool(v.get("dropped")), state="planned")
            for v in doc.get("videos") or []]
        if self.history is not None:                # the story thumbnails / sheets are shown on the plan card
            pics = [p for s in g["survey"]["stories"] for p in [*(s.get("thumbs") or []), s.get("sheet")] if p]
            try:
                self.history.allow_media(pics)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ the plan card
    def edit(self, gid, ops):
        g = self._get(gid)
        need(g["state"] == "planned", "the plan can be changed until the videos are being made")
        need(isinstance(ops, list) and 0 < len(ops) <= 50 and all(isinstance(o, dict) for o in ops), "ops: 1-50 edits")
        doc = self.plan_doc(gid)
        need(isinstance(doc, dict), "the plan is not ready yet")
        from vstudio.intake.goal import edit_goal
        try:
            doc = edit_goal(doc, ops)
        except ValueError as e:
            need(False, str(e))
        write_json(self._path(gid, plan=True), doc)
        self._take_plan(g, doc)
        self._save(g)
        return self.view(gid)

    def approve(self, gid):
        g = self._get(gid)
        need(g["state"] == "planned", "this plan is not waiting to be made")
        live = [v for v in g["videos"] if not v.get("planned_out")]
        need(live, "keep at least one video")
        for v in g["videos"]:
            if v.get("planned_out"):
                v["state"] = "skipped"
            else:
                v.update(state="waiting", attempts=0, intake=None, projects=[], reason=None, reason_code=None)
        g.update(state="running", step="running", approved=time.time())
        self._save(g)
        if self.bus:
            self.bus.publish("batches")
        self._ensure_ticker()
        self.tick(gid)
        return self.view(gid)

    # ------------------------------------------------------------------ her controls
    def stop(self, gid):
        """「Stop」: the survey ends, or every video still in flight stops (made ones stay made)."""
        from .caps import kill_tracked
        g = self._get(gid)
        if g["state"] == "surveying":
            kill_tracked(self._procs.get(gid) or [])
            g.update(state="stopped", step="stopped", progress=None)
        elif g["state"] in ("running", "planned"):
            for v in g["videos"]:
                if v.get("state") in ("waiting", "planning", "making", "you"):
                    self._halt(v)
                    self._drop(v, "stopped")
            g.update(state="stopped", step="stopped")
        self._save(g)
        return self.view(gid)

    def video(self, gid, vid, action):
        """One video's row menu: ``drop`` (stop it, out of the goal) | ``retry`` (a dropped one, once more)."""
        need(isinstance(vid, str) and VID_RE.match(vid), "bad video id")
        need(action in ("drop", "retry"), "action: drop | retry")
        g = self._get(gid)
        v = next((x for x in g["videos"] if x["id"] == vid), None)
        need(v is not None, "no such video in this goal")
        if action == "drop":
            need(v.get("state") not in ("made", "dropped", "skipped"), "this video is already settled")
            self._halt(v)
            self._drop(v, "by-you")
        else:
            need(v.get("state") == "dropped", "only a dropped video can be tried again")
            self._retry_video(v)
            if g["state"] in ("done", "stopped"):
                g.update(state="running", step="running", finished=None)
        self._save(g)
        self._ensure_ticker()
        self.tick(gid)
        return self.view(gid)

    def retry_version(self, gid, vid, item):
        """Resume one existing language/cut project, preserving every other version."""
        g = self._get(gid)
        v = next((x for x in g["videos"] if x.get("id") == vid), None)
        need(v is not None and not v.get("cleared"), "no such video in this goal")
        p = next((x for x in v.get("projects") or [] if x.get("item") == item), None)
        need(p is not None, "no such version in this video")
        state, _detail = project_state(p["dir"])
        need(state in ("failed", "stopped", "you"), "this version is already made or running")
        self.intake.retry_pilot(p["dir"])
        if self.bus:
            self.bus.publish("batches")
        return self.view(gid)

    def _retry_video(self, v):
        # Keep the successful language/cut projects. Resume only unfinished versions, rather than re-plan
        # the whole video and leave the finished files behind in a retired request.
        projects = v.get("projects") or []
        if projects and not v.get("cleared") and all(os.path.isdir(p.get("dir") or "") for p in projects):
            for p in projects:
                state, _detail = project_state(p["dir"])
                if state not in ("made", "running"):
                    self.intake.retry_pilot(p["dir"])
            v.update(state="making", attempts=1, seen=time.time(), reason=None, reason_code=None,
                     last_error=None, live=None, queued=False, cleared=None)
            return
        _retire(v)
        v.update(state="waiting", attempts=0, intake=None, projects=[], versions=None, reason=None,
                 reason_code=None, cleared=None)

    def _retry_dropped(self, gid):
        g = self._get(gid)
        for v in g["videos"]:
            if v.get("state") == "dropped" and not v.get("cleared"):
                self._retry_video(v)
        self._save(g)
        return self.view(gid)

    def clear(self, gid):
        """The unfinished videos go: requests that never became projects are deleted, projects are archived."""
        g = self._get(gid)
        need(g["state"] in ("done", "stopped"), "the goal is still going")
        reqs, dirs = [], []
        for v in g["videos"]:
            past = v.get("past") or {}               # what a fresh try left behind goes too, whatever became of it
            reqs += [r for r in past.get("intakes") or [] if r not in reqs]
            dirs += [d for d in past.get("dirs") or [] if d not in dirs]
            v["past"] = dict(intakes=[], dirs=[])
            if v.get("state") != "dropped" or v.get("cleared"):
                continue
            if v.get("projects"):
                dirs += [p["dir"] for p in v["projects"] if p.get("dir")]
            elif v.get("intake"):
                reqs.append(v["intake"])
            v["cleared"] = True
        for rid in reqs:
            try:
                self.intake.delete([rid])
            except Exception:  # noqa: BLE001  (already gone)
                pass
        if dirs and self.history is not None:
            try:
                self.history.archive(dirs)
            except Exception:  # noqa: BLE001
                pass
        self._save(g)
        if self.bus:
            self.bus.publish("batches")
        return dict(self.view(gid), cleared=dict(requests=len(reqs), projects=len(dirs)))

    def forget(self, dirs=(), requests=()):
        """Projects / requests she deleted (purge.py): a goal's video made from them leaves its group's links and,
        when nothing of it is left, is dropped (``deleted``) - no group points at a folder that is gone."""
        rps = {os.path.realpath(d) for d in dirs}
        rids = set(requests)
        for g in self._all():
            hit = False
            for v in g.get("videos") or []:
                projs = v.get("projects") or []
                left = [p for p in projs if not (p.get("dir") and os.path.realpath(p["dir"]) in rps)]
                gone_req = v.get("intake") in rids
                if len(left) == len(projs) and not gone_req:
                    continue
                hit = True
                v["projects"] = left
                if gone_req:
                    v["intake"] = None
                if not left and v.get("state") != "dropped":
                    v.update(state="dropped", reason_code="deleted", cleared=True, finished=time.time())
            if hit:
                self._save(g)
        return dict(ok=True)

    def dismiss(self, gid):
        """The group leaves the lists (its videos stay where they are)."""
        g = self._get(gid)
        need(g["state"] not in ("surveying", "running"), "stop the goal first")
        g["dismissed_at"] = time.time()
        self._save(g)
        return dict(ok=True, id=gid)

    # ------------------------------------------------------------------ moving along
    def _ensure_ticker(self):
        if not self._ticker or (self._thread and self._thread.is_alive()):
            return

        def loop():
            while not self._stop.wait(TICK_S):
                for g in self._all():
                    if g.get("state") == "running":
                        try:
                            self.tick(g["id"])
                        except Exception:  # noqa: BLE001  (read again on the next tick)
                            pass
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()

    def tick(self, gid, now=None):
        """Move one running goal along: start waiting videos while there is room, follow the ones in flight, retry
        or drop the ones that failed, finish the goal when every video is settled."""
        now = now or time.time()
        with self._lock:
            g = self.goals.get(gid)
            if not g or g.get("state") != "running":
                return g
            before = repr(g["videos"])
            for v in g["videos"]:
                if v.get("state") in ACTIVE or v.get("state") == "you":
                    self._follow(g, v, now)
            room = _parallel() - sum(1 for v in g["videos"] if v.get("state") in ACTIVE)
            for v in g["videos"]:
                if room <= 0:
                    break
                if v.get("state") == "waiting":
                    self._begin(g, v, now)
                    room -= 1
            live = [v for v in g["videos"] if v.get("state") != "skipped" and not v.get("proposed")]
            if live and all(v.get("state") in SETTLED for v in live):
                g.update(state="done", step="done", finished=now)
            changed = repr(g["videos"]) != before or g["state"] != "running"
        if changed:
            self._save(g)
            if self.bus:
                self.bus.publish("batches")
        return g

    def _begin(self, g, v, now):
        # no model answered the survey: none will plan the video either - its recipe is fixed for the rules
        fixed = v.get("recipe") if (g.get("planner") or {}).get("fallback") else None
        try:
            r = self.intake.start(v["request"], list(v.get("inputs") or []), v.get("platforms"), g.get("lang"),
                                  "autopilot", **({"recipe": fixed} if fixed else {}), group=g["id"],
                                  **({"ai": v.get("ai") or g.get("ai")} if (v.get("ai") or g.get("ai")) else {}))
        except Exception as e:  # noqa: BLE001
            self._failed(g, v, getattr(e, "code", None) or "intake", now, str(e))
            return
        v.update(state="planning", intake=r["id"], started=now, seen=now, projects=[], sig=_sig({}),
                 attempts=(v.get("attempts") or 0) + 1)

    def _follow(self, g, v, now):
        if v["state"] == "planning":
            j = (self.intake.jobs.get(v.get("intake")) or {}) if v.get("intake") else {}
            if not j:
                return self._failed(g, v, "lost", now)
            if j.get("applied"):
                v["projects"] = [dict(dir=p["dir"], name=p.get("name"), item=batch_id(os.path.join(p["dir"], "state")))
                                 for p in j["applied"] if p.get("dir")]
                v.update(state="making", seen=now)
                return None
            st = j.get("state")
            if st == "error" and j.get("error_code") == "stopped":
                # the app was closed (an update, a restart) while it planned: planned again, not a failure - no try
                # is used up and nothing is dropped as "stopped by you"
                try:
                    self.intake.retry(v["intake"])
                    v["seen"] = now
                    return None
                except Exception as e:  # noqa: BLE001
                    return self._failed(g, v, "app-closed", now, str(e))
            if st == "error":
                return self._failed(g, v, j.get("error_code") or "plan", now, j.get("error"))
            if st == "stopped":
                if (j.get("stopped_by") or "you") != "you":   # stopped by the app (it hung): a failure, tried again
                    return self._failed(g, v, "stalled", now)
                return self._drop(v, "stopped")
            if st == "needs":                         # what only she could add: on a goal, plan with what is there
                try:
                    self.intake.go_on(v["intake"])
                except Exception:  # noqa: BLE001
                    pass
                v["seen"] = now
                return None
            if st == "done" and j.get("plan") and not j.get("applied"):
                try:
                    self.intake.apply(v["intake"], run=True)
                except Exception as e:  # noqa: BLE001
                    return self._failed(g, v, "apply", now, str(e))
                return None
            prog = _sig(j.get("progress") or {})
            if prog != v.get("sig"):
                v.update(sig=prog, seen=now)
            elif now - (v.get("seen") or now) > STALL_S:
                try:
                    self.intake.stop(v["intake"], by="stall")    # the goal stopped it, not her
                except Exception:  # noqa: BLE001
                    pass
                return self._failed(g, v, "stalled", now)
            return None
        # making / you: its project(s)
        states = [(p, *project_state(p["dir"])) for p in v.get("projects") or []]
        if not states:
            return self._failed(g, v, "lost", now)
        v["versions"] = [dict(item=p.get("item"), dir=p.get("dir"), name=p.get("name"), lang=_lang_of(p), state=s,
                              code=d.get("code"), queued=bool(d.get("queued")),
                              progress=(d.get("live") or {}).get("progress") if s == "running" else None)
                         for p, s, d in states]
        bad = next(((p, d) for p, s, d in states if s == "failed"), None)
        if bad:
            return self._failed(g, v, bad[1].get("code") or "unknown", now, error=bad[1].get("error"), project=bad[0])
        stuck = next(((p, d) for p, s, d in states if s == "you" and d.get("blocker") in RETRY_BLOCKERS), None)
        if stuck:                                     # autopilot could not draft a step: a failure, not a question
            return self._failed(g, v, stuck[1]["blocker"], now, project=stuck[0])
        if all(s == "made" for _p, s, _d in states):
            v.update(state="made", finished=now, progress=1.0, live=None)
            if (v.get("recut") or {}).get("state") == "making":
                v["recut"]["state"] = "made"
            return None
        if any(s == "stopped" for _p, s, _d in states) and not any(s == "running" for _p, s, _d in states):
            return self._drop(v, "stopped")
        lives = [d.get("live") for _p, s, d in states if s == "running" and d.get("live")]
        ps = [float(x.get("progress") or 0) for x in lives if isinstance(x.get("progress"), (int, float))]
        made = sum(1 for _p, s, _d in states if s == "made")
        v["progress"] = round(min(0.99, (made + sum(ps)) / len(states)), 3)
        v["live"] = {k: lives[0].get(k) for k in ("stage", "message", "eta", "code", "params") if lives[0].get(k) is not None} \
            if lives else None
        v["state"] = "you" if any(s == "you" for _p, s, _d in states) and not lives else "making"
        sig = repr([(x.get("heartbeat"), x.get("stage")) for x in lives])
        waiting_turn = any(d.get("queued") for _p, s, d in states if s == "running")   # in line for a run slot
        v["queued"] = bool(waiting_turn and not lives)
        if v["state"] == "you" or waiting_turn or sig != v.get("sig"):
            v.update(sig=sig, seen=now)
        elif now - (v.get("seen") or now) > STALL_S:
            from . import pilot
            for p, s, _d in states:
                if s == "running":
                    pilot.stop(p["dir"], self.bus)
            return self._failed(g, v, "stalled", now)
        return None

    def _failed(self, g, v, code, now, error=None, project=None):
        """A failure: tried once more while it has tries left, else dropped with the reason."""
        v["last_error"] = (str(error)[:300] if error else None)
        if code == "disk":  # a retry cannot create free space and may leave another partial render
            return self._drop(v, code)
        if (v.get("attempts") or 0) < MAX_TRIES:
            v["attempts"] = (v.get("attempts") or 0) + 1
            v["retried"] = code
            try:
                if project is not None and v.get("intake"):
                    self.intake.retry_pilot(project["dir"])
                    v.update(state="making", seen=now)
                    return
                if v.get("intake") and code not in ("lost", "stalled"):
                    j = self.intake.jobs.get(v["intake"]) or {}
                    if j.get("state") in ("error", "stopped"):
                        self.intake.retry(v["intake"])
                        v.update(state="planning", seen=now)
                        return
            except Exception:  # noqa: BLE001  (a retry that cannot start: a fresh request instead)
                pass
            _retire(v)
            v.update(state="waiting", intake=None, projects=[], versions=None)
            v["attempts"] -= 1                       # _begin counts the try
            return
        self._drop(v, code)

    def _drop(self, v, code):
        v.update(state="dropped", reason_code=code, finished=time.time(), live=None)
        if (v.get("recut") or {}).get("state") == "making":
            v["recut"]["state"] = "failed"              # its cut before is still there: Undo re-cut brings it back

    def _halt(self, v):
        from . import pilot
        if v.get("state") == "planning" and v.get("intake"):
            try:
                self.intake.stop(v["intake"])
            except Exception:  # noqa: BLE001
                pass
        for p in v.get("projects") or []:
            try:
                pilot.stop(p["dir"], self.bus)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ edit the collection (a made group)
    def _doc(self, gid):
        doc = self.plan_doc(gid)
        need(isinstance(doc, dict) and doc.get("kind") == "vstudio.intake.goal",
             "this group has no survey of its footage to pick from")
        return doc

    def _used_by(self, v):
        """The source clips one video plays: its made cuts' edit lists, else the clips it was given."""
        from vstudio.intake.goal import used_in_project
        if v.get("state") in ("dropped", "skipped") or v.get("planned_out"):
            return set()
        out = set()
        if v.get("state") == "made":
            for p in v.get("projects") or []:
                if p.get("dir"):
                    out |= set(used_in_project(p["dir"]))
        return out or set(v.get("pick") or v.get("inputs") or [])

    def _used(self, g, but=None):
        out = set()
        for v in g.get("videos") or []:
            if v.get("id") != but:
                out |= self._used_by(v)
        return out

    def _engine_extend(self, g, doc, n, used, about):
        """``vstudio.intake goal-more`` on the group's AI (the product); the rules in this process without an engine."""
        if self.runner is None or self.mode != "real":
            from vstudio.intake.goal import extend_goal
            return extend_goal(doc, n, used, about=about, ui_lang=_ui(g), provider="none")
        import json
        import tempfile
        path = self._path(g["id"], plan=True)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(sorted(used), f)
            upath = f.name
        try:
            args = ["goal-more", "--goal", path, "--n", str(n), "--used", upath, "--out", path, "--json-events"]
            if about:
                args += ["--about", about]
            if _ui(g):
                args += ["--ui-lang", _ui(g)]
            from .aichoice import env as ai_env
            done = self.runner.sibling("vstudio.intake").events(args, lambda ev: None, timeout=1800,
                                                                track=self._procs.setdefault(g["id"], []),
                                                                env_extra=ai_env(g.get("ai")))
        finally:
            try:
                os.unlink(upath)
            except OSError:
                pass
        return done.get("plan") or read_json(path, None) or {}, list(done.get("added") or []), done.get("planner") or {}

    def more(self, gid, n=None, about=None, to=None):
        """「再做 3 条」/「补够 12 条」/「再做一条关于 X 的」: new plan cards for the group over the same footage, cut only
        from clips no video plays yet. Planned in the background (``more.state`` planning -> ready | failed); on
        autopilot they are made the moment they are ready, else they wait for 「Make these」 (``more_act``)."""
        g = self._get(gid)
        need(g["state"] in ("done", "stopped", "running"), "more videos can be asked for once the group is being made")
        need((g.get("more") or {}).get("state") not in ("planning", "ready"),
             "the last ask for more videos is still open: make or discard those first")
        need(about is None or (isinstance(about, str) and len(about) <= 200), "about: up to 200 chars")
        if to is not None:
            need(isinstance(to, int) and not isinstance(to, bool) and 1 <= to <= 40, "to: 1-40")
            fill = self._fill(g, self.view(gid).get("count")) or {}
            have = fill.get("have") if fill else sum(1 for v in g["videos"] if v.get("state") not in ("skipped", "dropped"))
            n = to - (have or 0)
            need(n > 0, f"the group already has {have} videos")
        if n is None:
            n = ((self._fill(g, self.view(gid).get("count")) or {}).get("need") or 3)
        need(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= MORE_MAX, f"n: 1-{MORE_MAX}")
        self._doc(gid)
        g["more"] = dict(state="planning", n=n, about=(about or "").strip() or None, at=time.time(), ids=[],
                         error=None, error_code=None)
        self._save(g)
        threading.Thread(target=self._run_more, args=(gid,), daemon=True).start()
        return self.view(gid)

    def _run_more(self, gid):
        g = self._get(gid)
        m = g["more"]
        try:
            doc = self._doc(gid)
            used = self._used(g)
            doc, ids, info = self._extend(dict(g), doc, m["n"], used, m.get("about"))
            need(isinstance(doc, dict) and doc.get("kind") == "vstudio.intake.goal", "the planner returned no plan")
        except Exception as e:  # noqa: BLE001
            from . import pilot
            g = self._get(gid)
            if (g.get("more") or {}).get("state") == "planning":
                g["more"].update(state="failed", error=pilot.scrub(str(e), 300), error_code=pilot.classify(str(e)))
                self._save(g)
            return
        g = self._get(gid)
        if (g.get("more") or {}).get("state") != "planning":
            return                                    # she discarded it meanwhile
        write_json(self._path(gid, plan=True), doc)
        have = {v["id"] for v in g["videos"]}
        ids = [i for i in ids if i not in have]
        self._take_extra(g, doc, ids)
        g["more"].update(state="ready" if ids else "empty", ids=ids, planner=info,
                         left=((doc.get("more") or [{}])[-1]).get("left"))
        self._save(g)
        if ids and g.get("mode") == "autopilot":
            self.more_act(gid, "approve")

    def _take_extra(self, g, doc, ids):
        """The new videos of ``doc`` (``ids``) as the group's plan cards (``proposed``); existing ones refreshed."""
        keys = ("id", "title", "title_zh", "kind", "theme", "why", "length_s", "clips", "stills", "stories", "platforms",
                "request", "inputs", "merged_into", "recipe", "lengths", "lengths_own", "cuts", "possible_s",
                "over_footage", "extra", "about", "pick")
        by = {v["id"]: v for v in doc.get("videos") or []}
        for v in g["videos"]:
            if v.get("proposed") and v["id"] in by:
                d = by[v["id"]]
                v.update({k: d.get(k) for k in keys}, planned_out=bool(d.get("dropped")))
        for i in ids:
            d = by.get(i)
            if d:
                g["videos"].append(dict({k: d.get(k) for k in keys}, state="planned", proposed=True,
                                        planned_out=bool(d.get("dropped"))))
        if self.history is not None:
            try:
                self.history.allow_media([p for p in (self._thumb(x) for v in g["videos"] if v.get("proposed")
                                                      for x in (v.get("inputs") or [])[:3]) if p])
            except Exception:  # noqa: BLE001
                pass

    def edit_more(self, gid, ops):
        """Her edits on the new plan cards (the same ops as the plan card) - only the proposed videos."""
        g = self._get(gid)
        need((g.get("more") or {}).get("state") == "ready", "there are no new videos waiting to be made")
        need(isinstance(ops, list) and 0 < len(ops) <= 50 and all(isinstance(o, dict) for o in ops), "ops: 1-50 edits")
        mine = {v["id"] for v in g["videos"] if v.get("proposed")}
        for o in ops:
            ids = o.get("videos") if o.get("op") == "merge" else [o.get("video")]
            need(isinstance(ids, list) and all(i in mine for i in ids), "only the new videos can be changed here")
        from vstudio.intake.goal import edit_goal
        try:
            doc = edit_goal(self._doc(gid), ops)
        except ValueError as e:
            need(False, str(e))
        write_json(self._path(gid, plan=True), doc)
        self._take_extra(g, doc, [])
        self._save(g)
        return self.view(gid)

    def more_act(self, gid, action):
        """The new plan cards: ``approve`` (「Make these」: they join the group and are made) | ``discard``."""
        need(action in ("approve", "discard"), "action: approve | discard")
        g = self._get(gid)
        need((g.get("more") or {}).get("state") == "ready", "there are no new videos waiting to be made")
        new = [v for v in g["videos"] if v.get("proposed")]
        if action == "discard":
            ids = {v["id"] for v in new}
            g["videos"] = [v for v in g["videos"] if v["id"] not in ids]
            doc = self.plan_doc(gid)
            if isinstance(doc, dict):
                doc["videos"] = [v for v in doc.get("videos") or [] if v.get("id") not in ids]
                write_json(self._path(gid, plan=True), doc)
            g["more"]["state"] = "discarded"
            self._save(g)
            return self.view(gid)
        need(any(not v.get("planned_out") for v in new), "keep at least one video")
        for v in new:
            v.pop("proposed", None)
            if v.get("planned_out"):
                v["state"] = "skipped"
            else:
                v.update(state="waiting", attempts=0, intake=None, projects=[], reason=None, reason_code=None)
        g["more"]["state"] = "made"
        g.update(state="running", step="running", finished=None)
        self._save(g)
        if self.bus:
            self.bus.publish("batches")
        self._ensure_ticker()
        self.tick(gid)
        return self.view(gid)

    # ---- one video's re-cut: more shots / another shot, from the clips no video plays
    @staticmethod
    def _thumb(path):
        """The survey's frame of a clip (cached by the survey), or None."""
        try:
            from vstudio.intake.goal import _frame_cache
            p = _frame_cache(path)
        except Exception:  # noqa: BLE001  (the clip is gone / an engine without goal mode)
            return None
        return p if os.path.exists(p) else None

    def _video_of(self, g, vid):
        need(isinstance(vid, str) and VID_RE.match(vid), "bad video id")
        v = next((x for x in g["videos"] if x["id"] == vid), None)
        need(v is not None, "no such video in this group")
        return v

    def candidates(self, gid, vid):
        """What one video's re-cut can pick from: its shots now (timeline order, their source clip) and the clips no
        video of the group plays (its own stories first), each with the survey's frame."""
        from vstudio.intake.goal import edl_shots
        g = self._get(gid)
        v = self._video_of(g, vid)
        doc = self._doc(gid)
        shots = []
        for p in v.get("projects") or []:
            if p.get("dir"):
                shots = edl_shots(p["dir"])
                if shots:
                    break
        # what its cut plays (the clips it was given but its cut never shows are candidates too)
        mine = {s["src"] for s in shots} or set(v.get("inputs") or [])
        taken = self._used(g, but=vid) | mine
        free = []
        for k, s in enumerate((doc.get("survey") or {}).get("stories") or []):
            clips = s.get("clips") or []
            secs = s.get("clip_secs") or [None] * len(clips)
            for path, dur in zip(clips, secs):
                if path in taken:
                    continue
                free.append(dict(path=path, name=os.path.basename(path), dur=dur, story=s.get("id"),
                                 place=s.get("place"), date=s.get("date"), start=s.get("start"),
                                 same=s.get("id") in (v.get("stories") or []), order=k, thumb=self._thumb(path)))
        free.sort(key=lambda c: (not c["same"], c["order"]))
        for s in shots:
            s["thumb"] = self._thumb(s["src"])
        if self.history is not None:
            try:
                self.history.allow_media([x["thumb"] for x in [*shots, *free] if x.get("thumb")])
            except Exception:  # noqa: BLE001
                pass
        return dict(video=vid, shots=shots[:80], free=free[:80], used_elsewhere=len(taken - mine))

    def recut(self, gid, vid, add=None, drop=None, shots=None, pick=None):
        """Re-cut one made video: ``add`` clips (paths from ``candidates``), ``drop`` clips / ``shots`` (their numbers
        on its timeline: the clip that shot plays leaves), ``pick`` "ai" (no clips named: its own stories' unused
        clips go in and its planner picks the moments). Only this video is made again (its versions, one project per
        language); its cut before stays (``undo_recut`` brings it back)."""
        g = self._get(gid)
        v = self._video_of(g, vid)
        need(v.get("state") == "made", "only a made video can be re-cut")
        need(pick in (None, "ai"), "pick: ai")
        add, drop, shots = list(add or []), list(drop or []), list(shots or [])
        need(all(isinstance(x, str) for x in add + drop) and len(add) <= 40 and len(drop) <= 40, "add / drop: paths")
        need(all(isinstance(x, int) and not isinstance(x, bool) for x in shots) and len(shots) <= 40, "shots: numbers")
        c = self.candidates(gid, vid)
        free = {x["path"] for x in c["free"]}
        need(all(p in free for p in add), "only clips no video of the group plays can be added")
        by_n = {s["i"]: s["src"] for s in c["shots"]}
        need(all(n in by_n for n in shots), "no such shot in this video")
        drop = list(dict.fromkeys([*drop, *[by_n[n] for n in shots]]))
        if pick == "ai" and not add:
            add = [x["path"] for x in c["free"] if x["same"]][:RECUT_AI_PICK] or \
                [x["path"] for x in c["free"]][:RECUT_AI_PICK]
        need(add or drop, "pick a clip to add or a shot to leave out")
        need(add or len(set(v.get("inputs") or []) - set(drop)) > 0, "the video would have no footage left")
        if drop and not add and shots:          # 「换掉第 3 个镜头」 with nothing picked: another clip in its place
            add = [x["path"] for x in c["free"] if x["same"]][:max(1, len(shots))] or \
                [x["path"] for x in c["free"]][:max(1, len(shots))]
        inputs = [p for p in v.get("inputs") or [] if p not in drop]
        inputs += [p for p in add if p not in inputs]
        base = v.get("request_base") or v.get("request") or ""
        words = []
        if add:
            words.append(f"use these {len(add)} added shots ({', '.join(os.path.basename(p) for p in add[:8])}"
                         f"{'...' if len(add) > 8 else ''})")
        if drop:
            words.append(f"leave out {', '.join(os.path.basename(p) for p in drop[:8])}")
        past = dict(intakes=list((v.get("past") or {}).get("intakes") or []),
                    dirs=list((v.get("past") or {}).get("dirs") or []))
        for p in (v.get("prev") or {}).get("projects") or []:     # a re-cut of a re-cut: the oldest cut stays the group's
            if p.get("dir") and p["dir"] not in past["dirs"]:
                past["dirs"].append(p["dir"])
        v["prev"] = {k: v.get(k) for k in ("projects", "versions", "inputs", "request", "finished", "intake")}
        v["prev"]["past"] = past
        v.update(request_base=base, request=f"{base} Re-cut of an earlier version: {'; '.join(words)}.",
                 inputs=inputs, state="waiting", attempts=0, intake=None, projects=[], versions=None, reason=None,
                 reason_code=None, progress=None, live=None, finished=None, past=past,
                 recut=dict(at=time.time(), add=[os.path.basename(p) for p in add],
                            drop=[os.path.basename(p) for p in drop], shots=shots, state="making",
                            ai=pick == "ai"))
        g.update(state="running", step="running", finished=None)
        self._save(g)
        if self.bus:
            self.bus.publish("batches")
        self._ensure_ticker()
        self.tick(gid)
        return self.view(gid)

    def undo_recut(self, gid, vid):
        """Back to the cut before the re-cut: the re-cut's projects are archived (Restore brings them back)."""
        g = self._get(gid)
        v = self._video_of(g, vid)
        prev = v.get("prev")
        need(prev, "this video has no earlier cut")
        if v.get("state") not in SETTLED:
            self._halt(v)
        mine = [p["dir"] for p in v.get("projects") or [] if p.get("dir")]
        if v.get("intake") and not mine:
            try:
                self.intake.delete([v["intake"]])
            except Exception:  # noqa: BLE001
                pass
        if mine and self.history is not None:
            try:
                self.history.archive(mine)
            except Exception:  # noqa: BLE001
                pass
        v.update({k: prev.get(k) for k in ("projects", "versions", "inputs", "request", "finished", "intake")},
                 past=prev.get("past") or dict(intakes=[], dirs=[]), state="made", progress=1.0, live=None,
                 reason=None, reason_code=None, prev=None, recut=dict(v.get("recut") or {}, state="undone"))
        if g["state"] == "running" and all(x.get("state") in SETTLED for x in g["videos"]
                                           if x.get("state") != "skipped" and not x.get("proposed")):
            g.update(state="done", step="done", finished=time.time())
        self._save(g)
        return self.view(gid)

    # ---- one edit across the group: each made video's clips through their own clip AI
    def fanout(self, gid, prompt, scope=None):
        """「全部加水印」/「所有 YouTube 版本加英文旁白」: the same request to every made video (``scope.lang``: only its
        English / Chinese versions), each clip through its own AI (``Outputs.ask``: the clip edit ops, ``voiceover``
        too); on autopilot the changes are applied and the versions rendered again, on Ask-me-first they wait for
        「Apply」 (``fanout_act``). Per video: progress, what changed, Undo."""
        g = self._get(gid)
        need(self.outputs is not None, "the clip editor is not available")
        need(isinstance(prompt, str) and 0 < len(prompt.strip()) <= 500, "prompt: 1-500 chars")
        from .goaledit import scope_of
        scope = scope if isinstance(scope, dict) else scope_of(prompt)
        lang = scope.get("lang")
        need(lang in (None, "en", "zh", "fr"), "scope.lang: en | zh | fr")
        need(not any(f.get("state") == "running" for f in g.get("fanouts") or []),
             "an edit across the group is still being made")
        rows = []
        for v in g["videos"]:
            if v.get("state") != "made" or v.get("proposed"):
                continue
            for p in v.get("projects") or []:
                pl = _lang_of(p)
                if lang and pl and pl != lang:
                    continue
                if p.get("item"):
                    rows.append(dict(video=v["id"], item=p["item"], lang=pl, state="waiting"))
        need(rows, "no made video matches" if lang else "no video of the group is made yet")
        fid = hashlib.sha1(f"{gid}{prompt}{time.time()}".encode()).hexdigest()[:10]
        job = dict(id=fid, prompt=prompt.strip(), scope=scope, at=time.time(), state="running", mode=g.get("mode"),
                   rows=rows)
        g["fanouts"] = [*(g.get("fanouts") or [])[-(FANOUT_KEEP - 1):], job]
        self._save(g)
        threading.Thread(target=self._run_fanout, args=(gid, fid), daemon=True).start()
        return self.view(gid)

    def _fan(self, gid, fid):
        g = self._get(gid)
        f = next((x for x in g.get("fanouts") or [] if x["id"] == fid), None)
        need(f is not None, "no such edit in this group")
        return g, f

    def _run_fanout(self, gid, fid):
        from concurrent.futures import ThreadPoolExecutor
        g, f = self._fan(gid, fid)
        rows = []                                     # one per clip of each version
        for r in list(f["rows"]):
            try:
                cl = [c for c in self.outputs.clips(r["item"]).get("clips") or [] if not c.get("extra") and c.get("files")]
            except Exception as e:  # noqa: BLE001
                self._set(g, r, state="failed", error=str(e)[:200])
                continue
            if not cl:
                self._set(g, r, state="nothing")
                continue
            with self._lock:
                r["clip"] = cl[0]["id"]
                rows.append(r)
                for c in cl[1:]:
                    x = dict(r, clip=c["id"])
                    f["rows"].append(x)
                    rows.append(x)
                self._save(g)
        ask = f.get("mode") == "ask"

        def one(r):
            self._fan_row(gid, f, r, apply=not ask)
        with ThreadPoolExecutor(max_workers=FANOUT_PARALLEL) as ex:
            list(ex.map(one, rows))
        with self._lock:
            f["state"] = "done"
            self._save(g)

    def _set(self, g, r, **kw):
        """One row of an edit across the group changes (the rows change from several threads: under the lock)."""
        with self._lock:
            r.update(kw)
            self._save(g)

    def _fan_row(self, gid, f, r, apply=True):
        g = self._get(gid)
        try:
            self._set(g, r, state="asking")
            res = self.outputs.ask(r["item"], r["clip"], f["prompt"])
            props = [p for p in res.get("proposals") or [] if isinstance(p, dict) and isinstance(p.get("op"), dict)]
            ops = [p["op"] for p in props]
            self._set(g, r, summary=res.get("summary"), provider=res.get("provider"), turn=res.get("turn"), ops=ops,
                      describe=[p.get("describe") for p in props][:8])
            if not props:
                return self._set(g, r, state="nothing")
            hold = next((o["op"] for o in ops if o.get("op") in ("reset", "export_remove")), None)
            if hold or not apply:
                return self._set(g, r, state="proposed", hold=hold)
            self._fan_apply(g, r)
        except Exception as e:  # noqa: BLE001  (one clip failing never stops the others)
            from . import pilot
            self._set(g, r, state="failed", error=pilot.scrub(str(getattr(e, "doc", None) or e), 300))
        return None

    def _fan_apply(self, g, r):
        self._set(g, r, state="applying")
        out = self.outputs.edit(r["item"], r["clip"], r["ops"], by="ai",
                                turn=r.get("turn") if isinstance(r.get("turn"), str) else None)
        self._set(g, r, step=(out.get("step") or {}).get("id"), state="rendering")
        self.outputs.render(r["item"], r["clip"], quality="final", targets="all")
        self._set(g, r, state="done")

    def fanout_act(self, gid, fid, action, video=None):
        """``apply`` (Ask-me-first: its proposed changes, every video or one) | ``undo`` (one video, or all: its
        steps taken back on their own - later edits stay - and its versions rendered again)."""
        need(action in ("apply", "undo"), "action: apply | undo")
        need(video is None or (isinstance(video, str) and VID_RE.match(video)), "video: a video id")
        g, f = self._fan(gid, fid)
        rows = [r for r in f["rows"] if video is None or r["video"] == video]
        if action == "apply":
            rows = [r for r in rows if r.get("state") == "proposed"]
            need(rows, "nothing waits to be applied")
        else:
            rows = [r for r in rows if r.get("state") == "done" and r.get("step")]
            need(rows, "nothing to undo")
        with self._lock:
            for r in rows:
                r["state"] = "waiting"
            f["state"] = "running"
            self._save(g)
        threading.Thread(target=self._run_fan_act, args=(gid, f, rows, action), daemon=True).start()
        return self.view(gid)

    def _run_fan_act(self, gid, f, rows, action):
        g = self._get(gid)
        for r in rows:
            try:
                if action == "apply":
                    self._fan_apply(g, r)
                else:
                    self._fan_undo(g, r)
            except Exception as e:  # noqa: BLE001
                from . import pilot
                self._set(g, r, state="failed", error=pilot.scrub(str(getattr(e, "doc", None) or e), 300))
        with self._lock:
            f["state"] = "done"
            self._save(g)

    def _fan_undo(self, g, r):
        self._set(g, r, state="applying")
        doc = self.outputs.show(r["item"], r["clip"])
        steps = [s.get("id") for s in doc.get("steps") or []]
        if steps and steps[-1] == r["step"]:
            self.outputs.undo(r["item"], r["clip"], 1)
        else:
            self.outputs.revert(r["item"], r["clip"], r["step"])
        self._set(g, r, state="rendering")
        self.outputs.render(r["item"], r["clip"], quality="final", targets="all")
        self._set(g, r, state="undone")

    # ---- her words to the group
    def say(self, gid, text):
        """What she said to the group (the composer on its page) -> what it does: more videos, one video's re-cut
        (the page shows that video's candidates: nothing is re-made until she picks or lets the AI pick), or the
        edit across the group. -> {intent, goal}."""
        from .goaledit import intent
        need(isinstance(text, str) and 0 < len(text.strip()) <= 500, "text: 1-500 chars")
        g = self._get(gid)
        made = [v for v in g["videos"] if v.get("state") not in ("skipped",) and not v.get("proposed")]
        fill = self._fill(g, self.view(gid).get("count")) or {}
        it = intent(text, made, need=fill.get("need") or 0)
        if it["kind"] == "more":
            view = self.more(gid, n=it.get("n") if not it.get("to") else None, about=it.get("about"), to=it.get("to"))
        elif it["kind"] == "recut":
            v = next((x for x in made if x["id"] == it.get("video")), None)
            if v is not None and v.get("state") != "made":
                it["video"] = None
            view = self.view(gid)
        elif it["kind"] == "fanout":
            view = self.fanout(gid, text.strip(), it.get("scope"))
        else:
            view = self.view(gid)
        return dict(intent=it, goal=view)

    # ------------------------------------------------------------------ read
    def set_ai(self, gid, ai, video=None):
        """Switch the group's AI (``video`` None) or one video's: a video still waiting plans with it, one planning
        uses it from its next AI call, one making from its project's next AI step; made / dropped ones stay as they
        were made. -> the goal's view."""
        from .aichoice import clean, set_project
        ai = clean(ai)
        g = self._get(gid)
        need(video is None or (isinstance(video, str) and VID_RE.match(video)), "video: a video id")
        vids = [v for v in g.get("videos") or [] if video is None or v.get("id") == video]
        need(video is None or vids, f"no video {video}")
        if video is None:
            g["ai"] = ai
        for v in vids:
            if video is None:
                v.pop("ai", None)                    # the group's AI again
            else:
                v["ai"] = ai
            if v.get("state") in SETTLED or v.get("state") == "skipped":
                continue
            eff = v.get("ai") or g.get("ai")         # a video's own AI, else the group's
            if v.get("state") == "planning" and v.get("intake"):
                try:
                    self.intake.set_ai(v["intake"], eff, by="group")
                except Exception:  # noqa: BLE001  (the request is gone: its retry plans with the new AI)
                    pass
            for p in v.get("projects") or []:
                if p.get("dir") and os.path.isfile(os.path.join(p["dir"], "project.yaml")):
                    set_project(self.intake.runner, p["dir"], eff, by="group")
        self._save(g)
        return self.view(gid)

    def view(self, gid):
        g = self._get(gid)
        vids = [v for v in g.get("videos") or [] if v.get("state") != "skipped" and not v.get("proposed")]
        counts = dict(total=len(vids), made=sum(1 for v in vids if v.get("state") == "made"),
                      dropped=sum(1 for v in vids if v.get("state") == "dropped"),
                      making=sum(1 for v in vids if v.get("state") in ACTIVE),
                      you=sum(1 for v in vids if v.get("state") == "you"),
                      waiting=sum(1 for v in vids if v.get("state") == "waiting"))
        if g.get("state") == "planned":
            counts["total"] = sum(1 for v in g.get("videos") or [] if not v.get("planned_out"))
        out = {k: g.get(k) for k in ("id", "prompt", "inputs", "platforms", "lang", "mode", "state", "step", "goal",
                                     "survey", "planner", "error", "error_code", "progress", "created", "updated",
                                     "approved", "finished", "dismissed_at", "count", "ai")}
        out["videos"] = [{**{k: v.get(k) for k in ("id", "title", "title_zh", "kind", "theme", "why", "length_s", "clips", "stills",
                                                "lengths", "lengths_own", "cuts", "possible_s", "over_footage",
                                                "stories", "platforms", "request", "state", "intake", "projects",
                                                "attempts", "retried", "reason_code", "progress", "live", "queued", "started",
                                                "finished", "planned_out", "merged_into", "cleared", "versions", "last_error",
                                                "extra", "about", "proposed", "recut")},
                          "ai": v.get("ai") or g.get("ai"), "own_ai": bool(v.get("ai")),
                          "can_undo_recut": bool(v.get("prev")) and v.get("state") in SETTLED}
                         for v in g.get("videos") or []]
        # Settled goals stop ticking, but their projects can finish or be retried outside the goal.
        # Refresh the public view without rewriting her stored goal or reviving deliberate drops.
        for row in out["videos"]:
            if (row.get("state") != "dropped" or not row.get("projects") or row.get("cleared")
                    or row.get("planned_out") or row.get("reason_code") in ("by-you", "stopped", "deleted")):
                continue
            states = [(p, *project_state(p.get("dir") or "")) for p in row["projects"]]
            row["versions"] = [dict(item=p.get("item"), dir=p.get("dir"), name=p.get("name"), lang=_lang_of(p),
                                    state=s, code=d.get("code"), queued=bool(d.get("queued")),
                                    progress=(d.get("live") or {}).get("progress")) for p, s, d in states]
            if all(s == "made" for _p, s, _d in states):
                row.update(state="made", reason_code=None, last_error=None, progress=1.0, live=None)
                counts["made"] += 1
                counts["dropped"] -= 1
            else:
                if any(s == "running" for _p, s, _d in states):
                    row.update(state="making", queued=all(d.get("queued") for _p, s, d in states if s == "running"),
                               progress=sum(s == "made" for _p, s, _d in states) / len(states))
                    counts["making"] += 1
                    counts["dropped"] -= 1
                bad = next((d for _p, s, d in states if s == "failed"), None)
                if bad:
                    row["reason_code"] = bad.get("code") or row.get("reason_code")
                    row["last_error"] = bad.get("error")
        out["counts"] = counts
        out["goal_code"] = g.get("goal_code") or _goal_code(g.get("goal"))
        if not out.get("count"):                    # a goal planned before the count was kept: her words still say it
            rng = _wanted(g.get("prompt"))
            if rng and (rng.get("want") or rng.get("min") or rng.get("max")):
                out["count"] = dict(asked=rng.get("want"), min=rng.get("min"), max=rng.get("max"),
                                    planned=counts["total"])
        out["fill"] = self._fill({**g, "videos": out["videos"]}, out.get("count"))
        out["more"] = g.get("more")
        out["fanouts"] = [_public_fanout(f, g) for f in (g.get("fanouts") or [])[-FANOUT_KEEP:]]
        return out

    @staticmethod
    def _fill(g, count):
        """How far the group is from what she asked for: {target, have, need} (have: the videos made or still being
        made; a dropped one does not count) - 「补够」 makes ``need`` more. None when she named no number."""
        c = count or {}
        target = c.get("asked") or c.get("min")
        if not target:
            return None
        have = sum(1 for v in g.get("videos") or [] if v.get("state") not in ("skipped", "dropped")
                   and not v.get("planned_out"))
        return dict(target=int(target), min=c.get("min"), have=have, need=max(0, int(target) - have))

    def list(self, now=None):
        """Goals for the lists: every one not dismissed, the finished ones for ``RECENT_S``; newest first."""
        now = now or time.time()
        out = []
        for g in self._all():
            if g.get("dismissed_at"):
                continue
            if g.get("state") in ("done", "stopped", "failed") and now - (g.get("updated") or 0) > RECENT_S:
                continue
            out.append(self.view(g["id"]))
        out.sort(key=lambda x: -(x.get("created") or 0))
        return dict(goals=out)

    def owned(self):
        """{request id: (goal, video)}, {project real path: (goal, video)}: what belongs to a goal (the lists show
        them under their group, never twice)."""
        reqs, dirs = {}, {}
        for g in self._all():
            if g.get("dismissed_at"):
                continue
            for v in g.get("videos") or []:
                past = v.get("past") or {}
                for rid in [*(past.get("intakes") or []), *([v["intake"]] if v.get("intake") else [])]:
                    reqs[rid] = (g["id"], v["id"])
                prev = [p.get("dir") for p in (v.get("prev") or {}).get("projects") or []]
                for d in [*(past.get("dirs") or []), *[p.get("dir") for p in v.get("projects") or []], *prev]:
                    if d:
                        dirs[os.path.realpath(d)] = (g["id"], v["id"])
        return reqs, dirs

    def _video(self, gid, vid):
        g = self.goals.get(gid) or {}
        return next((v for v in g.get("videos") or [] if v.get("id") == vid), None) or {}

    def mark(self, rows, key):
        """Put ``goal`` / ``goal_video`` on rows of the lists (``key``: "id" for requests, "dir" for projects)."""
        reqs, dirs = self.owned()
        for r in rows or []:
            hit = reqs.get(r.get("id")) if key == "id" else dirs.get(os.path.realpath(r.get("dir") or "")) if r.get("dir") else None
            if hit:
                r["goal"], r["goal_video"] = hit
                v = self._video(*hit)            # the row's title is the video's, never the request's raw words
                r["goal_title"], r["goal_title_zh"] = v.get("title"), v.get("title_zh")
        return rows

    def filter_inbox(self, items, hist=None):
        """The group is the one place a goal's videos are followed: a question of one of its projects reaches the
        Inbox only when the goal itself says the video waits for her (``you``) - never an autopilot step it answers
        by itself, never a project it already left behind for a fresh try."""
        _reqs, dirs = self.owned()
        if not dirs:
            return items
        by_id = {e.get("id"): os.path.realpath(e.get("dir") or "") for e in hist or [] if e.get("dir")}
        out = []
        for x in items or []:
            d = (x.get("engine") or {}).get("dir") or by_id.get((x.get("project") or {}).get("id"))
            hit = dirs.get(os.path.realpath(d)) if d else None
            if hit:
                v = self._video(*hit)
                hers = {os.path.realpath(x.get("dir") or "") for x in v.get("versions") or []
                        if x.get("state") in ("you", "failed")}
                if v.get("state") != "you" or os.path.realpath(d) not in hers:
                    continue
            out.append(x)
        return out

    def inbox_items(self):
        """For the Inbox: a plan of videos that waits for her 「Make these videos」 and a goal whose survey failed."""
        out = []
        for g in self._all():
            if g.get("dismissed_at") or g.get("state") not in ("planned", "failed"):
                continue
            kind = "plan" if g["state"] == "planned" else "failed"
            name = (g.get("goal") or g.get("prompt") or "")[:60]
            n = sum(1 for v in g.get("videos") or [] if not v.get("planned_out"))
            out.append(dict(key=f"goal-{g['id']}-{g['state']}", kind=kind, group="choose" if kind == "plan" else "other",
                            project=dict(id=None, name=name, kind="plan", thumb=None, type="other"),
                            code="goal.inbox" if kind == "plan" else "inbox.planFailed",
                            params=dict(name=name, n=n), text=None, minutes=1, need=None,
                            error_code=g.get("error_code") if kind == "failed" else None, source="goal",
                            href=f"#/studio?goal={g['id']}", at=g.get("updated") or time.time()))
        return out

    def without_owned(self, items):
        """The intake's Inbox items minus the ones about a goal's requests (key ``plan-<id>-<state>``)."""
        reqs, _dirs = self.owned()

        def rid(x):
            parts = str(x.get("key") or "").split("-")
            return parts[1] if len(parts) > 2 and parts[0] == "plan" else None
        return [x for x in items or [] if rid(x) not in reqs]

    def detect(self, prompt, inputs=()):
        return detect(prompt, inputs)

    def roots(self):
        """Folders the UI may show files from: her footage and the survey's frames / contact sheets."""
        out = []
        for g in self._all():
            for p in g.get("inputs") or []:
                out.append(p if os.path.isdir(p) else os.path.dirname(p))
            for s in (g.get("survey") or {}).get("stories") or []:
                out += [os.path.dirname(p) for p in [*(s.get("thumbs") or []), s.get("sheet")] if p]
        return sorted(set(out))
