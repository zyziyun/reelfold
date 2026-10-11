"""Test fixture for the voice-key e2e (dogfood 2026-10-11: her course explainer stopped at the voice on "OPENAI_API_KEY
is not set"). Two explainer projects on a short Chinese script, run with the REAL engine:

* ``course``  - on autopilot, made while an OpenAI key was set (the voice was approved for OpenAI), whose voice step
  then ran without the key: failed, exactly as hers (``run --autopilot --json-events`` into ``desk-pilot.log`` + its
  ``desk-pilot.json`` record, the way the desk runs it);
* ``asking``  - Ask me first, ``tts_engine: openai``, no key: waits at the voice question.

Writes a test-only ``sitecustomize`` hook to ``ROOT/hook`` (put it on the desk's PYTHONPATH with ``VOICEKEY_LOG``):
this computer "has" the free voice Kokoro (``VOICEKEY_FREE``), and a take is never made - the engine and voice of the
first take are recorded in ``VOICEKEY_LOG``, then the step stops. ``VOICEKEY_DROP_KEY`` drops OPENAI_API_KEY in the
voice step only (how the key went missing). The only fakes; the rest is the real engine.

    python voice_project.py ROOT   (VSTUDIO_HOME etc. from the environment) -> prints {course, asking, hook, log, exit}
"""
import json
import os
import subprocess
import sys
import time

ROOT = sys.argv[1]
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "lib"))

HOOK = '''import json, os, sys
if os.environ.get("VOICEKEY_LOG"):
    if os.environ.get("VOICEKEY_DROP_KEY") and os.path.basename(sys.argv[0] if sys.argv else "") == "tts.py":
        os.environ.pop("OPENAI_API_KEY", None)
    try:
        from vstudio import tts as _tts
    except ImportError:
        _tts = None
    if _tts is not None:
        _free = os.environ.get("VOICEKEY_FREE", "")
        _tts.installed = lambda e: e == _free if e in _tts.LOCAL else True
        _real = _tts.synth

        def _synth(text, engine="openai", voice=None, out=None, **kw):
            engine = _tts.pick_engine(engine)
            if _tts.missing_key(engine):
                return _real(text, engine=engine, voice=voice, out=out, **kw)
            with open(os.environ["VOICEKEY_LOG"], "a", encoding="utf-8") as f:
                f.write(json.dumps(dict(engine=engine, voice=voice, out=out)) + "\\n")
            raise RuntimeError("test: no real take (the engine and voice are recorded)")
        _tts.synth = _synth
'''

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

hook = os.path.join(ROOT, "hook")
os.makedirs(hook, exist_ok=True)
with open(os.path.join(hook, "sitecustomize.py"), "w", encoding="utf-8") as f:
    f.write(HOOK)
log_path = os.path.join(ROOT, "voice.jsonl")
script = os.path.join(ROOT, "SCRIPT.md")
with open(script, "w", encoding="utf-8") as f:
    f.write(SCRIPT)

from vstudio import tts  # noqa: E402
from vstudio.project import autopilot as AP  # noqa: E402
from vstudio.project.core import Project  # noqa: E402

tts.installed = lambda e: e == "kokoro" if e in tts.LOCAL else True       # this process too: the same machine

# ---- hers: made with a key on autopilot, the voice step ran without it
p = Project.create(os.path.join(ROOT, "projects", "course"), recipe="explainer", name="MCP course",
                   items=[dict(id="ep1", inputs=dict(script=script))])
AP.configure(p, on=True, judge=False)
args = ["-m", "vstudio.project", "run", "--dir", p.dir, "--autopilot", "--json-events"]
env = dict(os.environ, PYTHONPATH=os.pathsep.join([hook, os.path.join(REPO, "lib")]), VOICEKEY_LOG=log_path,
           VOICEKEY_FREE="kokoro", VOICEKEY_DROP_KEY="1", OPENAI_API_KEY="sk-test-not-a-key")
with open(os.path.join(p.dir, "desk-pilot.log"), "ab") as log:
    started = time.time()
    code = subprocess.run([sys.executable, *args], stdout=log, stderr=log, env=env).returncode
with open(os.path.join(p.dir, "desk-pilot.json"), "w", encoding="utf-8") as f:
    json.dump(dict(pid=None, started=started, offset=0, agent_offset=0, exit=code, finished=time.time(), provider=None,
                   args=args), f)

# ---- Ask me first, OpenAI chosen, no key: the voice question
os.environ.pop("OPENAI_API_KEY", None)
q = Project.create(os.path.join(ROOT, "projects", "asking"), recipe="explainer", name="Asking course",
                   params=dict(tts_engine="openai"), items=[dict(id="ep1", inputs=dict(script=script))])
AP.configure(q, on=False)
for _ in range(4):
    q = Project(q.dir)
    for x in q.pending():
        if x["id"] in ("script", "storyboard"):
            q.answer(x["id"], x.get("default") or dict(done=True), items=["ep1"])
    q.run()
    if any(x["id"] == "voice" for x in Project(q.dir).pending()):
        break
print(json.dumps(dict(course=p.dir, asking=q.dir, hook=hook, log=log_path, exit=code,
                      pending=[(x["item"], x["id"]) for x in Project(q.dir).pending()])))
