"""Which models each AI provider can use here, and her words ("5.5", "sonnet", "opus 5.5") -> one model id.

    python -m vstudio.llm models [--provider codex ...] [--json] [--no-probe]

    from vstudio import llm_models
    llm_models.models("codex")       # {provider, source, models: [{id, label, ...}], cli_default, problem}
    llm_models.resolve("5.5", llm_models.models("claude-code")["models"])   # -> the Opus 5.5 entry

Sources per provider:
  claude-code  the Claude Code CLI has no "list models" command: a maintained list of the current Claude models
               (``CLAUDE_MODELS``, passed as ``claude --model <id>``); "CLI default" = no ``--model``
  codex        ``codex debug models``: the catalog of the model ids THIS Codex login can use (a ChatGPT login cannot
               use every API model); the model Codex's own config.toml picks is checked against it - not in it
               (her ``gpt-6-astra`` on a ChatGPT login) -> ``problem`` code ``codex-model-unsupported`` with a fix
  anthropic    the same maintained Claude list (+ the API's own ``/v1/models`` when a key is set and probe=True)
  openai / openrouter / deepseek / qwen / kimi / glm / doubao
               the provider's ``/models`` when its key is set (probe=True, at the endpoint of the chosen region),
               else a short maintained list / the preset's default
  ACP agents   (gemini-cli, qwen-code, kimi-cli, codebuddy, opencode, ...) the models the agent itself offers this
               sign-in: an ACP session is opened and closed (``vstudio.acp.probe``, no prompt); without the probe a
               short maintained list where there is one (else only "the agent's default")
  ollama / lmstudio / vllm / llamacpp
               what the local server lists (``/v1/models``)
Nothing here costs anything: listing models is free on every provider.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request

# The current Claude models, newest first within a family. ``aliases`` are what the CLI also accepts / what she types.
CLAUDE_MODELS = (
    dict(id="claude-opus-5-5", label="Opus 5.5", family="opus", version="5.5", aliases=["opus"]),
    dict(id="claude-sonnet-5-5", label="Sonnet 5.5", family="sonnet", version="5.5", aliases=["sonnet"]),
    dict(id="claude-haiku-5-5", label="Haiku 5.5", family="haiku", version="5.5", aliases=["haiku"]),
    dict(id="claude-fable-5-1", label="Fable 5.1", family="fable", version="5.1", aliases=["fable"]),
    dict(id="claude-opus-5", label="Opus 5", family="opus", version="5", older=True),
    dict(id="claude-haiku-4-5", label="Haiku 4.5", family="haiku", version="4.5", older=True),
)
# a bare version ("5.5") picks this family first: the most capable general model of that version
FAMILY_RANK = ("opus", "sonnet", "haiku", "fable")

OPENAI_MODELS = ("gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini")
PRESET_MODELS = {
    "deepseek": ("deepseek-chat", "deepseek-reasoner"),
    "qwen": ("qwen-plus", "qwen3-max", "qwen-flash", "qwen-turbo", "qwen3-coder-plus"),
    "kimi": ("kimi-k2-0905-preview", "kimi-k2-turbo-preview", "kimi-k2-thinking"),
    "glm": ("glm-4.6", "glm-4.5", "glm-4.5-air", "glm-4.5-flash"),
    "doubao": ("doubao-seed-1-6-250615", "doubao-seed-1-6-flash-250828", "doubao-seed-1-6-thinking-250715",
               "doubao-1-5-pro-32k-250115"),
    "openrouter": ("openai/gpt-4.1-mini",),
}
# ACP agents before their session answers (the agent's own list replaces it)
AGENT_MODELS = {"gemini-cli": ("gemini-2.5-pro", "gemini-2.5-flash")}

CODEX_CONFIG = "~/.codex/config.toml"


def _entry(mid, label=None, **kw):
    d = dict(id=mid, label=label or mid)
    d.update({k: v for k, v in kw.items() if v not in (None, "", [])})
    return d


def _problem(code, message, message_zh, **params):
    return dict(code=code, params=params, message=message, message_zh=message_zh)


# ------------------------------------------------------------------ codex
def codex_config_model(path=None):
    """The ``model = "..."`` Codex's own config.toml sets at its top level (None when unset / unreadable)."""
    p = os.path.expanduser(path or os.environ.get("VSTUDIO_CODEX_CONFIG") or CODEX_CONFIG)
    try:
        with open(p, encoding="utf-8") as f:
            for ln in f:
                s = ln.strip()
                if s.startswith("["):                        # a table: top-level keys are over
                    break
                m = re.match(r'model\s*=\s*["\']([^"\']+)["\']', s)
                if m:
                    return m.group(1)
    except OSError:
        return None
    return None


