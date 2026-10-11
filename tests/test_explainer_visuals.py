"""The explainer's visuals (her MCP course, 2026-10-11): Claude Code timed out, the scenes step fell back to the rules
and the autopilot approved a storyboard full of "TODO: what appears" and a scenes folder of plain text lines - a
5:34 video of sentences in the top-left corner. Now:

* the storyboard stage's "TODO" shots are a skeleton (never an answer): the AI plans each beat, the rules only drop
  the TODOs; scenes are drawn by the routed AI only (diagrams and motion on the cue times), checked before they are
  kept, never a text-only fallback;
* the autopilot never approves a draft with a placeholder, nor a rules draft of a step that needs a model: it asks
  the routed AI again, else stops in Needs you with "The visuals need an AI model — Claude Code didn't answer";
* a finished explainer's visuals are redone without the voice (``remake --do visuals``)."""
import json
import os
import re

import pytest

from vstudio import llm
from vstudio.project import autopilot as AP
from vstudio.project import drafts as DR
from vstudio.project.adapters import explainer as X
from vstudio.project.adapters import explainer_scenes as S
from vstudio.project.core import Project
from vstudio.project.remake import RemakeError, remake

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WF = os.path.join(ROOT, "workflows", "explainer")

SCRIPT = """# SCRIPT — MCP

Narration: 中文讲解

---

## Line 1 — 乘法变加法 (Frame 1)

**Delivery:** Calm. 画面：M×N 的连线变成 M+N。

    没有协议，3 个应用乘 4 个工具等于 12 份接线。插入 MCP 这一层，12 份变 7 份。

## Line 2 — USB-C (Frame 2)

    MCP 是 AI 应用的 USB-C 接口。
"""

TODO_SHOTS = ('Scene title fades in at 0.2s.\n- 0.3s ("没有协议，3 个应用…"): reveal 3, 4, 12 (mono; count up or pop on '
              'the word) — TODO\n- 3.0s ("插入 MCP 这一层…"): TODO: what appears (one visual per idea)\n'
              'Ambient: whole group drifts up 6px over the scene.')


def scene_html(sid, dur, w=1920, h=1080):
    """A scene the way the channel draws them: a diagram (boxes + an arrow) built on the timeline."""
    return f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; width: 100%; height: 100%; overflow: hidden; }}
  </style>
  <div id="root" data-composition-id="{sid}" data-width="{w}" data-height="{h}" data-duration="{dur:.2f}">
    <div id="{sid}-stage" class="clip" data-start="0" data-duration="{dur:.2f}" data-track-index="1">
      <svg id="{sid}-svg" viewBox="0 0 {w} {h}">
        <rect id="{sid}-a" x="200" y="300" width="300" height="120" rx="14" fill="none" stroke="#58C4DD" stroke-width="3"/>
        <rect id="{sid}-b" x="1300" y="300" width="300" height="120" rx="14" fill="none" stroke="#5CD0B3" stroke-width="3"/>
        <path id="{sid}-arrow" d="M500 360 L1300 360" stroke="#F4D35E" stroke-width="3"/>
        <text x="350" y="370" fill="#ECEEF2">App</text><text x="1450" y="370" fill="#ECEEF2">MCP</text>
      </svg>
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});
      tl.fromTo("#{sid}-a", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.6 }}, 0.2);
      tl.fromTo("#{sid}-arrow", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.6 }}, 1.0);
      window.__timelines["{sid}"] = tl;
    }})();
  </script>
</template>"""


TEXT_LINES = """<template>
  <div id="root" data-composition-id="{sid}" data-width="1920" data-height="1080" data-duration="{dur:.2f}">
    <div id="{sid}-stage" class="clip" data-start="0" data-duration="{dur:.2f}" data-track-index="1">
      <div id="{sid}-title">Tool Calling</div><div id="{sid}-lines"></div></div></div>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <script>(function () {{ const R = [{{"t": 0.3, "text": "没有协议，3 个应用乘 4 个工具等于 12 份接线"}}];
    const tl = gsap.timeline({{ paused: true }}); window.__timelines["{sid}"] = tl; }})();</script>
