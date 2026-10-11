"""Test fixture for the explainer-visuals e2e (her MCP course, 2026-10-11: Claude Code timed out, the scenes fell back
to the rules and the autopilot rendered a video of text lines). Two explainer projects on a short Chinese script, run
on autopilot with the REAL engine:

* ``needs``  - the model answers the storyboard but not the scenes: the run stops in Needs you at "Build the scenes"
  ("The visuals need an AI model — Claude Code didn't answer"), nothing rendered;
* ``plain``  - finished the way hers was (an older engine drew its scenes as text lines, ``by: rules``): rendered and
  exported - what "Redo the visuals" redraws.

Stand-ins (test only, the rest is the real engine): ``ROOT/bin/claude`` (Claude Code: plans the storyboard, draws a
scene; it "times out" while ``ROOT/claude-down`` exists), ``ROOT/bin/npx`` (``hyperframes render``: a plain video of
the narration's length with ffmpeg; each render is logged in ``ROOT/renders.log``) and ``ROOT/hook/sitecustomize.py``
(the voice: a tone per line; the ASR: the line's own words; with EXPLAINER_FAKE_BIN=ROOT/bin it pins the two
stand-ins, the app puts its own bin folders first on PATH) - put ROOT/hook on the engine's PYTHONPATH.

    python explainer_project.py ROOT   (VSTUDIO_HOME etc. from the environment) -> prints {needs, plain, bin, hook}
"""
import json
import os
import stat
import sys

ROOT = os.path.abspath(sys.argv[1])
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "lib"))

SCRIPT = """# SCRIPT — MCP

Narration: 中文讲解

---

## Line 1 — 乘法变加法 (Frame 1)

**Delivery:** Calm. 画面：M×N 的连线变成 M+N。

    没有协议，3 个应用乘 4 个工具等于 12 份接线。插入 MCP 这一层，12 份变 7 份。

## Line 2 — USB-C (Frame 2)

    MCP 是 AI 应用的 USB-C 接口。
"""

HOOK = r'''import json, os, re, subprocess
if os.environ.get("EXPLAINER_FAKE_VOICE"):
    from vstudio import asr as _asr, tts as _tts

    def _words(text):
        return re.findall(r"[㐀-鿿]|[A-Za-z0-9][A-Za-z0-9.+-]*", text or "")

    def _synth(text, engine="openai", voice=None, out=None, **kw):
        dur = 0.3 + 0.18 * len(_words(text))
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=f=220:d={dur:.2f}:sample_rate=48000",
                        out], check=True)
        open(out + ".txt", "w", encoding="utf-8").write(text)
        return out

    def _spread(text, t0, dur):
        ws = _words(text)
        step = dur / max(1, len(ws))
        return [dict(w=w, t=round(t0 + k * step, 3), te=round(t0 + (k + 1) * step, 3)) for k, w in enumerate(ws)]

    def _transcribe(path, language=None, **kw):
        words = []
        if os.path.exists(path + ".txt"):
            dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                        path], capture_output=True, text=True).stdout.strip() or 1)
            words = _spread(open(path + ".txt", encoding="utf-8").read(), 0.0, dur)
        else:                                  # the joined narration: each line's words at its offset
            vo = os.path.join(os.path.dirname(path), "vo")
            for n, start, dur in json.load(open(os.path.join(vo, "offsets.json"))):
                words += _spread(open(os.path.join(vo, f"line{n:02d}.wav.txt"), encoding="utf-8").read(), start, dur)
        text = "".join(w["w"] for w in words)
        return dict(language=language or "zh", backend="test", text=text, words=words,
                    segments=[dict(start=words[0]["t"] if words else 0, end=words[-1]["te"] if words else 0, text=text,
                                   words=[dict(word=w["w"], start=w["t"], end=w["te"]) for w in words])])
    _tts.synth = _synth
    _tts.installed = lambda e: True
    _asr.transcribe = _transcribe
if os.environ.get("EXPLAINER_FAKE_BIN"):
    # the app puts Homebrew / ~/.local/bin first on PATH: the stand-ins are pinned here instead
    _bin = os.environ["EXPLAINER_FAKE_BIN"]
    from vstudio import llm as _llm
    _find = _llm.find_cli
    _llm.find_cli = lambda name, opts=None: os.path.join(_bin, "claude") if name == "claude" else _find(name, opts)
    from vstudio.project import build as _build
    _run = _build.Env.run

    def _env_run(self, argv, *a, **k):
        if argv and str(argv[0]) == "npx":
            argv = [os.path.join(_bin, "npx"), *argv[1:]]
        return _run(self, argv, *a, **k)
    _build.Env.run = _env_run
'''

