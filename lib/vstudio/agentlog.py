"""The live transcript of a job: what the model CLIs (Claude Code, Codex) and the API models were asked and did,
line by line, for the desk's live pane (a terminal-style view of the run, like tmux + Claude Code).

Off unless env ``VSTUDIO_AGENT_LOG`` names a file (the desk sets it per request / per project run; child processes
inherit it). Each line is one JSON object, appended with a single write (several processes of one run share the file):

    {at, src: agent|engine, kind, text, pid, turn?, task?, provider?, model?, tool?, data?}

kind (agent): turn (a model call starts: task, provider, model) | prompt (what was sent: its head) | thinking (the
reasoning summary a CLI streams) | tool (a tool call: name + its input in short) | tool-result | say (the model's
text) | result (the call's end: tokens, cost, time) | error. Engine lines (``src: engine``) are written by the desk
from the run's own events / log (``emit_engine``).

Everything goes through :func:`redact` first: API keys, bearer / basic credentials, JWTs, cookies, private keys,
``*_KEY=`` / ``token: ...`` assignments, e-mail addresses and the home folder (``~``). Lines are capped
(``MAX_TEXT``) and the file stops growing at ``MAX_BYTES`` (one ``truncated`` note).

Nothing here is ever faked: a call that streams nothing leaves its turn / prompt / result lines only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time

ENV = "VSTUDIO_AGENT_LOG"
MAX_TEXT = 4000
MAX_BYTES = 16 << 20
PROMPT_HEAD = 700

_lock = threading.Lock()
_turns = [0]
_truncated = set()

# ------------------------------------------------------------------ redaction
_SECRET_RX = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
     "[redacted private key]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{8,}"), "[redacted key]"),
    (re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{16,}"), "[redacted key]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), "[redacted key]"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "[redacted token]"),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}"), "[redacted token]"),
    (re.compile(r"\bhf_[A-Za-z0-9]{30,}"), "[redacted token]"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[redacted key]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), "[redacted token]"),
    (re.compile(r"\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=\-]{8,}", re.I), r"\1 [redacted]"),
    (re.compile(r"\b((?:set-)?cookie)(\s*[:=]\s*)[^\r\n]+", re.I), r"\1\2[redacted]"),
    # NAME_API_KEY=..., "token": "...", password: ... - the value only (a secret-looking value; any password)
    (re.compile(r"(?i)(\b[\w.\-]*(?:api[_\-]?key|secret|token|session[_\-]?id|auth[_\-]?key|access[_\-]?key|"
                r"private[_\-]?key|credential)s?[\"']?)(\s*[:=]\s*[\"']?)"
                r"((?=[^\s\"',;}]*[A-Za-z])(?=[^\s\"',;}]*\d)[^\s\"',;}]{8,}|[A-Za-z0-9_\-./+=]{16,})"),
     r"\1\2[redacted]"),
    (re.compile(r"(?i)(\b[\w.\-]*passw(?:or)?d[\"']?)(\s*[:=]\s*[\"']?)([^\s\"',;}]{3,})"), r"\1\2[redacted]"),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"), "[email]"),
]


def _home():
    h = os.path.expanduser("~")
    return h if h and h not in ("/", "~") and len(h) > 3 else None


def redact(text):
    """``text`` with secrets, e-mail addresses and the home folder taken out (see the module doc)."""
    s = str(text if text is not None else "")
    if not s:
        return s
    for rx, rep in _SECRET_RX:
        s = rx.sub(rep, s)
    h = _home()
    if h:
        s = s.replace(h, "~")
        if os.sep == "\\":
            s = s.replace(h.replace("\\", "/"), "~")       # the C:/Users/... spelling too (Node, git, ffmpeg)
    return s


def clip(text, n=MAX_TEXT):
    s = str(text or "")
    return s if len(s) <= n else s[:n] + f" … (+{len(s) - n} chars)"


# ------------------------------------------------------------------ writing
def target():
    """The transcript file of this process's job, or None (off)."""
    p = os.environ.get(ENV)
    return p or None


def active():
    return bool(target())


def _write(path, rec):
    line = json.dumps(rec, ensure_ascii=False, default=str) + "\n"
    data = line.encode("utf-8")
    with _lock:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if size + len(data) > MAX_BYTES:
            if path in _truncated:
                return
            _truncated.add(path)
            data = (json.dumps(dict(at=time.time(), src="engine", kind="truncated", pid=os.getpid(),
                                    text="live log is full; later lines are not kept"), ensure_ascii=False)
                    + "\n").encode("utf-8")
        try:
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)
        except OSError:
            pass                                          # the live view is never worth failing a run for


