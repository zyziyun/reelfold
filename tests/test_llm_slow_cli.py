"""The clip chat fell to the rules ("No model") with Claude Code set up (2026-10-11): ``output ai`` gave the CLI 60 s,
Claude Code (Opus) takes ~65 s on a clip's ~15k-char context, so it timed out, was marked unresponsive for 10 min
and every later ask skipped it - with Codex failing too, the rules answered. Real CLI path (a fake ``claude`` that
reads its stdin to the end like ``claude -p`` - it would hang if stdin stayed open - and answers after a delay):
a slow answer within the limit is used, a timed-out CLI that was skipped is asked again when the fallback fails too,
and output ai's per-attempt limit leaves room for a slow model."""
import json
import os
import sys

import pytest

from vstudio import llm, llm_auth as A

FAKE_CLAUDE = r'''#!{python}
import json, os, sys, time
sys.stdin.read()                                   # claude -p reads the prompt to EOF first
time.sleep(float(os.environ.get("FAKE_SLEEP") or 0))
print(json.dumps(dict(type="result", is_error=False, result="", structured_output={{"ops": [], "summary": "ok"}},
                      usage=dict(input_tokens=10, output_tokens=2), modelUsage={{"claude-opus": {{}}}})))
'''
FAKE_CODEX = r'''#!{python}
import sys
sys.stdin.read()
print('{{"type":"error","status":400,"error":{{"message":"The model is not supported with a ChatGPT account."}}}}')
sys.exit(1)
'''


@pytest.fixture
def clis(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("the fake CLIs are scripts")
    b = tmp_path / "bin"
    b.mkdir()
    for name, body in (("claude", FAKE_CLAUDE), ("codex", FAKE_CODEX)):
        p = b / name
        p.write_text(body.format(python=sys.executable))
        p.chmod(0o755)
    monkeypatch.setenv("PATH", str(b) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("VSTUDIO_CLI_EXTRA_DIRS", "")
    monkeypatch.setenv("VSTUDIO_AUTH_CACHE", str(tmp_path / "auth.json"))
    monkeypatch.delenv("VSTUDIO_LLM_CLI_TIMEOUT", raising=False)
    monkeypatch.delenv("VSTUDIO_LLM_NO_CLI", raising=False)
    monkeypatch.setattr(llm, "route", lambda task="default", provider=None, model=None, config=None:
                        llm.Route("claude-code", None, {"fallback": ["codex"]}, "test")
                        if not provider else llm.Route(llm.canonical(provider), model, {}, "argument"))
    monkeypatch.setattr(A, "fingerprint", lambda provider, status_out=None: "fp")
    return b


SCHEMA = {"type": "object", "properties": {"ops": {"type": "array"}}, "required": ["ops"]}


def ask(timeout):
    return llm.complete("output_edit", "system", "x" * 15000, schema=SCHEMA, retries=0, cli_timeout=timeout)


def test_a_slow_cli_answer_is_used_and_a_skipped_one_is_asked_again(clis, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "1.5")
    r = ask(10)                                                       # slow but within the limit: its answer
    assert r["provider"] == "claude-code" and r["json"]["summary"] == "ok" and not r.get("fallback")
    with pytest.raises(llm.LLMError) as e:                            # past the limit: it times out, Codex fails
        ask(0.5)
    assert [a["code"] for a in llm.attempts_of(e.value)] == ["timeout", "model-unsupported"]  # Codex: a model its login cannot use
    assert A.known_unresponsive("claude-code")
    # the next ask: skipped as unresponsive, Codex fails again -> Claude Code is asked after all and answers
    monkeypatch.setenv("FAKE_SLEEP", "0")
    r = ask(10)
    assert r["provider"] == "claude-code" and r["json"]["ops"] == [] and not r.get("fallback")
    assert [(a["provider"], a.get("cached", False)) for a in r["failed_attempts"]] == \
        [("claude-code", True), ("codex", False)]
    assert not A.known_unresponsive("claude-code")                    # it answered: the mark is gone


def test_output_ai_gives_a_cli_model_room_for_a_slow_answer():
    from vstudio.project import outputs as O
    assert O.AI_CLI_TIMEOUT >= 120                                    # Claude Code takes ~65 s on a clip's context
