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
