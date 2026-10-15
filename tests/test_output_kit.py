"""A launch-kit film in the clip chat (vstudio.project.outkit): her words on her 0.2.7 promo - "这个效果不好，不够高端大气上档次，
且功能完备清晰的展示" - stacked a talking-head treatment on the finished film (editorial look, studio sound, a title band, a
chapter rule, a second music bed). A request about the film's look / pacing / how the features show is now routed to
the launch kit: launch.config.yaml keys (backdrop, transitions, each feature's time on screen, pace, camera, music),
written with the header kept and a backup, so the kit renders the film again. Literal edits of the file (cover, trim,
export, a selected range) stay with the editor; the model of the editor path is told what the clip is and its voice /
music treatments are refused. Synthetic project, no model, no network."""
import json
import os
import shutil
import subprocess

import pytest
import yaml

from vstudio import llm
from vstudio.project import outkit as K
from vstudio.project import outputs as O

HER = "这个效果不好，不够高端大气上档次，且功能完备清晰的展示"
HEAD = "# launch.config.yaml - drafted by Reelfold from your clips, your brief and your request.\n# Edit anything.\n"
CFG = dict(out="kit", product=dict(name="Reelfold", version="v0.2.7", one_liner=dict(en="Free and open source for Mac.",
                                                                                    zh="免费开源的 Mac 应用。")),
           brand=dict(theme="night", colors=dict(accent="#4FBFAE")), languages=["en", "zh"],
           platforms=["youtube", "tiktok"],
           features=[dict(id=f"{i:02d}-{n}", shot=f"{i:02d}-{n}", caption=dict(en=en, zh=zh), seconds=s)
                     for i, (n, en, zh, s) in enumerate([("home", "Reelfold 0.2.7", "Reelfold 0.2.7", 4.0),
                                                         ("watch-all", "Watch every job at once.", "所有任务，一屏看完。", 3.0),
                                                         ("publish-calendar", "Plan the week in one sentence.",
                                                          "一句话排好一周。", 5.0),
                                                         ("post-copy", "Copy for each platform.", "每个平台各写各的文案。", 3.0)],
                                                        1)],
           pace=1.1, motion=dict(transition="mix", seconds=0.3, camera="push"),
           demo=dict(title_card=False, end_seconds=4.0, max_seconds=24, min_seconds=12), make=["demo"], music="tech")


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_BATCH_BENCH", str(tmp_path / "bench.json"))
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VSTUDIO_LLM_PROVIDER", "VSTUDIO_LLM_OUTPUT_EDIT_PROVIDER"):
        monkeypatch.delenv(k, raising=False)


def _kit(tmp_path, film=True):
    """A launch-kit project folder: project.yaml, items/main/launch.config.yaml and its demo film."""
    d = tmp_path / "promo"
    item = d / "items" / "main"
    (item / "kit" / "demo").mkdir(parents=True)
    (d / "project.yaml").write_text(yaml.safe_dump(dict(version=1, name="promo", recipe="launch-kit", items=[])))
    (item / "launch.config.yaml").write_text(HEAD + yaml.safe_dump(CFG, allow_unicode=True, sort_keys=False))
    f = item / "kit" / "demo" / "demo-en-16x9.mp4"
    if film:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=3",
                        "-f", "lavfi", "-i", "sine=frequency=330:duration=3", "-shortest", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", str(f)], check=True)
    else:
        f.write_bytes(b"")
    return str(d), str(f)


def _src(tmp_path):
    d, f = _kit(tmp_path, film=False)
    src = K.source(dict(kind="project", owner=d, file=f))
    assert src is not None
    return src


