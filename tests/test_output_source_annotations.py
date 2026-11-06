"""Shot replacements must not inherit source highlights via preserved title bars."""
import shutil

import cv2
import pytest

from vstudio import media
from vstudio.project import outrender as R


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_replaced_shot_keeps_header_without_old_source_outline(tmp_path, monkeypatch):
    source, replacement = tmp_path / "original.mp4", tmp_path / "replacement.mp4"
    for path, color in [(source, "0x303030"), (replacement, "0x304050")]:
        media.run([media.ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i",
                   f"color=c={color}:s=320x180:r=15:d=3", "-c:v", "libx264", str(path)])
    spec = dict(src=str(source), spans=[[0, 1], [2, 3]], effects=[dict(
        effect="red-box", start=0, end=3, params=dict(
            anchor="source", x=.5, y=.12, w=.4, h=.15, color="#FF0000", width=12, anim="fade"))])
    annotated = R.run_source_annotations(spec, str(tmp_path / "annotated.mp4"), "preview")
    # Explicit known header bounds isolate copying from detector heuristics. Rendering is real.
    monkeypatch.setattr(R, "title_bar", lambda *a: [(0, 45)])
    parts = dict(op="splice", w=320, h=180, fps=15, pieces=[
        dict(kind="file", a=0, b=1),
        dict(kind="source", a=1, b=2, src=str(replacement), t=0, box=[0, 0, 1, 1]),
        dict(kind="file", a=2, b=3)])
    out = R.run_pieces(parts, annotated, str(tmp_path / "result.mp4"), "preview", str(tmp_path))
    cap = cv2.VideoCapture(out)
    counts = []
    for t in (.5, 1.5, 2.5):
        cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
        ok, fr = cap.read()
        assert ok
        counts.append(((fr[:, :, 2] > 140) & (fr[:, :, 1] < 90) & (fr[:, :, 0] < 90)).sum())
    cap.release()
    assert counts[0] > 100 and counts[2] > 100
    assert counts[1] == 0, "old annotation leaked into the replacement's preserved header"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_second_edit_portrait_keeps_source_region_and_audio(tmp_path):
    from vstudio import spoken
    source = tmp_path / "landscape.mp4"
    media.run([media.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i",
               "color=c=0x303030:s=320x180:r=15:d=3", "-f", "lavfi", "-i",
               "sine=frequency=440:duration=3", "-c:v", "libx264", "-c:a", "aac", str(source)])
    effects = [dict(effect="red-box", start=1, end=2, params=dict(
        anchor="source", x=.2, y=.3, w=.2, h=.2, color="#FF0000", width=18, anim="fade"))]
    annotated = R.run_source_annotations(dict(src=str(source), effects=effects),
                                         str(tmp_path / "annotated.mp4"), "preview")
    out = R.run_canvas(dict(op="reframe", src=annotated, w=180, h=320, fallback="center",
                            source_regions=spoken.source_regions(effects)),
                       str(tmp_path / "portrait.mp4"), "preview", [0, 0, 180, 320])
    cap = cv2.VideoCapture(out)
    for t in (.5, 1.5, 2.5):
        cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
        ok, frame = cap.read()
        assert ok
        red = (frame[:, :, 2] > 140) & (frame[:, :, 1] < 90) & (frame[:, :, 0] < 90)
        if t == 1.5:
            import numpy as np
            ys, xs = np.where(red)
            assert red.sum() > 50
            assert xs.mean() == pytest.approx(36, abs=2)
            assert ys.mean() == pytest.approx((320-180*180/320)/2 + .3*180*180/320, abs=2)
        else:
            assert red.sum() == 0
    cap.release()
    info = media.probe(out)
    assert info["has_audio"] and info["duration"] == pytest.approx(3, abs=.1)
