"""Learn-and-share routing, source fidelity, honest recording gates and real montage handoffs."""
import copy
import json
import os
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from vstudio import learning as L, media
from vstudio.intake import rules as R
from vstudio.project import manifests as M
from vstudio.project.adapters import learning as A


def sources():
    return {'ref': dict(role='reference', image=False, duration=8, has_audio=True, width=320),
            'me': dict(role='commentary', image=False, duration=8, has_audio=True, width=320)}


def doc():
    return dict(title='What I learned', segments=[
        dict(source='ref', start=1, end=2, point='Listen to the claim',
             citation=dict(title='An interview', creator='A guest', locator='https://example.org/interview')),
        dict(source='me', start=2, end=4, point='My own application')])


@pytest.mark.parametrize('mutate', [
    lambda d: d['segments'][0].update(source='invented'),
    lambda d: d['segments'][0].update(end=9),
    lambda d: d['segments'][0].update(start=True),
    lambda d: d['segments'][0].update(start=float('nan')),
    lambda d: d['segments'][0].update(end=float('inf')),
    lambda d: d['segments'][0].pop('citation'),
    lambda d: d['segments'][0]['citation'].update(creator=''),
    lambda d: d['segments'][1].update(source='ref'),
    lambda d: d['segments'][1].update(point=''),
])
def test_unfounded_or_invalid_montage_rejected(mutate):
    d = doc(); mutate(d)
    with pytest.raises(ValueError):
        L.validate(d, sources())


def test_both_real_sides_and_source_citations():
    assert L.validate(doc(), sources())
    assert 'https://example.org/interview · 1.00–2.00s' in L.citations(doc())
    s = sources(); s['me']['has_audio'] = False
    with pytest.raises(ValueError, match='no audio'):
        L.validate(doc(), s)


@pytest.mark.parametrize('prompt', ['学习分享，把访谈切片后加我的口播和感想',
    '边学习边介绍，基于播客讲解自己的经验', '读书分享加自己理解',
    'Make a learning commentary from a course and my own experience', 'Create a reaction video'])
def test_learning_purpose_wins_over_plain_slicing(prompt):
    intent = R.parse_prompt(prompt)
    assert R.choose_recipes(intent, dict(files=[], groups=[]))[0][0] == 'learning-commentary'


def test_registry_and_format_expose_mode():
    from vstudio import formats
    assert not M.validate(M.get('learning-commentary'))
    assert formats.detect('学习分享，播客切片后加口播') == 'learning-commentary'
    assert formats.get('learning-commentary', {})['speed']['inserts'] == 1


def test_missing_take_prepares_recording_prompt_without_model(tmp_path):
    class C:
        inputs = {}; item_dir = str(tmp_path)
        def request(self): return 'Learn from this interview and discuss my experience'
        def lang(self): return 'en'
        def item_path(self, name): return str(tmp_path/name)
    with pytest.raises(ValueError, match='recording first'):
        A.draft_montage(C(), {}, str(tmp_path/'montage.json'),
            complete=lambda *a, **k: pytest.fail('Do not manufacture a personal take'))
    assert 'one real experience' in (tmp_path/'RECORDING.md').read_text()
    assert not (tmp_path/'montage.json').exists()


@pytest.fixture
def actual(tmp_path):
    paths = []
    for name, colour, freq in [('ref', 'red', 440), ('me', 'blue', 880)]:
        path = str(tmp_path/f'{name}.mp4')
        media.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', f'color={colour}:s=320x240:r=30:d=5',
            '-f', 'lavfi', '-i', f'sine=frequency={freq}:sample_rate=48000:duration=5',
            *media.delivery_args(preset='ultrafast', audio=True, encoder='libx264'), path])
        paths.append(path)
    return paths


def mapped(actual):
    src = L.catalog(dict(references=[actual[0]], takes=[actual[1]]))
    ids = list(src)
    d = doc(); d['segments'][0]['source'] = ids[0]; d['segments'][1]['source'] = ids[1]
    return src, d


