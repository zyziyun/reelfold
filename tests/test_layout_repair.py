from types import SimpleNamespace
from vstudio.project import layout_review as LR, autopilot as AP, drafts
from vstudio.project.build import file_sha


def test_repair_passes_actual_review_images_and_persists_retry_limit(tmp_path, monkeypatch):
    image = tmp_path / 'frame.jpg'
    image.write_bytes(b'frame')
    project = SimpleNamespace(state_dir=str(tmp_path / 'state'),
                              checkpoint=lambda _:dict(visual_repair='story'))
    pay = dict(id='layout', item='one')
    decision = dict(reason='Subject cropped', visual_review=dict(
        frames=[dict(index=0, verdict='fix', evidence='Cup bottom cut')],
        evidence=[dict(path=str(image), sha=file_sha(image))]))
    calls = []
    def complete(*args, **kwargs):
        assert kwargs['images'] == ['source.jpg', str(image)]
    def redraft(p, author, item, instruction, complete):
        assert author == 'story' and item == 'one' and 'Cup bottom cut' in instruction
        complete('planner', 'system', 'body', images=['source.jpg'])
        calls.append(item)
        return dict(ok=True, changed=True)
    monkeypatch.setattr(drafts, 'redraft', redraft)
    assert LR.repair(project, pay, decision, complete)
    # Reconstructing the project simulates a resume; retry count must survive it.
    resumed = SimpleNamespace(**vars(project))
    assert LR.repair(resumed, pay, decision, complete)
    assert not LR.repair(resumed, pay, decision, complete)
    assert calls == ['one', 'one']
    assert len([e for e in AP.history(project) if e['event']=='layout-repair-started']) == 2


def test_unknown_or_changed_evidence_does_not_trigger_blind_rewrite(tmp_path, monkeypatch):
    image = tmp_path / 'frame.jpg'
    image.write_bytes(b'frame')
    project = SimpleNamespace(state_dir=str(tmp_path / 'state'),
                              checkpoint=lambda _:dict(visual_repair='story'))
    decision = dict(visual_review=dict(frames=[dict(verdict='unknown')],
                    evidence=[dict(path=str(image),sha=file_sha(image))]))
    def forbidden(*a, **k):
        raise AssertionError('must not rewrite')
    monkeypatch.setattr(drafts, 'redraft', forbidden)
    assert not LR.repair(project, dict(id='layout',item='one'), decision)
    decision['visual_review']['frames'][0]['verdict'] = 'fix'
    image.write_bytes(b'new frame')
    assert not LR.repair(project, dict(id='layout',item='one'), decision)
    assert not AP.history(project)


def test_unchanged_redraft_is_not_a_success(tmp_path, monkeypatch):
    image = tmp_path / 'frame.jpg'
    image.write_bytes(b'frame')
    project = SimpleNamespace(state_dir=str(tmp_path / 'state'), checkpoint=lambda _:dict(visual_repair='story'))
    decision = dict(visual_review=dict(frames=[dict(verdict='fix')],
                    evidence=[dict(path=str(image),sha=file_sha(image))]))
    monkeypatch.setattr(drafts, 'redraft', lambda *a, **kw: dict(ok=True,changed=False))
    assert not LR.repair(project, dict(id='layout',item='one'), decision)
    assert AP.history(project)[-1]['ok'] is False
