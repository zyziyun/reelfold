"""The live pane's data (the desk's terminal-style view of a run, like tmux + Claude Code): one job's transcript - the
model CLIs' turns the engine captured (``vstudio.agentlog``: prompts, thinking, tool calls, replies) and the engine's
own stage events / log lines - read in order from a cursor, and a nudge on the event bus when a watched job's files
grow.

Files
  a request (planning)  <data>/intake/<id>.live.jsonl      agent lines (the engine child writes them: VSTUDIO_AGENT_LOG)
                                                            + engine lines the desk writes (stages, the engine's log)
  a project run         <project>/desk-agent.jsonl          agent lines of the run (``agent_offset`` in desk-pilot.json
                                                            marks where the current run starts)
                        <project>/desk-pilot.log            the run's --json-events + log (``offset``: the current run)

``read(paths, cursor)`` -> {lines [{at, src agent|engine, kind, text, turn?, task?, provider?, model?, tool?, data?}],
cursor, more}. ``cursor``: "<file#>:<byte offset>,..." (opaque to the desk). Every line is redacted again on the way
out (``vstudio.agentlog.redact``), engine log lines included; ANSI colour codes are left for the desk to render.

``LiveHub``: ``watch(key, paths)`` (each GET renews it for ``WATCH_S``); a thread checks the watched files' sizes and
publishes ``live {key}`` on the bus when one grew, so the desk fetches from its cursor at once (no polling while a
pane is open, no duplicate or lost lines: the cursor is the desk's).
"""
import json
import os
import re
import threading
import time

from .common import read_json

READ_MAX = 256 * 1024
WATCH_S = 120.0
TICK_S = 0.4
LIVE_NAME = "desk-agent.jsonl"

try:                                                         # the engine library: one redaction for both sides
    from vstudio.agentlog import ENV as AGENT_ENV, emit_engine as _emit_engine, redact
except Exception:  # noqa: BLE001  (an engine without it: plain lines, the basic redaction below)
    AGENT_ENV = "VSTUDIO_AGENT_LOG"
    _BASIC = [re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), re.compile(r"\b(Bearer)\s+\S{8,}", re.I),
              re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")]

    def redact(text):
        s = str(text or "")
        for rx in _BASIC:
            s = rx.sub("[redacted]", s)
        return s

    def _emit_engine(path, kind, text, data=None, at=None):
        rec = dict(at=round(at or time.time(), 3), src="engine", kind=kind, text=redact(text)[:4000])
        if data:
            rec["data"] = data
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass


def emit_engine(path, kind, text, data=None, at=None):
    if path:
        _emit_engine(path, kind, text, data=data, at=at)


# ------------------------------------------------------------------ engine events in words (the log's own terms)
def _fmt_s(s):
    try:
        s = int(round(float(s)))
    except (TypeError, ValueError):
        return ""
    return f"{s // 60}:{s % 60:02d}"


def intake_stage_text(ev):
    """An intake --json-events line -> one log line (``probe · DJI_0412.MP4 · 16/27``)."""
    st = ev.get("stage") or ev.get("event") or "?"
    bits = [st]
    if ev.get("file"):
        bits.append(str(ev["file"]))
    if ev.get("i") and ev.get("n"):
        bits.append(f"{ev['i']}/{ev['n']}")
    if ev.get("files") is not None:
        bits.append(f"{ev['files']} files")
    if ev.get("total_s"):
        bits.append(f"{_fmt_s(ev.get('done_s') or 0)} / {_fmt_s(ev['total_s'])}")
    if ev.get("cached"):
        bits.append("cached")
    if ev.get("provider"):
        bits.append(str(ev["provider"]) + (f" ({ev['model']})" if ev.get("model") else ""))
    return " · ".join(bits)


_EV_KEYS = ("event", "job", "stage", "state", "status", "checkpoint", "item", "by", "exit_code", "kind", "checkpoint_kind",
            "qc", "progress", "provider", "reason", "pick", "cached", "seconds", "error", "code")


def run_event_line(ev, at):
    """A project run's --json-events line -> a transcript line (``stage-start · s01 · asr``)."""
    data = {k: ev[k] for k in _EV_KEYS if isinstance(ev.get(k), (str, int, float)) and not isinstance(ev.get(k), bool)}
    if isinstance(ev.get("jobs"), list):
        data["n"] = len(ev["jobs"])
    name = ev.get("event") or ("error" if ev.get("ok") is False else "event")
    bits = [name] + [str(data[k]) for k in ("job", "stage", "state", "checkpoint", "by") if k in data]
    if ev.get("ok") is False and ev.get("error"):
        bits.append(str(ev["error"]))
    if name == "run-start" and "n" in data:
        bits.append(f"{data['n']} jobs")
    if "exit_code" in data:
        bits.append(f"exit {data['exit_code']}")
    return dict(at=ev.get("ts") or at, src="engine", kind="error" if name in ("stage-fail", "error") else "event",
                text=redact(" · ".join(bits)), data=data)


