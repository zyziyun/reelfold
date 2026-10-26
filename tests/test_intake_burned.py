"""Finished-source captions stay intact by default; a designed crop/band is an explicit preference.
Finished landscape sources stay landscape; these planning tests do not prove deliberate aspect recomposition.
"""
import pytest

from vstudio.intake import plan as PL
from test_intake import build


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "VSTUDIO_LLM_PROVIDER", "VSTUDIO_LLM_INTAKE_PROVIDER", "VSTUDIO_LLM_ROUTES_FILE"):
        monkeypatch.delenv(k, raising=False)


def _th(plan):
    ps = [p for p in plan["projects"] if p["recipe"] == "talkinghead"]
    assert ps, [p["recipe"] for p in plan["projects"]]
    return ps[0]


def test_finished_edit_keeps_baked_captions_without_automatic_band_crop(tmp_path):
    a = build("finished", tmp_path)
    a["files"][0]["caption_band"] = "lower"
    plan = PL.make_plan("把后面自媒体的思考单独剪出来发小红书", analysis=a, asr="off")
    p = _th(plan)
    pr = p["params"]
    assert pr.get("layout") != "band" and "crop_bottom" not in pr and pr["captions"] is False
    assert pr["platforms"] == ["xiaohongshu:horizontal"]
    assert pr["preserve_source_aspect"] is True and pr["pipeline"] == "fast"
    assert pr["speed"] == 1.0 and pr["cleanup_profile"] == "gentle"
    assert "保留原字幕" in plan["summary_zh"] and "裁掉旧字幕" not in plan["summary_zh"]
    assert PL.validate(plan) == []


def test_keep_old_captions_when_asked(tmp_path):
    plan = PL.make_plan("把后面自媒体的思考单独剪出来，保留原字幕", analysis=build("finished", tmp_path), asr="off")
    pr = _th(plan)["params"]
    assert pr["captions"] is False and pr.get("layout") != "band" and "crop_bottom" not in pr


def test_persona_keep_and_explicit_9x16(tmp_path, monkeypatch):
    from vstudio import config
    real = config.persona()
    monkeypatch.setattr(PL, "context", lambda client=None, _c=PL.context: dict(_c(client), burned="keep"))
    pr = _th(PL.make_plan("把后面自媒体的思考单独剪出来", analysis=build("finished", tmp_path), asr="off"))["params"]
    assert pr["captions"] is False and pr.get("layout") != "band"
    monkeypatch.undo()
    pr = _th(PL.make_plan("这段口播剪干净发小红书 9:16", analysis=build("talk", tmp_path / "t"), asr="off"))["params"]
    assert pr["platforms"] == ["xiaohongshu:full"]
    assert real is config.persona()


def test_persona_post_shape_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(PL, "context", lambda client=None, _c=PL.context: dict(
        _c(client), shapes={"xiaohongshu": "full"}))
    pr = _th(PL.make_plan("这段口播剪干净发小红书", analysis=build("talk", tmp_path), asr="off"))["params"]
    assert pr["platforms"] == ["xiaohongshu:full"]


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="ffmpeg not installed")
def test_export_band_layout_crops_old_captions(tmp_path):
    """layout band: the bottom 28 % (old burned captions) is cropped off, the rest fitted on the 3:4 canvas."""
    import subprocess
    from vstudio import export as X, platform as PF
    src = tmp_path / "m.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25", "-f", "lavfi",
                    "-i", "sine=f=440:sample_rate=48000", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(src)], check=True)
    e = X.export_one(str(src), PF.profile("xiaohongshu", "vertical"), str(tmp_path), mode="band", crop_bottom=0.28,
                     captions=False)
    assert (e["w"], e["h"]) == (1080, 1440)
    assert e["reframe"]["band"]["region"] == [0, 0, 640, 258] and e["reframe"]["mode_used"] == "pad-blur"

@pytest.mark.parametrize('layout', ['letterbox', 'pad-blur', 'face'])
def test_model_cannot_add_second_captions_over_retained_baked_text(tmp_path, layout):
    analysis = build('finished', tmp_path)
    raw = dict(recipe='talkinghead', inputs={'video': [analysis['files'][0]['id']]},
               items=dict(method='per-file'), params=dict(captions=True, layout=layout))
    plan = PL.make_plan('剪成口播视频', analysis=analysis, asr='off',
                        call=lambda s, b: dict(json=dict(projects=[raw]), model='mock'))
    assert plan['planner']['fallback'] is False
    assert _th(plan)['params']['captions'] is False

@pytest.mark.parametrize('source,layout', [('finished', 'band'), ('talk', 'letterbox')])
def test_new_captions_remain_available_for_band_reconstruction_and_raw_speech(tmp_path, source, layout):
    analysis = build(source, tmp_path)
    raw = dict(recipe='talkinghead', inputs={'video': [analysis['files'][0]['id']]},
               items=dict(method='per-file'), params=dict(captions=True, layout=layout, crop_bottom=0.28))
    plan = PL.make_plan('剪成口播视频', analysis=analysis, asr='off',
                        call=lambda s, b: dict(json=dict(projects=[raw]), model='mock'))
    assert plan['planner']['fallback'] is False
    assert _th(plan)['params']['captions'] is True