def test_real_order_geometry_timing_audio_and_originals(tmp_path, actual):
    import hashlib
    before = [hashlib.sha256(open(p,'rb').read()).hexdigest() for p in actual]
    src, d = mapped(actual)
    dest = str(tmp_path/'montage.mp4')
    result = L.render(d, src, dest, width=320, height=240, preset='ultrafast')
    info = media.probe(dest)
    assert (info['display_w'], info['display_h']) == (320, 240)
    assert abs(info['duration']-3) < .15 and info['has_audio']
    assert [x['role'] for x in result['timeline']] == ['reference','commentary']
    for t, channel, hz in [(.5,0,440),(1.7,2,880)]:
        raw = subprocess.check_output([media.ffmpeg_bin(), '-v', 'error', '-ss', str(t), '-i', dest,
            '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
        assert np.frombuffer(raw,np.uint8).reshape(240,320,3).mean(axis=(0,1))[channel] > 200
        wav = subprocess.check_output([media.ffmpeg_bin(), '-v','error','-ss',str(t),'-i',dest,
            '-t','0.25','-vn','-ar','48000','-ac','1','-f','f32le','-'])
        samples = np.frombuffer(wav,np.float32)
        peak = np.fft.rfftfreq(len(samples),1/48000)[np.argmax(abs(np.fft.rfft(samples)))]
        assert abs(peak-hz) < 6
    assert before == [hashlib.sha256(open(p,'rb').read()).hexdigest() for p in actual]


def test_page_with_own_voice_and_not_reference_audio(tmp_path, actual):
    from PIL import Image
    page = str(tmp_path/'page.png'); Image.new('RGB',(200,300),'green').save(page)
    src = L.catalog(dict(pages=[page], takes=[actual[1]])); ids=list(src)
    s = dict(source=ids[0], start=0,end=1,point='My reading',voice=ids[1],voice_start=1,
             citation=dict(title='A book',creator='Author',locator='First edition, page 12'))
    d = dict(title='A reading',segments=[s,dict(s,voice_start=2)])
    result=L.render(d,src,str(tmp_path/'reading.mp4'),width=320,height=240,preset='ultrafast')
    assert 1.9 < result['duration'] < 2.15
    d['segments'][0]['voice'] = 'missing'
    with pytest.raises(ValueError,match='own commentary'):
        L.validate(d,src)


def test_real_project_reaches_source_review_without_model(tmp_path, actual, monkeypatch):
    from vstudio.project.core import Project
    monkeypatch.setenv('VSTUDIO_HOME',str(tmp_path/'home'))
    monkeypatch.setenv('VSTUDIO_CACHE',str(tmp_path/'cache'))
    monkeypatch.setenv('VSTUDIO_LLM_PROVIDER','none')
    monkeypatch.setenv('VSTUDIO_LLM_SEGMENT_PLAN_PROVIDER','none')
    p=Project.create(str(tmp_path/'project'),recipe='learning-commentary',inputs=dict(references=[actual[0]]))
    (tmp_path/'project/items/main/SCRIPT.md').write_text('# My outline\n\n## RECORD\nMy actual thoughts.')
    result=p.run(auto=["all"])
    assert (tmp_path/'project/items/main/RECORDING.md').exists(), result
    assert not (tmp_path/'project/items/main/work/master.mp4').exists()


def test_creation_entry_exists_before_materials_or_recording(tmp_path, monkeypatch):
    from vstudio.intake import plan
    monkeypatch.setenv('VSTUDIO_LLM_PROVIDER', 'none')
    result = plan.make_plan('学习分享：我想读书加上自己的理解', [], ui_lang='zh')
    assert [x['recipe'] for x in result['projects']] == ['learning-commentary']
    assert not result['projects'][0]['inputs']
    assert result['projects'][0]['checkpoints'][0]['id'] == 'outline'


def test_real_pipeline_exports_source_citations_and_keeps_publish_gate(tmp_path, actual, monkeypatch):
    from vstudio.project.core import Project
    monkeypatch.setenv('VSTUDIO_HOME',str(tmp_path/'home'))
    monkeypatch.setenv('VSTUDIO_CACHE',str(tmp_path/'cache'))
    monkeypatch.setenv('VSTUDIO_LLM_PROVIDER','none')
    src,d = mapped(actual)
    p=Project.create(str(tmp_path/'pipeline'),recipe='learning-commentary',
        inputs=dict(references=[actual[0]], takes=[actual[1]]),
        params=dict(width=320,height=240,preset='ultrafast',platforms=['youtube']))
    item=tmp_path/'pipeline/items/main'
    (item/'SCRIPT.md').write_text('# Learning outline\n\n## RECORD\nMy real point.')
    (item/'work').mkdir(exist_ok=True)
    (item/'work/sources.json').write_text(json.dumps(src))
    (item/'work/montage.json').write_text(json.dumps(d))
    p.run(auto=['outline','montage'])
    manifest=json.loads((item/'exports/manifest.json').read_text())
    assert len(manifest['exports'])==1
    out=manifest['exports'][0]
    assert media.probe(str(item/'exports'/out['file']))['has_audio']
    assert 'https://example.org/interview' in (item/'exports'/out['post']).read_text()
    assert p.data['answers'].get('publish') is None
    from vstudio.project import outputs as O
    oid=O.list_outputs(p.dir)['outputs'][0]['id']
    view=O.show(p.dir,oid)
    assert view['ok'] and view['caps']['trim'] and view['caps']['audio']
    O.edit(p.dir,oid,[dict(op='trim',start=.1,snap=False)])
    assert O.show(p.dir,oid)['state']['trim'][0] == .1
    O.undo(p.dir,oid)
    assert O.show(p.dir,oid)['state']['trim'] == [None,None]