</template>"""


def scene_model(calls=None, bad=()):
    """The routed model drawing scenes (Claude Code here): a valid scene for the id the brief names."""
    def complete(task, system, prompt, schema=None, **kw):
        m = re.search(r"SCENE_ID = (\S+), W = (\d+), H = (\d+), DURATION = (\d+(?:\.\d+)?)", prompt)
        if calls is not None:
            calls.append(dict(id=m.group(1), effort=kw.get("effort"), timeout=kw.get("timeout")))
        if m.group(1) in bad:
            return dict(provider="claude-code", model="test", text="Here is a plan.")
        return dict(provider="claude-code", model="test",
                    text=scene_html(m.group(1), float(m.group(4)), int(m.group(2)), int(m.group(3))))
    return complete


def no_model(*a, **k):
    raise llm.LLMError("claude CLI timed out after 600.0 s")


def item_dir(tmp_path, shots=TODO_SHOTS):
    """An explainer item after its voice: the script, the storyboard skeleton, the scene windows and cues."""
    d = tmp_path / "items" / "ep1"
    (d / "audio").mkdir(parents=True)
    (d / "subtitles").mkdir()
    (d / "SCRIPT.md").write_text(SCRIPT, encoding="utf-8")
    cfg = dict(platform="youtube", scenes=[dict(id="f01-mn", transition=None, shots=shots),
                                           dict(id="f02-usb-c", transition=["fade", 0.6], shots=shots)])
    (d / "scenes.config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    (d / "audio" / "scenes.json").write_text(json.dumps(dict(total=12.0, scenes=[
        dict(frame=1, start=0.0, end=8.0, duration=8.0), dict(frame=2, start=8.0, end=12.0, duration=4.0)])))
    (d / "audio" / "scene_cues.json").write_text(json.dumps({
        "1": [dict(t=0.3, te=3.0, text="没有协议，3 个应用乘 4 个工具等于 12 份接线"),
              dict(t=3.1, te=7.5, text="插入 MCP 这一层，12 份变 7 份")],
        "2": [dict(t=0.2, te=3.5, text="MCP 是 AI 应用的 USB-C 接口")]}, ensure_ascii=False), encoding="utf-8")
    return d


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_LLM_PLANNER_PROVIDER", "claude-code")      # her route: Claude Code
    monkeypatch.setattr(S, "LINT", False)                                     # no real renderer here
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VSTUDIO_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)


def _ctx(tmp_path, d):
    return DR.Ctx(str(tmp_path), "ep1", dict(_item_dir=str(d)), "explainer")


def _cp(cid):
    from vstudio.project import manifests as M
    return next(c for c in M.get("explainer")["checkpoints"] if c["id"] == cid)


# --------------------------------------------------------------------------- the storyboard
def test_the_stage_s_todo_storyboard_is_a_skeleton_never_an_answer(tmp_path):
    d = item_dir(tmp_path)
    path = str(d / "scenes.config.json")
    assert DR.state(path, None, _cp("storyboard"), "explainer") == "template"     # "TODO" shots: not a draft
    rec = DR.ensure(_ctx(tmp_path, d), _cp("storyboard"), path, complete=no_model)
    text = open(path, encoding="utf-8").read()
    assert rec["by"] == "rules" and "TODO" not in text                             # the rules only drop the TODOs
    assert "reveal 3, 4, 12" in text and "draw its key term as a diagram" in text
    assert DR.state(path, None, _cp("storyboard"), "explainer") == "drafted"


def test_the_ai_plans_each_beat_of_the_storyboard(tmp_path):
    d = item_dir(tmp_path)
    seen = []

    def planner(task, system, prompt, schema=None, **kw):
        seen.append(prompt)
        ids = re.findall(r'"id": "(f\d\d-[^"]+)"', prompt)
        return dict(provider="claude-code", model="t", json=dict(summary="two scenes", scenes=[
            dict(id=i, shots='- 0.3s ("没有协议"): 3 App boxes wire to 4 Tool boxes, 12 red lines') for i in ids]))
    path = str(d / "scenes.config.json")
    rec = DR.ensure(_ctx(tmp_path, d), _cp("storyboard"), path, complete=planner)
    assert rec["by"] == "ai" and rec["provider"] == "claude-code"
    cfg = json.load(open(path, encoding="utf-8"))
    assert [s["shots"] for s in cfg["scenes"]] == ['- 0.3s ("没有协议"): 3 App boxes wire to 4 Tool boxes, 12 red lines'] * 2
    assert cfg["platform"] == "youtube" and cfg["scenes"][1]["transition"] == ["fade", 0.6]
    assert "画面：M×N" in seen[0]                                                  # her direction reaches the plan


# --------------------------------------------------------------------------- a scene is checked before it is kept
def test_a_text_lines_scene_is_refused_and_a_diagram_passes():
    assert S.scene_problems(scene_html("f01-mn", 8.0), "f01-mn", 8.0, 1920, 1080) == []
    bad = S.scene_problems(TEXT_LINES.format(sid="f01-mn", dur=8.0), "f01-mn", 8.0, 1920, 1080)
    assert any("draw the idea" in p for p in bad)
    assert any("TODO" in p for p in S.scene_problems(scene_html("f01-mn", 8.0).replace("App", "TODO"), "f01-mn"))
    assert any("data-duration" in p for p in S.scene_problems(scene_html("f01-mn", 3.0), "f01-mn", 8.0))
    assert S.extract_template("Sure!\n```html\n" + scene_html("x", 1) + "\n```") == scene_html("x", 1)


def test_scenes_are_drawn_by_the_routed_ai_in_parallel_on_the_cue_times(tmp_path):
    d = item_dir(tmp_path)
    calls = []
    r = S.author_scenes(str(d), WF, request="图解动画", complete=scene_model(calls))
    assert r["ok"] and sorted(r["written"]) == ["f01-mn", "f02-usb-c"] and r["provider"] == "claude-code"
    assert {c["effort"] for c in calls} == {"medium"} and min(c["timeout"] for c in calls) >= 300
    html = (d / "compositions" / "f01-mn.html").read_text(encoding="utf-8")
    assert html.startswith(S.AI_MARK) and 'data-duration="8.00"' in html
    assert S.scenes_complete(str(d / "compositions"))
    # what the brief tells the model: the cue table with its times, the narration never as on-screen text
    prompt = S.scene_prompt(S.scene_inputs(str(d), WF), S.scene_inputs(str(d), WF)["scenes"][0], "图解动画")
    assert "|   0.30 |   3.00 | 没有协议" in prompt and "画面：M×N" in prompt and "TODO" not in prompt


def test_no_model_draws_nothing_and_says_so_plainly(tmp_path):
    d = item_dir(tmp_path)
    r = S.author_scenes(str(d), WF, complete=no_model, parallel=2)
    assert not r["ok"] and r["error_code"] == "needs-model" and r["written"] == []
    assert r["error"] == ("The visuals need an AI model — Claude Code didn't answer. Try again, or choose another "
                          "model in Settings › AI.")
    assert not [f for f in os.listdir(d / "compositions") if f.endswith(".html")]      # never a text-only scene
    # through the drafts: nothing usable, the reason and its code in the payload record
    rec = DR.ensure(_ctx(tmp_path, d), _cp("scenes"), str(d / "compositions"), complete=no_model)
    assert rec["failed_code"] == "ai-needs-model" and "Claude Code didn't answer" in rec["failed"]
    assert DR.state(str(d / "compositions"), None, _cp("scenes"), "explainer") == "missing"


def test_a_second_try_draws_only_the_scenes_still_missing(tmp_path):
    d = item_dir(tmp_path)
    r = S.author_scenes(str(d), WF, complete=scene_model(bad={"f02-usb-c"}))
    assert r["written"] == ["f01-mn"] and r["error_code"] == "scene-failed"
    assert DR.state(str(d / "compositions"), None, _cp("scenes"), "explainer") == "template"   # not every scene
    calls = []
    r = S.author_scenes(str(d), WF, complete=scene_model(calls))
    assert r["ok"] and [c["id"] for c in calls] == ["f02-usb-c"]


def test_a_scene_the_renderer_s_lint_refuses_is_drawn_again_with_the_fix(tmp_path, monkeypatch):
    d = item_dir(tmp_path)
    monkeypatch.setattr(S, "LINT", True)
    finding = "renderer lint gsap_css_transform_conflict: CSS transform and a GSAP scaleX. Fix: use tl.fromTo"
    checks = []
    monkeypatch.setattr(S, "lint_scenes", lambda sd, scenes, W, H: checks.append(1) or (
        {"f02-usb-c": [finding]} if len(checks) == 1 else {}))
    prompts = []
    model = scene_model()

    def complete(task, system, prompt, **kw):
        prompts.append(prompt)
        return model(task, system, prompt, **kw)
    r = S.author_scenes(str(d), WF, complete=complete)
    assert r["ok"] and r["linted"] == ["f02-usb-c"] and len(prompts) == 3 and len(checks) == 2   # checked again
    assert finding in prompts[-1] and "Your previous version" in prompts[-1] and "SCENE_ID = f02-usb-c" in prompts[-1]


# --------------------------------------------------------------------------- the autopilot
def _pay(cp, **kw):
    return dict(dict(id=cp["id"], kind=cp["kind"], item="ep1", default=dict(done=True), draft_state="drafted",
                     review=dict(summary=dict(code="draft.items", params=dict(n=2)))), **kw)


def test_autopilot_never_approves_a_rules_draft_of_a_step_that_needs_a_model():
    for cid in ("script", "storyboard", "scenes"):
        cp = _cp(cid)
        d = AP.rules(cp, _pay(cp, draft_by="rules"))
        assert d["blocker"] == "needs-model", cid
        what = "script" if cid == "script" else "visuals"
        assert d["reason"].startswith(f"The {what} need" if what == "visuals" else "The script needs")
        assert "Claude Code didn't answer" in d["reason"] and d["params"]["provider"] == "claude-code"
        assert AP.rules(cp, _pay(cp, draft_by="ai"))["value"] == dict(done=True)
    # the cues step's rules draft (the workflow's own pairing) stays fine
    assert AP.rules(_cp("cues"), _pay(_cp("cues"), draft_by="rules"))["value"] == dict(done=True)


def test_autopilot_never_approves_a_draft_with_a_placeholder():
    cp = _cp("cues")
    d = AP.rules(cp, _pay(cp, draft_by="her", placeholders=3))
    assert d["blocker"] == "needs-input" and "placeholder" in d["reason"]


def test_a_model_that_did_not_draw_the_scenes_stops_in_needs_you():
    cp = _cp("scenes")
    msg = S.needs_model_message("claude-code")
    d = AP.rules(cp, dict(id="scenes", kind="author", item="ep1", default=None, draft_error=msg,
                          draft_error_code="ai-needs-model", draft_error_params=dict(provider="claude-code")))
    assert d["blocker"] == "needs-model" and d["reason"] == msg


def test_autopilot_asks_the_routed_ai_again_before_it_stops(tmp_path, monkeypatch):
    p = Project.create(str(tmp_path / "course"), recipe="explainer", items=[dict(id="ep1")])
    p.data["autopilot"] = dict(on=True, judge=False)
    p.save()
    cp = _cp("storyboard")
    asked = []
    monkeypatch.setattr(AP, "_redraft", lambda project, c, pay: asked.append(c["id"]) or _pay(c, draft_by="ai"))
    d = AP.decide(Project(p.dir), _pay(cp, draft_by="rules"))
    assert asked == ["storyboard"] and d["by"] == "ai" and d["value"] == dict(done=True)
    monkeypatch.setattr(AP, "_redraft", lambda project, c, pay: _pay(c, draft_by="rules"))
    assert AP.decide(Project(p.dir), _pay(cp, draft_by="rules"))["blocker"] == "needs-model"


# --------------------------------------------------------------------------- redo the visuals of a finished one
def finished(tmp_path):
    """Her course after the old engine: rules scenes (text lines), captions, a render, exports; the voice made."""
    p = Project.create(str(tmp_path / "course"), recipe="explainer", name="MCP course", items=[dict(id="ep1")])
    p.data["prompt"] = "把讲稿做成图解动画课程视频"
    p.save()
    d = tmp_path / "course" / "items" / "ep1"
    src = item_dir(tmp_path / "src", shots="- 0.3s: a diagram")
    for f in ("SCRIPT.md", "scenes.config.json", "audio/scenes.json", "audio/scene_cues.json"):
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        (d / f).write_bytes((src / f).read_bytes())
    (d / "audio" / "narration.wav").write_bytes(b"RIFF-the-voice")
    comp = d / "compositions"
    comp.mkdir()
    for sid, dur in (("f01-mn", 8.0), ("f02-usb-c", 4.0)):
        (comp / f"{sid}.html").write_text(TEXT_LINES.format(sid=sid, dur=dur), encoding="utf-8")
    (comp / "captions.html").write_text("<template>captions</template>", encoding="utf-8")
    DR.write_side(str(comp), "scenes", dict(by="rules"))
    (d / "renders").mkdir()
    (d / "renders" / "ep1.mp4").write_bytes(b"old video")
    return Project(p.dir), d


@pytest.fixture
def no_run(monkeypatch):
    runs = []
    monkeypatch.setattr(Project, "stale", lambda self: {})
    monkeypatch.setattr(Project, "run", lambda self, **kw: runs.append(kw) or dict(exit_code=0, status="done"))
    return runs


def test_redo_the_visuals_draws_every_scene_again_and_keeps_the_voice(tmp_path, monkeypatch, no_run):
    p, d = finished(tmp_path)
    vis = [c for c in AP.choices(p) if c.get("remake_as") == "visuals"]
    assert vis == [dict(checkpoint="scenes", kind="author", item="ep1", pick=None, choice="rules", options=[],
                        by="rules", remake_as="visuals")]
    monkeypatch.setattr(llm, "complete", scene_model())
    evs = []
    r = remake(p, "ep1", {"visuals": None}, emit=evs.append)
    assert r["ok"] and r["done"][0]["checkpoint"] == "scenes" and sorted(r["done"][0]["scenes"]) == ["f01-mn",
                                                                                                    "f02-usb-c"]
    for sid in ("f01-mn", "f02-usb-c"):
        assert (d / "compositions" / f"{sid}.html").read_text(encoding="utf-8").startswith(S.AI_MARK)
    assert (d / "compositions" / "captions.html").read_text() == "<template>captions</template>"
    assert (d / "audio" / "narration.wav").read_bytes() == b"RIFF-the-voice"                # the voice kept
    backup = r["done"][0]["backup"]
    assert backup and os.path.exists(os.path.join(backup, "f01-mn.html"))
    assert os.sep + os.path.join("state", "remake", "ep1", "visuals") + os.sep in backup   # not a stage folder
    assert no_run == [dict(only=["ep1"], on_event=no_run[0]["on_event"])]                 # index/render/export
    q = Project(p.dir)
    assert q.data["answers"]["scenes"]["ep1"]["value"] == dict(done=True)
    assert [c["choice"] for c in AP.choices(q) if c.get("remake_as")] == ["ai"]
    assert [e["event"] for e in evs][0] == "run-start" and evs[-1]["event"] == "project-end"


def test_redo_the_visuals_without_a_model_keeps_the_video_and_says_why(tmp_path, monkeypatch, no_run):
    p, d = finished(tmp_path)
    before = {f: (d / "compositions" / f).read_bytes() for f in os.listdir(d / "compositions")}
    monkeypatch.setattr(llm, "complete", no_model)
    evs = []
    with pytest.raises(RemakeError, match="The visuals need an AI model — Claude Code didn't answer"):
        remake(p, "ep1", {"visuals": None}, emit=evs.append)
    assert {f: (d / "compositions" / f).read_bytes() for f in os.listdir(d / "compositions")} == before
    fail = next(e for e in evs if e["event"] == "stage-fail")
    assert fail["code"] == "ai-needs-model" and fail["params"]["what"] == "visuals" and no_run == []


def test_redo_the_visuals_never_makes_the_voice_again(tmp_path, monkeypatch, no_run):
    p, d = finished(tmp_path)
    monkeypatch.setattr(Project, "stale", lambda self: {"ep1": ["voice", "narration", "render"]})
    monkeypatch.setattr(llm, "complete", scene_model())
    with pytest.raises(RemakeError, match="narration would be made again"):
        remake(p, "ep1", {"visuals": None})
    assert no_run == []


def test_the_cli_names_it_visuals(tmp_path, monkeypatch, no_run):
    from vstudio.project import cli
    p, d = finished(tmp_path)
    monkeypatch.setattr(llm, "complete", scene_model())
    assert cli.main(["remake", "--dir", p.dir, "--item", "ep1", "--do", "visuals", "--json"]) == 0
    assert (d / "compositions" / "f01-mn.html").read_text(encoding="utf-8").startswith(S.AI_MARK)


# --------------------------------------------------------------------------- a scene that keeps calling fetch()
# her MCP course, 2026-10-11: after ~22 min the redo failed on "1 of 14 scenes could not be drawn (f14-mcp-a2a:
# remove fetch())" and threw the other 13 away. Now the brief forbids the network up front, the repair round gets the
# exact finding and its fix with the rejected version, and a scene that still fails keeps its old version.
def fetch_scene(sid, dur, w=1920, h=1080):
    return scene_html(sid, dur, w, h).replace("const tl =", 'fetch("/a2a/agents.json").then((r) => r.json());\n      const tl =')


def fetching_model(prompts, always=(), once=()):
    """Claude Code drawing scenes, calling fetch() in ``always`` scenes every time, in ``once`` only the first time."""
    def complete(task, system, prompt, schema=None, **kw):
        m = re.search(r"SCENE_ID = (\S+), W = (\d+), H = (\d+), DURATION = (\d+(?:\.\d+)?)", prompt)
        sid, dur = m.group(1), float(m.group(4))
        prompts.append((sid, prompt))
        n = sum(1 for s, _p in prompts if s == sid)
        make = fetch_scene if sid in always or (sid in once and n == 1) else scene_html
        return dict(provider="claude-code", model="test", text=make(sid, dur, int(m.group(2)), int(m.group(3))))
    return complete


def test_the_brief_forbids_the_network_up_front():
    for api in ("fetch()", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon", "import()", "<iframe>",
                "localStorage"):
        assert api in S.SYSTEM, api
    assert "INLINE" in S.SYSTEM


def test_fetch_is_refused_with_its_fix_but_a_code_card_showing_it_is_not():
    bad = S.scene_problems(fetch_scene("f14", 8.0), "f14", 8.0, 1920, 1080)
    assert bad == ["fetch() is not allowed: the scene renders offline with no network: write the data inline in the "
                   "script as a constant (const items = [...]); to SHOW a request on a code card, put it in an SVG "
                   "<text> label, never call it"]
    assert S.problem_kind(bad) == "network"
    card = scene_html("f14", 8.0).replace(
        "const tl =", 'const code = ["const r = await fetch(\\"/tools\\")", `fetch(url)`]; // fetch() here\n      const tl =')
    card = card.replace("<text x=\"350\"", "<text x=\"200\" y=\"200\">await fetch('/tools')</text><text x=\"350\"")
    assert S.scene_problems(card, "f14", 8.0, 1920, 1080) == []
    for call, what in (("new XMLHttpRequest()", "XMLHttpRequest"), ("new WebSocket('wss://x')", "WebSocket"),
                       ("import('./x.js')", "import()"), ("localStorage.getItem('k')", "browser storage"),
                       ("setTimeout(() => 1, 5)", "timers")):
        html = scene_html("f1", 8.0).replace("const tl =", f"{call};\n      const tl =")
        assert any(p.startswith(f"{what} is not allowed") for p in S.scene_problems(html, "f1", 8.0)), call
    other = scene_html("f1", 8.0).replace("</svg>", '<image href="https://x.com/a.png"/></svg>')
    assert any("outside file" in p for p in S.scene_problems(other, "f1", 8.0))


def test_the_repair_round_gets_the_exact_finding_and_the_rejected_version(tmp_path):
    d = item_dir(tmp_path)
    prompts, log = [], []
    res = S.author_scenes(str(d), WF, complete=fetching_model(prompts, once={"f02-usb-c"}), parallel=1,
                          log=log.append)
    assert res["ok"] and sorted(res["written"]) == ["f01-mn", "f02-usb-c"]
    second = [p for s, p in prompts if s == "f02-usb-c"][1]
    assert "fetch() is not allowed: the scene renders offline with no network: write the data inline" in second
    assert 'fetch("/a2a/agents.json")' in second                    # her previous version, to correct
    assert any("refused by the check" in m and "fetch()" in m for m in log)


def test_a_scene_that_keeps_failing_is_named_plainly(tmp_path):
    d = item_dir(tmp_path)
    prompts = []
    res = S.author_scenes(str(d), WF, complete=fetching_model(prompts, always={"f02-usb-c"}), parallel=1)
    assert not res["ok"] and res["error_code"] == "scene-failed" and res["written"] == ["f01-mn"]
    assert len([s for s, _p in prompts if s == "f02-usb-c"]) == 1 + S.REPAIRS      # the first + the repairs
    assert res["why"] == {"f02-usb-c": "network"}
    assert res["error"] == ("Scene 2 of 2 couldn't be drawn: it tried to load data from the internet, which a video "
                            "can't do. Try again.")
    assert not (d / "compositions" / "f02-usb-c.html").exists()


def test_redo_keeps_the_old_version_of_a_scene_that_failed_and_makes_the_video(tmp_path, monkeypatch, no_run):
    p, d = finished(tmp_path)
    old = (d / "compositions" / "f02-usb-c.html").read_text(encoding="utf-8")
    prompts = []
    monkeypatch.setattr(llm, "complete", fetching_model(prompts, always={"f02-usb-c"}))
    r = remake(p, "ep1", {"visuals": None})
    done = r["done"][0]
    assert done["scenes"] == ["f01-mn"] and done["note"] == "1 of 2 scenes redrawn; scene 2 kept as before"
    assert done["kept"] == [dict(id="f02-usb-c", n=2, how="before", why="network")]
    assert (d / "compositions" / "f01-mn.html").read_text(encoding="utf-8").startswith(S.AI_MARK)
    assert (d / "compositions" / "f02-usb-c.html").read_text(encoding="utf-8") == old          # as before
    assert len(no_run) == 1                                                                    # the video is made
    vis, = [c for c in AP.choices(Project(p.dir)) if c.get("remake_as") == "visuals"]
    assert (vis["options"], vis["kept"], vis["total"]) == (["missing"], done["kept"], 2)
    # "Redraw scene 2": only that one is asked for, the redrawn one stays
    prompts.clear()
    f01 = (d / "compositions" / "f01-mn.html").read_text(encoding="utf-8")
    monkeypatch.setattr(llm, "complete", fetching_model(prompts))
    r = remake(Project(p.dir), "ep1", {"visuals": "missing"})
    assert {s for s, _p in prompts} == {"f02-usb-c"} and r["done"][0]["kept"] == [] and r["done"][0]["note"] is None
    assert (d / "compositions" / "f01-mn.html").read_text(encoding="utf-8") == f01
    assert (d / "compositions" / "f02-usb-c.html").read_text(encoding="utf-8").startswith(S.AI_MARK)
    vis, = [c for c in AP.choices(Project(p.dir)) if c.get("remake_as") == "visuals"]
    assert vis["options"] == [] and "kept" not in vis


def test_a_scene_with_no_old_version_gets_a_simple_diagram_never_text_lines(tmp_path, monkeypatch, no_run):
    p, d = finished(tmp_path)
    (d / "compositions" / "f02-usb-c.html").unlink()
    monkeypatch.setattr(llm, "complete", fetching_model([], always={"f02-usb-c"}))
    r = remake(p, "ep1", {"visuals": None})
    assert r["done"][0]["kept"][0]["how"] == "diagram"
    html = (d / "compositions" / "f02-usb-c.html").read_text(encoding="utf-8")
    assert html.startswith(S.FALLBACK_MARK) and not S.is_ai_scene(str(d / "compositions" / "f02-usb-c.html"))
    body = html.split("\n", 1)[1].strip()
    assert S.scene_problems(body, "f02-usb-c", 4.0, 1920, 1080) == []
    assert ">MCP 是 AI 应用的…<" in body and "<rect" in body and not S.PLACEHOLDER.search(body)
    assert r["done"][0]["note"] == "1 of 2 scenes redrawn; scene 2 kept as a simple diagram"


def test_fallback_diagram_follows_the_cues_in_portrait_and_english():
    inp = dict(canvas=dict(W=1080, H=1920, legacy=False, math=(80, 300, 1000, 1400), describe=""), lang="en",
               scenes=[])
    sc = dict(id="f03-x", label="Agent to agent, over HTTP", duration=12.0, last=True, spoken="",
              cues=[dict(t=0.4, text="MCP connects an agent to its tools and data."),
                    dict(t=4.0, text="A2A lets agents talk to each other."), dict(t=8.0, text="Both work together.")])
    body = S.fallback_scene(inp, sc).split("\n", 1)[1].strip()
    assert S.scene_problems(body, "f03-x", 12.0, 1080, 1920) == []
    labels = re.findall(r"<tspan[^>]*>([^<]*)</tspan>", body)
    assert labels == ["MCP connects", "agent tools", "A2A lets", "agents talk", "Both work", "together"]
    assert body.count("<rect") == 3 and body.count("<line") == 3            # three boxes, two arrows, the spine
    assert "tl.to(q(\"n2\")" in body and "opacity: 0, duration: 0.6" in body       # cue times; the final fade


def test_all_scenes_failing_keeps_the_video_and_try_again_draws_only_the_missing(tmp_path, monkeypatch, no_run):
    p, d = finished(tmp_path)
    before = {f: (d / "compositions" / f).read_bytes() for f in os.listdir(d / "compositions")}
    prompts = []
    monkeypatch.setattr(llm, "complete", fetching_model(prompts, always={"f01-mn", "f02-usb-c"}))
    evs = []
    with pytest.raises(RemakeError, match="2 of 2 scenes couldn't be drawn"):
        remake(p, "ep1", {"visuals": None}, emit=evs.append)
    fail = next(e for e in evs if e["event"] == "stage-fail")
    assert fail["code"] == "stage-visuals-failed"
    assert fail["params"] == dict(scene="1", id="f01-mn", total="2", n="2", why="network")
    assert {f: (d / "compositions" / f).read_bytes() for f in os.listdir(d / "compositions")} == before
    assert no_run == []
    from vstudio.batch import livestatus as LS
    assert (LS.read(p.dir) or {}).get("state") == "done"           # the project is not broken: its video stands
    # a model that stops half-way: Try again goes on with the scenes still missing
    prompts.clear()
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(llm.LLMError("timed out"))
                        if "f02-usb-c" in a[2] else fetching_model(prompts)(*a, **k))
    with pytest.raises(RemakeError, match="AI model"):
        remake(Project(p.dir), "ep1", {"visuals": None})
    assert {s for s, _p in prompts} == {"f01-mn"}
    prompts.clear()
    monkeypatch.setattr(llm, "complete", fetching_model(prompts))
    r = remake(Project(p.dir), "ep1", {"visuals": None})
    assert {s for s, _p in prompts} == {"f02-usb-c"}                                 # only the missing one
    assert sorted(r["done"][0]["scenes"]) == ["f01-mn", "f02-usb-c"] and r["done"][0]["kept"] == []
