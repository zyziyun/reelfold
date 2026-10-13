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


def _sig(progress):
    """What a request's planning is doing right now (no change for ``STALL_S``: stalled)."""
    return repr((progress.get("stage"), progress.get("i"), progress.get("done_s")))


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
            return "failed", dict(code=fail.get("code") or "unknown", stage=fail.get("stage"))
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
    def __init__(self, data_dir, bus, intake, history=None, runner=None, mode="real", survey=None, ticker=True):
        """``survey``: fn(goal record, on_event) -> the engine's goal document (tests pass one; the product runs
        ``vstudio.intake goal``). ``ticker``: a background thread moves running goals along."""
        self.dir = os.path.join(data_dir, "goals")
        self.bus, self.intake, self.history, self.runner, self.mode = bus, intake, history, runner, mode
        self._survey = survey or self._engine_survey
        self._lock = threading.RLock()
        self._procs = {}
        self._stop = threading.Event()
        self._thread = None
        self._ticker = ticker
        self._load()
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
            self.goals[g["id"]] = g

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
    def start(self, prompt, inputs, platforms=None, lang=None, mode="autopilot"):
        need(isinstance(prompt, str) and len(prompt) <= 2000, "prompt: max 2000 chars")
        need(mode in ("autopilot", "ask"), "mode: autopilot | ask")
        named = [p for p in paths_in(prompt) if p not in (inputs or [])]
        inputs = list(dict.fromkeys([*(inputs or []), *named]))
        need(inputs, "drop the folder with the footage, or name it in the request")
        gid = hashlib.sha1(f"{prompt}\0{inputs}\0{time.time()}\0{os.urandom(4).hex()}".encode()).hexdigest()[:12]
        g = dict(id=gid, prompt=prompt.strip(), inputs=inputs, platforms=platforms or None, lang=lang, mode=mode,
                 state="surveying", step="scan", created=time.time(), videos=[], goal=None, survey=None,
                 error=None, error_code=None, progress=None)
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
        done = r.events([*args, "--json-events"], on_event, timeout=3600, track=track)
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
        sv = doc.get("survey") or {}
        g["survey"] = dict(totals=sv.get("totals"), notes=sv.get("notes"), unused=sv.get("unused"),
                           stories=[{k: s.get(k) for k in ("id", "place", "date", "start", "end", "time_of_day", "videos",
                                                          "photos", "panoramas", "seconds", "aerial", "thumbs", "sheet", "folder")}
                                    for s in sv.get("stories") or []])
        old = {v["id"]: v for v in g.get("videos") or []}
        g["videos"] = [dict(old.get(v["id"]) or {}, **{k: v.get(k) for k in (
            "id", "title", "title_zh", "kind", "theme", "why", "length_s", "clips", "stills", "stories", "platforms",
            "request", "inputs", "merged_into", "recipe")}, planned_out=bool(v.get("dropped")), state="planned")
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
            v.update(state="waiting", attempts=0, intake=None, projects=[], reason=None, reason_code=None,
                     cleared=None)
            if g["state"] in ("done", "stopped"):
                g.update(state="running", step="running", finished=None)
        self._save(g)
        self._ensure_ticker()
        self.tick(gid)
        return self.view(gid)

    def _retry_dropped(self, gid):
        g = self._get(gid)
        for v in g["videos"]:
            if v.get("state") == "dropped" and not v.get("cleared"):
                v.update(state="waiting", attempts=0, intake=None, projects=[], reason=None, reason_code=None)
        self._save(g)
        return self.view(gid)

    def clear(self, gid):
        """The unfinished videos go: requests that never became projects are deleted, projects are archived."""
        g = self._get(gid)
        need(g["state"] in ("done", "stopped"), "the goal is still going")
        reqs, dirs = [], []
        for v in g["videos"]:
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
            live = [v for v in g["videos"] if v.get("state") != "skipped"]
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
                                  "autopilot", **({"recipe": fixed} if fixed else {}))
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
            if st == "error":
                return self._failed(g, v, j.get("error_code") or "plan", now, j.get("error"))
            if st == "stopped":
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
                    self.intake.stop(v["intake"])
                except Exception:  # noqa: BLE001
                    pass
                return self._failed(g, v, "stalled", now)
            return None
        # making / you: its project(s)
        states = [(p, *project_state(p["dir"])) for p in v.get("projects") or []]
        if not states:
            return self._failed(g, v, "lost", now)
        bad = next(((p, d) for p, s, d in states if s == "failed"), None)
        if bad:
            return self._failed(g, v, bad[1].get("code") or "unknown", now, project=bad[0])
        stuck = next(((p, d) for p, s, d in states if s == "you" and d.get("blocker") in RETRY_BLOCKERS), None)
        if stuck:                                     # autopilot could not draft a step: a failure, not a question
            return self._failed(g, v, stuck[1]["blocker"], now, project=stuck[0])
        if all(s == "made" for _p, s, _d in states):
            v.update(state="made", finished=now, progress=1.0, live=None)
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
            v.update(state="waiting", intake=None, projects=[])
            v["attempts"] -= 1                       # _begin counts the try
            return
        self._drop(v, code)

    def _drop(self, v, code):
        v.update(state="dropped", reason_code=code, finished=time.time(), live=None)

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

    # ------------------------------------------------------------------ read
    def view(self, gid):
        g = self._get(gid)
        vids = [v for v in g.get("videos") or [] if v.get("state") != "skipped"]
        counts = dict(total=len(vids), made=sum(1 for v in vids if v.get("state") == "made"),
                      dropped=sum(1 for v in vids if v.get("state") == "dropped"),
                      making=sum(1 for v in vids if v.get("state") in ACTIVE),
                      you=sum(1 for v in vids if v.get("state") == "you"),
                      waiting=sum(1 for v in vids if v.get("state") == "waiting"))
        if g.get("state") == "planned":
            counts["total"] = sum(1 for v in g.get("videos") or [] if not v.get("planned_out"))
        out = {k: g.get(k) for k in ("id", "prompt", "inputs", "platforms", "lang", "mode", "state", "step", "goal",
                                     "survey", "planner", "error", "error_code", "progress", "created", "updated",
                                     "approved", "finished", "dismissed_at")}
        out["videos"] = [{k: v.get(k) for k in ("id", "title", "title_zh", "kind", "theme", "why", "length_s", "clips", "stills",
                                                "stories", "platforms", "request", "state", "intake", "projects",
                                                "attempts", "retried", "reason_code", "progress", "live", "queued", "started",
                                                "finished", "planned_out", "merged_into", "cleared")}
                         for v in g.get("videos") or []]
        out["counts"] = counts
        out["goal_code"] = g.get("goal_code") or _goal_code(g.get("goal"))
        return out

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
                if v.get("intake"):
                    reqs[v["intake"]] = (g["id"], v["id"])
                for p in v.get("projects") or []:
                    if p.get("dir"):
                        dirs[os.path.realpath(p["dir"])] = (g["id"], v["id"])
        return reqs, dirs

    def mark(self, rows, key):
        """Put ``goal`` / ``goal_video`` on rows of the lists (``key``: "id" for requests, "dir" for projects)."""
        reqs, dirs = self.owned()
        for r in rows or []:
            hit = reqs.get(r.get("id")) if key == "id" else dirs.get(os.path.realpath(r.get("dir") or "")) if r.get("dir") else None
            if hit:
                r["goal"], r["goal_video"] = hit
        return rows

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
