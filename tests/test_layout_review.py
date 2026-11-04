from types import SimpleNamespace
import pytest
from vstudio.project import autopilot as AP, manifests
from vstudio.project.build import file_sha


@pytest.mark.parametrize('verdict', ['pass', 'fix', 'unknown', 'missing', 'changed', 'error'])
def test_layout_judge_receives_images_and_never_defaults_past_unknown(tmp_path, verdict):
    p = tmp_path / 'frame.jpg'
    p.write_bytes(b'frame')
    cp = dict(id='layout', kind='review', scope='item', visual_review=True)
    project = SimpleNamespace(data={'autopilot':True, 'prompt':'product'}, checkpoint=lambda _:cp)
    pay = dict(id='layout', item='one', default={'approve':True},
               previews=[dict(kind='image', path=str(p))], options=[dict(file=str(p),sha=file_sha(p))])
    def complete(*args, **kwargs):
        assert kwargs['images'] == [str(p)]
        if verdict == 'error':
            raise RuntimeError('offline')
        if verdict == 'changed':
            p.write_bytes(b'changed')
        rows = [] if verdict == 'missing' else [dict(index=0, verdict=verdict if verdict != 'changed' else 'pass', evidence='Subject intact')]
        return dict(provider='test', json=dict(frames=rows, summary='Specific layout result'))
    d = AP.decide(project, pay, complete=complete)
    if verdict == 'pass':
        assert d['value'] == {'approve':True} and d['by'] == 'ai'
        assert d['visual_review']['evidence'][0]['sha'] == file_sha(p)
    else:
        assert d['blocker'] == 'needs-input' and 'value' not in d


def test_photo_story_enables_visual_review():
    m = manifests.get('photo-story')
    assert not manifests.validate(m)
    assert next(c for c in m['checkpoints'] if c['id']=='layout')['visual_review']
