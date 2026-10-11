"""The explainer's voice is the voice this machine has (dogfood 2026-10-11: her course project, Chinese narration on
autopilot, failed at the voice stage with "OPENAI_API_KEY is not set" - she has no OpenAI key, only Claude Code /
Codex subscriptions and the free local voice).

* the plan's default engine: her persona's, else OpenAI only with its key, else the free local voice (Mandarin for
  中文讲解); a plan never defaults to a paid engine without its key;
* a project that chose OpenAI without a key: autopilot takes the free voice and records why; Ask-me-first stops at
  a plain "no OpenAI key" question (never auto-answered);
* a project like hers (voice failed on the missing key) recovers on Try again under the same rule;
* the missing key is a plain message naming the service and the fix (never a traceback).

The voice stage runs workflows/explainer/scripts/tts.py for real; ``vstudio.tts.synth`` is replaced in that child
process by a test sitecustomize (records the engine / voice of the first take, then stops) - no network, no model.

    python3 -m pytest tests/test_explainer_voice_key.py -q
"""
import json
import os
import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from vstudio import proctail, tts  # noqa: E402
from vstudio.project import inbox as IB  # noqa: E402
from vstudio.project.core import Project  # noqa: E402

SCRIPT = """# SCRIPT — MCP

Narration: 中文讲解

---

## Line 1 — Hook (Frame 1)

    你有 3 个 AI 应用，要接 4 个工具。没有标准的话，就是 12 份集成代码。

EN: Three apps, four tools, twelve integrations.

## Line 2 — USB-C (Frame 2)

    MCP 是 AI 应用的 USB-C 接口。你写一个 MCP server，所有支持 MCP 的应用都能直接用它。

EN: MCP is the USB-C port of AI apps.
"""

FAKE_SYNTH = '''
import json, os
_log = os.environ.get("VSTUDIO_TEST_TTS_LOG")
if _log:
    from vstudio import tts as _tts
    _free = os.environ.get("VSTUDIO_TEST_FREE_VOICE", "")
    _tts.installed = lambda e: e == _free if e in _tts.LOCAL else True

    def _synth(text, engine="openai", voice=None, **kw):
        engine = _tts.pick_engine(engine)
        if _tts.missing_key(engine):
            raise _tts.MissingKey(engine)
        with open(_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(engine=engine, voice=voice)) + "\\n")
        raise RuntimeError("test: no real take (the engine and voice are recorded)")
    _tts.synth = _synth
'''


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_BATCH_BENCH", str(tmp_path / "bench.json"))
    monkeypatch.setenv("VSTUDIO_LLM_PROVIDER", "none")
    for k in ("OPENAI_API_KEY", "ELEVENLABS_API_KEY", "VSTUDIO_TTS_ENGINE", "VSTUDIO_PERSONA", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    fake = tmp_path / "fake_tts"
    fake.mkdir()
    (fake / "sitecustomize.py").write_text(FAKE_SYNTH, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(fake), os.environ.get("PYTHONPATH", "")]))
    monkeypatch.setenv("VSTUDIO_TEST_TTS_LOG", str(tmp_path / "tts.jsonl"))
    free_voice(monkeypatch, "kokoro")               # this computer has the free voice (Kokoro); see free_voice()
    from vstudio import config
    config.persona.cache_clear()
    yield tmp_path
    config.persona.cache_clear()


def free_voice(monkeypatch, engine):
    """Which free voice this computer has ("" = none: the packaged app's runtime has neither mlx-audio nor
    edge-tts), in the test process and in the voice stage's child process alike."""
    monkeypatch.setenv("VSTUDIO_TEST_FREE_VOICE", engine)
    monkeypatch.setattr(tts, "installed", lambda e: e == engine if e in tts.LOCAL else True)


def _persona(iso, monkeypatch, text):
    (iso / "persona.yaml").write_text(text, encoding="utf-8")
    monkeypatch.setenv("VSTUDIO_PERSONA", str(iso / "persona.yaml"))
    from vstudio import config
    config.persona.cache_clear()


def _takes(iso):
    p = iso / "tts.jsonl"
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def _project(iso, params=None, autopilot=True):
    script = iso / "SCRIPT.md"
    script.write_text(SCRIPT, encoding="utf-8")
    pdir = str(iso / "course")
    Project.create(pdir, recipe="explainer", params=dict(params or {}),
                   items=[dict(id="ep1", inputs=dict(script=str(script)))])
    p = Project(pdir)
    p.data["autopilot"] = dict(on=bool(autopilot), spend_cap=0, judge=False)
    p.save()
    return pdir


def _run(pdir):
    evs = []
    out = Project(pdir).run(on_event=evs.append)
    return out, evs


def _voice_fail(evs):
    return [e for e in evs if e.get("event") == "stage-fail" and e.get("stage") == "voice"]


def _local_zh():
    return "kokoro", "zf_xiaobei"                  # Kokoro's Mandarin voice (its lang code "z" goes with it)


