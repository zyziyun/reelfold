"""Finished-media planning must survive expansion and actual export, not just rename a portrait file."""
import json
import shutil
import subprocess

import pytest

from test_intake import build
from vstudio.intake import plan as PL


@pytest.mark.parametrize("prompt", [
    "把后面自媒体的思考单独剪出来发小红书",
    "把长视频剪成四条口播切片发小红书",
])
def test_finished_source_shape_is_visible_in_plan_and_expanded_jobs(tmp_path, monkeypatch, prompt):
    monkeypatch.setenv("VSTUDIO_LLM_PROVIDER", "none")
    from vstudio.project.core import Project
    plan = PL.make_plan(prompt, analysis=build("finished", tmp_path / "sources"), asr="off")
    item = plan["projects"][0]
    assert item["params"]["platforms"] == ["xiaohongshu:horizontal"]
    assert item["params"]["preserve_source_aspect"] is True
    if item["recipe"] == "talkinghead":
        assert item["params"]["pipeline"] == "fast"
        source = tmp_path / "fixture.mp4"
        if not shutil.which("ffmpeg"):
            pytest.skip("ffmpeg not installed")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=640x360:d=1", "-y", str(source)], check=True)
        p = Project.create(str(tmp_path / "project"), recipe="talkinghead", inputs=dict(video=[str(source)]), params=item["params"])
        assert p.batch() == "talkinghead-clips"
        assert p.spec()["defaults"]["preserve_source_aspect"] is True
        from vstudio.project.build import build as build_recipe
        # Build validation resolves the fast pipeline's actual finishing/export dependencies.
        assert "finish" in {s.name for s in build_recipe(p.manifest, batch=p.batch()).stages}
    assert PL.validate(plan) == []


@pytest.mark.parametrize("prompt", [
    "把后面自媒体的思考单独剪出来发小红书 9:16",
    "把长视频剪成四条口播切片发小红书 9:16",
])
def test_explicit_shape_is_not_overridden_by_source_default(tmp_path, monkeypatch, prompt):
    monkeypatch.setenv("VSTUDIO_LLM_PROVIDER", "none")
    item = PL.make_plan(prompt, analysis=build("finished", tmp_path), asr="off")["projects"][0]
    assert item["params"]["platforms"] == ["xiaohongshu:full"]
    assert item["params"]["preserve_source_aspect"] is False


def test_legacy_vertical_engine_refuses_false_source_preservation():
    from types import SimpleNamespace
    from vstudio.batch import thfolder
    with pytest.raises(ValueError, match="pipeline=fast"):
        thfolder.run_prep(SimpleNamespace(params=dict(preserve_source_aspect=True)))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_actual_export_keeps_source_corners_and_landscape_canvas(tmp_path, monkeypatch):
    import numpy as np
    from PIL import Image
    from vstudio.batch import stages
    from vstudio.batch.recipes import Ctx
    from vstudio import media
    monkeypatch.setenv("VSTUDIO_LLM_PROVIDER", "none")
    image = Image.new("RGB", (640, 360), (200, 200, 180))
    colours = [(240, 20, 20), (20, 240, 20), (20, 20, 240), (240, 20, 240)]
    for box, colour in zip([(0, 0, 80, 80), (560, 0, 640, 80), (0, 280, 80, 360), (560, 280, 640, 360)], colours):
        image.paste(colour, box)
    still = tmp_path / "source.png"; image.save(still)
    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(still), "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=48000", "-t", "2", "-r", "15", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)], check=True)
    post = tmp_path / "post.json"; post.write_text(json.dumps(dict(title="Source shape", body="", tags=[])))
    monkeypatch.setattr(stages, "draft_title", lambda *a, **k: None)
    params = dict(platforms=["xiaohongshu:vertical"], preserve_source_aspect=True, captions=False,
                  watermark=False, preset="ultrafast")
    ctx = Ctx(dict(params=params), {}, str(tmp_path),
              dict(compose=dict(master=str(source), post=str(post), duration=2)), str(tmp_path))
    result = stages.run_export(ctx)
    output = result["exports"][0]
    assert output["orientation"] == "horizontal"
    info = media.probe(output["file"])
    assert abs(info["display_w"] / info["display_h"] - 16 / 9) < .01
    # FFmpeg honours the H.264 colour matrix; OpenCV's RGB conversion can ignore
    # it, creating a false 601/709 colour mismatch in an otherwise correct export.
    raw = subprocess.check_output([media.ffmpeg_bin(), "-v", "error", "-ss", "0.8", "-i", output["file"],
                                   "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    rgb = np.frombuffer(raw, np.uint8).reshape(info["display_h"], info["display_w"], 3).astype(int)
    for colour in colours:
        assert np.any(np.all(np.abs(rgb - colour) < 8, axis=2))
