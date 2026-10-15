"""Source-shot masks must fail visibly on stale/missing tracks and keep audio/timing intact."""
import json
import shutil

import numpy as np
import pytest

from vstudio import face_privacy as F, media


def builder():
    import importlib.util
    from pathlib import Path
    script = Path(__file__).resolve().parents[1] / 'workflows/vlog/scripts/build_vlog.py'
    spec = importlib.util.spec_from_file_location('vlog_face_test', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_choose_does_not_guess_a_middle_face_or_a_distant_click():
    boxes = [np.array([10, 20, 20, 25.]), np.array([60, 20, 20, 25.])]
    with pytest.raises(ValueError, match='ambiguous'):
        F.choose(boxes)
    with pytest.raises(ValueError, match='inside'):
        F.choose(boxes, point=np.array([0, 0]))
    assert np.array_equal(F.choose(boxes, point=np.array([65, 25])), boxes[1])
    assert np.array_equal(F.choose(boxes, 'left'), boxes[0])
    assert np.array_equal(F.choose(boxes, 'right'), boxes[1])


def test_association_rejects_crossing_candidates_and_distant_people():
    old = np.array([50, 50, 20, 25.])
    assert F.associate([old + [2, 0, 0, 0], old - [2, 0, 0, 0]], old) is None
    assert F.associate([old + [80, 0, 0, 0]], old) is None
    assert np.array_equal(F.associate([old + [2, 0, 0, 0]], old), old + [2, 0, 0, 0])


@pytest.mark.parametrize('mode', ['mosaic', 'blur', 'cat', 'dog'])
def test_missing_track_never_silently_passes_or_blacks_out_the_picture(mode):
    image = np.full((100, 160, 3), 120, np.uint8)
    before = image.copy()
    with pytest.raises(ValueError, match='uncertain'):
        F.cover(image, None, mode)
    assert np.array_equal(image, before)


def test_invalid_tracking_request_is_rejected_before_opening_video():
    for start, end, kw in [(-1, 2, {}), (0, float('nan'), {}), (0, 2, {'target': 'any'}),
                           (0, 2, {'point': [2, .5]})]:
        with pytest.raises(ValueError):
            F.analyze('not-a-video.mp4', start, end, **kw)


@pytest.fixture(params=["untagged", "709"])
def shot(tmp_path, request):
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg unavailable')
    src = tmp_path / 'shot.mp4'
    tags = [] if request.param == 'untagged' else ['-vf', 'scale=out_color_matrix=bt709:out_range=tv',
                                                   '-colorspace', 'bt709', '-color_range', 'tv']
    media.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=10:d=1',
               '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=1',
               *tags, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(src)])
    info = media.probe(src)
    track = dict(source_sha256=F._sha(src), start=0, width=320, height=180, fps=10, frames=10,
                 boxes=[[.3 + .01*i, .3, .2, .25] for i in range(10)], uncertain=[])
    return src, track, tmp_path


