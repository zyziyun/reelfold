"""Native screen-detail composition, source bounds and subtitle-space contract."""
import shutil

import pytest
from vstudio import clipkit as CK, media, lesson


@pytest.mark.parametrize('regions', [[], [[0, 0, 10, 10]] * 3, [[-1, 0, 10, 10]],
                                     [[0, 0, 641, 10]], [[0, 0, float('nan'), 10]],
                                     [[True, 0, 10, 10]], [[0, 0, 0, 10]]])
def test_invalid_regions_fail(regions):
    with pytest.raises(ValueError, match='detail_regions'):
        CK.detail_geometry(CK.geometry((360, 640), 'screen', (640, 360)), (640, 360), regions)


def test_portrait_details_reserve_caption_rail_and_landscape_keeps_full_source():
    regions = [[0, 0, 320, 180], [320, 180, 320, 180]]
    portrait = CK.detail_geometry(CK.geometry((360, 640), 'screen', (640, 360)),
                                 (640, 360), regions, True)
    boxes = [portrait['main']] + [r['box'] for r in portrait['details']]
    assert all(y + h <= int(640 * .60) for x, y, w, h in boxes)
    assert all(boxes[i][1] + boxes[i][3] <= boxes[i + 1][1] for i in range(2))
    landscape = CK.geometry((640, 360), 'screen', (640, 360))
    assert CK.detail_geometry(landscape, (640, 360), regions) == landscape
    with pytest.raises(ValueError, match='camera'):
        CK.detail_geometry(dict(portrait, camera=(0, 0, 50, 50)), (640, 360), regions)


def test_lesson_preserves_verified_point_regions():
    regions = [[10, 20, 200, 100]]
    p = dict(id='p1', kind='concept', start=1, end=5, title='Tracing', detail_regions=regions)
    spec = lesson.clip_specs(dict(lang='en', points=[p]), 'source.mp4')[0]
    assert spec['parts'][1]['detail_regions'] == regions
    assert (spec['parts'][1]['a'], spec['parts'][1]['b']) == (1, 5)


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg required')
def test_native_details_duplicate_source_without_repeating_audio(tmp_path):
    import subprocess
    import numpy as np
    src = str(tmp_path / 'source.mp4')
    media.run(['ffmpeg', '-y', '-f', 'lavfi', '-i',
               'color=red:s=320x180:r=30:d=1,drawbox=x=160:y=0:w=160:h=180:color=blue:t=fill',
               '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=1',
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', src])
    spec = dict(id='test', source=src, layout='screen', _caption_rail=True,
                parts=[dict(kind='src', a=0, b=.5, detail_regions=[[0, 0, 160, 180], [160, 0, 160, 180]]),
                       dict(kind='src', a=.5, b=1)])
    result = CK.render_clip(spec, canvas=(360, 640), workdir=str(tmp_path / 'render'))
    info = media.probe(result['master'])
    assert info['has_audio'] and abs(info['duration'] - 1) < .08
    frame = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', '0.4', '-i', result['master'],
                                     '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
    rgb = np.frombuffer(frame, dtype=np.uint8).reshape(640, 360, 3)
    for i, detail in enumerate(result['timeline'][0]['details']):
        x, y, w, h = detail['box']
        pixel = rgb[y + h // 2, x + w // 2]
        assert pixel[0 if i == 0 else 2] > 200
        assert pixel[2 if i == 0 else 0] < 30
    assert len([b for b in result['keepouts'] if b['kind'] == 'source-detail']) == 2
    assert result['timeline'][1]['details'] == []
    assert all(b['t1'] <= .54 for b in result['keepouts'] if b['kind'] == 'source-detail')
    assert result['content_policy'] == 'unobstructed-source'

    def rms(path):
        data = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', path, '-vn', '-ac', '1',
                                        '-ar', '48000', '-f', 'f32le', '-'])
        wave = np.frombuffer(data, dtype=np.float32)[4800:38400]
        return np.sqrt(np.mean(wave ** 2))
    assert abs(20 * np.log10(rms(result['master']) / rms(src))) < .5


def test_mixed_aspect_details_share_space_by_content_not_equal_slots():
    geo = CK.geometry((360, 640), 'screen', (640, 360))
    regions = [[0, 0, 600, 100], [0, 0, 180, 360]]
    result = CK.detail_geometry(geo, (640, 360), regions, caption_band=(210, 240))
    wide, tall = [r['box'] for r in result['details']]
    # One wide strip must not reserve half the remaining height while a tall
    # detail is unnecessarily shrunk. Both remain uncropped and above bottom.
    assert tall[2] >= 140
    assert abs(wide[3] / wide[2] - 100 / 600) < .02
    assert abs(tall[3] / tall[2] - 2) < .02
    assert wide[1] >= 240
    assert wide[1] + wide[3] < tall[1]
    assert tall[1] + tall[3] <= 628