def parse_codex_catalog(text):
    """``codex debug models`` JSON -> (listed [{id, label, note}], every slug) in Codex's own priority order."""
    try:
        d = json.loads(text or "")
    except ValueError:
        return [], set()
    rows = d.get("models") if isinstance(d, dict) else d
    if not isinstance(rows, list):
        return [], set()
    rows = [r for r in rows if isinstance(r, dict) and r.get("slug")]
    rows.sort(key=lambda r: (r.get("priority") if isinstance(r.get("priority"), (int, float)) else 999))
    listed = [_entry(r["slug"], r.get("display_name") or r["slug"], note=r.get("description"))
              for r in rows if r.get("visibility", "list") == "list"]
    return listed, {r["slug"] for r in rows}


def codex_catalog(timeout=20):
    """(listed, slugs) of this Codex login, or (None, None) when the CLI is missing / has no catalog command."""
    from . import llm
    exe = llm.find_cli("codex")
    if not exe:
        return None, None
    try:
        r = subprocess.run([*llm.cli_argv(exe), "debug", "models"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=llm._cli_env(llm.CODEX_STRIP_ENV, {}))
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if r.returncode:
        return None, None
    listed, slugs = parse_codex_catalog(r.stdout)
    return (listed, slugs) if slugs else (None, None)


def codex_unsupported(model, catalog=None):
    """The problem record for a Codex model this login cannot use (her config's gpt-6-astra on a ChatGPT login)."""
    good = next((m["id"] for m in catalog or []), None)
    fix = f" (for example {good})" if good else ""
    fix_zh = f"（比如 {good}）" if good else ""
    return _problem("codex-model-unsupported",
                    f"Codex is set to use “{model}”, which your Codex login can’t use. Pick a Codex model here"
                    f"{fix}, or change `model` in ~/.codex/config.toml.",
                    f"Codex 设置的模型是「{model}」，你现在的 Codex 登录用不了。请在这里选一个 Codex 模型{fix_zh}，"
                    f"或者改掉 ~/.codex/config.toml 里的 model。",
                    model=model, suggest=good)


# ------------------------------------------------------------------ API / local listings
def _get_json(url, headers, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "vstudio", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(2_000_000) or b"{}")


def _live_ids(provider, timeout=4.0):
    """The model ids a hosted API lists for the key in the environment, or None (no key / no answer)."""
    from . import llm
    try:
        if provider == "anthropic":
            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                return None
            d = _get_json("https://api.anthropic.com/v1/models?limit=100",
                          {"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout)
        else:
            base, key_env, _, _ = llm.compatible_target(provider, {}) if provider != "openai" else \
                ("https://api.openai.com/v1", "OPENAI_API_KEY", None, "api")
            key = os.environ.get(key_env or "")
            if not base or not key:
                return None
            d = _get_json(base.rstrip("/") + "/models", {"Authorization": f"Bearer {key}"}, timeout)
    except Exception:  # noqa: BLE001  (no network, a bad key: the maintained list stands)
        return None
    ids = [m.get("id") for m in (d.get("data") or []) if isinstance(m, dict) and m.get("id")]
    if provider == "openai":                                 # chat models only (not embeddings / audio / images)
        ids = [i for i in ids if re.match(r"(gpt-|o\d|chatgpt-)", i) and not re.search(
            r"audio|realtime|transcribe|tts|image|embedding|search|instruct", i)]
    return ids or None


# ------------------------------------------------------------------ public
def models(provider, probe=True):
    """{provider, source, models: [{id, label, ...}], cli_default, problem} for one provider (see module doc)."""
    from . import llm
    p = llm.canonical(provider) or "none"
    out = dict(provider=p, source="list", models=[], cli_default=None, problem=None)
    if p == "none":
        return out
    if p in ("claude-code", "anthropic"):
        out["models"] = [dict(m) for m in CLAUDE_MODELS]
        if p == "anthropic" and probe:
            ids = _live_ids(p)
            if ids:
                known = {m["id"] for m in CLAUDE_MODELS}
                out["models"] += [_entry(i) for i in ids if i not in known]
                out["source"] = "api"
        return out
    if p == "codex":
        cfg = codex_config_model()
        out["cli_default"] = cfg
        listed, slugs = codex_catalog() if probe else (None, None)
        if listed is not None:
            out["models"], out["source"] = listed, "cli"
            if cfg and cfg not in slugs:
                out["problem"] = codex_unsupported(cfg, listed)
        return out
    if p == "openai":
        ids = _live_ids(p) if probe else None
        out["models"] = [_entry(i) for i in (ids or OPENAI_MODELS)]
        out["source"] = "api" if ids else "list"
        return out
    if p in llm.acp.AGENTS:
        out["models"] = [_entry(i) for i in AGENT_MODELS.get(p, ())]
        if probe:
            r = llm.acp.probe(p)
            if r["models"]:
                out["models"], out["source"] = [dict(m) for m in r["models"]], "agent"
            out["cli_default"] = r.get("current_model")
            kind = llm.acp.issue(r["state"], r.get("detail"))
            if kind:
                # a calm line + what to do (the desk shows it beside the agent, the raw text only as a tooltip)
                name = llm.acp.label(p)
                en, zh = {"sign-in": (f"Sign in to {name} to use it here", f"登录 {name} 后就能在这里用"),
                          "update": (f"Update {name} to use it here", f"更新 {name} 后就能在这里用"),
                          "region": (f"{name} is not available in your region", f"你所在的地区用不了 {name}"),
                          "timeout": (f"{name} did not answer: check again in a moment", f"{name} 没有响应，稍后再检查一次"),
                          }.get(kind, (f"{name} could not start here: try it in a terminal",
                                       f"{name} 在这里启动不了，先在终端里试试"))
                out["problem"] = _problem(f"agent-{kind}", en, zh, state=r["state"], issue=kind,
                                          detail=(r.get("detail") or "")[:300] or None)
        return out
    preset = llm.PRESETS.get(p)
    if preset and preset["kind"] == "api":
        ids = _live_ids(p) if probe else None
        out["models"] = [_entry(i) for i in (ids or PRESET_MODELS.get(p) or [preset["model"]])]
        out["source"] = "api" if ids else "list"
        return out
    c = llm.check(p, probe=probe)                              # local servers: what they list
    out["models"] = [_entry(i) for i in c.get("models") or []]
    out["source"] = "server"
    return out


def all_models(providers=None, probe=True):
    from . import llm
    from concurrent.futures import ThreadPoolExecutor
    names = providers or [x for x in llm.names() if x not in ("openai-compatible", "none", "gemini", "llamacpp")]
    # side by side: each installed agent opens a session (seconds), Codex reads its catalog, APIs list their models
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(names)))) as ex:
        return list(ex.map(lambda p: models(p, probe=probe), names))


