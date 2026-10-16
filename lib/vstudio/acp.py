"""Agent Client Protocol (ACP) client: one integration that drives every coding agent the user installed and signed
in to (Gemini CLI, Qwen Code, Kimi CLI, CodeBuddy, iFlow, OpenCode, Cursor CLI, GitHub Copilot CLI, Claude Code /
Codex through their ACP adapters) as a text model for the engine's AI steps.

    from vstudio import acp
    acp.run("qwen-code", system="...", prompt="...", model=None, timeout=300)   # -> {text, usage, model, stop_reason}
    acp.probe("kimi-cli")          # -> {state: logged-in | not-logged-in | not-installed | error, models, ...}

ACP (agentclientprotocol.com) is JSON-RPC 2.0, one JSON object per line, over the agent's stdin / stdout. This module
is the client: ``initialize`` -> ``session/new`` (an empty temp folder, no MCP servers) -> optional model choice
(``session/set_config_option`` or the older ``session/set_model``) -> ``session/prompt``; the reply is the text of
the ``agent_message_chunk`` updates. The agent may ask for permission to run a tool (``session/request_permission``):
it is always refused (these calls only want text), and the client offers no file system or terminal.

The user's own installation, unmodified, with its own sign-in: the engine starts the program the user installed
(PATH, then the folders installers use), never reads a credential, and removes the API keys the desk / engine itself
might have in its environment (Anthropic / OpenAI variables) so the agent uses the login the user gave it - the same
principle as the ``claude-code`` / ``codex`` providers in ``vstudio.llm``. Route option ``inherit_env: true`` keeps
every variable; ``cli`` names the program; ``acp_args`` replaces the arguments that start ACP mode.

Errors are plain words that ``vstudio.llm.failure_code`` classifies: "... is not installed" (not-installed), "...
is not logged in" (not-logged-in), "... not available in your region" (region-blocked), "unsupported model"
(model-unsupported), "timed out after N s" (timeout).
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import threading
import time

PROTOCOL_VERSION = 1
AUTH_REQUIRED = -32000
METHOD_NOT_FOUND = -32601

# Each agent: the program names it installs (first found wins), the arguments that start ACP mode (``alt_args``: what
# older versions took), its own sign-in command (``login``; [] = the program itself asks on its first run), the ACP
# auth method that takes up its existing sign-in (``authenticate``), where to get it, and whether it works from
# mainland China without a VPN (``china``: yes | partly | no) and with what account (``account``).
AGENTS = {
    "qwen-code": dict(label="Qwen Code", maker="Alibaba", exe=("qwen",), args=["--acp"],
                      alt_args=[["--experimental-acp"]], login=[], china="yes",
                      account="Qwen OAuth (qwen.ai, free daily quota) or a DashScope / Bailian key",
                      install=dict(url="https://github.com/QwenLM/qwen-code",
                                   command="npm install -g @qwen-code/qwen-code@latest")),
    "kimi-cli": dict(label="Kimi CLI", maker="Moonshot AI", exe=("kimi",), args=["acp"], alt_args=[["--acp"]],
                     login=["login"], china="yes", dirs=("~/.kimi-code/bin",),
                     account="Kimi / Moonshot account",
                     install=dict(url="https://github.com/MoonshotAI/kimi-cli", command="uv tool install kimi-cli")),
    "codebuddy": dict(label="CodeBuddy", maker="Tencent", exe=("codebuddy", "cbc"), args=["--acp"], login=[],
                      china="yes", account="CodeBuddy account (China site codebuddy.cn or international codebuddy.ai)",
                      install=dict(url="https://www.codebuddy.ai/cli",
                                   command="npm install -g @tencent-ai/codebuddy-code")),
    "iflow": dict(label="iFlow CLI", maker="Alibaba iFlow", exe=("iflow",), args=["--experimental-acp"],
                  alt_args=[["--acp"]], login=[], china="yes", account="iFlow account (iflow.cn) or its API key",
                  install=dict(url="https://github.com/iflow-ai/iflow-cli", command="npm install -g @iflow-ai/iflow-cli")),
    "opencode": dict(label="OpenCode", maker="SST", exe=("opencode",), args=["acp"], login=["auth", "login"],
                     china="yes", dirs=("~/.opencode/bin",),
                     account="any provider you add to it (DeepSeek, Kimi, GLM, Qwen keys work in China)",
                     install=dict(url="https://opencode.ai", command="npm install -g opencode-ai")),
    "gemini-cli": dict(label="Gemini CLI", maker="Google", exe=("gemini",), args=["--acp"],
                       alt_args=[["--experimental-acp"]], login=[], china="no", account="Google account",
                       install=dict(url="https://github.com/google-gemini/gemini-cli",
                                    command="npm install -g @google/gemini-cli")),
    "cursor-agent": dict(label="Cursor CLI", maker="Cursor", exe=("cursor-agent",), args=["acp"], login=["login"],
                         authenticate="cursor_login", china="partly", account="Cursor account",
                         install=dict(url="https://cursor.com/cli", command="curl https://cursor.com/install -fsS | bash")),
    "copilot": dict(label="GitHub Copilot CLI", maker="GitHub", exe=("copilot",), args=["--acp"], login=["login"],
                    china="partly", account="GitHub account with Copilot",
                    install=dict(url="https://github.com/github/copilot-cli", command="npm install -g @github/copilot")),
    # the makers' official ACP adapters around the user's own Claude Code / Codex (they take its path)
    "claude-acp": dict(label="Claude Code (ACP)", maker="Anthropic", exe=("claude-agent-acp", "claude-code-acp"),
                       args=[], login=[], china="no", account="your Claude Code sign-in", wraps="claude",
                       wrap_env="CLAUDE_CODE_EXECUTABLE",
                       install=dict(url="https://github.com/agentclientprotocol/claude-agent-acp",
                                    command="npm install -g @agentclientprotocol/claude-agent-acp")),
    "codex-acp": dict(label="Codex (ACP)", maker="OpenAI", exe=("codex-acp",), args=[], login=[], china="no",
                      account="your Codex sign-in", wraps="codex", wrap_env="CODEX_PATH",
                      install=dict(url="https://github.com/zed-industries/codex-acp",
                                   command="npm install -g @zed-industries/codex-acp")),
}
# international first, then the agents made in China (the order every list shows)
IDS = ("gemini-cli", "cursor-agent", "copilot", "opencode", "claude-acp", "codex-acp", "qwen-code", "kimi-cli",
       "codebuddy", "iflow")
AGENTS = {k: AGENTS[k] for k in IDS}
ALIASES = {"gemini-acp": "gemini-cli", "qwen-cli": "qwen-code", "qwencode": "qwen-code", "kimi-code": "kimi-cli",
           "kimi-acp": "kimi-cli", "cursor": "cursor-agent", "cursor-cli": "cursor-agent", "github-copilot": "copilot",
           "copilot-cli": "copilot", "tencent-codebuddy": "codebuddy", "iflow-cli": "iflow",
           "claude-agent-acp": "claude-acp", "claude-code-acp": "claude-acp"}

# the keys a desk / engine environment may carry for the API providers: an agent would take them up instead of the
# login the user gave it ("X_*" = every X_ variable)
STRIP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL",
             "OPENAI_*", "CODEX_API_KEY")
NOT_ACP = re.compile(r"unknown (option|argument|command|flag)|unrecognized|invalid (option|argument)|no such (option|"
                     r"command)|did you mean|usage:", re.I)
AUTH_WORDS = re.compile(r"auth(entication)? required|not (logged|signed) in|please (log ?in|sign in)|login required|"
                        r"no credentials|\b401\b|unauthori[sz]ed|invalid api key|api key (is )?(missing|not (set|configured))|"
                        r"credentials? (are |is )?(missing|not found)", re.I)
REGION_WORDS = re.compile(r"not (available|supported) in your (country|region)|unsupported_country|"
                          r"location is not supported|country,? region,? or territory|region (is )?not supported|"
                          r"not available in (this|your) (location|area)|不支持.{0,8}(地区|区域)|(地区|区域).{0,6}不(支持|可用)", re.I)


class AcpError(RuntimeError):
    """A JSON-RPC error from the agent (``code``, ``data``) or the agent process ending / not answering."""

    def __init__(self, message, code=None, data=None):
        super().__init__(message)
        self.code = code
        self.data = data


def canonical(name):
    n = str(name or "").strip().lower()
    n = ALIASES.get(n, n)
    return n if n in AGENTS else None


def label(agent):
    return AGENTS[agent]["label"]


# ------------------------------------------------------------------ finding and starting the agent
def find(agent, opts=None):
    """Absolute path of the agent's program (route option ``cli``, PATH, installers' folders), or None."""
    from . import llm
    spec = AGENTS[agent]
    if (opts or {}).get("cli"):
        return opts["cli"]
    for name in spec["exe"]:
        exe = llm.find_cli(name)
        if exe:
            return exe
    # the folders its own installer uses (not when VSTUDIO_CLI_EXTRA_DIRS says where to look: tests, packaged apps)
    for d in spec.get("dirs", ()) if os.environ.get("VSTUDIO_CLI_EXTRA_DIRS") is None else ():
        for name in spec["exe"]:
            p = os.path.join(os.path.expanduser(d), name)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


def environment(agent, opts=None):
    """The agent's environment: this one minus the API keys the desk / engine carries (unless ``inherit_env``) and a
    Claude Code session's own variables; an adapter is told where the user's own Claude Code / Codex is."""
    from . import llm
    o = opts or {}
    env = dict(os.environ) if o.get("inherit_env") else llm.strip_env(os.environ, STRIP_ENV)
    env = llm.strip_claude_session_env(env)
    spec = AGENTS[agent]
    if spec.get("wraps"):
        inner = llm.find_cli(spec["wraps"])
        if inner:
            env[spec["wrap_env"]] = inner
    return env


def _argv_options(agent, opts):
    spec = AGENTS[agent]
    if (opts or {}).get("acp_args") is not None:
        return [list((opts or {})["acp_args"])]
    return [list(spec["args"]), *[list(a) for a in spec.get("alt_args", ())]]


# ------------------------------------------------------------------ JSON-RPC over stdio
class Connection:
    """One agent process and the JSON-RPC traffic with it. The agent's requests to the client are answered here:
    permission is always refused, file system / terminal methods do not exist."""

    def __init__(self, argv, cwd, env, on_update=None):
        from . import agentlog
        kw = dict(start_new_session=True) if os.name != "nt" else dict(creationflags=0x08000000)   # no console window
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  cwd=cwd, env=env, **kw)
        with agentlog._CHILDREN_LOCK:                    # the engine kills it when the app quits
            agentlog._CHILDREN.add(self.p)
        self.on_update = on_update
        self.stderr = ""
        self.permission_asks = 0
        self._id = 0
        self._pending = {}
        self._lock = threading.Lock()
        self._wlock = threading.Lock()
        self._closed = threading.Event()
        self._stderr_thread = threading.Thread(target=self._read_err, daemon=True)
        self._stderr_thread.start()
        threading.Thread(target=self._read_out, daemon=True).start()

    # -- transport
    def _send(self, msg):
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self._wlock:
            try:
                self.p.stdin.write(data)
                self.p.stdin.flush()
            except (OSError, ValueError) as e:
                if self.p.poll() is not None:
                    self._stderr_thread.join(timeout=1)
                    raise AcpError(self._exit_words(), code="exited", data=self.stderr) from e
                raise AcpError(f"the agent stopped reading ({e})") from e

    def _read_err(self):
        for raw in iter(self.p.stderr.readline, b""):
            self.stderr = (self.stderr + raw.decode("utf-8", "replace"))[-16000:]

    def _read_out(self):
        for raw in iter(self.p.stdout.readline, b""):
            ln = raw.decode("utf-8", "replace").strip()
            if not ln.startswith("{"):
                continue                                   # an agent's own log line on stdout
            try:
                msg = json.loads(ln)
            except ValueError:
                continue
            if isinstance(msg, dict):
                try:
                    self._dispatch(msg)
                except Exception:  # noqa: BLE001 - one odd message never stops the reader
                    pass
        self.p.wait()
        # stdout EOF can win the race against stderr, even after process exit.
        # Drain its reader before waking requests; bound the wait in case a
        # descendant inherited stderr and keeps the pipe open.
        self._stderr_thread.join(timeout=1)
        self._closed.set()
        with self._lock:
            pending, self._pending = self._pending, {}
        for slot in pending.values():
            slot["error"] = AcpError(self._exit_words(), code="exited", data=self.stderr)
            slot["event"].set()

    def _exit_words(self):
        tail = " ".join(self.stderr.strip().splitlines()[-4:])[:400]
        return f"the agent exited (code {self.p.returncode})" + (f": {tail}" if tail else "")

    def _dispatch(self, msg):
        if "id" in msg and ("result" in msg or "error" in msg) and "method" not in msg:
            with self._lock:
                slot = self._pending.pop(msg["id"], None)
            if slot is None:
                return
            if "error" in msg and msg["error"] is not None:
                e = msg["error"] if isinstance(msg["error"], dict) else {"message": str(msg["error"])}
                data = e.get("data")
                text = str(e.get("message") or "error")
                if isinstance(data, (str, dict)) and data:
                    text += f": {data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)[:300]}"
                slot["error"] = AcpError(text, code=e.get("code"), data=data)
            else:
                slot["result"] = msg.get("result")
            slot["event"].set()
            return
        method, params = msg.get("method"), msg.get("params") or {}
        if "id" in msg:                                    # the agent asks the client something
            self._send(dict(jsonrpc="2.0", id=msg["id"], **self._answer(method, params)))
        elif method == "session/update" and self.on_update:
            self.on_update(params.get("update") or {})

    def _answer(self, method, params):
        if method == "session/request_permission":
            # never: these calls want text only. Prefer the agent's own "reject" option, else cancel.
            self.permission_asks += 1
            opt = next((o.get("optionId") for o in params.get("options") or []
                        if isinstance(o, dict) and o.get("kind") == "reject_once"), None)
            return dict(result={"outcome": {"outcome": "selected", "optionId": opt}} if opt else
                        {"outcome": {"outcome": "cancelled"}})
        return dict(error={"code": METHOD_NOT_FOUND, "message": f"{method} is not offered by this client"})

    def request(self, method, params, timeout):
        with self._lock:
            self._id += 1
            rid = self._id
            slot = self._pending[rid] = dict(event=threading.Event())
        if self._closed.is_set():
            raise AcpError(self._exit_words(), code="exited", data=self.stderr)
        self._send(dict(jsonrpc="2.0", id=rid, method=method, params=params))
        if not slot["event"].wait(timeout):
            with self._lock:
                self._pending.pop(rid, None)
            raise AcpError(f"{method} timed out after {round(timeout)} s", code="timeout")
        if "error" in slot:
            raise slot["error"]
        return slot.get("result") or {}

    def notify(self, method, params):
        try:
            self._send(dict(jsonrpc="2.0", method=method, params=params))
        except AcpError:
            pass

    def close(self):
        from . import agentlog
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            self.p.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            agentlog._kill(self.p)
        with agentlog._CHILDREN_LOCK:
            agentlog._CHILDREN.discard(self.p)


# ------------------------------------------------------------------ sessions
def _client_info():
    try:
        from importlib.metadata import version
        v = version("vstudio")
    except Exception:  # noqa: BLE001
        v = "0"
    return {"name": "reelfold", "title": "Reelfold", "version": v}


def session_models(sess):
    """(models [{id, label, note?}], current id, how to set it: "config:<id>" | "set_model" | None) of a session/new
    reply: the ``configOptions`` select of category model, else the older ``models`` list."""
    for o in (sess or {}).get("configOptions") or []:
        if isinstance(o, dict) and o.get("category") == "model" and isinstance(o.get("options"), list):
            rows = []
            for x in o["options"]:
                if isinstance(x, dict) and isinstance(x.get("options"), list):     # a grouped select
                    rows += [y for y in x["options"] if isinstance(y, dict)]
                elif isinstance(x, dict):
                    rows.append(x)
            ms = [dict(id=str(x["value"]), label=str(x.get("name") or x["value"]),
                       **({"note": str(x["description"])} if x.get("description") else {}))
                  for x in rows if x.get("value")]
            return ms, o.get("currentValue"), f"config:{o.get('id') or 'model'}"
    m = (sess or {}).get("models") or {}
    ms = [dict(id=str(x["modelId"]), label=str(x.get("name") or x["modelId"]),
               **({"note": str(x["description"])} if x.get("description") else {}))
          for x in m.get("availableModels") or [] if isinstance(x, dict) and x.get("modelId")]
    return ms, m.get("currentModelId"), "set_model" if ms else None


class Session:
    """``with Session(agent) as s: s.prompt(...)`` - an agent process, initialized, with one session open."""

    def __init__(self, agent, opts=None, timeout=60.0, on_update=None):
        self.agent, self.opts, self.spec = agent, dict(opts or {}), AGENTS[agent]
        self.exe = find(agent, self.opts)
        self.start_timeout = timeout
        self.on_update = on_update
        self.conn = self.init = self.sess = None
        self.tmp = None

    def __enter__(self):
        from . import llm
        if not self.exe:
            raise llm.LLMError(f"{label(self.agent)} is not installed (`{self.spec['exe'][0]}` not on PATH): "
                               f"{self.spec['install']['command']}")
        self.tmp = tempfile.TemporaryDirectory(prefix="vstudio-acp-")
        try:
            return self._open(llm)
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _open(self, llm):
        env = environment(self.agent, self.opts)
        last = None
        for args in _argv_options(self.agent, self.opts):
            try:
                self._start([*llm.cli_argv(self.exe), *args], env)
                return self
            except OSError as e:
                raise llm.LLMError(f"{label(self.agent)} could not be started ({self.exe}): {e}") from e
            except AcpError as e:
                last = e
                self._stop()
                # an older / newer version that starts ACP with other arguments: try those
                if e.code == "exited" and NOT_ACP.search(f"{e}\n{e.data or ''}"):
                    continue
                raise _plain(self.agent, e) from e
        raise llm.LLMError(f"{label(self.agent)} did not start in ACP mode - update it "
                           f"({self.spec['install']['command']}): {last}")

    def _start(self, argv, env):
        self.conn = Connection(argv, self.tmp.name, env, on_update=self._update)
        self.init = self.conn.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
            "clientInfo": _client_info()}, self.start_timeout)
        params = {"cwd": self.tmp.name, "mcpServers": []}
        try:
            self.sess = self.conn.request("session/new", params, self.start_timeout)
        except AcpError as e:
            auth = self.spec.get("authenticate")
            methods = {m.get("id") for m in (self.init or {}).get("authMethods") or [] if isinstance(m, dict)}
            if e.code != AUTH_REQUIRED or not auth or auth not in methods:
                raise
            # the agent's own existing sign-in, taken up (Cursor asks for this before any session)
            self.conn.request("authenticate", {"methodId": auth}, self.start_timeout)
            self.sess = self.conn.request("session/new", params, self.start_timeout)

    def _update(self, u):
        if self.on_update:
            self.on_update(u)

    def _stop(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __exit__(self, *exc):
        self._stop()
        if self.tmp:
            self.tmp.cleanup()
            self.tmp = None

    @property
    def session_id(self):
        return (self.sess or {}).get("sessionId")

    def models(self):
        return session_models(self.sess)

    def use_model(self, model, timeout=30.0):
        """Switch the session to ``model``: an id the agent does not list is refused before anything runs."""
        from . import llm
        ms, cur, how = self.models()
        if not model or model == cur:
            return
        ids = [m["id"] for m in ms]
        if ids and model not in ids:
            hit = next((m["id"] for m in ms if m["label"].lower() == str(model).lower()), None)
            if not hit:
                raise llm.LLMError(f"{label(self.agent)}: unsupported model '{model}' for this sign-in - it offers "
                                   f"{', '.join(ids[:8])}{' ...' if len(ids) > 8 else ''}")
            model = hit
        try:
            if how and how.startswith("config:"):
                self.conn.request("session/set_config_option", {"sessionId": self.session_id,
                                                                "configId": how[7:], "value": model}, timeout)
            else:
                self.conn.request("session/set_model", {"sessionId": self.session_id, "modelId": model}, timeout)
        except AcpError as e:
            raise llm.LLMError(f"{label(self.agent)}: unsupported model '{model}' ({e})") from e

    def prompt(self, blocks, timeout):
        try:
            return self.conn.request("session/prompt", {"sessionId": self.session_id, "prompt": blocks}, timeout)
        except AcpError as e:
            if e.code == "timeout":
                self.conn.notify("session/cancel", {"sessionId": self.session_id})
            raise


def _plain(agent, e):
    """An ACP / process error -> an LLMError in words ``vstudio.llm.failure_code`` understands."""
    from . import llm
    name, spec = label(agent), AGENTS[agent]
    text = str(e)
    login = " ".join([spec["exe"][0], *spec["login"]]) if spec["login"] else spec["exe"][0]
    if getattr(e, "code", None) == AUTH_REQUIRED or AUTH_WORDS.search(text):
        return llm.LLMError(f"{name} is not logged in: run `{login}` in a terminal and sign in ({text[:160]})")
    if REGION_WORDS.search(text):
        return llm.LLMError(f"{name} is not available in your region: {text[:200]}")
    if getattr(e, "code", None) == "timeout":
        m = re.search(r"after (\d+) s", text)
        return llm.LLMError(f"{name} timed out after {m.group(1) if m else '?'} s")
    if re.search(r"rate.?limit|\b429\b|quota|overloaded", text, re.I):
        return llm.TransientError(f"{name}: {text[:300]}")
    return llm.LLMError(f"{name} (ACP) failed: {text[:300]}")


# ------------------------------------------------------------------ public
def _image_blocks(paths):
    out = []
    for p in paths or []:
        ext = os.path.splitext(p)[1].lower()
        mt = {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
        with open(p, "rb") as f:
            out.append({"type": "image", "mimeType": mt, "data": base64.b64encode(f.read()).decode()})
    return out


def run(agent, system, prompt, model=None, timeout=600.0, images=(), opts=None, on_event=None):
    """One prompt in a fresh session -> {text, usage {input, output}, model, stop_reason, tool_asks}. ``on_event``
    (kind, text, data) hears thinking / tool / say as they stream (the desk's live pane). Raises vstudio.llm.LLMError."""
    from . import llm
    t0 = time.time()
    deadline = t0 + float(timeout or 600)
    parts, thought = [], []

    def update(u):
        kind = u.get("sessionUpdate")
        c = u.get("content")
        if kind == "agent_message_chunk" and isinstance(c, dict) and c.get("type") == "text":
            if thought and on_event:
                on_event("thinking", "".join(thought), None)
                thought.clear()
            parts.append(str(c.get("text") or ""))
        elif kind == "agent_thought_chunk" and isinstance(c, dict) and c.get("type") == "text":
            thought.append(str(c.get("text") or ""))
        elif kind == "tool_call" and on_event:
            on_event("tool", str(u.get("title") or u.get("kind") or "tool"), dict(kind=u.get("kind")))
    try:
        with Session(agent, opts, timeout=min(90.0, float(timeout or 600)), on_update=update) as s:
            s.use_model(model)
            caps = ((s.init or {}).get("agentCapabilities") or {}).get("promptCapabilities") or {}
            text = f"{system}\n\n---\n\n{prompt}" if system else prompt
            blocks = [{"type": "text", "text": text}]
            imgs = list(images or [])
            if imgs and caps.get("image"):
                blocks += _image_blocks(imgs)
            elif imgs:
                blocks[0]["text"] += "\n\n(Pictures of the footage were attached but this agent cannot take images.)"
            left = max(5.0, deadline - time.time())
            try:
                res = s.prompt(blocks, left)
            except AcpError as e:
                if e.code == "timeout":
                    raise llm.LLMError(f"{label(agent)} timed out after {round(float(timeout or 600))} s") from e
                raise _plain(agent, e) from e
            used = model or s.models()[1]
            asks = s.conn.permission_asks if s.conn else 0
    except AcpError as e:
        raise _plain(agent, e) from e
    if thought and on_event:
        on_event("thinking", "".join(thought), None)
    stop = (res or {}).get("stopReason")
    if stop == "refusal":
        raise llm.LLMError(f"{label(agent)}: the model declined the request (stop_reason refusal)")
    out = "".join(parts)
    if not out.strip() and stop not in (None, "end_turn"):
        raise llm.LLMError(f"{label(agent)} ended without an answer (stop_reason {stop})")
    u = (res or {}).get("usage") or ((res or {}).get("_meta") or {}).get("usage") or {}
    usage = dict(input=int(u.get("inputTokens", u.get("input_tokens", 0)) or 0),
                 output=int(u.get("outputTokens", u.get("output_tokens", 0)) or 0))
    if on_event and out.strip():
        on_event("say", out, None)
    return dict(text=out, usage=usage, model=used or f"{agent}-default", stop_reason=stop, tool_asks=asks,
                seconds=round(time.time() - t0, 1))


UPDATE_WORDS = re.compile(r"did not start in ACP mode|unknown (flag|option|command|argument)|unrecognized (option|argument)"
                          r"|no such (option|command)", re.I)


def issue(state, detail=None):
    """What stands between an installed agent and using it here, in one word: sign-in | update | region | timeout |
    error; None when it works (or is simply not installed). The desk shows it as one calm line with its action."""
    if state in (None, "logged-in", "installed", "not-installed", "ready"):
        return None
    if state in ("not-logged-in", "expired"):
        return "sign-in"
    if state in ("region-blocked", "region"):
        return "region"
    if state == "timeout":
        return "timeout"
    return "update" if UPDATE_WORDS.search(detail or "") else "error"


def probe(agent, timeout=30.0, opts=None):
    """Is the agent installed and signed in, and which models does it offer? A session is opened and closed (no
    prompt: nothing is spent). -> {agent, state, installed, exe, models, current_model, agent_info, auth_methods,
    detail}; state: logged-in | not-logged-in | not-installed | region-blocked | timeout | error."""
    from . import llm
    exe = find(agent, opts)
    out = dict(agent=agent, state="not-installed", installed=bool(exe), exe=exe, models=[], current_model=None,
               agent_info=None, auth_methods=[], detail=None)
    if not exe:
        return out
    try:
        with Session(agent, opts, timeout=timeout) as s:
            ms, cur, _ = s.models()
            out.update(state="logged-in", models=ms, current_model=cur, agent_info=(s.init or {}).get("agentInfo"),
                       auth_methods=[m.get("id") for m in (s.init or {}).get("authMethods") or []
                                     if isinstance(m, dict)])
    except llm.LLMError as e:
        code = llm.failure_code(e)
        out.update(state={"not-logged-in": "not-logged-in", "auth-expired": "not-logged-in",
                          "region-blocked": "region-blocked", "timeout": "timeout",
                          "not-installed": "error"}.get(code, "error"), detail=str(e)[:300])
    return out
