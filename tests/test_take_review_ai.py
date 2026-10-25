from types import SimpleNamespace
import json

import pytest
from vstudio import take_review as R, take_review_ai as AI
from vstudio.project.adapters import aivideo as A


def response():
    return dict(hard={k: dict(flaw=False, reason='Not visible in this inanimate product shot', time=None) for k in R.HARD},
                soft={k: dict(flaw=False, reason='Not applicable to this flat illustration', time=None) for k in R.SOFT},
                scores=dict(A=5, B=4, C=4), notes='Product stays in frame')


def normalize(doc=None, audio=False, shots=None, missing=None):
    return AI.normalize(doc or response(), 'a.mp4', 'hash', dict(duration=2, has_audio=audio),
                        shots or [{}], [], missing or [])


def test_audio_claims_cannot_pass_image_only_review():
    card = normalize(audio=True)
    assert card['hard']['lipsync_or_line'] is None
    assert card['soft']['sound_mismatch'] is None
    assert R.verdict(card)[0] != 'pass'
    assert normalize(audio=False)['hard']['lipsync_or_line'] is False
    assert normalize(shots=[dict(lines=[dict(text='Hello')])])['hard']['lipsync_or_line'] is True
    assert R.verdict(normalize(shots=[dict(audio='native')]))[0] == 'redo'


def test_missing_references_remain_unknown():
    card = normalize(missing=[dict(kind='characters'), dict(kind='scenes')])
    assert card['scores']['A'] is None
    assert card['hard']['scene_master'] is None
    assert R.verdict(card)[0] != 'pass'


@pytest.mark.parametrize('key,value', [('time', 3), ('time', float('nan')), ('flaw', 'false'), ('reason', '')])
def test_invalid_evidence_rejected(key, value):
    doc = response(); doc['hard']['physics'][key] = value
    with pytest.raises(ValueError):
        normalize(doc)


def test_visible_flaw_needs_timestamp():
    doc = response(); doc['hard']['physics']['flaw'] = True
    with pytest.raises(ValueError):
        normalize(doc)
    doc['hard']['physics']['time'] = .5
    assert R.verdict(normalize(doc))[0] == 'redo'


def test_real_route_receives_sequence_and_invalidates_plan(tmp_path, monkeypatch):
    from vstudio import footage, media
    video = tmp_path/'u1_v1.mp4'; video.write_bytes(b'fixture')
    brief = tmp_path/'project.yaml'; brief.write_text('shots: []')
    ref = tmp_path/'ref.jpg'; ref.write_bytes(b'ref')
    sheet = tmp_path/'sheet.jpg'; sheet.write_bytes(b'sheet')
    monkeypatch.setattr(footage, 'sequence_context', lambda *a, **k: ('sampled frames', [str(sheet)], [dict(sampling_gap=.25)]))
    monkeypatch.setattr(media, 'probe', lambda _: dict(duration=2, has_audio=False))
    calls = []
    def complete(*args, **kwargs):
        calls.append((args, kwargs))
        return dict(json=response(), provider='test', model='fixture')
    project = dict(shots=[dict(id='u1', chars=['A'])], characters=dict(A=dict(ref='ref.jpg')))
    card = AI.review(str(video), project, 'u1', str(tmp_path/'review'), str(tmp_path), complete=complete)
    assert calls[0][1]['images'] == [str(sheet), str(ref)]
    path = tmp_path/'card.json'; path.write_text(json.dumps(card))
    assert R.inspect(str(video), str(path))[0] == 'pass'
    ref.write_bytes(b'changed')
    assert R.inspect(str(video), str(path))[0] == 'redo'
    ref.write_bytes(b'ref'); brief.write_text('shots: changed')
    assert R.inspect(str(video), str(path))[0] == 'redo'


def test_adapter_runs_visual_review_not_just_sheet(tmp_path, monkeypatch):
    root = tmp_path/'work'/'ai'; (root/'takes').mkdir(parents=True)
    (root/'takes'/'u1_v1.mp4').write_bytes(b'video')
    (root/'project.yaml').write_text('shots: [{id: u1}]')
    calls = []
    def review(*args):
        calls.append(args)
        return normalize()
    monkeypatch.setattr(AI, 'review', review)
    env = SimpleNamespace(item_dir=str(tmp_path), workflow_dir='unused', params={}, fmt=lambda x: x,
                          run=lambda *a, **k: None)
    result = A.judge(env)
    assert len(calls) == 1
    assert calls[0][2] == 'u1'
    rows = json.load(open(result['takes']))['takes']
    assert json.load(open(rows[0]['card']))['review_source'] == 'ai-sampled-visual'


def test_adapter_preserves_manual_rejection(tmp_path, monkeypatch):
    root = tmp_path/'work'/'ai'; (root/'takes').mkdir(parents=True); (root/'judge').mkdir()
    video = root/'takes'/'u1_v1.mp4'; video.write_bytes(b'video')
    (root/'project.yaml').write_text('shots: [{id: u1}]')
    card = R.bound_card(str(video)); card['hard']['physics'] = True
    path = root/'judge'/'u1_v1.card.json'; path.write_text(json.dumps(card))
    monkeypatch.setattr(AI, 'review', lambda *a: pytest.fail('manual review must not be overwritten'))
    env = SimpleNamespace(item_dir=str(tmp_path), workflow_dir='unused', params={}, fmt=lambda x: x,
                          run=lambda *a, **k: None)
    A.judge(env)
    assert json.load(open(path)) == card
