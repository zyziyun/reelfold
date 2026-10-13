"""Per-project AI (vstudio.llm.project_ai): step override > project ai > task route > default; a switch mid-run
applies from the next AI step; a run saving project.yaml keeps the AI the app switched meanwhile."""
import json
import os

import pytest
import yaml

from vstudio import llm


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for k in list(os.environ):
        if k.startswith("VSTUDIO_LLM_") or k == "VSTUDIO_PROJECT_DIR":
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "_persona_llm", lambda: {})
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps({
        "default": {"provider": "claude-code", "model": "claude-opus-5-5", "fallback": ["codex", "kimi"]},
        "tasks": {"intake": {"provider": "claude-code", "model": "claude-opus-5-5", "fallback": ["codex", "kimi"]},
                  "copy": {"provider": "deepseek"}},
        "models": {"kimi": "kimi-k2-turbo", "codex": "gpt-6"},
    }))
    monkeypatch.setenv("VSTUDIO_LLM_ROUTES_FILE", str(routes))


def _project(tmp_path, ai=None):
    d = tmp_path / "proj"
    d.mkdir(exist_ok=True)
    data = {"version": 1, "name": "p", "recipe": "talkinghead", "items": [], "answers": {}}
    if ai:
        data["ai"] = ai
    (d / "project.yaml").write_text(yaml.safe_dump(data))
    return d


def test_no_project_ai_follows_task_routes():
    assert llm.route("copy").provider == "deepseek"
    assert llm.route("intake").provider == "claude-code"


def test_project_ai_beats_task_route_and_default(tmp_path, monkeypatch):
    d = _project(tmp_path, {"provider": "kimi", "model": "kimi-k2"})
    monkeypatch.setenv("VSTUDIO_PROJECT_DIR", str(d))
    for task in ("intake", "copy", "planner", "output_edit", "segment_plan"):
        r = llm.route(task)
        assert (r.provider, r.model, r.source) == ("kimi", "kimi-k2", "project ai")


def test_project_fallback_is_global_order_minus_itself(tmp_path, monkeypatch):
    d = _project(tmp_path, {"provider": "kimi"})
    monkeypatch.setenv("VSTUDIO_PROJECT_DIR", str(d))
    r = llm.route("copy")
    assert r.opts["fallback"] == [{"provider": "claude-code", "model": "claude-opus-5-5"}, "codex"]
    assert r.model == "kimi-k2-turbo"                # no model of its own: the desk's model for Kimi


def test_step_override_beats_project(tmp_path, monkeypatch):
    d = _project(tmp_path, {"provider": "kimi"})
    monkeypatch.setenv("VSTUDIO_PROJECT_DIR", str(d))
    monkeypatch.setenv("VSTUDIO_LLM_COPY_PROVIDER", "codex")
    assert llm.route("copy").provider == "codex"
    assert llm.route("intake").provider == "kimi"
    r = llm.route("intake", provider="ollama")
    assert r.provider == "ollama" and r.source == "argument"


def test_explicit_same_provider_keeps_project_model(tmp_path, monkeypatch):
    d = _project(tmp_path, {"provider": "kimi", "model": "kimi-k2"})
    monkeypatch.setenv("VSTUDIO_PROJECT_DIR", str(d))
    assert llm.route("copy", provider="kimi").model == "kimi-k2"


def test_switch_mid_run_applies_to_next_call(tmp_path, monkeypatch):
    d = _project(tmp_path, {"provider": "kimi"})
    monkeypatch.setenv("VSTUDIO_PROJECT_DIR", str(d))
    assert llm.route("intake").provider == "kimi"
    data = yaml.safe_load((d / "project.yaml").read_text())
    data["ai"] = {"provider": "deepseek", "model": "deepseek-chat"}
    (d / "project.yaml").write_text(yaml.safe_dump(data))
    r = llm.route("intake")
    assert (r.provider, r.model) == ("deepseek", "deepseek-chat")
    data.pop("ai")
    (d / "project.yaml").write_text(yaml.safe_dump(data))
    assert llm.route("intake").provider == "claude-code"     # cleared: the app's routes again


def test_request_env_before_it_is_a_project(monkeypatch):
    monkeypatch.setenv("VSTUDIO_LLM_PROJECT_AI", json.dumps({"provider": "kimi", "model": "kimi-k2"}))
    r = llm.route("intake")
    assert (r.provider, r.model, r.source) == ("kimi", "kimi-k2", "project ai")


def test_bad_project_ai_is_ignored(tmp_path, monkeypatch):
    d = _project(tmp_path, {"provider": "no-such-ai"})
    monkeypatch.setenv("VSTUDIO_PROJECT_DIR", str(d))
    assert llm.route("intake").provider == "claude-code"
    (d / "project.yaml").write_text("::: not yaml [")
    assert llm.route("intake").provider == "claude-code"


def test_complete_uses_project_ai_and_falls_back(tmp_path, monkeypatch):
    d = _project(tmp_path, {"provider": "kimi"})
    monkeypatch.setenv("VSTUDIO_PROJECT_DIR", str(d))
    calls = []

    def fake(task, system, prompt, provider=None, model=None, **kw):
        p = provider or llm.route(task).provider
        calls.append(p)
        if p == "kimi":
            raise llm.LLMError("kimi: 503 overloaded")
        return dict(text="{}", json={}, usage={}, cost_usd=0.0, provider=p, model=model)
    monkeypatch.setattr(llm, "_complete", fake)
    r = llm.complete("copy", "s", "p", schema=True)
    assert calls == ["kimi", "claude-code"] and r["provider"] == "claude-code"


def test_project_save_keeps_ai_switched_meanwhile(tmp_path):
    from vstudio.project.core import Project
    d = _project(tmp_path, {"provider": "kimi"})
    run = Project(str(d))                            # the run's copy, read before the switch
    app = Project(str(d))
    app.set_ai("deepseek", "deepseek-chat", by="you")
    run.data["answers"]["x"] = {"*": {"value": 1}}
    run.save()                                       # the run saves its stale copy
    data = yaml.safe_load((d / "project.yaml").read_text())
    assert data["ai"] == {"provider": "deepseek", "model": "deepseek-chat"}
    assert data["answers"]["x"]
    from vstudio.project import autopilot as AP
    ev = [e for e in AP.history(app) if e.get("event") == "ai"]
    assert ev and ev[-1]["provider"] == "deepseek" and ev[-1]["before"] == {"provider": "kimi"}
    app.set_ai(None)
    assert "ai" not in yaml.safe_load((d / "project.yaml").read_text())


def test_cli_model_switches_and_shows(tmp_path, capsys):
    from vstudio.project import cli
    d = _project(tmp_path)
    assert cli.main(["model", "--dir", str(d), "--provider", "kimi", "--model", "kimi-k2", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ai"] == {"provider": "kimi", "model": "kimi-k2"}
    assert out["resolved"]["provider"] == "kimi" and out["resolved"]["source"] == "project ai"
    assert "VSTUDIO_PROJECT_DIR" not in os.environ   # restored after the command
    assert cli.main(["model", "--dir", str(d), "--clear", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ai"] is None
