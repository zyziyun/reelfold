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
  POST /api/brain/<item>/estimate {id}   the Create spend gate's sheet for one proposal: price, the most it can
                                          cost, the month left, every refusal now (``codes``) - nothing is sent
  POST /api/brain/<item>/generate {id, estimate_id, confirm_code, max_cny, code}   her click in the gate: the one
                                          paid generation runs in the background (``brain`` events: generating ->
                                          placed | generated | failed), the take goes into the edit and the project
                                          re-renders -> {ok, started}
  POST /api/brain/<item>/place {id, undo?}   Undo (out of the edit again; the paid take is kept) / put it back; the
                                          project re-renders -> {ok, doc, resumed}
  GET  /api/brain/<item>/shots?clip=     the clip's per-shot edit list with the plan's why + alternatives per shot

Only recipe projects (``project.yaml``) have a brain; other folders answer ``supported: false``. Nothing here spends
except ``generate``, which only her click in the gate calls (the autopilot never does).
"""
import os
import threading
import time

from .common import BadRequest, need, read_json

ID_RE = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,80}$"
SHOT_KEYS = ("transition", "speed", "reframe", "skip", "punch_in")


GEN_RE = r"^g[0-9a-f]{8}$"


class Brain:
    def __init__(self, history, runner, bus=None, outputs=None, spawn=None):
        self.history, self.runner, self.bus, self.outputs = history, runner, bus, outputs
        self._busy, self._err = set(), {}
        self._gen = {}                  # (item, proposal id) -> {state, error?} while a generation runs
        self._lock = threading.Lock()
        self._spawn = spawn             # tests: stands in for pilot.spawn (the project's re-render)

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

    def _allow(self, doc):
        """The shot stills (state/brain/thumbs/) and generated takes (state/brain/gen/) the cards show become
        viewable through the media protocol (it serves only folders the UI was handed)."""
        if not isinstance(doc, dict) or not hasattr(self.history, "allow_media"):
            return doc
        paths = [r.get("thumb") for r in ((doc.get("plan") or {}).get("shots") or [])]
        for p in doc.get("proposals") or []:
            paths += [(p.get("source") or {}).get("thumb"), p.get("file")]
        for s in doc.get("shots") or []:
            paths += [(s.get("brain") or {}).get("thumb")]
        self.history.allow_media([x for x in paths if isinstance(x, str) and x])
        return doc

    def _running_gens(self, item):
        return {pid: dict(v) for (it, pid), v in self._gen.items() if it == item}

    def get(self, item):
        d, ok = self._project(item)
        if not ok:
            return dict(item=item, supported=False)
        r = self._get(item, d)
        if r.get("supported"):
            r["generating"] = self._running_gens(item)
            self._allow(r.get("doc"))
        return r

    def _get(self, item, d):
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
        return dict(ok=True, doc=self._allow(doc))

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
            return self._restyled(d, self._run(["shot", "--dir", d, "--id", sid, "--reset", "--json"]))
        need(isinstance(change, dict) and change and set(change) <= set(SHOT_KEYS),
             f"set: an object with {', '.join(SHOT_KEYS)}")
        kv = [f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in change.items()]
        need(all(isinstance(v, (str, bool)) and len(str(v)) <= 30 for v in change.values()), "set: short values")
        return self._restyled(d, self._run(["shot", "--dir", d, "--id", sid, "--set", *kv, "--json"]))

    def _restyled(self, d, r):
        """Her shot change reached the drafted edit (``edit``: the files it changed): the project re-renders."""
        out = self._after(d, r)
        if isinstance(r, dict) and any(x.get("file") for x in r.get("edit") or []):
            out["resumed"] = self._rerender(d)
        return out

    # ------------------------------------------------------------ generation (the Create spend gate)
    def _refused(self, e):
        """An engine refusal with a Create code (create.provider-not-ready, create.over-cap ...) -> the same error
        shape the Create page reads (``code`` + ``params``)."""
        from .create import Refused
        doc = getattr(e, "doc", None) or {}
        if isinstance(doc, dict) and str(doc.get("code") or "").startswith("create."):
            return Refused(doc["code"], doc.get("params") or {}, 409)
        return BadRequest(str(e))

    def estimate(self, item, pid):
        import re
        from .caps import CliError
        need(isinstance(pid, str) and re.match(GEN_RE, pid), "id: a proposal id")
        d = self._ready(item)
        try:
            return self._cli().json(["estimate", "--dir", d, "--id", pid, "--json"], timeout=180)
        except CliError as e:
            raise self._refused(e) from e

    def generate(self, item, pid, estimate_id, confirm_code, max_cny, code=None):
        """Her click in the gate: the paid generation in the background; the gate is checked first (a refusal comes
        back at once, nothing sent)."""
        import re
        need(isinstance(pid, str) and re.match(GEN_RE, pid), "id: a proposal id")
        need(isinstance(estimate_id, str) and re.match(r"^est-[0-9a-f]{10}$", estimate_id), "estimate_id")
        need(isinstance(confirm_code, str) and re.match(r"^[0-9a-f]{8}$", confirm_code), "confirm_code: 8 hex")
        need(isinstance(max_cny, (int, float)) and not isinstance(max_cny, bool) and 0 <= max_cny <= 100000,
             "max_cny: the most she agreed to")
        need(code is None or (isinstance(code, str) and re.match(r"^[0-9a-f]{6}$", code)), "code: the proposal's")
        d = self._ready(item)
        from .caps import CliError
        args = ["generate", "--dir", d, "--id", pid, "--estimate", estimate_id, "--confirm", confirm_code,
                "--max-cny", str(float(max_cny)), "--json"] + (["--code", code] if code else [])
        with self._lock:
            if (self._gen.get((item, pid)) or {}).get("state") == "generating":
                return dict(ok=True, started=False, state="generating")
        try:                                   # the gate first: a refusal comes back now, nothing is sent
            self._cli().json(args + ["--check"], timeout=120)
        except CliError as e:
            raise self._refused(e) from e
        with self._lock:
            if (self._gen.get((item, pid)) or {}).get("state") == "generating":
                return dict(ok=True, started=False, state="generating")
            self._gen[(item, pid)] = dict(state="generating", at=time.time())
        threading.Thread(target=self._generate, args=(item, d, pid, args), daemon=True).start()
        self._emit_gen(item, pid, "generating")
        return dict(ok=True, started=True, state="generating")

    def _generate(self, item, d, pid, args):
        from .caps import CliError
        try:
            r = self._cli().json(args, timeout=2400)
            st = r.get("status") or ("placed" if r.get("placed") else "generated")
            self._gen[(item, pid)] = dict(state=st, at=time.time(), error=r.get("error") or r.get("code"))
            if st == "placed":
                self._rerender(d)
        except CliError as e:
            doc = getattr(e, "doc", None) or {}
            self._gen[(item, pid)] = dict(state="failed", at=time.time(), error=str(e)[:300],
                                         code=doc.get("code"), params=doc.get("params"))
        except Exception as e:  # noqa: BLE001  (shown on the card)
            self._gen[(item, pid)] = dict(state="failed", at=time.time(), error=str(e)[:300])
        self._emit_gen(item, pid, self._gen[(item, pid)]["state"])

    def _emit_gen(self, item, pid, state):
        if self.bus:
            self.bus.publish("brain", item=item, state="ready", gen=pid, gen_state=state)

    def place(self, item, pid, undo=False):
        import re
        need(isinstance(pid, str) and re.match(GEN_RE, pid), "id: a proposal id")
        d = self._ready(item)
        self._run(["place", "--dir", d, "--id", pid, "--json"] + (["--undo"] if undo else []))
        resumed = self._rerender(d)
        out = self._after(d, {})
        return dict(out, resumed=resumed)

    def _rerender(self, d):
        """The edit changed (a take placed / taken out, her shot change): the project runs the stages that read it
        again in the background (unless a run goes already)."""
        from . import pilot
        if self.runner is None or pilot.running(d) or pilot.queued(d):
            return False
        py = self.runner.python
        args = [py, "-m", "vstudio.project", "resume", "--dir", d, "--json-events"]
        (self._spawn or pilot.spawn)(py, self.runner.env, d, bus=self.bus, args=args)
        return True

    def shots(self, item, clip):
        """The clip's shots on its timeline with the plan's why + alternatives (``vstudio.brain shots``)."""
        d, ok = self._project(item)
        if not ok or self.runner is None:
            return dict(item=item, supported=False, shots=[])
        out_id = None
        if self.outputs is not None and clip:
            try:
                e, c = self.outputs._clip(item, clip)
                out_id = self.outputs._output_id(e, c) or ((c.get("files") or [{}])[0].get("path"))
            except (KeyError, BadRequest):
                out_id = None
        args = ["shots", "--dir", d, "--json"] + (["--output", out_id] if out_id else [])
        doc = self._run(args)
        return dict(self._allow(doc), item=item, supported=True)

    def gen(self, item, pid, action, code=None):
        import re
        need(isinstance(pid, str) and re.match(r"^g[0-9a-f]{8}$", pid), "id: a proposal id")
        need(action in ("approve", "skip", "undo"), "action: approve | skip | undo")
        need(action != "approve" or (isinstance(code, str) and re.match(r"^[0-9a-f]{6}$", code)),
             "code: the proposal's confirm code (approve)")
        d = self._ready(item)
        args = ["decide", "--dir", d, "--id", pid, f"--{action}", "--json"] + (["--code", code] if code else [])
        return self._after(d, self._run(args))
