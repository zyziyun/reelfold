"""The vlog's edit is drafted, never the probe's starter (a 0.2.7 autopilot rendered every clip's first 8 s, and a fun
reel failed on its placeholder MUSIC.mp3): the AI gets a whole-clip contact sheet per clip (vstudio.footage) and
writes the windows for her request's length; a fun reel also gets a title, end card and a built-in beat track;
without a model the rules spread the length over the clips; an edited starter is hers. Tiny synthetic clips."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from vstudio import footage
from vstudio.project import drafts as DR
from vstudio.project.adapters import vlog as V

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_MUSIC_DIRS", "")


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("dji")
    out = []
    for i in range(2):
        p = str(d / f"DJI_2026061120454{i}_008{i}_D.MP4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=size=320x180:rate=30:duration=12", "-c:v", "libx264", "-pix_fmt", "yuv420p", p],
                       check=True)
        with open(p[:-4] + ".SRT", "w") as f:
            f.write("1\n00:00:00,000 --> 00:00:00,033\n<font size=\"28\">FrameCnt: 1\n2026-06-11 20:45:41.000\n"
                    "[latitude: 47.62655] [longitude: -122.37584] [rel_alt: 43.6 abs_alt: 10.1]</font>\n\n")
        out.append(p)
    return out


def starter(tmp_path, clips, style):
    work = tmp_path / "item" / "work"
    work.mkdir(parents=True)
    path = str(work / "edit.json")
    subprocess.run([sys.executable, os.path.join(ROOT, "workflows/vlog/scripts/probe.py"), *clips, "--init", path,
                    "--style", style], check=True, capture_output=True)
    return path


class Ctx:
    def __init__(self, request):
        self.recipe, self.params, self.data = "vlog", dict(platforms=["youtube"]), dict(name="Trip")
        self._r = request

    def request(self):
        return self._r

    def lang(self):
        return "en"


def test_footage_facts_and_whole_clip_sheet(tmp_path, clips):
    f = footage.facts(clips[0])
    assert f["dur"] == 12.0 and f["recorded"] == "2026-06-11 20:45" and f["time_of_day"] == "evening"
    assert f["city"]["en"] == "Seattle" and f["gps"][0]["lat"] == 47.62655
    text, images, facts = footage.context(clips, str(tmp_path / "s"), ids=["a", "b"])
    assert len(images) == 2 and os.path.getsize(images[0]) > 0 and text.splitlines()[0].startswith("a: DJI_")
    assert footage.tiles_for(200)[-1] < 200 and len(footage.tiles_for(200)) == 20 and len(footage.tiles_for(10)) == 6


def test_target_seconds():
    assert V.target_seconds("Make a 75-second road-trip vlog", 60) == 75
    assert V.target_seconds("a 2-minute history", 60) == 120
    assert V.target_seconds("剪一个 45 秒的短片", 60) == 45
    assert V.target_seconds("the 1990s waterfront", 60) == 60


def test_starter_is_unfinished_until_edited(tmp_path, clips):
    path = starter(tmp_path, clips, "calm")
    assert V.edit_unfinished(path) and DR.state(path, None, dict(id="edit"), "vlog") == "template"
    cfg = json.load(open(path))
    cfg["segments"][0]["start"] = 2
    json.dump(cfg, open(path, "w"))
    assert not V.edit_unfinished(path)          # she (or her agent) edited it: hers, never drafted over


def test_ai_draft_calm_windows_from_the_sheets(tmp_path, clips):
    path = starter(tmp_path, clips, "calm")
    ids = list(json.load(open(path))["clips"])
    seen = {}

    def complete(task, system, body, **kw):
        seen.update(kw, body=body)
        return dict(json=dict(segments=[dict(clip=ids[1], start=3, dur=6), dict(clip=ids[0], start=10, dur=9),
                                        dict(clip="nope", start=0, dur=5)], summary="Two windows."),
                    provider="claude-code", model="test")
    rec = V.draft_edit(Ctx("a 12-second calm film"), dict(id="edit"), path, complete=complete)
    cfg = json.load(open(path))
    assert rec["by"] == "ai" and "starter" not in cfg and len(seen["images"]) == 2 and "12 s" in seen["body"]
    assert cfg["segments"] == [dict(clip=ids[1], start=3.0, dur=6.0), dict(clip=ids[0], start=8.9, dur=3.0)]
    assert DR.state(path, None, dict(id="edit"), "vlog") == "hers"      # no side record in this direct call


def test_ai_draft_fun_gets_title_and_a_beat_track(tmp_path, clips):
    path = starter(tmp_path, clips, "fun")
    ids = list(json.load(open(path))["clips"])
    reply = dict(title=dict(text="Lake Days", sub="Kirkland"), end_card=dict(text="See you"), music_mood="bright",
                 shots=[dict(clip=ids[0], start=1, dur=2, place="Kirkland"), dict(clip=ids[1], start=4, dur=1.5)])
    rec = V.draft_edit(Ctx("a 20-second upbeat short"), dict(id="edit"), path,
                       complete=lambda *a, **k: dict(json=reply, provider="claude-code", model="t"))
    cfg = json.load(open(path))
    assert rec["by"] == "ai" and rec["music_mood"] == "bright" and cfg["title"]["text"] == "Lake Days"
    assert cfg["shots"][0]["place"] == "Kirkland" and os.path.isfile(os.path.join(os.path.dirname(path),
                                                                                  cfg["music"]))
    assert cfg["shots"][0] == dict(clip=ids[0], start=1.0, beats=2, place="Kirkland")     # beats, not seconds


def test_fun_shots_fit_the_beat_budget():
    assert V.fun_body_beats(35) == 33 and V.fun_body_beats(5) == 12
    shots = [dict(clip="a", beats=4)] * 20
    assert len(V.fit_beats(shots, 33)) == 8


def test_no_model_spreads_the_length_over_the_clips(tmp_path, clips):
    path = starter(tmp_path, clips, "calm")

    def boom(*a, **k):
        raise RuntimeError("no provider")
    rec = V.draft_edit(Ctx("a 20-second film"), dict(id="edit"), path, complete=boom)
    cfg = json.load(open(path))
    assert rec["by"] == "rules" and "no provider" in rec["note"]
    assert len(cfg["segments"]) >= 2 and all(s["start"] > 0 for s in cfg["segments"])


def test_generic_draft_of_a_photo_story_sees_the_footage(tmp_path, clips):
    """The photo story's spec is written by the generic drafter: it now gets every clip's facts + contact sheet."""
    proj = tmp_path / "proj"
    proj.mkdir()
    ctx = DR.Ctx(str(proj), "main", dict(_inputs=dict(clips=list(clips)), _item_dir=str(tmp_path / "item")),
                 "photo-story")
    seen = {}

    def complete(task, system, body, **kw):
        seen.update(kw, body=body)
        return dict(json=dict(content="TITLE_EN = 'x'\n", summary="ok"), provider="claude-code", model="t")
    path = str(tmp_path / "item" / "work" / "spec.py")
    rec = DR.generic(ctx, dict(id="story", author=dict(format="spec")), path, complete=complete)
    assert rec["by"] == "ai" and len(seen["images"]) == 2 and "near Seattle" in seen["body"]


def test_photo_story_spec_is_drafted_as_data_with_frames_and_music(tmp_path, clips):
    """A photo story on autopilot used to stop at "write spec.py": the AI drafts it from the contact sheets; only a
    plain-data module is accepted; the frames it names are cut from the clips; a built-in bed when music is asked."""
    from vstudio.project.adapters import photostory as PS
    proj = tmp_path / "proj"
    proj.mkdir()
    ctx = DR.Ctx(str(proj), "main", dict(_inputs=dict(clips=list(clips)), _item_dir=str(tmp_path / "item"),
                                         title="红叶 · 放手"), "photo-story")
    ctx.request_text = "a 45-second calm essay with soft piano, Chinese voice-over"
    stem = os.path.splitext(os.path.basename(clips[0]))[0]
    spec = (f'TITLE_ZH = "红叶"\nMEDIA = dict(images=["frames", "../inputs"], videos="../inputs")\n'
            f'TTS = dict(language="zh")\nSCRIPT = [(0, [("Leaves fall.", "叶子落了。")], [("v{stem}", 1, "still", '
            f'dict(off=2.0))])]\nCOVER = dict(title="红叶", hero=dict(src="cover_a"))\n')
    seen = {}

    def complete(task, system, body, **kw):
        seen.update(kw, body=body)
        return dict(json=dict(content=spec, frames=[dict(name="cover_a", clip=stem, t=3.0),
                                                    dict(name="../evil", clip=stem, t=1)], summary="ok"),
                    provider="claude-code", model="t")
    path = str(tmp_path / "item" / "work" / "spec.py")
    rec = PS.draft_spec(ctx, dict(id="story", author=dict(doc="workflows/photo-story/WORKFLOW.md")), path,
                        complete=complete)
    assert rec["by"] == "ai" and rec["frames"] == 1 and rec["language"] == "zh" and rec["bgm"].startswith("music_")
    assert os.path.isfile(tmp_path / "item" / "work" / "frames" / "cover_a.jpg") and len(seen["images"]) == 2
    assert 'language="zh"' in seen["body"] and "BGM = \"music_" in seen["body"] and PS.spec_language(path) == "zh"
    evil = dict(json=dict(content="import os\nX = 1\n"), provider="claude-code", model="t")
    os.remove(path)
    assert PS.draft_spec(ctx, dict(id="story", author={}), path, complete=lambda *a, **k: evil) is None
    assert not os.path.exists(path)


def test_photo_story_voice_speaks_the_chinese_cue():
    sys.path.insert(0, os.path.join(ROOT, "workflows/photo-story/scripts"))
    from photostory import tts as PT
    chunks = [("The **Space Needle** opened in 1962.", "太空针塔于**1962年**落成。")]
    assert PT.narration_texts(chunks, {}, "zh") == (["太空针塔于1962年落成。"], ["太空针塔于1962年落成。"])
    assert PT.narration_texts(chunks, {"1962": "nineteen sixty-two"}, "en")[0] == [
        "The Space Needle opened in nineteen sixty-two."]
    assert PT.norm("太空针 Needle") == ["太", "空", "针", "needle"]


def test_each_version_narrates_in_its_own_language():
    from vstudio.project.adapters.photostory import narration_is_chinese as zh
    ask = "Narrate in Chinese for Xiaohongshu and Bilibili and in English for YouTube"
    assert zh(ask, "Seattle Center 1962 — 中文版") and not zh(ask, "Seattle Center 1962 — English version")
    assert zh(ask, "History", "西雅图简史", item="zh-version") and not zh(ask, "History", "In 2 Minutes",
                                                                        item="en-version")
    assert zh("a calm voice-over in Chinese about seasons", "Autumn essay") and not zh("Narrate it.", "Trip")


def test_standing_tags_and_chapter_line_fit_the_post(monkeypatch):
    """Her career tags (#AIEngineer, #AI面试) matched "ai" inside "Fair"; her 中文 chapter line led an English post."""
    from vstudio import publish as P
    assert P.relevant_tags(["#AIEngineer", "#AI面试", "#SDE"], "Seattle World's Fair 1962") == []
    assert P.relevant_tags(["#AIEngineer", "#SDE"], "my AI interview prep as an SDE") == ["#AIEngineer", "#SDE"]
    monkeypatch.setattr(P, "_p", lambda k, d=None: "时间线在下面，按需跳👇" if k == "publish.chapter_line" else d)
    en = P.post_body(None, "A night flight.", chapters=[(0, "Intro"), (20, "The Needle")], platform="youtube",
                     title="Seattle 1962", use_persona_tags=False)
    zh = P.post_body(None, "夜航西雅图。", chapters=[(0, "开场"), (20, "太空针塔")], platform="xiaohongshu",
                     title="西雅图 1962", use_persona_tags=False)
    assert "时间线" not in en and "Chapters" in en and "时间线在下面" in zh


def test_photo_story_spec_refs_are_repaired_not_left_to_crash_the_render():
    """A drafted spec named clip "..._0336_D" with another clip's time stamp, and a still no frame was cut for."""
    from vstudio.project.adapters import photostory as PS
    ids = {"DJI_20260624222712_0335_D": 1, "DJI_20260624223151_0336_D": 1}
    spec = ('SCRIPT = [(0, [("a", "甲")], [("vDJI_20260624222712_0336_D", 1, "still", dict(off=2.0)), '
            '("film:skyline,needle", 1, "still", {}), ("route:home", 1, "still", {})])]\n'
            'COVER = dict(hero=dict(src="needle"), polaroids=[dict(src="arches")])\n'
            'frames = [dict(name="skyline", clip="DJI_20260624222712_0335_D", t=3)]\n')
    fixed = PS.fix_video_refs(spec, ids)
    assert '"vDJI_20260624223151_0336_D"' in fixed
    assert PS.image_refs(fixed, set(ids)) == ["skyline", "needle", "arches"]
    assert [f["name"] for f in PS._frames_asked({"frames": [dict(name="needle", clip="x", t=1)]}, spec)] == [
        "needle", "skyline"]
    assert PS._clip_id("DJI_0335", ids) == "DJI_20260624222712_0335_D" and PS._clip_id("nope", ids) is None


def test_photo_story_renders_another_canvas_for_each_other_platform(tmp_path):
    """Bilibili 16:9 next to a 3:4 Xiaohongshu story is laid out again (header / subtitle band per canvas); a
    platform with the first one's canvas reuses the video; every platform gets its own cover and post copy."""
    from vstudio.project.adapters import photostory as PS
    runs = []

    class Env:
        params = dict(platforms=["xiaohongshu:full", "bilibili", "douyin"], mode="narration")
        item_dir, workflow_dir = str(tmp_path), "/wf"

        def fmt(self, t):
            return "py"

        def run(self, argv, log=None):
            runs.append(argv)
            out = argv[argv.index("--out") + 1]
            target = out if out.endswith((".mp4", ".png")) else os.path.join(out, "post.md")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            open(target, "w").write("x")
    r = PS.more_platforms(Env())
    rendered = [a for a in runs if a[1].endswith("render.py")]
    assert len(rendered) == 1 and "bilibili" in rendered[0]
    assert [p["platform"] for p in r["platforms"]] == ["bilibili", "douyin"]
    assert r["platforms"][1]["file"].endswith(os.path.join("out", "story.mp4"))
    assert all(os.path.exists(p["post"]) for p in r["platforms"])


def test_clip_page_export_keeps_the_projects_framing(tmp_path):
    """A vlog re-exported to a vertical platform from the clip page follows the subject like the project's own
    export; her blurred-fill choice and other recipes keep the blurred fill."""
    from vstudio.project import outrender as OR
    (tmp_path / "project.yaml").write_text("recipe: vlog\nparams: {}\nitems: [{id: a, params: {}}]\noverrides: {}\n")
    rec = dict(kind="project", owner=str(tmp_path))
    assert OR.framing_fallback(rec) == "subject"
    (tmp_path / "project.yaml").write_text("recipe: vlog\nparams: {}\nitems: []\noverrides: {a: {reframe: blur}}\n")
    assert OR.framing_fallback(rec) == "pad-blur"
    (tmp_path / "project.yaml").write_text("recipe: talkinghead\nparams: {}\nitems: []\n")
    assert OR.framing_fallback(rec) == "pad-blur" and OR.framing_fallback(dict(kind="work")) == "pad-blur"


def test_cover_candidates_skip_crossfades():
    from vstudio.project.adapters import common as CM
    tr = [[5.8, 6.6], [12.4, 13.2]]
    assert CM.clear_of_transitions([6.0, 9.0, 12.9], tr, 20) == [9.5, 16.6]


def test_portrait_cover_is_its_own_subject_crop_with_readable_text(tmp_path):
    from PIL import Image, ImageDraw
    from vstudio.batch.edits import _text_cover
    from vstudio.project.adapters import common as CM
    im = Image.new("RGB", (1920, 1080), (30, 60, 90))
    ImageDraw.Draw(im).ellipse((1500, 400, 1700, 600), fill=(250, 250, 250))       # the subject, right of centre
    src = str(tmp_path / "f.jpg")
    im.save(src)
    out = CM.subject_crop(src, 9 / 16, str(tmp_path / "v.jpg"))
    w, h = Image.open(out).size
    assert abs(w / h - 9 / 16) < 0.01 and CM.subject_crop(out, 9 / 16, str(tmp_path / "x.jpg")) is None
    assert Image.open(out).getpixel((w // 2, 500))[0] > 200 or Image.open(out).getpixel((w - 20, 500))[0] > 200
    _text_cover(out, "Eastern Washington Road Trip — Columbia River, Dusk Deer, Lake & Creek", str(tmp_path / "c.jpg"))
    assert Image.open(tmp_path / "c.jpg").size == (w, h)


def test_english_narration_gets_respellings_for_names_the_local_voice_lacks():
    pytest.importorskip("misaki")
    from vstudio.project.adapters import photostory as PS
    spec = 'SCRIPT = [(0, [("Elliott Bay meets Puget Sound in Seattle.", "甲")], [])]\n'
    asks = []

    def complete(task, system, body, **kw):
        asks.append(body)
        if len(asks) == 1:
            return dict(json={"Puget": "pew jet", "Elliott": "ell ee it"}, provider="claude-code")
        return dict(json={"Elliott": "ell yacht"}, provider="claude-code")
    out = PS.add_respellings(spec, complete)
    assert "SAY_TTS = {'Puget': 'pew jet', 'Elliott': 'ell yacht'}" in out and "ell ee it" in asks[1]
    assert PS.add_respellings('SCRIPT = [(0, [("Seattle at night.", "甲")], [])]\n', complete).count("SAY_TTS") == 0
