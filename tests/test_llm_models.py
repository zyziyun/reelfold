"""Model choice per provider (vstudio.llm_models + vstudio.llm): the model lists, her words -> a model ("5.5" -> Opus
5.5, "sonnet" -> the newest Sonnet), ``--model`` reaching the CLIs from the desk's routes file (and the fallback's own
model), the model that really answered, and a Codex model the login cannot use said plainly with the fix."""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
from vstudio import llm, llm_models  # noqa: E402

CATALOG = {"models": [
    {"slug": "gpt-reserve", "display_name": "GPT-Reserve", "visibility": "hide", "priority": 4},
    {"slug": "gpt-5.6-luna", "display_name": "GPT-5.6-Luna", "visibility": "list", "priority": 9},
    {"slug": "gpt-6-luna", "display_name": "GPT-6-Luna", "visibility": "list", "priority": 4,
     "description": "Fast and affordable model for easier tasks."},
    {"slug": "gpt-5.6-terra", "display_name": "GPT-5.6-Terra", "visibility": "list", "priority": 8},
]}
CHATGPT_REJECT = ('{"type":"error","status":400,"error":{"type":"invalid_request_error","message":"The '
                  "'gpt-6-astra' model is not supported when using Codex with a ChatGPT account.\"}}")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for k in list(os.environ):
        if k.startswith("VSTUDIO_LLM_") or k.endswith("_API_KEY"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "_persona_llm", lambda: {})
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setenv("VSTUDIO_CODEX_CONFIG", str(tmp_path / "none.toml"))


CLAUDE = [dict(m) for m in llm_models.CLAUDE_MODELS]


@pytest.mark.parametrize("words,want", [
    ("5.5", "claude-opus-5-5"), ("opus 5.5", "claude-opus-5-5"), ("Opus 5.5", "claude-opus-5-5"),
    ("opus-5-5", "claude-opus-5-5"), ("claude-opus-5-5", "claude-opus-5-5"), ("opus", "claude-opus-5-5"),
    ("sonnet", "claude-sonnet-5-5"), ("son", "claude-sonnet-5-5"), ("Sonnet 5.5", "claude-sonnet-5-5"),
    ("haiku", "claude-haiku-5-5"), ("haiku 4.5", "claude-haiku-4-5"), ("fable", "claude-fable-5-1"),
    ("5.1", "claude-fable-5-1"), ("opus 5", "claude-opus-5"),
])
def test_resolve_claude_words(words, want):
    assert llm_models.resolve(words, CLAUDE)["id"] == want


@pytest.mark.parametrize("words", ["4.7", "gpt", "opus 9", ""])
def test_resolve_nothing(words):
    assert llm_models.resolve(words, CLAUDE) is None


def test_resolve_default_and_codex_words():
    assert llm_models.resolve("default", CLAUDE) == dict(id=None, label="default")
    listed, slugs = llm_models.parse_codex_catalog(json.dumps(CATALOG))
    assert [m["id"] for m in listed] == ["gpt-6-luna", "gpt-5.6-terra", "gpt-5.6-luna"]     # priority, hidden out
    assert "gpt-reserve" in slugs
    assert llm_models.resolve("luna", listed)["id"] == "gpt-6-luna"          # the newest Luna
    assert llm_models.resolve("5.6 luna", listed)["id"] == "gpt-5.6-luna"
    assert llm_models.resolve("6", listed)["id"] == "gpt-6-luna"


