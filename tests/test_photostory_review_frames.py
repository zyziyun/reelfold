"""Layout sampling must cover brief shots and closing frames, not fixed wall times."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows/photo-story/scripts"))
from photostory.render import review_frames


def test_every_shot_including_short_final_shot_has_endpoint_evidence():
    shots = [dict(start=0, end=8.5), dict(start=8.5, end=19), dict(start=19, end=20)]
    frames = review_frames(shots, 20, 30)
    assert frames == [0, 127, 254, 255, 412, 569, 570, 584, 599]


def test_single_frame_shots_are_unique_and_do_not_sample_past_duration():
    frames = review_frames([dict(start=0, end=1/30), dict(start=1/30, end=2/30)], 2/30, 30)
    assert frames == [0, 1]


def test_fractional_boundaries_only_sample_frames_inside_each_shot():
    frames = review_frames([dict(start=.021, end=.099), dict(start=.099, end=.16)], .16, 30)
    assert frames == [1, 2, 3, 4]


def test_outside_and_zero_length_shots_do_not_leak_into_review():
    assert review_frames([dict(start=1, end=1), dict(start=2, end=3)], 1, 30) == []


def test_end_fade_keeps_a_readable_hero_frame_and_the_actual_final_frame():
    assert review_frames([dict(start=19, end=20)], 20, 30, end_fade=.4) == [570, 584, 587, 599]
