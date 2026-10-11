"""vstudio.agentlog: the live transcript of a job - what the model CLIs were asked and did, captured as they stream
(fake CLIs from tests/fixtures/fake_cli stand in for claude / codex), redacted before it is stored."""
import json
import os
import threading
import time

import pytest

from vstudio import agentlog, llm

FAKE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_cli")
posix_only = pytest.mark.skipif(os.name == "nt", reason="the fake CLIs are POSIX scripts")


@pytest.fixture(autouse=True)
def clean_llm(monkeypatch):
    for k in list(os.environ):
        if k.startswith("VSTUDIO_LLM_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "_persona_llm", lambda: {})
    monkeypatch.setattr(llm, "_sleep", lambda s: None)


def lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


# ------------------------------------------------------------------ redaction
@pytest.mark.parametrize("raw,gone", [
    ("ANTHROPIC_API_KEY=sk-ant-" "api03-abcdefghijklmnop", "sk-ant-api03"),
    ("use sk-proj-" "ABCDEFGHIJKLMNOPQRSTUV now", "sk-proj-" "ABCD"),
    ("Authorization: Bearer abc.def.ghijklmnopq", "abc.def.ghijklmnopq"),
    ("Cookie: sessionid=abc123; csrftoken=zzz", "sessionid=abc123"),
    ("Set-Cookie: a=b; HttpOnly", "a=b"),
    ("ping ops@example.com about it", "ops@example.com"),
    ('{"token": "9f8e7d6c5b4a3f2e"}', "9f8e7d6c5b4a3f2e"),
    ("password=hunter2", "hunter2"),
    ("gh token ghp_" "abcdefghijklmnopqrstuvwxyz0123", "ghp_abcdefghij"),
    ("AKIA" "ABCDEFGHIJKLMNOP is aws", "AKIA" "ABCDEFGHIJKLMNOP"),
    ("jwt eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4", "eyJhbGciOiJIUzI1"),
    ("hf_abcdefghijklmnopqrstuvwxyzABCDEF", "hf_abcdefghij"),
    ("-----BEGIN " "PRIVATE KEY-----\nMIIEv\n-----END PRIVATE KEY-----", "MIIEv"),
])
def test_redact_takes_secrets_out(raw, gone):
    out = agentlog.redact(raw)
    assert gone not in out
    assert "redacted" in out or "[email]" in out


def test_redact_keeps_ordinary_words_and_numbers():
    s = '"input_tokens": 18200, tokens in 18.2k · Read inventory.json · 4K 60 fps'
    assert agentlog.redact(s) == s


def test_redact_home_folder(monkeypatch, tmp_path):
    home = str(tmp_path / "someone")
    monkeypatch.setenv("HOME", home)
    monkeypatch.setenv("USERPROFILE", home)                      # what expanduser reads on Windows
    assert agentlog.redact(f"open {home}/Movies/a.mp4") == "open ~/Movies/a.mp4"  # check-skill: allow
    if os.name == "nt":
        assert agentlog.redact(f"open {home.replace(os.sep, '/')}/a.mp4") == "open ~/a.mp4"


# ------------------------------------------------------------------ writing
def test_off_without_the_env(tmp_path, monkeypatch):
    monkeypatch.delenv(agentlog.ENV, raising=False)
    agentlog.emit("say", "hello")
    assert agentlog.begin("intake", "claude-code", None, "s", "p") is None
    assert not list(tmp_path.iterdir())


def test_emit_redacts_caps_and_appends(tmp_path, monkeypatch):
    p = tmp_path / "live.jsonl"
    monkeypatch.setenv(agentlog.ENV, str(p))
    agentlog.emit("say", "key sk-ant-" "api03-abcdefghijklmnop " + "x" * 9000, provider="claude-code")
    agentlog.emit_engine(str(p), "stage", "scan · 3 files", data=dict(stage="scan", files=3, mail="a@b.co"))
    a, b = lines(p)
    assert a["src"] == "agent" and a["kind"] == "say" and "sk-ant" not in a["text"]
    assert len(a["text"]) < agentlog.MAX_TEXT + 40 and "+" in a["text"][-20:]
    assert b["src"] == "engine" and b["data"]["files"] == 3 and b["data"]["mail"] == "[email]"
    if os.name != "nt":                                          # no POSIX file modes on Windows
        assert oct(os.stat(p).st_mode & 0o777) == "0o600"


def test_file_stops_growing_at_the_cap(tmp_path, monkeypatch):
    p = tmp_path / "live.jsonl"
    monkeypatch.setenv(agentlog.ENV, str(p))
    monkeypatch.setattr(agentlog, "MAX_BYTES", 2000)
    for _ in range(50):
        agentlog.emit("say", "y" * 200)
    got = lines(p)
    assert os.path.getsize(p) < 2600
    assert got[-1]["kind"] == "truncated"


# ------------------------------------------------------------------ capture from the CLIs
@posix_only
def test_claude_code_stream_is_captured_live_and_redacted(tmp_path, monkeypatch):
    p = tmp_path / "live.jsonl"
    monkeypatch.setenv(agentlog.ENV, str(p))
    r = llm.complete("intake", "SYSTEM", "Plan 27 travel files", provider="claude-code",
                     schema={"type": "object"}, cli=os.path.join(FAKE, "claude"), timeout=30)
    assert r["json"] == {"projects": 2} and r["usage"]["input"] == 1200 and r["model"] == "claude-fake-1"
    got = lines(p)
    kinds = [x["kind"] for x in got]
    assert kinds[:2] == ["turn", "prompt"] and kinds[-1] == "result"
    for k in ("info", "thinking", "tool", "tool-result", "say"):
        assert k in kinds
    turn = got[0]["turn"]
    assert all(x.get("turn") == turn for x in got)                       # one call, one turn
    assert got[0]["task"] == "intake" and got[0]["provider"] == "claude-code"
    text = json.dumps(got)
    assert "SECRETSECRET" not in text and "ops@example.com" not in text
    assert "Read  /tmp/inventory.json" in text
    assert "subscription" in got[-1]["text"]


@posix_only
def test_claude_code_without_the_live_view_keeps_plain_json(tmp_path, monkeypatch):
    monkeypatch.delenv(agentlog.ENV, raising=False)
    seen = {}
    real = llm.subprocess.run

    def spy(cmd, **kw):
        seen["cmd"] = cmd
        return real(cmd, **kw)
    monkeypatch.setattr(llm.subprocess, "run", spy)
    r = llm.complete("intake", "s", "p", provider="claude-code", schema=True, cli=os.path.join(FAKE, "claude"))
    assert r["json"] == {"projects": 2}
    assert seen["cmd"][seen["cmd"].index("--output-format") + 1] == "json" and "--verbose" not in seen["cmd"]


@posix_only
def test_claude_code_failure_is_a_line_too(tmp_path, monkeypatch):
    p = tmp_path / "live.jsonl"
    monkeypatch.setenv(agentlog.ENV, str(p))
    monkeypatch.setenv("FAKE_CLI_FAIL", "1")
    with pytest.raises(llm.LLMError, match="token expired"):
        llm.complete("intake", "s", "p", provider="claude-code", cli=os.path.join(FAKE, "claude"), retries=0)
    errs = [x for x in lines(p) if x["kind"] == "error"]
    assert errs and "token expired" in errs[-1]["text"]


@posix_only
def test_lines_arrive_while_the_cli_still_runs(tmp_path, monkeypatch):
    """Streaming, not a dump at the end: the first lines are in the file before the call returns."""
    p = tmp_path / "live.jsonl"
    monkeypatch.setenv(agentlog.ENV, str(p))
    monkeypatch.setenv("FAKE_CLI_DELAY", "0.4")
    seen_early = []

    def watch():
        t0 = time.time()
        while time.time() - t0 < 5:
            if p.exists() and any(x["kind"] == "thinking" for x in lines(p)):
                seen_early.append(not done)
                return
            time.sleep(0.05)
    done = False
    th = threading.Thread(target=watch)
    th.start()
    llm.complete("intake", "s", "p", provider="claude-code", schema=True, cli=os.path.join(FAKE, "claude"))
    done = True
    th.join()
    assert seen_early == [True]


@posix_only
def test_codex_events_are_captured_and_redacted(tmp_path, monkeypatch):
    p = tmp_path / "live.jsonl"
    monkeypatch.setenv(agentlog.ENV, str(p))
    r = llm.complete("copy", "s", "write it", provider="codex", schema=True, cli=os.path.join(FAKE, "codex"))
    assert r["json"] == {"ok": True} and r["usage"]["input"] == 300
    got = lines(p)
    kinds = [x["kind"] for x in got]
    assert {"turn", "prompt", "info", "thinking", "tool", "tool-result", "say", "result"} <= set(kinds)
    assert any(x["text"] == "$ ls clips" for x in got)
    assert "sk-proj-abcdefgh" not in json.dumps(got)


def test_api_provider_reply_is_one_say_line(tmp_path, monkeypatch):
    p = tmp_path / "live.jsonl"
    monkeypatch.setenv(agentlog.ENV, str(p))
    monkeypatch.setitem(llm.BACKEND_FNS, "openai", lambda *a: ('{"a": 1}', dict(input=5, output=2), "gpt-x"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    llm.complete("copy", "s", "p", provider="openai", schema=True)
    kinds = [x["kind"] for x in lines(p)]
    assert kinds == ["turn", "prompt", "say", "result"]


def test_stream_parsers_ignore_junk():
    agentlog.claude_event("not a dict")
    agentlog.claude_event({"type": "assistant", "message": {"content": ["x", {"type": "text", "text": " "}]}})
    agentlog.codex_event({"type": "item.completed", "item": "x"})