def _clean(v):
    if isinstance(v, str):
        return clip(redact(v), 600)
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in list(v)[:50]]
    if isinstance(v, dict):
        return {str(k)[:40]: _clean(x) for k, x in list(v.items())[:40]}
    return clip(redact(str(v)), 200)


def emit(kind, text="", src="agent", path=None, **fields):
    """Append one line (redacted) to the job's transcript; no-op when the transcript is off."""
    path = path or target()
    if not path:
        return
    rec = dict(at=round(time.time(), 3), src=src, kind=kind, text=clip(redact(text)), pid=os.getpid())
    for k, v in fields.items():
        if v is not None and v != "":
            rec[k] = _clean(v)
    _write(path, rec)


def emit_engine(path, kind, text, data=None, at=None):
    """An engine line (a stage, a log line) written by the desk into a job's transcript."""
    if not path:
        return
    rec = dict(at=round(at or time.time(), 3), src="engine", kind=kind, text=clip(redact(text)), pid=os.getpid())
    if data:
        rec["data"] = _clean(data)
    _write(path, rec)


def new_turn():
    with _lock:
        _turns[0] += 1
        return f"{os.getpid()}-{_turns[0]}"


def begin(task, provider, model, system, prompt):
    """A model call starts: its turn line + the head of what is sent. -> the turn id (None when off)."""
    if not active():
        return None
    turn = new_turn()
    emit("turn", f"{task} · {provider}" + (f" ({model})" if model else ""), task=task, provider=provider,
         model=model, turn=turn)
    p = str(prompt or "")
    head = p[:PROMPT_HEAD] + (f" … (+{len(p) - PROMPT_HEAD} chars)" if len(p) > PROMPT_HEAD else "")
    emit("prompt", head, turn=turn, provider=provider,
         data=dict(chars=len(p), system_chars=len(system or "")))
    return turn


def finish(turn, out, seconds):
    if turn is None:
        return
    u = out.get("usage") or {}
    bits = [f"{int(u.get('input', 0) or 0):,} in", f"{int(u.get('output', 0) or 0):,} out", f"{seconds:.1f} s"]
    if out.get("cost_usd"):
        bits.append(f"${out['cost_usd']:.3f}")
    elif u.get("notional_cost_usd") is not None:
        bits.append("subscription")
    emit("result", " · ".join(bits), turn=turn, provider=out.get("provider"), model=out.get("model"),
         data=dict(input=u.get("input"), output=u.get("output"), seconds=round(seconds, 2),
                   json=out.get("json") is not None))


def fail(turn, err, provider=None):
    if turn is not None:
        emit("error", str(err), turn=turn, provider=provider)


# ------------------------------------------------------------------ CLI event streams -> lines
def _short_input(inp):
    if not isinstance(inp, dict):
        return clip(str(inp or ""), 300)
    for k in ("command", "file_path", "path", "pattern", "url", "query", "description", "prompt"):
        if isinstance(inp.get(k), str):
            return clip(inp[k], 300)
    return clip(json.dumps(inp, ensure_ascii=False), 300)


