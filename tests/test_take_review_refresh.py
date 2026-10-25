import json
from types import SimpleNamespace

import pytest

from vstudio import take_review as R, take_review_ai as AI
from vstudio.project import take_reviews as T, manifests
from vstudio.project.adapters import aivideo as A
from vstudio.batch.run import BatchBusy
from vstudio.oscompat import try_lock, unlock


def fixture(tmp_path):
    root = tmp_path/'items'/'one'/'work'/'ai'
    (root/'takes').mkdir(parents=True)
    (root/'judge').mkdir()
    (tmp_path/'state'/'checkpoints'/'one').mkdir(parents=True)
    (root/'project.yaml').write_text('shots: [{id: u1}]')
    video = root/'takes'/'u1_v1.mp4'; video.write_bytes(b'old')
    card = root/'judge'/'u1_v1.card.json'; card.write_text(json.dumps(R.bound_card(str(video))))
    (root/'judge'/'takes.json').write_text(json.dumps({'takes': [dict(unit='u1',take=str(video),card=str(card),sheet='unused')]}))
    m = manifests.get('ai-video')
    project = SimpleNamespace(dir=str(tmp_path),state_dir=str(tmp_path/'state'),manifest=m,data={},
        params=lambda: {}, jobs_rows=lambda: [dict(id='one',judge_asr=False)],
        checkpoint=lambda _: next(c for c in m['checkpoints'] if c['id']=='takes'),
        pending=lambda **kw: [{}])
    return project, video, card


def test_refresh_calls_only_judge_and_keeps_gate_pending(tmp_path, monkeypatch):
    project, video, card = fixture(tmp_path)
    video.write_bytes(b'changed')
    calls = []
    monkeypatch.setattr(T.B.Env, 'run', lambda self, argv, **kw: calls.append(argv))
    monkeypatch.setattr(AI, 'review', lambda *a: R.bound_card(str(video)))
    result = T.refresh(project, 'one')
    assert result['ok']
    assert all('judge.py' in cmd[1] and cmd[2] == 'sheet' for cmd in calls)
    payload = json.loads((tmp_path/'state'/'checkpoints'/'one'/'takes.json').read_text())
    assert payload['default'] is None
    assert payload['options'][0]['takes'][0]['stale'] is False
    assert len(list(card.parent.glob('history/*.json'))) == 1


def test_current_payload_detects_changed_take_without_writing(tmp_path):
    project, video, card = fixture(tmp_path)
    before = T.current_payload(project,'one',{})
    oldcard = card.read_bytes()
    video.write_bytes(b'changed')
    after = T.current_payload(project,'one',{})
    assert before['digest'] != after['digest']
    assert after['options'][0]['takes'][0]['stale']
    assert card.read_bytes() == oldcard


def test_refresh_rejects_busy_unknown_or_not_waiting(tmp_path, monkeypatch):
    project, _, _ = fixture(tmp_path)
    monkeypatch.setattr(A, 'judge', lambda *a: pytest.fail('must not review'))
    with pytest.raises(ValueError, match='unknown'):
        T.refresh(project,'../other')
    with open(tmp_path/'state'/'run.lock','a') as lock:
        assert try_lock(lock)
        try:
            with pytest.raises(BatchBusy): T.refresh(project,'one')
        finally: unlock(lock)
    project.pending = lambda **kw: []
    with pytest.raises(ValueError,match='not waiting'): T.refresh(project,'one')
