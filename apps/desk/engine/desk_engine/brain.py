"""The editor brain on the project page (the engine's ``python -m vstudio.brain``): which template the project is cut
with and why (she can change it), what each shot gets and why, and the "Could be generated" proposals she approves or
skips. Nothing here spends: an approved proposal waits for the Create spend gate.

  GET  /api/brain/<item>                  {supported, state: ready | computing | failed, doc?, error?}: the cached
                                          brain (``state/brain/brain.json``); none yet -> it is computed in the
                                          background (shot detection decodes the footage once) and ``brain`` events say
                                          when it is ready
  POST /api/brain/<item>/refresh          compute again (new footage, a changed request)
  POST /api/brain/<item>/template {id}    her template (same recipe) -> {ok, doc}
  POST /api/brain/<item>/shot {id, set {transition|speed|reframe|skip|punch_in: value} | reset: true} -> {ok, doc}
  POST /api/brain/<item>/gen {id, action: approve | skip | undo, code?}   her answer on a proposal (approve carries
                                          the proposal's confirm code = this price) -> {ok, doc}

Only recipe projects (``project.yaml``) have a brain; other folders answer ``supported: false``.
"""
import os
import threading

from .common import BadRequest, need, read_json

ID_RE = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,80}$"
SHOT_KEYS = ("transition", "speed", "reframe", "skip", "punch_in")


class Brain:
    def __init__(self, history, runner, bus=None):
        self.history, self.runner, self.bus = history, runner, bus
        self._busy, self._err = set(), {}
        self._lock = threading.Lock()

    def _project(self, item):
        e = self.history.find(item)
        d = e.get("dir") or ""
        return d, e.get("kind") == "project" and os.path.isfile(os.path.join(d, "project.yaml"))

    def _cli(self):
        need(self.runner is not None, "the engine is not available")
        return self.runner.sibling("vstudio.brain")

    @staticmethod
    def _cached(d):
        return read_json(os.path.join(d, "state", "brain", "brain.json"), None)

    def _emit(self, item, state):
        if self.bus:
            self.bus.publish("brain", item=item, state=state)

    def _compute(self, item, d, refresh):
        try:
            args = ["show", "--dir", d, "--json"] + (["--refresh"] if refresh else [])
            self._cli().json(args, timeout=1800)
            self._err.pop(item, None)
            self._emit(item, "ready")
        except Exception as e:  # noqa: BLE001  (shown on the card; she can try again)
            self._err[item] = str(e)[:300]
            self._emit(item, "failed")
        finally:
            with self._lock:
                self._busy.discard(item)

    def _start(self, item, d, refresh=False):
        with self._lock:
            if item in self._busy:
                return False
            self._busy.add(item)
        self._err.pop(item, None)
        threading.Thread(target=self._compute, args=(item, d, refresh), daemon=True).start()
        return True

    def get(self, item):
        d, ok = self._project(item)
        if not ok:
            return dict(item=item, supported=False)
        doc = self._cached(d)
        if item in self._busy:
            return dict(item=item, supported=True, state="computing", doc=doc)
        if doc is not None:
            return dict(item=item, supported=True, state="ready", doc=doc)
        if item in self._err:
            return dict(item=item, supported=True, state="failed", error=self._err[item])
        if self.runner is None:
            return dict(item=item, supported=True, state="failed", error="the engine is not available")
        self._start(item, d)
        return dict(item=item, supported=True, state="computing", doc=None)

    def refresh(self, item):
        d, ok = self._project(item)
        need(ok, "only a recipe project has an editor brain")
        need(self.runner is not None, "the engine is not available")
        return dict(ok=True, started=self._start(item, d, refresh=True))

    def _run(self, args):
        from .caps import CliError
        try:
            return self._cli().json(args, timeout=60)
        except CliError as e:                     # the engine said no (another recipe's template, a stale price)
            raise BadRequest(str(e)) from e

    def _after(self, d, r):
        if isinstance(r, dict) and r.get("ok") is False:
            raise BadRequest(r.get("error") or "the engine refused the change")
        doc = self._cli().json(["show", "--dir", d, "--json"], timeout=600)
        return dict(ok=True, doc=doc)

    def _ready(self, item):
        d, ok = self._project(item)
        need(ok, "only a recipe project has an editor brain")
        if item in self._busy:
            raise BadRequest("the shots are still being read; try again in a moment")
        return d

    def template(self, item, tid):
        need(isinstance(tid, str) and 0 < len(tid) <= 40, "id: a template id")
        d = self._ready(item)
        return self._after(d, self._run(["template", "--dir", d, "--id", tid, "--json"]))

    def shot(self, item, sid, change=None, reset=False):
        import re
        need(isinstance(sid, str) and re.match(ID_RE, sid), "id: a shot id")
        d = self._ready(item)
        if reset:
            return self._after(d, self._run(["shot", "--dir", d, "--id", sid, "--reset", "--json"]))
        need(isinstance(change, dict) and change and set(change) <= set(SHOT_KEYS),
             f"set: an object with {', '.join(SHOT_KEYS)}")
        kv = [f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in change.items()]
        need(all(isinstance(v, (str, bool)) and len(str(v)) <= 30 for v in change.values()), "set: short values")
        return self._after(d, self._run(["shot", "--dir", d, "--id", sid, "--set", *kv, "--json"]))

    def gen(self, item, pid, action, code=None):
        import re
        need(isinstance(pid, str) and re.match(r"^g[0-9a-f]{8}$", pid), "id: a proposal id")
        need(action in ("approve", "skip", "undo"), "action: approve | skip | undo")
        need(action != "approve" or (isinstance(code, str) and re.match(r"^[0-9a-f]{6}$", code)),
             "code: the proposal's confirm code (approve)")
        d = self._ready(item)
        args = ["decide", "--dir", d, "--id", pid, f"--{action}", "--json"] + (["--code", code] if code else [])
        return self._after(d, self._run(args))