def _codex_cli(monkeypatch, tmp_path, cfg_model, catalog=CATALOG, reject=None):
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'service_tier = "default"\nmodel = "{cfg_model}"\n\n[plugins."x"]\nmodel = "other"\n')
    monkeypatch.setenv("VSTUDIO_CODEX_CONFIG", str(cfg))
    monkeypatch.setattr(llm.shutil, "which", lambda n: f"/opt/bin/{n}" if n in ("codex", "claude") else None)
    calls = []

    def run(cmd, input=None, capture_output=None, text=None, cwd=None, timeout=None, env=None, **kw):
        calls.append(cmd)
        if cmd[1:3] == ["debug", "models"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(catalog), "")
        model = cmd[cmd.index("--model") + 1] if "--model" in cmd else cfg_model
        if reject and model in reject:
            ev = [dict(type="thread.started"), dict(type="turn.started"), dict(type="error", message=CHATGPT_REJECT),
                  dict(type="turn.failed", error=dict(message=CHATGPT_REJECT))]
            return subprocess.CompletedProcess(cmd, 1, "\n".join(json.dumps(e) for e in ev), "")
        with open(cmd[cmd.index("--output-last-message") + 1], "w") as f:
            f.write('{"ok": true}')
        ev = [dict(type="turn.completed", usage=dict(input_tokens=5, output_tokens=2))]
        return subprocess.CompletedProcess(cmd, 0, "\n".join(json.dumps(e) for e in ev), "")
    monkeypatch.setattr(llm.subprocess, "run", run)
    monkeypatch.setattr(llm_models.subprocess, "run", run)
    return calls


def test_codex_models_flags_her_config_model(monkeypatch, tmp_path):
    _codex_cli(monkeypatch, tmp_path, "gpt-6-astra")
    assert llm_models.codex_config_model() == "gpt-6-astra"                 # the top-level key, not the plugin's
    r = llm_models.models("codex")
    assert r["source"] == "cli" and r["cli_default"] == "gpt-6-astra"
    assert [m["id"] for m in r["models"]][:1] == ["gpt-6-luna"]
    p = r["problem"]
    assert p["code"] == "codex-model-unsupported" and p["params"] == dict(model="gpt-6-astra", suggest="gpt-6-luna")
    assert "gpt-6-astra" in p["message"] and "config.toml" in p["message"] and "gpt-6-luna" in p["message"]


def test_codex_models_ok_config(monkeypatch, tmp_path):
    _codex_cli(monkeypatch, tmp_path, "gpt-6-luna")
    assert llm_models.models("codex")["problem"] is None
    # no probe: no CLI call, no catalog
    assert llm_models.models("codex", probe=False)["models"] == []


def test_codex_invalid_model_message(monkeypatch, tmp_path):
    _codex_cli(monkeypatch, tmp_path, "gpt-6-astra", reject={"gpt-6-astra"})
    with pytest.raises(llm.LLMError) as e:
        llm.complete("copy", "s", "p", provider="codex", fallback=False)
    msg = str(e.value)
    assert "gpt-6-astra" in msg and "ChatGPT login" in msg and "Settings > AI" in msg and "config.toml" in msg
    assert llm.failure_code(msg) == "model-unsupported"
    assert llm.error_info(e.value)["code"] == "model-unsupported"
    # the model she picked for Codex (the routes file) goes in as --model and works
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps({"default": {"provider": "codex", "model": "gpt-6-luna"}}))
    monkeypatch.setenv("VSTUDIO_LLM_ROUTES_FILE", str(routes))
    r = llm.complete("copy", "s", "p", schema=True)
    assert r["provider"] == "codex" and r["model"] == "gpt-6-luna" and r["json"] == {"ok": True}


