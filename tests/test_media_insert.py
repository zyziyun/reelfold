"""Actual source pixels, source limits, scrolling and narrated native exports."""
import subprocess
import numpy as np
import pytest
from PIL import Image
from vstudio import media, export, platform
from vstudio.project import outfx

@pytest.fixture
def assets(tmp_path, monkeypatch):
    monkeypatch.setenv('VSTUDIO_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('VSTUDIO_DEFAULT_PERSONA', '1')
    video = tmp_path / 'insert.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc2=size=320x180:rate=15:duration=5', '-c:v', 'libx264', str(video)], check=True)
    photo = tmp_path / 'page.png'
    pixels = np.zeros((1200, 400, 3), np.uint8)
    pixels[:400] = (240, 30, 20)
    pixels[400:800] = (20, 240, 30)
    pixels[800:] = (20, 30, 240)
    Image.fromarray(pixels).save(photo)
    return video, photo

def inst(path, **params):
    p, warnings = outfx.validate('media-insert', dict(file=str(path), **params))
    assert not warnings
    return dict(id='insert', effect='media-insert', start=2, end=5, params=p)

@pytest.mark.parametrize('size', [(640, 360), (360, 640), (450, 600)])
def test_full_width_document_scroll_is_seek_safe(assets, size):
    w, h = size
    layer = outfx.make_layer(inst(assets[1], fit='card'), w, h)
    frames = []
    for t in (0, 1.5, 2.99, 1.5):
        frame = np.zeros((h, w, 3), np.uint8)
        layer.draw(frame, t, 3)
        frames.append(frame)
    assert np.array_equal(frames[1], frames[3])
    assert frames[0][0, w//2, 2] > 200
    assert frames[2][-1, w//2, 0] > 200
    assert not np.array_equal(frames[0], frames[2])

def test_video_offset_decode_and_cleanup(assets):
    layer = outfx.make_layer(inst(assets[0], offset=1), 320, 180)
    frame = np.zeros((180, 320, 3), np.uint8)
    layer.draw(frame, .5, 3)
    import cv2
    cap = cv2.VideoCapture(str(assets[0])); cap.set(cv2.CAP_PROP_POS_FRAMES, round(1.5*15))
    ok, expected = cap.read(); cap.release()
    assert ok and np.array_equal(frame, expected)
    layer.close()
    assert not layer.item.src.cap.isOpened()
    bad = outfx.make_layer(inst(assets[0], offset=4), 320, 180)
    with pytest.raises(ValueError, match='exceeds'):
        bad.draw(frame, 0, 3)
    assert not bad.item.src.cap.isOpened()

def test_missing_material_is_not_accepted(tmp_path):
    with pytest.raises(ValueError, match='existing local'):
        inst(tmp_path / 'missing.mp4')

@pytest.mark.parametrize('size', [(640, 360), (360, 640)])
def test_native_export_keeps_voice_and_returns_to_speaker(assets, tmp_path, size):
    import cv2
    w, h = size
    source = tmp_path / 'speaker.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        f'color=c=0x304050:s={w}x{h}:r=15:d=7', '-f', 'lavfi', '-i',
        'sine=frequency=440:duration=7', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(source)], check=True)
    out = tmp_path / 'out'; out.mkdir()
    prof = platform.profile('youtube', 'horizontal', overrides=dict(w=w, h=h))
    result = export.export_one(str(source), prof, str(out), captions=False, watermark=False,
        effects=[inst(assets[0], offset=1)], encoder='libx264', preset='ultrafast', mode='letterbox')
    path = str(out / result['file'])
    info = media.probe(path)
    assert info['has_audio'] and abs(info['duration']-7) < .15
    cap = cv2.VideoCapture(path); frames = []
    for t in (1, 3, 6):
        cap.set(cv2.CAP_PROP_POS_MSEC, t*1000); ok, frame = cap.read(); assert ok
        frames.append(frame.astype(float))
    cap.release()
    assert np.mean(np.abs(frames[0]-frames[2])) < 2
    assert np.mean(np.abs(frames[0]-frames[1])) > 25
    pcm = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-ac', '1', '-ar', '8000', '-'],
                         check=True, capture_output=True).stdout
    samples = np.frombuffer(pcm, np.float32)[int(2.5*8000):int(4.5*8000)]
    peak = np.argmax(abs(np.fft.rfft(samples))) * 8000 / len(samples)
    assert abs(peak-440) < 2

@pytest.mark.parametrize('trim,cuts,speed,at,expected_time', [
    ([3, 7], [], 2, .25, 1.5),
    ([0, 7], [[3, 4, 'pause']], 1, 1.25, 2.25),
])
def test_second_edit_tracks_source_time_and_material_changes(assets, trim, cuts, speed, at, expected_time):
    from vstudio.project import outputs as O, outrender as R
    effect = inst(assets[1], fit='card')
    st = O.empty_state()
    st['effects'] = [effect]
    st['trim'], st['cuts'], st['speed'] = trim, cuts, speed
    rec = dict(mode='pipeline', info=dict(duration=7, w=640, h=360), cues=[])
    tg = dict(target='primary', w=640, h=360, profile=None, layout='auto')
    tl = O.Timeline(st, 7)
    spec = R.visual_spec(rec, st, tl, tg, False)
    layer = outfx.make_layer(spec['layers'][0], 640, 360)
    reference = outfx.make_layer(effect, 640, 360)
    got = np.zeros((360,640,3), np.uint8); expected = got.copy()
    layer.draw(got, at, 1)
    reference.draw(expected, expected_time, 3)
    assert np.array_equal(got, expected)
    old = spec['layers'][0]['source_sig']
    Image.new('RGB', (400,1200), 'yellow').save(assets[1])
    assert R.visual_spec(rec, st, tl, tg, False)['layers'][0]['source_sig'] != old

def test_secondary_frame_pass_renders_material(assets, tmp_path):
    import cv2
    from vstudio.project import outputs as O, outrender as R
    source, photo = assets
    st = O.empty_state(); st['effects'] = [inst(photo, fit='card')]
    rec = dict(mode='pipeline', info=dict(duration=5, w=320, h=180), cues=[])
    tg = dict(target='primary', w=320, h=180, profile=None, layout='auto')
    vis = R.visual_spec(rec, st, O.Timeline(st, 5), tg, False)
    dest = str(tmp_path/'second-edit.mp4')
    R.frame_pass(str(source), dest, None, vis, tg, 15, 'preview', None, lambda progress: None)
    cap = cv2.VideoCapture(dest); cap.set(cv2.CAP_PROP_POS_MSEC, 2000)
    ok, frame = cap.read(); cap.release()
    assert ok and frame[20,160,2] > 180 and frame[20,160,0] < 50
