"""Ground a fixed-region proposal in actual local source frames, not model coordinates alone."""
import cv2
import numpy as np
import pytest

from vstudio import spoken

CUES = [dict(start=i, end=i+1, text="The saved draft remains available.") for i in range(8)]
BEAT = dict(**{"from": 3, "to": 5}, kind="source-outline", title="", items=[],
            evidence="The saved draft remains available.", source_box=[.1, .1, .4, .2])


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 180))
    assert writer.isOpened()
    for i in range(80):
        frame = np.full((180, 320, 3), 40, np.uint8)
        cv2.putText(frame, "Saved draft", (35, 43), cv2.FONT_HERSHEY_SIMPLEX, .5, (240, 240, 240), 1)
        # The rest of the frame moves; only the selected static region matters.
        frame[100:, :] = (i*3 % 255, 100, 80)
        writer.write(frame)
    writer.release()
    return path


def test_planner_emits_source_anchored_effect_from_real_stable_region(source):
    def model(_task, system, prompt, **kw):
        assert "source-outline" in system and "ENTIRE composed source frame" in system
        return dict(json=dict(beats=[BEAT]))
    result = spoken.plan(CUES, 8, source=source, source_context="Full source samples", complete=model)
    effect = result["effects"][0]
    assert effect["effect"] == "red-box" and effect["params"]["anchor"] == "source"
    assert effect["params"]["x"] == pytest.approx(.3)
    assert effect["start"] == 3 and effect["end"] == 6


@pytest.mark.parametrize("box", [[-.1, .1, .4, .2], [.9, .1, .4, .2],
                                 [.1, .1, float("nan"), .2], [.1, .1, .4], [.1, .1, 0, .2]])
def test_invalid_regions_fail(source, box):
    with pytest.raises(ValueError, match="source_box"):
        spoken.validate(dict(beats=[dict(BEAT, source_box=box)]), CUES, 8, source=source)


def test_missing_source_and_changing_region_are_not_accepted(source):
    with pytest.raises(ValueError, match="composed video"):
        spoken.validate(dict(beats=[BEAT]), CUES, 8)
    # This region includes both the note and changing picture below it.
    with pytest.raises(ValueError, match="region changes"):
        spoken.validate(dict(beats=[dict(BEAT, source_box=[0, 0, 1, 1])]), CUES, 8, source=source)


def test_incomplete_interval_is_rejected(source):
    with pytest.raises(ValueError, match="incomplete"):
        spoken._check_source_region(source, BEAT["source_box"], 7, 10)