# ------------------------------------------------------------------ her words -> a model
def _tokens(s):
    """"Claude Opus 5.5" / "claude-opus-5-5" / "opus5.5" -> ["claude", "opus", "5.5"] (digit runs joined by - . _
    become one version token)."""
    s = str(s or "").lower()
    toks = re.findall(r"[a-z]+|\d+(?:[.\-_]\d+)*", s)
    return [re.sub(r"[\-_]", ".", t) if t[0].isdigit() else t for t in toks]


def _norm(s):
    """Case, spaces and punctuation out ("Opus 5.5" == "opus-5-5" == "opus55"); other scripts kept ("默认")."""
    return re.sub(r"[\s\-_.:/()'\"]", "", str(s or "").lower())


def _version_key(v):
    try:
        return tuple(int(x) for x in str(v or "").split("."))
    except ValueError:
        return ()


DEFAULT_WORDS = {"default", "cli-default", "auto", "reset", "默认", "défaut", "par défaut"}


def resolve(query, catalog):
    """Her words -> the best catalog entry, None (nothing matches), or {"id": None, ...} for "default".

    Exact id / alias / label first ("sonnet" -> the newest Sonnet, "claude-opus-5-5"); then every word of the query
    must be in the model's id / label / family (prefixes count: "son"), a version must be equal ("5.5" matches 5.5,
    never 5.1); ties go to the family order (opus, sonnet, haiku, fable), then the newest version, then the list."""
    q = str(query or "").strip()
    if not q:
        return None
    if _norm(q) in {_norm(w) for w in DEFAULT_WORDS}:
        return dict(id=None, label="default")
    qn, qt = _norm(q), _tokens(q)
    best, best_key = None, None
    for i, m in enumerate(catalog or []):
        names = [m.get("id"), m.get("label"), *(m.get("aliases") or [])]
        if qn in {_norm(x) for x in names if x}:
            # an alias names the newest of its family: the first listed (the catalog is newest first)
            score = 100
        else:
            mt = set(_tokens(" ".join(str(x) for x in names if x)) + _tokens(m.get("family")))
            if m.get("version"):
                mt.add(str(m["version"]))
            ok = qt and all((t in mt) if t[0].isdigit() else any(x.startswith(t) for x in mt if not x[0].isdigit())
                            for t in qt)
            if not ok:
                continue
            score = 50
        fam = m.get("family")
        key = (score, -(FAMILY_RANK.index(fam) if fam in FAMILY_RANK else len(FAMILY_RANK)),
               0 if m.get("older") else 1, _version_key(m.get("version") or _version_of(m.get("id"))), -i)
        if best_key is None or key > best_key:
            best, best_key = m, key
    return best