# ------------------------------------------------------------------------------------------------ the request
def test_her_request_goes_to_the_kit_literal_edits_stay_with_the_editor():
    for t in (HER, "make it more premium", "show the features clearly", "slower please", "太快了，看不清",
              "darker background", "背景深一点", "focus on the calendar", "change the music to calm", "no music",
              "make the transitions smoother", "镜头别动"):
        assert K.wants_kit(t), t
    for t in ("换个封面", "cut the first 2 seconds", "去掉开头2秒", "export a 9:16 version", "出一个竖屏版本", "1.2倍速",
              "加个进度条", "Pop “底气” when she says it", "-16 LUFS", "undo that"):
        assert not K.wants_kit(t), t
    assert not K.wants_kit("剪掉这段，太慢了", dict(range=[1.0, 2.0]))          # a selection: the editor's


def test_source_is_only_a_launch_kit_film(tmp_path):
    d, f = _kit(tmp_path, film=False)
    src = K.source(dict(kind="project", owner=d, file=f))
    assert (src["item"], src["cut"], src["lang"], src["aspect"], src["speech"]) == ("main", "demo", "en", "16:9", False)
    ctx = K.context(src)
    assert ctx["kind"] == "launch-kit film" and "NO speech" in ctx["note"] and ctx["kit"]["backdrop"] == "studio"
    assert K.source(dict(kind="work", owner=d, file=f)) is None
    other = os.path.join(d, "items", "main", "exports", "a.mp4")
    assert K.source(dict(kind="project", owner=d, file=other)) is None
    with open(os.path.join(d, "project.yaml"), "w") as fh:
        yaml.safe_dump(dict(recipe="talkinghead"), fh)
    assert K.source(dict(kind="project", owner=d, file=f)) is None


# ------------------------------------------------------------------------------------------------ the change
def test_her_words_become_kit_settings(tmp_path):
    src = _src(tmp_path)
    p = K.plan(src, HER)
    patch = p["patch"]
    assert "pace" not in patch                               # her 1.1x stays: "clearly" = longer scenes, not slower
    assert patch["brand"] == dict(backdrop="deep")           # a night brand: the dark stage
    assert patch["motion"] == dict(seconds=0.45)             # a calmer hand-over, her transitions kept
    secs = {f["id"]: f["seconds"] for f in patch["features"]}
    assert all(s >= 4.0 for s in secs.values()) and secs["03-publish-calendar"] == 5.0
    assert sum(secs.values()) <= 24 - 4.0 + 0.01            # inside the film's length
    codes = [c["code"] for c in p["changes"]]
    assert codes == ["kit-feature-time", "kit-transition", "kit-backdrop"] and all(c["message_zh"] for c in p["changes"])
    assert K.plan(src, "slower please")["patch"] == dict(pace=1.0)
    assert K.plan(src, "focus on the calendar")["patch"] == dict(features=[dict(id="03-publish-calendar", seconds=6.5)])
    assert K.plan(src, "no music")["patch"] == dict(music="none")
    assert K.plan(src, "镜头别动")["patch"] == dict(motion=dict(camera="still"))
    assert K.plan(src, "突出一下")["patch"] == {}             # names nothing the kit has: no change, it asks


SAME = "每一帧都是一个标题和一个小的视频，这样不行，标题太丑了，可以一段是标题，但是不能所有文字都是这样的呈现方式"


def test_every_shot_the_same_and_ugly_titles_become_film_language_settings(tmp_path):
    src = _src(tmp_path)
    assert K.wants_kit(SAME) and K.wants_kit("the titles are ugly") and K.wants_kit("every shot looks the same")
    p = K.plan(src, SAME)
    patch = p["patch"]
    assert patch["film"] == dict(variety="lively", text=0.3)          # varied layouts, words <= 30 % of the time
    assert patch["type"] == dict(weight=520, scale=0.9)               # lighter, smaller type
    assert "brand" not in patch                                       # a type / layout ask keeps the light look
    codes = [c["code"] for c in p["changes"]]
    assert {"kit-film-variety", "kit-film-text", "kit-type"} <= set(codes) and all(c["message_zh"] for c in p["changes"])
    assert K.plan(src, "more variety please")["patch"]["film"] == dict(variety="lively", text=0.35)
    assert K.plan(src, "titles are ugly")["patch"] == dict(film=dict(text=0.3), type=dict(weight=520, scale=0.9))
    assert not K.wants_kit("加个封面")
    done = K.apply(src, patch)                                         # the kit accepts it as written
    cfg = yaml.safe_load(open(done["config"], encoding="utf-8"))
    assert cfg["film"]["variety"] == "lively" and cfg["type"]["scale"] == 0.9


