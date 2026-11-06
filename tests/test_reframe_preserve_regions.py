import numpy as np
import pytest

from vstudio import reframe as R


def test_moving_crop_checks_whole_active_interval_without_mutating_plan():
    pl = dict(src_w=400, src_h=200, target=[100, 200], mode_used="subject", fps=2,
              start=3, dur=2, rects=[[0, 0, 100, 200], [0, 0, 100, 200],
                                   [300, 0, 100, 200], [300, 0, 100, 200]])
    annotation = (3, 5, .05, .3, .1, .2)
    keep = R.preserve_regions(pl, [annotation])
    assert keep["mode_used"] == "letterbox"
    assert pl["mode_used"] == "subject"
    frame = np.zeros((200, 400, 3), np.uint8)
    frame[60:100, 20:60] = (0, 255, 0)
    assert (R.frame_fn(pl)(3, frame)[:, :, 1] > 200).sum() == 0
    assert (R.frame_fn(keep)(3, frame)[:, :, 1] > 200).sum() == 100
    assert R.preserve_regions(pl, [(3, 4, *annotation[2:])]) is pl
    assert R.preserve_regions(pl, [(0, 1, *annotation[2:])]) is pl


def test_region_crop_preserves_full_source_when_note_is_outside_camera_tile():
    pl = dict(src_w=200, src_h=100, full_w=400, full_h=200, region=[100, 50, 200, 100],
              target=[100, 200], mode_used="letterbox", fps=10, start=0, dur=3)
    kept = R.preserve_regions(pl, [(0, 2, .01, .01, .1, .1)])
    assert (kept["src_w"], kept["src_h"], kept["region"]) == (400, 200, None)
    with pytest.raises(ValueError, match="complete source frame"):
        R.preserve_regions(pl, [(0, 2, -.1, .1, .2, .2)])


def test_replaced_intervals_do_not_constrain_new_footage():
    from vstudio import spoken
    effects = [dict(start=1, end=4, params=dict(x=.5, y=.5, w=.2, h=.2))]
    assert [r[:2] for r in spoken.source_regions(effects, [[0, 2], [3, 5]])] == [(1, 2), (3, 4)]
    assert spoken.source_regions(effects, []) == []