def _version_of(mid):
    m = re.search(r"(\d+(?:[.\-]\d+)*)", str(mid or ""))
    return m.group(1).replace("-", ".") if m else ""


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m vstudio.llm models", description="the models each AI provider can use")
    ap.add_argument("--provider", action="append")
    ap.add_argument("--resolve", help="her words (\"5.5\", \"sonnet\") -> the model id, for --provider")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-probe", action="store_true", help="no CLI catalog / API listing (fast, offline)")
    a = ap.parse_args(argv)
    rows = all_models(a.provider, probe=not a.no_probe)
    if a.resolve:
        hit = resolve(a.resolve, rows[0]["models"] if rows else [])
        doc = dict(ok=hit is not None, query=a.resolve, provider=rows[0]["provider"] if rows else None, model=hit)
        print(json.dumps(doc, ensure_ascii=False))
        return 0 if hit is not None else 1
    if a.json:
        print(json.dumps(dict(providers=rows), ensure_ascii=False))
        return 0
    for r in rows:
        ids = ", ".join(m["id"] for m in r["models"]) or "-"
        print(f"{r['provider']:<12} ({r['source']}) {ids}" + (f"  [cli default: {r['cli_default']}]"
                                                              if r.get("cli_default") else ""))
        if r.get("problem"):
            print(f"  ! {r['problem']['message']}")
    return 0
