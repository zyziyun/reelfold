"""Supplied media through the real context/planner/export path; fake only the model boundary."""
import json
import subprocess
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from vstudio import spoken, supporting_media
from vstudio.batch import stages
from vstudio.batch.recipes import Ctx

CUES = [dict(start=0, end=3, text='Here is the example.'),
        dict(start=3, end=6, text='The supplied graphic is red.'),
        dict(start=6, end=10, text='Now back to the explanation.')]
BEAT = {'from': 1, 'to': 1, 'kind': 'insert', 'title': '', 'items': [],
        'asset': 'p0001', 'evidence': CUES[1]['text']}

@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv('VSTUDIO_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('VSTUDIO_DEFAULT_PERSONA', '1')

@pytest.mark.parametrize('extra', [{'asset': []}, {'asset': 'missing'}, {'offset': -1},
    {'offset': float('nan')}, {'offset': True}, {'offset': 1}, {'fit': 'unknown'}, {'evidence': 'Wrong statement'}])
def test_insert_rejects_invalid_source_or_evidence(extra):
    with pytest.raises(ValueError):
        spoken.validate({'beats': [dict(BEAT, **extra)]}, CUES, 10,
                        [dict(id='p0001', kind='image', path='/unused.png')])

def test_video_range_must_fit_source():
    assets = [dict(id='p0001', kind='video', path='/unused.mp4', duration=4)]
    assert spoken.validate({'beats': [dict(BEAT, offset=1)]}, CUES, 10, assets)
    with pytest.raises(ValueError, match='exceeds'):
        spoken.validate({'beats': [dict(BEAT, offset=2)]}, CUES, 10, assets)

def test_context_freezes_exif_orientation_and_distinguishes_names(tmp_path):
    paths = []
    for folder, color in [('a', 'red'), ('b', 'blue')]:
        d = tmp_path / folder; d.mkdir()
        path = d / 'same.jpg'
        im = Image.new('RGB', (120, 60), color)
        exif = im.getexif(); exif[274] = 6
        im.save(path, exif=exif); paths.append(str(path))
    originals = [Path(p).read_bytes() for p in paths]
    text, sheets, assets = supporting_media.context(paths, str(tmp_path / 'context'))
    assert [a['id'] for a in assets] == ['p0001', 'p0002']
    assert all(Image.open(a['path']).size == (60, 120) for a in assets)
    assert sheets and all(Path(p).exists() for p in sheets)
    assert [Path(p).read_bytes() for p in paths] == originals
    assert 'p0001' in text and 'p0002' in text

def test_unpreviewed_video_cannot_be_selected(tmp_path, monkeypatch):
    from vstudio import footage
    path = tmp_path / 'bad.mp4'; path.write_bytes(b'bad')
    monkeypatch.setattr(footage, 'context', lambda *a, **kw: ('failed preview', [],
                        [dict(id='v0001', path=str(path), dur=10)]))
    text, sheets, assets = supporting_media.context([str(path)], str(tmp_path / 'work'))
    assert not assets and not sheets and 'UNAVAILABLE: v0001' in text

def test_native_export_uses_planned_material_and_retains_audio(tmp_path, monkeypatch):
    import cv2
    from vstudio import export, platform, media
    photo = tmp_path / 'red.png'; Image.new('RGB', (320, 180), 'red').save(photo)
    cuepath = tmp_path / 'cues.json'; cuepath.write_text(json.dumps(dict(cues=CUES)))
    job = dict(params=dict(_inputs=dict(broll=[str(photo)])))
    ctx = Ctx(job, {}, str(tmp_path), dict(compose=dict(cues=str(cuepath), duration=10)), str(tmp_path))
    calls = []
    def model(task, system, prompt, **kw):
        calls.append(kw)
        assert kw['images'] and 'p0001' in prompt
        return dict(json=dict(beats=[BEAT]))
    from vstudio import llm
    monkeypatch.setattr(llm, 'complete', model)
    result = stages.run_finish(ctx)
    assert calls and len(result['files']) >= 3 and all(Path(p).exists() for p in result['files'])
    effect = result['effects'][0]
    assert effect['effect'] == 'media-insert' and Path(effect['params']['file']).exists()
    sig = stages._material_signatures(job, {})
    Image.new('RGB', (320, 180), 'blue').save(photo)
    assert stages._material_signatures(job, {}) != sig
    # The plan's frozen image still has the pixels shown to the model.
    source = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'color=c=black:s=320x180:r=15:d=10', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=10',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-shortest', str(source)], check=True)
    out = tmp_path / 'out'; out.mkdir()
    prof = platform.profile('youtube', 'horizontal', overrides=dict(w=320, h=180))
    rendered = export.export_one(str(source), prof, str(out), effects=result['effects'],
        captions=False, watermark=False, encoder='libx264', preset='ultrafast', mode='letterbox')
    path = str(out / rendered['file']); cap = cv2.VideoCapture(path)
    for time, red in [(1, False), (4.5, True), (8, False)]:
        cap.set(cv2.CAP_PROP_POS_MSEC, time*1000); ok, frame = cap.read()
        assert ok
        assert (frame[:, :, 2].mean() > 200) == red
    cap.release()
    assert media.probe(path)['has_audio']
    pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', '4', '-i', path,
        '-t', '1', '-vn', '-ac', '1', '-ar', '8000', '-f', 'f32le', '-'])
    x = np.frombuffer(pcm, dtype='<f4')
    peak = np.argmax(abs(np.fft.rfft(x))) * 8000 / len(x)
    assert abs(peak - 440) < 2 and np.std(x) > .01

