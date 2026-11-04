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


def test_chapter_stills_refresh_without_retaining_old_frames(tmp_path, monkeypatch):
    from PIL import Image
    from photostory import render
    Image.new('RGB', (640, 480), '#408080').save(tmp_path / 'photo.jpg')
    spec = tmp_path / 'spec.py'
    spec.write_text('''
CANVAS = (640, 480)
FPS = 30
MODE = 'music'
TITLE_EN = 'Preview'
TITLE_ZH = 'Preview'
TITLE_CARD = False
CHAPTER_CARD = .5
MEDIA = dict(images=['.'])
MUSIC = dict(grid='seconds', length=2, tail=0, captions='all')
SECTIONS = ['Start', 'Finish']
SECTIONS_EN = ['Start', 'Finish']
SCRIPT = [(0, [('First', '')], [('photo', 1, 'still', dict(tr='cut'))]),
          (1, [('Second', '')], [('photo', 1, 'still', dict(tr='cut'))])]
GRADE_LOOK = None
COLOR_MATCH = 0
PRESERVE_COLOUR = True
''')
    dest = tmp_path / 'stills'
    dest.mkdir()
    unrelated = dest / 'reference.jpg'
    unrelated.write_bytes(b'keep')
    def run(times):
        monkeypatch.setattr(sys, 'argv', ['render', str(spec), '--stills', times, '--stills-dir', str(dest)])
        render.main()
    run('0.2,1.1,1.8')
    assert {p.name for p in dest.glob('st_frame_*.jpg')} == {
        'st_frame_00000006.jpg', 'st_frame_00000033.jpg', 'st_frame_00000054.jpg'}
    run('1.1')
    assert {p.name for p in dest.glob('st_frame_*.jpg')} == {'st_frame_00000033.jpg'}
    assert unrelated.read_bytes() == b'keep'
    with Image.open(dest / 'st_frame_00000033.jpg') as im:
        assert im.width > 0
    # A failed new generation must not replace any of the previous evidence.
    import pytest
    saved = (dest / 'st_frame_00000033.jpg').read_bytes()
    build = render.build
    def fail_second(C, shot, index):
        if index == 1:
            raise RuntimeError('failed second shot')
        return build(C, shot, index)
    monkeypatch.setattr(render, 'build', fail_second)
    with pytest.raises(RuntimeError, match='failed second shot'):
        run('0.2,1.1')
    assert {p.name for p in dest.glob('st_frame_*.jpg')} == {'st_frame_00000033.jpg'}
    assert (dest / 'st_frame_00000033.jpg').read_bytes() == saved
    assert not list(dest.glob('.review-*'))
