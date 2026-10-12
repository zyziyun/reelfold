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