# --------------------------------------------------------------------------- the plan's default
def test_the_plan_defaults_to_the_voice_this_machine_has(iso, monkeypatch):
    pdir = _project(iso)
    P = Project(pdir).params()
    assert P["tts_engine"] == "kokoro" and P["_tts_engine_auto"] is True
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")                    # a key: OpenAI (older projects keep theirs)
    assert Project(pdir).params()["tts_engine"] == "openai"
    _persona(iso, monkeypatch, "tts:\n  engine: clone\n")             # her persona's voice wins, key or not
    assert Project(pdir).params()["tts_engine"] == "clone" == tts.available_engine()
    monkeypatch.delenv("VSTUDIO_PERSONA")
    from vstudio import config
    config.persona.cache_clear()
    p = Project(pdir)
    p.data["params"]["tts_engine"] = "openai"                           # a choice she made stays hers
    p.save()
    monkeypatch.delenv("OPENAI_API_KEY")
    assert Project(pdir).params()["tts_engine"] == "openai" and "_tts_engine_auto" not in Project(pdir).params()


def test_the_intake_estimate_charges_the_voice_only_with_a_key(iso, monkeypatch):
    from vstudio.intake import estimate as E
    assert E._explainer_engine({}) == "kokoro" and E._explainer_engine({"tts_engine": "auto"}) == "kokoro"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert E._explainer_engine({}) == "openai"
    from vstudio.intake import plan as PL
    p = PL.make_plan("做一条讲解 transformer 的视频，中文讲解", [], provider="none", asr="off")
    assert p["projects"][0]["recipe"] == "explainer" and p["estimate"]["api_usd"] > 0
    monkeypatch.delenv("OPENAI_API_KEY")
    p = PL.make_plan("做一条讲解 transformer 的视频，中文讲解", [], provider="none", asr="off")
    assert p["estimate"]["api_usd"] == 0
    assert p["projects"][0]["params"].get("tts_engine") in (None, "auto")   # never "openai" without a key


def test_a_missing_key_is_a_plain_message_naming_the_service_and_the_fix(iso):
    with pytest.raises(tts.MissingKey) as e:
        tts.synth("你好", engine="openai", out=str(iso / "x.wav"), cache=False)
    msg = str(e.value)
    assert msg.startswith("No OpenAI key:") and "Settings > AI" in msg and "free local voice" in msg
    assert tts.missing_key("openai") == "OPENAI_API_KEY" and tts.missing_key("kokoro") is None
    stage = f"RuntimeError: tts.py exit 1: Traceback (most recent call last):\n  ...\nMissingKey: {msg}"
    assert proctail.tool_failure(stage) == dict(code="ai-key-missing", params=dict(service="OpenAI", fix="free-voice"))
    alone = str(tts.MissingKey("openai", free=False))                  # no free voice here: the key is the way
    assert "free local voice" not in alone and "Settings > AI" in alone
    assert proctail.tool_failure(f"tts.py exit 1: {alone}")["params"] == dict(service="OpenAI", fix="add-key")
    old = "RuntimeError: tts.py exit 1:\nTraceback ...\nRuntimeError: OPENAI_API_KEY is not set in the environment"
    assert proctail.tool_failure(old)["params"]["service"] == "OpenAI"
    assert proctail.tool_failure("RuntimeError: HEDRA_API_KEY is not set (Settings > Video generation > Hedra)") == \
        dict(code="ai-key-missing", params=dict(service="Hedra", fix="add-key"))


# --------------------------------------------------------------------------- the voice stage
def test_autopilot_takes_the_free_voice_when_openai_has_no_key(iso):
    pdir = _project(iso, params=dict(tts_engine="openai"))
    out, evs = _run(pdir)
    eng, voice = _local_zh()
    assert _takes(iso)[:1] == [dict(engine=eng, voice=voice)]          # the free local voice, in Mandarin
    assert not any("OPENAI_API_KEY" in str(e.get("error")) for e in _voice_fail(evs))
    p = Project(pdir)
    rec = p.data["answers"]["voice"]["ep1"]
    assert rec["auto"] and rec["by"] == "rules" and rec["reason_code"] == "free-voice"
    assert rec["reason"] == "used the free local voice — no OpenAI key" and rec["params"]["service"] == "OpenAI"
    assert rec["value"]["engine"] == eng and p.data["params"]["tts_engine"] == eng
    assert p.data["params"].get("voice") in (None, "cedar")            # the voice stays derived per line
    log = [json.loads(ln) for ln in open(os.path.join(p.state_dir, "autopilot.jsonl"), encoding="utf-8")]
    assert any(e.get("checkpoint") == "voice" and e.get("reason_code") == "free-voice" for e in log)
    # the next run: the free voice is the answer now (no question again, no loop)
    _run(pdir)
    assert Project(pdir).pending() == [] and Project(pdir).data["answers"]["voice"]["ep1"]["reason_code"] == "free-voice"