CLAUDE = r'''#!{python}
"""Claude Code, for the test: plans a storyboard, draws a scene; "times out" while ROOT/claude-down exists."""
import json, os, re, sys
argv = sys.argv[1:]
system = argv[argv.index("--system-prompt") + 1] if "--system-prompt" in argv else ""
prompt = sys.stdin.read()
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sid_m = re.search(r"SCENE_ID = (\S+),", prompt)
with open(os.path.join(root, "claude.log"), "a", encoding="utf-8") as f:
    f.write(json.dumps(dict(kind="scene" if "motion designer" in system else "plan" if "director" in system else
                            "other", effort=argv[argv.index("--effort") + 1] if "--effort" in argv else None,
                            scene=sid_m.group(1) if sid_m else None, offline="XMLHttpRequest" in system,
                            fetch_fix="fetch() is not allowed" in prompt)) + "\n")
# the scenes listed in ROOT/claude-fetch: "drawn" with a fetch() call every time (her MCP course's scene 14)
fetchy = open(os.path.join(root, "claude-fetch")).read().split() if os.path.exists(os.path.join(root, "claude-fetch")) \
    else []


def out(result, error=False):
    print(json.dumps(dict(type="result", is_error=error, result=result, usage={}, modelUsage={"test-model": {}})))
    sys.exit(1 if error else 0)


if "motion designer" in system:
    if os.path.exists(os.path.join(root, "claude-down")):
        out("Request timed out", error=True)
    m = re.search(r"SCENE_ID = (\S+), W = (\d+), H = (\d+), DURATION = (\d+(?:\.\d+)?)", prompt)
    sid, w, h, d = m.group(1), m.group(2), m.group(3), float(m.group(4))
    extra = 'fetch("/a2a/agents.json").then((r) => r.json());' if sid in fetchy else ""
    out(f"""<template>
  <style>#root {{ position: absolute; inset: 0; width: 100%; height: 100%; overflow: hidden; }}</style>
  <div id="root" data-composition-id="{sid}" data-width="{w}" data-height="{h}" data-duration="{d:.2f}">
    <div id="{sid}-stage" class="clip" data-start="0" data-duration="{d:.2f}" data-track-index="1">
      <svg viewBox="0 0 {w} {h}"><rect id="{sid}-a" x="200" y="300" width="300" height="120" rx="14" fill="none"
        stroke="#58C4DD" stroke-width="3"/><rect id="{sid}-b" x="1300" y="300" width="300" height="120" rx="14"
        fill="none" stroke="#5CD0B3" stroke-width="3"/><path id="{sid}-arrow" d="M500 360 L1300 360" stroke="#F4D35E"
        stroke-width="3"/><text x="350" y="370" fill="#ECEEF2">App</text><text x="1450" y="370" fill="#ECEEF2">MCP</text></svg>
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <script>(function () {{ {extra}
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo("#{sid}-arrow", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.6 }}, 0.3);
    window.__timelines["{sid}"] = tl; }})();</script>
</template>""")
if "director" in system:
    ids = re.findall(r'"id": "(f\d\d-[^"]+)"', prompt)
    out(json.dumps(dict(summary="two scenes", scenes=[dict(id=i, shots='- 0.3s ("x"): App boxes wire to MCP')
                                                      for i in ids])))
out("{}")
'''

NPX = r'''#!{python}
"""npx, for the test: `hyperframes render -o OUT` makes a plain video of the narration's length (ffmpeg)."""
import os, subprocess, sys, time
a = sys.argv[1:]
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if a[:2] == ["hyperframes", "render"]:
    o = a[a.index("-o") + 1]
    os.makedirs(os.path.dirname(o), exist_ok=True)
    nar = os.path.join(os.getcwd(), "audio", "narration.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x0B1020:s=1280x720:r=30", "-i", nar,
                    "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", o],
                   check=True)
    with open(os.path.join(root, "renders.log"), "a", encoding="utf-8") as f:
        f.write(f"{time.time()} {os.getcwd()}\n")
sys.exit(0)
'''

