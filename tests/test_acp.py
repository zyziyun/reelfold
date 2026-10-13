"""ACP agents (vstudio.acp) through the router, against a stand-in agent that speaks ACP (no accounts, no network)."""
import json
import os
import stat
import sys
import time

import pytest

from vstudio import acp, llm, llm_auth, llm_models

AGENT = os.path.join(os.path.dirname(__file__), "fixtures", "fake_acp", "agent.py")
pytestmark = pytest.mark.skipif(os.name == "nt", reason="the stand-in agent is a script with a shebang")


@pytest.fixture
def agents(tmp_path, monkeypatch):
    """install(name, mode) puts the stand-in agent on PATH as ``name``; ``log()`` reads what it was sent."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    logf = tmp_path / "acp.log"
    monkeypatch.setenv("PATH", str(bin_))
    monkeypatch.setenv("FAKE_ACP_LOG", str(logf))
    monkeypatch.delenv("VSTUDIO_LLM_ROUTES_FILE", raising=False)

    class A:
        @staticmethod
        def install(name, mode="ok"):
            f = bin_ / name
            f.write_text(f"#!{sys.executable}\nimport os, runpy\nos.environ['FAKE_ACP'] = {mode!r}\n"
                         f"runpy.run_path({AGENT!r}, run_name='__main__')\n")
            f.chmod(f.stat().st_mode | stat.S_IXUSR)
            return str(f)

        @staticmethod
        def log():
            if not logf.exists():
                return []
            return [json.loads(x) for x in logf.read_text().splitlines()]
    return A


def test_prompt_through_the_router_with_her_own_login(agents, monkeypatch):
    agents.install("qwen")
    monkeypatch.setenv("OPENAI_API_KEY", "desk-key-must-not-reach-the-agent")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "desk-key-must-not-reach-the-agent")
    r = llm.complete("copy", "You write copy. Answer in JSON.", "Return the JSON.", provider="qwen-code", schema=True)
    assert r["provider"] == "qwen-code" and r["json"]["ok"] is True and r["json"]["sum"] == 4
    assert r["json"]["perm"] == "no"                       # the tool permission was refused (reject_once)
    assert r["model"] == "fake-small" and r["usage"] == {"input": 12, "output": 5} and r["cost_usd"] == 0.0
    log = agents.log()
    assert [x["method"] for x in log][:2] == ["initialize", "session/new"]
    assert all(not k.startswith(("OPENAI_", "ANTHROPIC_")) for x in log for k in x.get("keys", []))
    new = next(x for x in log if x["method"] == "session/new")
    assert "vstudio-acp-" in new["params"]["cwd"] and new["params"]["mcpServers"] == []
    init = log[0]["params"]
    assert init["clientCapabilities"]["terminal"] is False and init["clientCapabilities"]["fs"]["readTextFile"] is False
    sent = next(x for x in log if x["method"] == "session/prompt")["params"]["prompt"][0]["text"]
    assert sent.startswith("You write copy.") and "Return the JSON." in sent
    assert next(x for x in log if x["method"] == "session/new")["argv"] == ["--acp"]


def test_model_choice_both_protocol_shapes_and_unsupported(agents):
    agents.install("kimi")
    r = llm.complete("copy", "s", "JSON please", provider="kimi-cli", model="fake-big", schema=True)
    assert r["json"]["model"] == "fake-big" and r["model"] == "fake-big"
    assert any(x["method"] == "session/set_model" for x in agents.log())
    agents.install("kimi", "config")
    r = llm.complete("copy", "s", "JSON please", provider="kimi-cli", model="Fake Big", schema=True)
    assert r["json"]["model"] == "fake-big"
    assert any(x["method"] == "session/set_config_option" and x["params"]["configId"] == "model" for x in agents.log())
    with pytest.raises(llm.LLMError) as e:
        llm.complete("copy", "s", "p", provider="kimi-cli", model="gpt-9")
    assert llm.failure_code(e.value) == "model-unsupported" and "fake-small" in str(e.value)


def test_not_signed_in_region_crash_and_not_installed_are_plain(agents):
    agents.install("kimi", "auth")
    with pytest.raises(llm.LLMError) as e:
        llm.complete("copy", "s", "p", provider="kimi-cli")
    assert llm.failure_code(e.value) == "not-logged-in" and "kimi login" in str(e.value)
    agents.install("codebuddy", "region")
    with pytest.raises(llm.LLMError) as e:
        llm.complete("copy", "s", "p", provider="codebuddy")
    assert llm.failure_code(e.value) == "region-blocked"
    agents.install("iflow", "crash")
    with pytest.raises(llm.LLMError, match="something broke"):
        llm.complete("copy", "s", "p", provider="iflow", retries=0)
    with pytest.raises(llm.LLMError) as e:
        llm.complete("copy", "s", "p", provider="gemini-cli")
    assert llm.failure_code(e.value) == "not-installed"
    agents.install("copilot", "refusal")
    with pytest.raises(llm.LLMError, match="declined"):
        llm.complete("copy", "s", "p", provider="copilot")


def test_timeout_kills_the_agent_and_says_so(agents):
    agents.install("opencode", "hang")
    t0 = time.time()
    with pytest.raises(llm.LLMError) as e:
        llm.complete("copy", "s", "p", provider="opencode", timeout=3, retries=0)
    assert llm.failure_code(e.value) == "timeout" and time.time() - t0 < 15


def test_older_versions_and_existing_sign_in(agents):
    agents.install("gemini", "old-args")                 # --acp unknown: --experimental-acp is tried
    r = llm.complete("copy", "s", "hi", provider="gemini-cli")
    assert r["text"] == "hello from fake-small"
    assert next(x for x in agents.log() if x["method"] == "session/new")["argv"] == ["--experimental-acp"]
    agents.install("cursor-agent", "cursor-auth")        # Cursor: its own sign-in taken up through `authenticate`
    assert llm.complete("copy", "s", "hi", provider="cursor")["text"] == "hello from fake-small"
    assert any(x["method"] == "authenticate" for x in agents.log())


def test_images_go_in_as_image_blocks_and_the_live_pane_hears_it(agents, tmp_path, monkeypatch):
    agents.install("qwen")
    img = tmp_path / "sheet.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0fake")
    live = tmp_path / "live.jsonl"
    monkeypatch.setenv("VSTUDIO_AGENT_LOG", str(live))
    r = llm.complete("intake", "s", "JSON please", provider="qwen-code", schema=True, images=[str(img)])
    assert r["json"]["images"] == 1
    kinds = [json.loads(x)["kind"] for x in live.read_text().splitlines()]
    assert {"turn", "thinking", "tool", "say", "result"} <= set(kinds)


def test_fallback_claude_code_then_qwen_code_then_deepseek(agents, tmp_path, monkeypatch):
    agents.install("qwen", "auth")                       # Claude Code is not installed, Qwen Code is signed out
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps({"default": {"provider": "claude-code", "fallback": ["qwen-code", "deepseek"]}}))
    monkeypatch.setenv("VSTUDIO_LLM_ROUTES_FILE", str(routes))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    seen = {}

    def chat(system, prompt, model, schema, max_tokens, timeout, opts, base_url=None, api_key=None, **kw):
        seen.update(base_url=base_url, model=model)
        return '{"ok": true}', dict(input=3, output=2), model
    monkeypatch.setattr(llm, "_openai_chat", chat)
    r = llm.complete("copy", "s", "p", schema=True)
    assert r["provider"] == "deepseek" and r["json"] == {"ok": True}
    assert r["fallback"]["tried"] == ["claude-code", "qwen-code"]
    assert [a["code"] for a in r["failed_attempts"]] == ["not-installed", "not-logged-in"]
    assert seen["base_url"].startswith("https://api.deepseek.com")


def test_probe_status_models_and_login_command(agents):
    agents.install("kimi")
    agents.install("qwen", "auth")
    assert acp.probe("kimi-cli")["state"] == "logged-in"
    assert acp.probe("qwen-code")["state"] == "not-logged-in"
    assert acp.probe("gemini-cli")["state"] == "not-installed"
    rows = {r["provider"]: r for r in llm_auth.status(["kimi-cli", "qwen-code", "gemini-cli", "codebuddy"])}
    assert rows["kimi-cli"]["state"] == "logged-in" and rows["kimi-cli"]["models"] == ["fake-small", "fake-big"]
    assert rows["kimi-cli"]["china"] == "yes" and rows["kimi-cli"]["acp"] is True
    assert rows["qwen-code"]["state"] == "not-logged-in" and rows["qwen-code"]["issue"] == "sign-in"
    assert rows["qwen-code"]["message"]["message"] == "Sign in to Qwen Code to use it here"
    assert rows["gemini-cli"]["state"] == "not-installed" and rows["gemini-cli"]["install"]["url"]
    quick = llm_auth.status(["kimi-cli"], probe=False)[0]
    assert quick["state"] == "installed" and quick["ready"] is True
    m = llm_models.models("kimi-cli")
    assert m["source"] == "agent" and [x["id"] for x in m["models"]] == ["fake-small", "fake-big"]
    assert m["cli_default"] == "fake-small" and llm_models.resolve("big", m["models"])["id"] == "fake-big"
    assert llm_models.models("gemini-cli", probe=False)["models"][0]["id"].startswith("gemini-")
    c = llm_auth.command("kimi-cli")
    assert c["ok"] and c["command"][-1] == "login" and c["display"] == "kimi login" and "OPENAI_*" in c["env_unset"]
    c = llm_auth.command("qwen-code")
    assert c["ok"] and c["display"] == "qwen" and c["note"]
    assert llm_auth.command("gemini-cli")["ok"] is False


def test_sandboxed_build_has_no_agents(agents, monkeypatch):
    agents.install("kimi")
    monkeypatch.setenv("VSTUDIO_LLM_NO_CLI", "1")
    with pytest.raises(llm.LLMError) as e:
        llm.complete("copy", "s", "p", provider="kimi-cli")
    assert llm.failure_code(e.value) == "unavailable"
    assert llm_auth.status(["kimi-cli"])[0]["state"] == "unavailable"


def test_china_endpoints_regions_and_doubao(tmp_path, monkeypatch):
    monkeypatch.delenv("VSTUDIO_LLM_ROUTES_FILE", raising=False)
    for p in ("qwen", "kimi", "glm", "doubao"):
        monkeypatch.delenv(f"VSTUDIO_{p.upper()}_REGION", raising=False)
    assert llm.compatible_target("qwen", {})[0] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert llm.compatible_target("qwen", {"region": "intl"})[0].startswith("https://dashscope-intl.")
    monkeypatch.setenv("VSTUDIO_KIMI_REGION", "international")
    assert llm.compatible_target("kimi", {})[0] == "https://api.moonshot.ai/v1"
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps({"default": {"provider": "glm"}, "regions": {"glm": "intl", "doubao": "intl"}}))
    monkeypatch.setenv("VSTUDIO_LLM_ROUTES_FILE", str(routes))
    assert llm.compatible_target("glm", {})[0] == "https://api.z.ai/api/paas/v4"
    assert "bytepluses" in llm.compatible_target("doubao", {})[0]
    assert llm.compatible_target("doubao", {"region": "cn"})[0] == "https://ark.cn-beijing.volces.com/api/v3"
    assert llm.canonical("volcengine") == "doubao" and llm.canonical("ark") == "doubao"
    assert llm.compatible_target("doubao", {})[1] == "ARK_API_KEY"
    monkeypatch.setenv("ARK_API_KEY", "ark-test")
    row = llm_auth.status(["doubao"])[0]
    assert row["state"] == "configured" and row["region"] == "intl" and "byteplus" in row["install"]["url"]
    assert "doubao-seed-1-6-250615" in [m["id"] for m in llm_models.models("doubao", probe=False)["models"]]


def test_every_agent_is_named_and_ordered():
    assert set(acp.IDS) <= set(llm.names()) and llm.canonical("cursor") == "cursor-agent"
    assert all(llm.canonical(a) == a for a in acp.IDS)
    china = [a for a in acp.IDS if acp.AGENTS[a]["china"] == "yes" and acp.AGENTS[a]["maker"] != "SST"]
    assert acp.IDS[-len(china):] == tuple(china)          # international first, the agents made in China after
    assert llm.failure_code("Gemini CLI is not available in your region") == "region-blocked"
    assert llm.failure_code("unsupported_country_region_territory") == "region-blocked"
    # Gemini CLI set to an API key it does not have: not signed in, in plain words
    e = acp._plain("gemini-cli", acp.AcpError("Gemini API key is missing or not configured.", code=-32603))
    assert llm.failure_code(e) == "not-logged-in" and "`gemini`" in str(e)


def test_issue_is_one_calm_word():
    # what the desk shows beside an installed agent instead of its raw error
    assert acp.issue("logged-in") is None and acp.issue("not-installed") is None and acp.issue("installed") is None
    assert acp.issue("not-logged-in", "Gemini API key is missing") == "sign-in"
    assert acp.issue("error", "GitHub Copilot CLI did not start in ACP mode: ✘ unknown flag: --acp") == "update"
    assert acp.issue("error", "error: unknown option '--acp'") == "update"
    assert acp.issue("region-blocked", "User location is not supported") == "region"
    assert acp.issue("timeout") == "timeout"
    assert acp.issue("error", "segfault") == "error"