def test_masked_shot_keeps_all_frames_and_original_audio(shot):
    src, track, root = shot
    dst = root / 'masked.mp4'
    F.render(src, dst, track)
    before, after = media.probe(src), media.probe(dst)
    assert (after['w'], after['h'], after['fps'], after['has_audio']) == (320, 180, 10, True)
    assert abs(after['duration'] - before['duration']) < .02
    def frames(p):
        raw = media.run(['ffmpeg', '-v', 'error', '-i', str(p), '-map', '0:v:0',
                         '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(-1,180,320,3)
    originals, masked_frames = frames(src), frames(dst)
    assert len(originals) == len(masked_frames) == 10
    for i, (original, masked) in enumerate(zip(originals, masked_frames)):
        x = int(track['boxes'][i][0] * 320)
        assert np.mean(np.abs(original[60:85, x:x+50].astype(float) - masked[60:85, x:x+50])) > 8
        assert np.mean(np.abs(original[:20].astype(float) - masked[:20])) < 4
    # Stream-copy the source audio, rather than accidentally re-timing or dropping it.
    payload = lambda p: media.run(['ffmpeg', '-v', 'error', '-i', str(p), '-map', '0:a:0',
                                  '-c', 'copy', '-f', 'adts', '-'], capture=True).stdout
    assert payload(src) == payload(dst)


def test_mask_retags_encoders_that_ignore_colour_metadata(shot, monkeypatch):
    src, track, root = shot
    popen = F.subprocess.Popen
    def encoder_without_tags(cmd, *args, **kwargs):
        if 'rawvideo' in cmd and '-c:v' in cmd:
            omit = {'-colorspace', '-color_primaries', '-color_trc', '-color_range'}
            cmd = [x for i, x in enumerate(cmd) if x not in omit and (not i or cmd[i-1] not in omit)]
        return popen(cmd, *args, **kwargs)
    monkeypatch.setattr(F.subprocess, 'Popen', encoder_without_tags)
    dst = root / 'tagged-mask.mp4'
    F.render(src, dst, track)
    info = media.probe(dst)
    assert info['primaries'] == info['transfer'] == 'bt709'
    assert info['has_audio'] and abs(info['duration'] - media.duration(src)) < .02


@pytest.mark.parametrize('damage', ['source', 'missing', 'short', 'box', 'fps'])
def test_bad_track_preserves_existing_output(shot, damage):
    src, track, root = shot
    dst = root / 'already-made.mp4'
    dst.write_bytes(b'existing output')
    if damage == 'source':
        track['source_sha256'] = 'wrong'
    elif damage == 'missing':
        track['boxes'][3] = None
        track['uncertain'] = [[.3, .4]]
    elif damage == 'short':
        track['boxes'].pop()
    elif damage == 'box':
        track['boxes'][0] = [float('nan'), .3, .2, .2]
    else:
        track['fps'] = 20
    with pytest.raises(ValueError):
        F.render(src, dst, track)
    assert dst.read_bytes() == b'existing output'


def test_source_hook_masks_before_transition_and_keeps_audit(shot, monkeypatch):
    src, track, root = shot
    monkeypatch.setattr(F, 'analyze', lambda *args, **kwargs: track)
    original_hash = F._sha(src)
    assert builder()._mask_segment(str(src), dict(face_mask=dict(target='center')), 1, False) == str(src)
    report = json.loads((root / 'shot.mp4.face-mask.json').read_text())
    assert report['source_sha256'] == original_hash
    assert report['masked_sha256'] == F._sha(src) != original_hash
    assert media.probe(src)['has_audio']
    assert not (root / 'shot.mp4.masked.mp4').exists()


def test_source_hook_aborts_on_a_lost_face_before_replacing_segment(shot, monkeypatch):
    src, track, root = shot
    track['boxes'][3] = None
    track['uncertain'] = [[.3, .4]]
    monkeypatch.setattr(F, 'analyze', lambda *args, **kwargs: track)
    original_hash = F._sha(src)
    module = builder()
    with pytest.raises(module.RenderError, match='segment 02.*needs checking'):
        module._mask_segment(str(src), dict(face_mask={}), 2, False)
    assert F._sha(src) == original_hash
    assert json.loads((root / 'shot.mp4.face-mask.json').read_text())['uncertain'] == [[.3, .4]]
    assert not (root / 'shot.mp4.masked.mp4').exists()



def test_wrong_model_checksum_fails_before_loading_onnx(tmp_path):
    model = tmp_path / 'wrong.onnx'
    model.write_bytes(b'not the pinned detector')
    with pytest.raises(ValueError, match='checksum'):
        F.detector(model)


def test_short_track_that_passes_metadata_tolerance_cannot_replace_output(shot):
    src, track, root = shot
    track['boxes'].pop()
    track['frames'] -= 1
    dst = root / 'keep.mp4'
    dst.write_bytes(b'keep existing render')
    with pytest.raises(ValueError, match='more frames'):
        F.render(src, dst, track)
    assert dst.read_bytes() == b'keep existing render'
    assert not list(root.glob('face-mask-*'))


def test_source_changed_during_render_cannot_replace_output(shot, monkeypatch):
    src, track, root = shot
    dst = root / 'keep.mp4'
    dst.write_bytes(b'keep existing render')
    values = iter([track['source_sha256'], 'changed'])
    monkeypatch.setattr(F, '_sha', lambda p: next(values))
    with pytest.raises(ValueError, match='changed'):
        F.render(src, dst, track)
    assert dst.read_bytes() == b'keep existing render'


def test_fun_builder_refuses_to_silently_drop_source_masks(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    cfg = tmp_path / 'edit.json'
    cfg.write_text(json.dumps(dict(style='fun', shots=[dict(clip='a', face_mask={})])))
    result = subprocess.run([sys.executable, str(root/'workflows/vlog/scripts/build_vlog.py'), str(cfg), '--dry-run'],
                            capture_output=True, text=True, env=dict(os.environ, VSTUDIO_DEFAULT_PERSONA='1'))
    assert result.returncode != 0 and 'Mask source shots' in result.stderr
    assert not list(tmp_path.glob('*.mp4'))



def test_tiny_masks_downsample_instead_of_resizing_up_and_back():
    image = np.arange(12*12*3, dtype=np.uint8).reshape(12,12,3)
    before = image.copy()
    F.cover(image, [.3,.3,.2,.2], 'mosaic')
    assert not np.array_equal(image[3:6,3:6], before[3:6,3:6])
    assert np.unique(image[3:6,3:6].reshape(-1,3), axis=0).shape[0] == 1


def test_edl_keeps_source_mask_intent(tmp_path):
    module = builder()
    cfg = dict(_src_dir=str(tmp_path), clips={'a':'source.mp4'}, segments=[dict(clip='a', start=0,dur=1,
               face_mask=dict(target='center',style='mosaic'))])
    module.write_edl(cfg,str(tmp_path/'film.mp4'),[0],[1],[0],1,1/30)
    edl = json.loads((tmp_path/'film.edl.json').read_text())
    assert edl['shots'][0]['face_mask'] == dict(target='center',style='mosaic')