def test_apply_keeps_her_header_and_a_backup_and_refuses_a_bad_config(tmp_path):
    src = _src(tmp_path)
    before = open(src["config"], encoding="utf-8").read()
    done = K.apply(src, K.plan(src, HER)["patch"])
    text = open(src["config"], encoding="utf-8").read()
    assert text.startswith(HEAD)
    cfg = yaml.safe_load(text)
    assert cfg["brand"] == dict(theme="night", colors=dict(accent="#4FBFAE"), backdrop="deep")
    assert cfg["motion"] == dict(transition="mix", seconds=0.45, camera="push") and cfg["pace"] == 1.1
    assert [f["caption"] for f in cfg["features"]] == [f["caption"] for f in CFG["features"]]
    assert open(done["backup"], encoding="utf-8").read() == before
    with pytest.raises(ValueError):
        K.apply(src, dict(motion=dict(transition="wobble")))
    assert yaml.safe_load(open(src["config"], encoding="utf-8"))["motion"]["transition"] == "mix"


# ------------------------------------------------------------------------------------------------ the clip chat
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_clip_ai_routes_to_the_kit_and_the_editor_knows_the_film(tmp_path, monkeypatch):
    d, f = _kit(tmp_path)
    oid = "main/demo-en-16x9.mp4"
    monkeypatch.setattr(O, "_project_outputs", lambda pdir, **kw: [dict(id=oid, file=f, item="main", job_state="done",
                                                                  platform=None, orientation=None, title="promo",
                                                                  _rows={}, _params={})])
    monkeypatch.setenv("VSTUDIO_LLM_OUTPUT_EDIT_PROVIDER", "claude-code")
    seen = []

    def fake_complete(task, system, prompt, schema=None, provider=None, model=None, **kw):
        seen.append(prompt)
        return dict(text="", json=dict(summary="s", ops=[
            dict(op="effect_add", effect="studio-sound", start=0),
            dict(op="effect_add", effect="music-bed", start=0, params=dict(mood="tech")),
            dict(op="effect_add", effect="progress-bar-pil", start=0)]),
            usage={}, cost_usd=0.0, provider="claude-code", model="m")
    monkeypatch.setattr(llm, "complete", fake_complete)
    # her words: the kit, no model call, no editor op
    r = O.ai(d, oid, HER)
    assert seen == [] and r["route"] == "launch-kit" and r["proposed"] == [] and r["turn"]
    assert r["kit"]["patch"]["brand"] == dict(backdrop="deep") and not r["kit"]["applied"]
    assert [w["code"] for w in r["warnings"]] == ["kit-feature-time", "kit-transition", "kit-backdrop"]
    assert O.show(d, oid)["history"]["undo"] == 0
    turn = O.chat(d, oid)["turns"][-1]
    assert turn["status"] == "note" and turn["warnings"][0]["code"] == "kit-feature-time"
    # written through the CLI's kit verb (what the desk calls), then the kit re-renders
    done = O.kit_apply(d, oid, r["kit"]["patch"])
    assert yaml.safe_load(open(done["config"], encoding="utf-8"))["brand"]["backdrop"] == "deep"
    # an editor request: the model is told it is a launch-kit film with no speech; voice / music treatments refused
    r = O.ai(d, oid, "加个进度条")
    ctx = json.loads(seen[-1].split("Context (JSON):\n", 1)[1])
    assert ctx["source"]["kind"] == "launch-kit film" and ctx["source"]["speech"] is False
    assert [p["normalized"]["effect"] for p in r["proposed"]] == ["progress-bar-pil"]
    assert sorted(x["error"]["code"] for x in r["dropped"]) == ["kit-has-music", "kit-no-voice"]