def _content_text(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(_content_text(x.get("text") if isinstance(x, dict) else x) for x in c)
    return str(c or "")


def claude_event(ev, turn=None, provider="claude-code", path=None):
    """One ``claude -p --output-format stream-json --verbose`` event -> transcript lines."""
    if not isinstance(ev, dict):
        return
    typ = ev.get("type")
    if typ == "system" and ev.get("subtype") == "init":
        emit("info", f"session · {ev.get('model') or 'default model'}", turn=turn, provider=provider, path=path)
    elif typ == "assistant":
        for b in ((ev.get("message") or {}).get("content") or []):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and (b.get("text") or "").strip():
                emit("say", b["text"], turn=turn, provider=provider, path=path)
            elif b.get("type") == "thinking" and (b.get("thinking") or "").strip():
                emit("thinking", b["thinking"], turn=turn, provider=provider, path=path)
            elif b.get("type") == "tool_use":
                emit("tool", f"{b.get('name') or 'tool'}  {_short_input(b.get('input'))}", turn=turn,
                     provider=provider, path=path, tool=b.get("name"))
    elif typ == "user":
        for b in ((ev.get("message") or {}).get("content") or []):
            if isinstance(b, dict) and b.get("type") == "tool_result":
                emit("tool-result", clip(_content_text(b.get("content")), 800), turn=turn, provider=provider, path=path,
                     data=dict(error=bool(b.get("is_error"))))
    elif typ == "result" and ev.get("is_error"):
        emit("error", str(ev.get("result") or ev.get("subtype") or "error"), turn=turn, provider=provider, path=path)


def codex_event(ev, turn=None, provider="codex", path=None):
    """One ``codex exec --json`` event -> transcript lines."""
    if not isinstance(ev, dict):
        return
    typ = ev.get("type") or ""
    item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
    it = item.get("type")
    if typ == "thread.started":
        emit("info", "session started", turn=turn, provider=provider, path=path)
    elif typ == "item.started" and it == "command_execution":
        emit("tool", f"$ {item.get('command') or ''}", turn=turn, provider=provider, path=path, tool="shell")
    elif typ == "item.completed":
        if it == "reasoning" and (item.get("text") or "").strip():
            emit("thinking", item["text"], turn=turn, provider=provider, path=path)
        elif it == "agent_message" and (item.get("text") or "").strip():
            emit("say", item["text"], turn=turn, provider=provider, path=path)
        elif it == "command_execution":
            out = clip(item.get("aggregated_output") or "", 800)
            emit("tool-result", out or f"exit {item.get('exit_code')}", turn=turn, provider=provider, path=path,
                 data=dict(exit=item.get("exit_code")))
        elif it == "file_change":
            ch = ", ".join(f"{c.get('kind', '')} {c.get('path', '')}".strip() for c in item.get("changes") or []
                           if isinstance(c, dict))
            emit("tool", f"edit  {ch}", turn=turn, provider=provider, path=path, tool="edit")
        elif it == "mcp_tool_call":
            emit("tool", f"{item.get('server', '')}.{item.get('tool', '')}", turn=turn, provider=provider, path=path, tool="mcp")
        elif it == "web_search":
            emit("tool", f"search  {item.get('query', '')}", turn=turn, provider=provider, path=path, tool="search")
        elif it == "todo_list":
            todo = "; ".join(("[x] " if t.get("completed") else "[ ] ") + str(t.get("text", ""))
                             for t in item.get("items") or [] if isinstance(t, dict))
            emit("thinking", f"plan: {todo}", turn=turn, provider=provider, path=path)
        elif it == "error":
            emit("error", item.get("message") or "error", turn=turn, provider=provider, path=path)
    elif typ in ("turn.failed", "error"):
        e = ev.get("error")
        emit("error", (e.get("message") if isinstance(e, dict) else e) or ev.get("message") or typ, turn=turn,
             provider=provider, path=path)


# ------------------------------------------------------------------ running a CLI while reading its stream
def run_streaming(cmd, input, cwd, env, timeout, on_line):
    """``subprocess.run(cmd, input=..., capture_output=True, text=True, timeout=...)`` that also hands every stdout
    line to ``on_line`` as it arrives. Raises ``subprocess.TimeoutExpired`` (the child is killed) like run()."""
    kw = dict(start_new_session=True) if os.name != "nt" else {}
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", cwd=cwd, env=env, bufsize=1, **kw)
    with _CHILDREN_LOCK:
        _CHILDREN.add(p)
    try:
        return _wait_streaming(p, cmd, input, timeout, on_line)
    finally:
        with _CHILDREN_LOCK:
            _CHILDREN.discard(p)


# The model CLIs running now (run_streaming). Each runs in its own session, so a Stop (SIGINT to the run's process
# group) never reaches them: the run ends them itself (kill_children) or it would wait out the whole call.
_CHILDREN = set()
_CHILDREN_LOCK = threading.Lock()


def kill_children():
    """End every model CLI this process is waiting on (a stopped run). -> how many."""
    with _CHILDREN_LOCK:
        ps = [p for p in _CHILDREN if p.poll() is None]
    for p in ps:
        _kill(p)
    return len(ps)


def _wait_streaming(p, cmd, input, timeout, on_line):
    out, err = [], []

    def feed():
        try:
            if input:
                p.stdin.write(input)
            p.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass

    def read_err():
        for ln in p.stderr:
            err.append(ln)

    def read_out():
        for ln in p.stdout:
            out.append(ln)
            try:
                on_line(ln)
            except Exception:  # noqa: BLE001  (the live view never breaks the call)
                pass
    ts = [threading.Thread(target=f, daemon=True) for f in (feed, read_err, read_out)]
    for t in ts:
        t.start()
    try:
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(p)
        p.wait()
        raise
    for t in ts[1:]:
        t.join(5)
    return subprocess.CompletedProcess(cmd, p.returncode, "".join(out), "".join(err))


def _kill(p):
    try:
        if os.name != "nt":
            import signal
            os.killpg(p.pid, signal.SIGKILL)
        else:
            p.kill()
    except OSError:
        try:
            p.kill()
        except OSError:
            pass


def json_lines(on_event):
    """A ``run_streaming`` line callback that parses JSON lines and hands each object to ``on_event``."""
    def on_line(ln):
        s = ln.strip()
        if s.startswith("{"):
            try:
                on_event(json.loads(s))
            except ValueError:
                pass
    return on_line