# ------------------------------------------------------------------ reading
def _parse_cursor(cursor, n):
    offs = [None] * n
    for part in str(cursor or "").split(","):
        m = re.match(r"^(\d):(\d{1,15})$", part.strip())
        if m and int(m.group(1)) < n:
            offs[int(m.group(1))] = int(m.group(2))
    return offs


def _read_from(path, start, base):
    """Complete lines of ``path`` from byte ``start`` (None: the last READ_MAX bytes after ``base``) -> (lines,
    end offset, more)."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return [], start if start is not None else base, False
    if start is None:
        start = max(base, size - READ_MAX)
        skip_partial = start > base
    else:
        skip_partial = False
    if start > size:                                         # the file was replaced: start over
        start, skip_partial = base if base <= size else 0, False
    with open(path, "rb") as f:
        f.seek(start)
        buf = f.read(READ_MAX)
    end = buf.rfind(b"\n")
    if end < 0:
        return [], start, False
    chunk = buf[:end + 1]
    lines = chunk.decode("utf-8", "replace").splitlines()
    if skip_partial and lines:
        lines = lines[1:]
    return lines, start + end + 1, start + end + 1 < size


def _agent_line(s):
    try:
        rec = json.loads(s)
    except ValueError:
        return None
    if not isinstance(rec, dict) or not rec.get("kind"):
        return None
    rec["text"] = redact(rec.get("text") or "")
    rec.pop("pid", None)
    return rec


def read(sources, cursor=None):
    """``sources``: [(path, kind 'jsonl' | 'runlog', base offset)] -> the lines after ``cursor``, in time order."""
    offs = _parse_cursor(cursor, len(sources))
    out, ends, more = [], [], False
    for k, (path, kind, base) in enumerate(sources):
        lines, end, m = _read_from(path, offs[k], base or 0)
        more = more or m
        ends.append(end)
        last_at = None
        for s in lines:
            s = s.rstrip("\r")
            if not s.strip():
                continue
            if kind == "jsonl":
                rec = _agent_line(s)
                if rec:
                    out.append(rec)
                    last_at = rec.get("at") or last_at
                continue
            t = s.strip()
            ev = None
            if t.startswith("{") and t.endswith("}"):
                try:
                    ev = json.loads(t)
                except ValueError:
                    ev = None
            if isinstance(ev, dict):
                if ev.get("event") == "progress":
                    continue                                 # counters: the hero shows them, not the log
                rec = run_event_line(ev, last_at)
            else:
                rec = dict(at=last_at, src="engine", kind="log", text=redact(s[:4000]))
            last_at = rec.get("at") or last_at
            out.append(rec)
    # one timeline; a line without a time keeps its place after the one before it
    seq = []
    t_prev = 0.0
    for i, r in enumerate(out):
        t_prev = r.get("at") or t_prev
        seq.append((t_prev, i, r))
    seq.sort(key=lambda x: (x[0], x[1]))
    return dict(lines=[r for _t, _i, r in seq], cursor=",".join(f"{k}:{e}" for k, e in enumerate(ends)), more=more)


# ------------------------------------------------------------------ where a job's files are
def request_path(data_dir, pid):
    return os.path.join(data_dir, "intake", f"{pid}.live.jsonl")


def request_sources(data_dir, pid):
    return [(request_path(data_dir, pid), "jsonl", 0)]


def project_sources(d):
    from .pilot import LOG, REC
    rec = read_json(os.path.join(d, REC), None)
    rec = rec if isinstance(rec, dict) else {}
    return [(os.path.join(d, LIVE_NAME), "jsonl", int(rec.get("agent_offset") or 0)),
            (os.path.join(d, LOG), "runlog", int(rec.get("offset") or 0))]


def file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


# ------------------------------------------------------------------ the nudge
class LiveHub:
    def __init__(self, bus):
        self.bus = bus
        self._lock = threading.Lock()
        self._watch = {}                                     # key -> {paths, until, sizes}
        self._thread = None

    def watch(self, key, sources):
        paths = [p for p, _k, _b in sources]
        with self._lock:
            cur = self._watch.get(key)
            sizes = cur["sizes"] if cur and cur["paths"] == paths else [file_size(p) for p in paths]
            self._watch[key] = dict(paths=paths, until=time.time() + WATCH_S, sizes=sizes)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, daemon=True, name="live-hub")
                self._thread.start()

    def _loop(self):
        while True:
            time.sleep(TICK_S)
            now = time.time()
            grew = []
            with self._lock:
                for key in list(self._watch):
                    w = self._watch[key]
                    if w["until"] < now:
                        del self._watch[key]
                        continue
                    sizes = [file_size(p) for p in w["paths"]]
                    if sizes != w["sizes"]:
                        w["sizes"] = sizes
                        grew.append(key)
                if not self._watch:
                    self._thread = None
                    return
            for key in grew:
                if self.bus:
                    self.bus.publish("live", key=key)