def test_claude_code_gets_model_from_routes_file_and_fallback_model(monkeypatch, tmp_path):
    monkeypatch.setattr(llm.shutil, "which", lambda n: f"/opt/bin/{n}" if n in ("codex", "claude") else None)
    seen = []

    def run(cmd, input=None, capture_output=None, text=None, cwd=None, timeout=None, env=None, **kw):
        seen.append(cmd)
        if os.path.basename(cmd[0]) == "claude":
            m = cmd[cmd.index("--model") + 1] if "--model" in cmd else None
            if m == "claude-fable-5-1":
                d = dict(type="result", is_error=True, result="usage limit reached (429)")
                return subprocess.CompletedProcess(cmd, 1, json.dumps(d), "")
            d = dict(type="result", is_error=False, result='{"ok": 1}', usage=dict(input_tokens=3, output_tokens=1),
                     modelUsage={"claude-haiku-4-5": {"outputTokens": 1}, (m or "claude-opus-4-7"): {"outputTokens": 9}})
            return subprocess.CompletedProcess(cmd, 0, json.dumps(d), "")
        with open(cmd[cmd.index("--output-last-message") + 1], "w") as f:
            f.write('{"ok": 2}')
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(llm.subprocess, "run", run)
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps({"default": {"provider": "claude-code", "model": "claude-opus-5-5",
                                              "fallback": [{"provider": "codex", "model": "gpt-6-luna"}]},
                                  "tasks": {"output_edit": {"provider": "claude-code", "model": "claude-fable-5-1",
                                                            "fallback": [{"provider": "codex",
                                                                          "model": "gpt-6-luna"}]}}}))
    monkeypatch.setenv("VSTUDIO_LLM_ROUTES_FILE", str(routes))
    r = llm.complete("copy", "s", "p", schema=True)
    assert seen[-1][seen[-1].index("--model") + 1] == "claude-opus-5-5"
    assert r["model"] == "claude-opus-5-5" and r["provider"] == "claude-code"
    # the edit task's own model fails (rate limit): the fallback answers with ITS model
    r = llm.complete("output_edit", "s", "p", schema=True, retries=0)
    assert r["provider"] == "codex" and r["model"] == "gpt-6-luna" and seen[-1][seen[-1].index("--model") + 1] == \
        "gpt-6-luna"
    # no model chosen ("CLI default"): no --model, the reply names the model that wrote most of it
    routes.write_text(json.dumps({"default": {"provider": "claude-code"}}))
    r = llm.complete("copy", "s", "p", schema=True)
    assert "--model" not in seen[-1] and r["model"] == "claude-opus-4-7"


def test_claude_model_used():
    assert llm._claude_model_used("opus", {"claude-opus-5-5": {}}) == "claude-opus-5-5"
    assert llm._claude_model_used("claude-sonnet-5-5", {}) == "claude-sonnet-5-5"
    assert llm._claude_model_used(None, {}) == "claude-code-default"


def test_models_cli_json(monkeypatch, tmp_path, capsys):
    _codex_cli(monkeypatch, tmp_path, "gpt-6-astra")
    assert llm.main(["models", "--provider", "claude-code", "--provider", "codex", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    rows = {r["provider"]: r for r in doc["providers"]}
    assert rows["claude-code"]["models"][0]["id"] == "claude-opus-5-5"
    assert {m["id"] for m in rows["claude-code"]["models"]} >= {"claude-sonnet-5-5", "claude-haiku-5-5",
                                                                "claude-fable-5-1"}
    assert rows["codex"]["problem"]["code"] == "codex-model-unsupported"
    assert llm.main(["models", "--provider", "claude-code", "--resolve", "5.5"]) == 0
    assert json.loads(capsys.readouterr().out)["model"]["id"] == "claude-opus-5-5"
    assert llm.main(["models", "--provider", "claude-code", "--resolve", "4.7"]) == 1


def test_api_lists_offline_and_local(monkeypatch):
    r = llm_models.models("openai", probe=False)
    assert r["source"] == "list" and "gpt-4.1-mini" in [m["id"] for m in r["models"]]
    assert [m["id"] for m in llm_models.models("deepseek", probe=False)["models"]][0] == "deepseek-chat"
    assert llm_models.models("anthropic", probe=False)["models"][0]["id"] == "claude-opus-5-5"
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setattr(llm_models, "_get_json", lambda url, h, t: {"data": [
        {"id": "gpt-4.1"}, {"id": "text-embedding-3-small"}, {"id": "gpt-4o-audio-preview"}, {"id": "o4-mini"}]})
    r = llm_models.models("openai")
    assert r["source"] == "api" and [m["id"] for m in r["models"]] == ["gpt-4.1", "o4-mini"]
