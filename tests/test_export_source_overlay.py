"""Real exports keep source outlines attached to content and the master clock."""
import shutil

import cv2
import numpy as np
import pytest

from vstudio import export, media, platform, spoken

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.mark.parametrize("vertical", [False, True])
def test_export_source_outline_survives_framing_and_trim(tmp_path, vertical):
    source = tmp_path / "source.mp4"
    args = [media.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi", "-i",
            "color=0x304050:s=640x360:r=15:d=4"]
    if vertical:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-c:a", "aac"]
    media.run(args + ["-c:v", "libx264", "-preset", "ultrafast", str(source)])
    w, h = (180, 320) if vertical else (640, 360)
    prof = platform.profile("youtube", "horizontal", overrides=dict(
        w=w, h=h, safe=dict(left=0, right=0, top=0, bottom=0)))
    effect = dict(effect="red-box", start=2, end=3, params=dict(
        x=.3, y=.3, w=.2, h=.2, color="#FF0000", width=12, anim="fade", anchor="source"))
    out = tmp_path / "out"
    out.mkdir()
    entry = export.export_one(str(source), prof, str(out), start=1, dur=2.5,
                              captions=False, watermark=False,
                              **({"effects": [effect]} if vertical else {"source_effects": [effect]}),
                              mode="center" if vertical else "letterbox", encoder="libx264", preset="ultrafast")
    cap = cv2.VideoCapture(str(out / entry["file"]))
    def red_at(t):
        cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
        ok, fr = cap.read()
        assert ok
        return (fr[:, :, 2] > 140) & (fr[:, :, 1] < 90) & (fr[:, :, 0] < 90)
    assert red_at(.4).sum() == 0
    red = red_at(1.5)  # master 2.5, not output 2.5
    assert red.sum() > 30
    yy, xx = np.where(red)
    assert xx.mean() == pytest.approx(.3*w, abs=2)
    # Letterboxed source is centred vertically: source y=.3 is not output y=.3.
    expected_y = (h - w*360/640)/2 + .3*w*360/640
    assert yy.mean() == pytest.approx(expected_y, abs=2)
    assert red_at(2.3).sum() == 0
    cap.release()
    info = media.probe(out / entry["file"])
    assert info["has_audio"] == vertical
    assert info["duration"] == pytest.approx(2.5, abs=.12)
    if vertical:
        assert any("emphasized source region" in s for s in entry["warnings"])


def test_source_pass_rejects_output_cards():
    with pytest.raises(ValueError, match="red-box only"):
        spoken.source_overlay([dict(effect="explanation-card")])