def test_project_materials_do_not_replace_primary_input(tmp_path):
    from vstudio.project.core import Project
    from vstudio.batch import thfolder, lfsplit
    source = tmp_path / 'talk.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'color=c=black:s=320x180:r=15:d=3', '-c:v', 'libx264', str(source)], check=True)
    photo = tmp_path / 'graphic.png'; Image.new('RGB', (32, 32)).save(photo)
    project = Project.create(str(tmp_path / 'project'), recipe='talkinghead',
        inputs=dict(video=[str(source)], broll=[str(photo)]), params=dict(pipeline='fast'))
    row = project.jobs_rows()[0]
    assert row['file'] == source.name
    job = dict(params=row)
    assert supporting_media.paths(job, project.spec()) == [str(photo)]
    dag = {s.name: s for s in thfolder.th_stages()}
    assert dag['finish'].enabled(job, {}) and 'finish' in dag['export'].deps
    assert not dag['finish'].enabled(dict(params=dict(finishing='editorial')), {})
    with pytest.raises(ValueError, match='layout_mode=reframe'):
        lfsplit.expand_split({}, [row])


def test_missing_material_and_all_failed_previews_stop_visibly(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='missing'):
        supporting_media.context([str(tmp_path / 'absent.png')], str(tmp_path / 'work'))
    cuepath = tmp_path / 'cues.json'; cuepath.write_text(json.dumps(dict(cues=CUES)))
    ctx = Ctx(dict(params=dict(broll=['bad.mp4'])), {}, str(tmp_path),
              dict(compose=dict(cues=str(cuepath), duration=10)), str(tmp_path))
    monkeypatch.setattr(supporting_media, 'context', lambda *a: ('unavailable', [], []))
    with pytest.raises(ValueError, match='no usable visual previews'):
        stages.run_finish(ctx)


def test_real_video_preview_maps_to_bounded_insert(tmp_path):
    path = tmp_path / 'sample.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc2=size=320x180:rate=15:duration=5', '-c:v', 'libx264', str(path)], check=True)
    text, images, assets = supporting_media.context([str(path)], str(tmp_path / 'work'))
    assert images and assets == [dict(id='v0001', kind='video', path=str(path), duration=5)]
    result = spoken.plan(CUES, 10, materials=assets, images=images, material_context=text,
        complete=lambda *a, **kw: dict(json=dict(beats=[dict(BEAT, asset='v0001', offset=1)])))
    assert result['effects'][0]['params'] == dict(file=str(path), offset=1, fit='contain')
