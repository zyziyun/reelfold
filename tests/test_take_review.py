import json
from types import SimpleNamespace

import pytest
import yaml
from vstudio import take_review as R
from vstudio.project.adapters import aivideo as A


def fixture(tmp_path):
    rows = []
    for name in ('a_v1', 'a_v2', 'b_v1'):
        video = tmp_path / (name + '.mp4')
        video.write_bytes(name.encode())
        card = tmp_path / (name + '.card.json')
        data = R.bound_card(str(video))
        data.update(hard=dict.fromkeys(R.HARD, False), soft=dict.fromkeys(R.SOFT, False),
                    scores=dict(A=5, B=5, C=5))
        card.write_text(json.dumps(data))
        rows.append(dict(unit=name.split('_')[0], take=str(video), card=str(card), sheet=str(tmp_path/'sheet.jpg')))
    index = tmp_path / 'takes.json'
    index.write_text(json.dumps(dict(takes=rows)))
    env = SimpleNamespace(inputs=dict(judge=dict(takes=str(index))))
    return rows, env


def test_latest_unreviewed_is_not_default(tmp_path):
    rows, env = fixture(tmp_path)
    open(rows[1]['card'], 'w').write(json.dumps(R.bound_card(rows[1]['take'])))
    payload = A.takes_payload(env, dict(after='judge'))
    assert payload['default']['picks']['a'] == rows[0]['take']
    open(rows[0]['take'], 'ab').write(b'replaced')
    assert A.takes_payload(env, dict(after='judge'))['default'] is None


def test_selection_requires_complete_units_and_current_reviews(tmp_path):
    rows, env = fixture(tmp_path)
    payload = A.takes_payload(env, dict(after='judge'))
    picks = payload['default']['picks']
    result = A.takes_apply(SimpleNamespace(payload=payload, value=dict(picks=picks)))
    assert len(result['params']['takes_reviews']) == 2
    for bad in ({}, {'a': rows[0]['take']}, {'a': rows[2]['take'], 'b': rows[1]['take']}):
        with pytest.raises(ValueError):
            A.takes_apply(SimpleNamespace(payload=payload, value=dict(picks=bad)))
    open(picks['a'], 'ab').write(b'changed after UI review')
    with pytest.raises(ValueError, match='current video'):
        A.takes_apply(SimpleNamespace(payload=payload, value=dict(picks=picks)))


def test_authored_timeline_cannot_bypass_review(tmp_path):
    rows, env = fixture(tmp_path)
    timeline = tmp_path/'timeline.yaml'
    timeline.write_text(yaml.safe_dump(dict(takes_dir='.', edl=[dict(take=rows[0]['take'])])))
    A._check_timeline_reviews(str(timeline), {rows[0]['take']: rows[0]['card']})
    with pytest.raises(ValueError):
        A._check_timeline_reviews(str(timeline), {})
    open(rows[0]['take'], 'ab').write(b'replaced')
    with pytest.raises(ValueError):
        A._check_timeline_reviews(str(timeline), {rows[0]['take']: rows[0]['card']})


def test_missing_or_broken_card_cannot_pass(tmp_path):
    video = tmp_path/'take.mp4'; video.write_bytes(b'video')
    card = tmp_path/'card.json'
    for data in (None, '{bad', '[]', '{}'):
        if data is not None:
            card.write_text(data)
        assert R.inspect(str(video), str(card))[0] == 'redo'


def test_review_changes_invalidate_cached_gate(tmp_path):
    root = tmp_path/'work'/'ai'
    (root/'takes').mkdir(parents=True)
    (root/'judge').mkdir()
    video = root/'takes'/'a_v1.mp4'; video.write_bytes(b'one')
    params = dict(_item_dir=str(tmp_path))
    before = A.takes_recheck(params)
    video.write_bytes(b'two')
    assert A.takes_recheck(params) != before
    before = A.takes_recheck(params)
    (root/'judge'/'a_v1.card.json').write_text('{}')
    assert A.takes_recheck(params) != before


def test_authored_adapter_emits_guarded_copy(tmp_path):
    rows, _ = fixture(tmp_path)
    root = tmp_path/'work'/'ai'; root.mkdir(parents=True)
    hand = root/'timeline.yaml'
    original = yaml.safe_dump(dict(edl=[dict(take=rows[0]['take'])]))
    hand.write_text(original)
    env = SimpleNamespace(item_dir=str(tmp_path), params=dict(takes_reviews={rows[0]['take']: rows[0]['card']}))
    result = A.timeline(env)
    assert result['authored']
    assert hand.read_text() == original
    checked = yaml.safe_load(open(result['timeline']))
    assert checked['review_cards'] == env.params['takes_reviews']


def test_human_can_complete_unknown_checks_without_bypassing_binding(tmp_path):
    rows, env = fixture(tmp_path)
    path = rows[1]['card']; card = json.load(open(path))
    card['hard']['lipsync_or_line'] = None
    card['soft']['sound_mismatch'] = None
    open(path, 'w').write(json.dumps(card))
    payload = A.takes_payload(env, dict(after='judge'))
    candidate = payload['options'][0]['takes'][1]
    patch = dict(revision=candidate['revision'], hard=dict(card['hard'], lipsync_or_line=False),
                 soft=dict(card['soft'], sound_mismatch=False), scores=card['scores'])
    picks = dict(a=rows[1]['take'], b=rows[2]['take'])
    A.takes_apply(SimpleNamespace(payload=payload, value=dict(picks=picks, reviews=dict(a=patch))))
    saved = json.load(open(path))
    assert saved['review_source'] == 'human'
    assert R.inspect(rows[1]['take'], path)[0] == 'pass'
    with pytest.raises(ValueError, match='reload'):
        A.takes_apply(SimpleNamespace(payload=payload, value=dict(picks=picks, reviews=dict(a=patch))))


def test_bad_selection_does_not_write_any_manual_reviews(tmp_path):
    rows, env = fixture(tmp_path)
    payload = A.takes_payload(env, dict(after='judge'))
    candidate = payload['options'][0]['takes'][1]
    before = open(rows[1]['card']).read()
    card = json.loads(before)
    patch = dict(revision=candidate['revision'], hard=card['hard'], soft=card['soft'], scores=card['scores'])
    with pytest.raises(ValueError):
        A.takes_apply(SimpleNamespace(payload=payload, value=dict(picks=dict(a=rows[1]['take'], b='not-a-take'), reviews=dict(a=patch))))
    assert open(rows[1]['card']).read() == before
    open(rows[1]['take'], 'ab').write(b'replaced')
    with pytest.raises(ValueError, match='current video'):
        A.takes_apply(SimpleNamespace(payload=payload, value=dict(picks=dict(a=rows[1]['take'], b=rows[2]['take']), reviews=dict(a=patch))))
    assert open(rows[1]['card']).read() == before
