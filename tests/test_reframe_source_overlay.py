"""Source annotations travel with the picture, independently of output-space overlays."""
import shutil

import cv2
import numpy as np
import pytest

from vstudio import media
from vstudio import reframe as R

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.mark.parametrize("mode", ["crop", "region", "letterbox", "prescaled"])
def test_source_annotation_moves_with_picture_and_preserves_clock(tmp_path, mode):
    # Two camera positions. A fixed source point must move on the output, whereas
    # the output-space blue badge must stay in the corner.
    frames = [np.zeros((120, 240, 3), np.uint8) for _ in range(8)]
    pl = dict(src_w=240, src_h=120, target=[60, 60], fps=8, start=1,
              dur=1, mode_used="subject", scale=.5,
              rects=[[0 if i < 4 else 60, 0, 120, 120] for i in range(8)])
    src = None
    inputs = frames
    if mode == "region":
        pl.update(src_w=180, src_h=120, full_w=240, full_h=120,
                  region=[30, 0, 180, 120], scale=1,
                  rects=[[0 if i < 4 else 30, 0, 120, 120] for i in range(8)])
    elif mode == "letterbox":
        pl.update(mode_used="letterbox")
    elif mode == "prescaled":
        src = tmp_path / "source.mp4"
        media.run([media.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i",
                   "color=black:s=240x120:r=8:d=2", "-f", "lavfi", "-i",
                   "sine=frequency=440:duration=2", "-c:v", "libx264", "-c:a", "aac", str(src)])
        inputs = None
    calls = []

    def source_overlay(i, t, fr):
        h, w = fr.shape[:2]
        calls.append((i, t, w, h))
        cv2.rectangle(fr, (round(.35*w), round(.4*h)),
                      (round(.45*w), round(.6*h)), (0, 255, 0), -1)
        # Exercise both supported callback forms.
        return fr if i % 2 else None

    def overlay(i, t, fr):
        fr[:8, :8] = (255, 0, 0)

    out = R.render(src, tmp_path / f"{mode}.mp4", pl, frames=inputs,
                   source_overlay=source_overlay, overlay=overlay)
    assert len(calls) == 8
    assert [t for _, t, _, _ in calls] == [1+i/8 for i in range(8)]
    assert calls[0][2:] == ((120, 60) if mode == "prescaled" else (240, 120))
    assert all(not f.any() for f in frames)  # no mutation of caller-owned source
    cap = cv2.VideoCapture(str(out))
    centres = []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        green = (fr[:, :, 1] > 160) & (fr[:, :, 0] < 80) & (fr[:, :, 2] < 80)
        assert green.sum() > 20
        centres.append(np.where(green)[1].mean())
        assert fr[3, 3, 0] > 160 and fr[3, 3, 1] < 80
    cap.release()
    assert len(centres) == 8
    expected_shift = {"crop": 30, "region": 15, "letterbox": 0, "prescaled": 30}[mode]
    assert centres[0] - centres[-1] == pytest.approx(expected_shift, abs=2)
    assert media.probe(out)["has_audio"] == (mode == "prescaled")