def test_ask_first_stops_at_a_plain_no_key_question(iso):
    pdir = _project(iso, params=dict(tts_engine="openai"), autopilot=False)
    p = Project(pdir)
    p.data["auto"] = ["voice"]                     # even a voice she lets the rules answer: no key = her call
    p.save()
    for _ in range(3):                             # script and storyboard: her answers
        pend = Project(pdir).pending()
        for x in pend:
            if x["id"] in ("script", "storyboard"):
                Project(pdir).answer(x["id"], x.get("default") or dict(done=True), items=["ep1"])
        out, evs = _run(pdir)
        if any(x["id"] == "voice" for x in Project(pdir).pending()):
            break
    pend = [x for x in Project(pdir).pending() if x["id"] == "voice"]
    assert pend, Project(pdir).pending()
    pay = pend[0]
    eng, voice = _local_zh()
    assert pay["no_key"] == dict(service="OpenAI", env="OPENAI_API_KEY", engine="openai", free_engine=eng,
                                 free_voice=voice)
    assert pay["default"] == dict(voice=voice, speed=1.0, approve=True, engine=eng) and pay["paid"] is False
    assert not _voice_fail(evs) and _takes(iso) == []                   # nothing ran, no traceback
    entry = next(e for e in IB.inbox([dict(dir=pdir)])["entries"] if e["id"] == "voice")
    assert entry["no_key"]["service"] == "OpenAI"
    Project(pdir).answer("voice", pay["default"], items=["ep1"])       # "Use the free voice"
    assert Project(pdir).pending() == [] and not IB.inbox([dict(dir=pdir)])["entries"]   # answered: the run may go on
    _run(pdir)
    assert _takes(iso)[:1] == [dict(engine=eng, voice=voice)]


@pytest.mark.parametrize("explicit", [True, False], ids=["tts_engine-openai", "openai-by-default"])
def test_a_project_that_failed_on_the_missing_key_recovers_on_try_again(iso, monkeypatch, explicit):
    """Hers: the voice was approved for OpenAI (then the default) and failed with no key. Try again (the same run on
    autopilot) re-opens the voice: the free voice, recorded; nothing before the voice runs again."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    pdir = _project(iso, params=dict(tts_engine="openai") if explicit else None)
    out, evs = _run(pdir)
    assert _takes(iso)[:1] == [dict(engine="openai", voice="cedar")] and _voice_fail(evs)
    p = Project(pdir)
    if not explicit:                   # an answer from before the engine was recorded, no tts_engine in the plan
        p.data["params"].pop("tts_engine", None)
        p.data["answers"]["voice"]["ep1"]["value"].pop("engine", None)
        p.save()
        out, evs = _run(pdir)                # her state: the gate passed on that answer, the voice failed
        assert _voice_fail(evs) and Project(pdir).pending() == []
    monkeypatch.delenv("OPENAI_API_KEY")
    (iso / "tts.jsonl").unlink()
    out, evs = _run(pdir)                                               # Try again
    started = [e["stage"] for e in evs if e["event"] == "stage-start"]
    assert "storyboard" not in started and "cp_voice" in started
    eng, voice = _local_zh()
    assert _takes(iso)[:1] == [dict(engine=eng, voice=voice)]
    assert not any("OPENAI_API_KEY" in str(e.get("error")) for e in _voice_fail(evs))
    rec = Project(pdir).data["answers"]["voice"]["ep1"]
    assert rec["reason_code"] == "free-voice" and rec["value"]["engine"] == eng


def test_a_project_with_its_key_keeps_openai_and_its_answer(iso, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    pdir = _project(iso)
    _run(pdir)
    first = Project(pdir).data["answers"]["voice"]["ep1"]
    (iso / "tts.jsonl").unlink()
    out, evs = _run(pdir)
    assert [t["engine"] for t in _takes(iso)][:1] == ["openai"]
    assert Project(pdir).data["answers"]["voice"]["ep1"] == first          # not asked again
    assert yaml.safe_load(open(os.path.join(pdir, "project.yaml"), encoding="utf-8"))["params"]["tts_engine"] == "openai"


def test_no_key_and_no_free_voice_asks_for_the_key_and_goes_on_once_it_is_there(iso, monkeypatch):
    """The packaged app has no free voice installed: no key = nothing can speak. Autopilot leaves her one plain
    question (needs-key), the voice step never runs into a traceback; with the key added, Try again goes on."""
    free_voice(monkeypatch, "")
    pdir = _project(iso)
    assert Project(pdir).params()["tts_engine"] == "kokoro"            # free by name, never a charge
    out, evs = _run(pdir)
    assert not _voice_fail(evs) and _takes(iso) == []
    pay = next(x for x in Project(pdir).pending() if x["id"] == "voice")
    assert pay["no_key"] == dict(service="OpenAI", env="OPENAI_API_KEY", engine="openai", free_engine=None,
                                 free_voice=None)
    assert pay["default"] is None and pay["options"] == []
    assert any(b["checkpoint"] == "voice" for b in out["blocked"])
    log = [json.loads(ln) for ln in open(os.path.join(Project(pdir).state_dir, "autopilot.jsonl"), encoding="utf-8")]
    assert any(e.get("blocker") == "needs-key" and e.get("params", {}).get("service") == "OpenAI" for e in log)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")                     # she adds her key, then Try again
    out, evs = _run(pdir)
    assert [t["engine"] for t in _takes(iso)][:1] == ["openai"] and not Project(pdir).pending()