TEXT_SCENE = """<template>
  <div id="root" data-composition-id="{sid}" data-width="1920" data-height="1080" data-duration="{dur:.2f}">
    <div id="{sid}-stage" class="clip" data-start="0" data-duration="{dur:.2f}" data-track-index="1">
      <div id="{sid}-title">{sid}</div><div id="{sid}-lines">没有协议，3 个应用乘 4 个工具等于 12 份接线</div></div></div>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <script>(function () {{ const tl = gsap.timeline({{ paused: true }}); window.__timelines["{sid}"] = tl; }})();</script>
</template>
"""


def write_exe(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.replace("{python}", sys.executable, 1))
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


os.makedirs(os.path.join(ROOT, "hook"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "bin"), exist_ok=True)
with open(os.path.join(ROOT, "hook", "sitecustomize.py"), "w", encoding="utf-8") as f:
    f.write(HOOK)
write_exe(os.path.join(ROOT, "bin", "claude"), CLAUDE)
write_exe(os.path.join(ROOT, "bin", "npx"), NPX)
script = os.path.join(ROOT, "SCRIPT.md")
with open(script, "w", encoding="utf-8") as f:
    f.write(SCRIPT)
os.environ.update(EXPLAINER_FAKE_VOICE="1", EXPLAINER_FAKE_BIN=os.path.join(ROOT, "bin"), VSTUDIO_SCENE_LINT="0",
                  VSTUDIO_LLM_PLANNER_PROVIDER="claude-code", VSTUDIO_CLI_EXTRA_DIRS="",
                  PATH=os.path.join(ROOT, "bin") + os.pathsep + os.environ.get("PATH", ""),
                  PYTHONPATH=os.pathsep.join([os.path.join(ROOT, "hook"), os.path.join(REPO, "lib")]))
sys.path.insert(0, os.path.join(ROOT, "hook"))
import sitecustomize  # noqa: E402,F401  (this process too: the gates run here)

from vstudio.project import autopilot as AP  # noqa: E402
from vstudio.project import drafts as DR  # noqa: E402
from vstudio.project.core import Project  # noqa: E402


def course(name):
    p = Project.create(os.path.join(ROOT, "projects", name), recipe="explainer", name=f"MCP course {name}",
                       params=dict(tts_engine="kokoro"), items=[dict(id="ep1", inputs=dict(script=script))])
    p.data["prompt"] = "把讲稿做成一集图解动画的课程视频，中文讲解"
    p.save()
    AP.configure(p, on=True, judge=False)
    return p


# ---- Needs you: the model plans the storyboard, then does not answer the scenes
open(os.path.join(ROOT, "claude-down"), "w").close()
needs = course("needs")
r1 = Project(needs.dir).run()

# ---- finished the way hers was: an older engine drew text lines (by: rules), rendered and exported
plain = course("plain")
for _ in range(3):
    Project(plain.dir).run()
    if any(x["id"] == "scenes" for x in Project(plain.dir).pending()):
        break
item = os.path.join(plain.dir, "items", "ep1")
comp = os.path.join(item, "compositions")
win = json.load(open(os.path.join(item, "audio", "scenes.json")))["scenes"]
cfg = json.load(open(os.path.join(item, "scenes.config.json")))["scenes"]
os.makedirs(comp, exist_ok=True)
for sc, w in zip(cfg, win):
    with open(os.path.join(comp, f"{sc['id']}.html"), "w", encoding="utf-8") as f:
        f.write(TEXT_SCENE.format(sid=sc["id"], dur=w["duration"]))
from vstudio.project.adapters.explainer import scene_support  # noqa: E402
scene_support(item, comp)
DR.write_side(comp, "scenes", dict(by="rules"))
q = Project(plain.dir)
q.answer("scenes", dict(done=True), items=["ep1"], auto=True, meta=dict(by="rules", reason="the drafted file",
                                                                        reason_code="drafted"))
r2 = Project(plain.dir).run()
os.remove(os.path.join(ROOT, "claude-down"))
print(json.dumps(dict(needs=needs.dir, plain=plain.dir, bin=os.path.join(ROOT, "bin"), hook=os.path.join(ROOT, "hook"),
                      needs_exit=r1.get("exit_code"), plain_exit=r2.get("exit_code"),
                      needs_pending=[x["id"] for x in Project(needs.dir).pending()],
                      plain_pending=[x["id"] for x in Project(plain.dir).pending()],
                      rendered=os.path.exists(os.path.join(item, "renders", "ep1.mp4")))))
