"""Output-editor face masks: tracked frame timing, fail-closed coverage, real rendering."""
import math
import subprocess
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("cv2")
from vstudio import face_privacy as FP
from vstudio.project import outfx as FX
from vstudio.project import outputs as O
from vstudio.project import outrender as R
from test_output_edit import synth, _work


def test_catalogue():
    spec = next(e for e in FX.catalogue() if e["id"] == "privacy-sticker")
    assert spec["stage"] == "frame"
    assert set(spec["params"]["style"]["enum"]) == {"mosaic", "blur", "cat", "dog"}
    assert 'effect="privacy-sticker"' in O.AI_SYSTEM


def test_fractional_interval_and_moving_face(monkeypatch):
    track = dict(start=1, fps=10, boxes=[[.1, .2, .1, .1], [.6, .2, .1, .1]], uncertain=[])
    def analyze(src, start, end, target):
        assert (src, start, end, target) == ("edited.mp4", 1.04, 1.2, "right")
        return track
    monkeypatch.setattr(FP, "analyze", analyze)
    layer = FX.FaceMask(dict(params=dict(target="right", style="cat")), 100, 100)
    layer.prepare("edited.mp4", 1.04, 1.2)
    a = np.zeros((100, 100, 3), np.uint8)
    b = a.copy()
    layer.draw(a, 0, .16)
    layer.draw(b, .06, .16)
    assert a[25, 15].any() and not a[25, 65].any()
    assert b[25, 65].any() and not b[25, 15].any()
    with pytest.raises(ValueError, match="cover this frame"):
        layer.draw(b, 1, .16)


def test_uncertain_never_renders(monkeypatch):
    monkeypatch.setattr(FP, "analyze", lambda *a, **k: dict(boxes=[None], uncertain=[[23.1, 23.2]]))
    layer = FX.FaceMask(dict(params={}), 100, 100)
    with pytest.raises(ValueError, match="23.1–23.2s"):
        layer.prepare("edited.mp4", 23, 36)


def test_actual_output_render(tmp_path, monkeypatch, synth):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(O, "TRANSCRIBE", lambda *a, **kw: synth["truth"])
    w, oid = _work(tmp_path, synth)
    seen = []
    def analyze(src, start, end, target):
        from vstudio import media
        info = media.probe(src)
        fps = info["fps"]
        first, last = math.floor(start * fps), math.ceil(end * fps)
        seen.append((start, end, target))
        return dict(start=first/fps, fps=fps, boxes=[[.3, .3, .2, .2]]*(last-first), uncertain=[])
    monkeypatch.setattr(FP, "analyze", analyze)
    O.edit(str(w), oid, dict(op="effect_add", effect="privacy-sticker", start=1, end=2,
                           params=dict(target="center", style="cat")))
    result = R.render(str(w), oid, quality="preview", targets=["primary"])
    assert seen == [(1, 2, "center")]
    def frame(path, at):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(path),
                              "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                             check=True, capture_output=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(640, 360, 3).astype(float)
    src = Path(w) / "final" / "clip.mp4"
    dst = result["targets"][0]["file"]
    region = (slice(200, 300), slice(110, 170))
    assert np.abs(frame(src, 1.5)[region] - frame(dst, 1.5)[region]).mean() > 15
    assert np.abs(frame(src, .5)[region] - frame(dst, .5)[region]).mean() < 4
    assert np.abs(frame(src, 2.5)[region] - frame(dst, 2.5)[region]).mean() < 4


def test_render_reports_tracking_failure_before_encoding(tmp_path, monkeypatch, synth):
    monkeypatch.setattr(FP, "analyze", lambda *a, **kw: dict(boxes=[None], uncertain=[[1.2, 1.3]]))
    monkeypatch.setattr(O, "TRANSCRIBE", lambda *a, **kw: synth["truth"])
    w, oid = _work(tmp_path, synth)
    O.edit(w, oid, dict(op="effect_add", effect="privacy-sticker", start=1, end=2))
    with pytest.raises(O.OutputError) as caught:
        R.render(w, oid, quality="preview", targets=["primary"])
    assert caught.value.info["code"] == "face-tracking-failed"
    assert "1.2–1.3s" in str(caught.value)
    assert not list(Path(w).rglob("primary.preview.mp4"))
