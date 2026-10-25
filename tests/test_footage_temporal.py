"""Process evidence retains moment/cut context and adds bounded ordered frames."""
import pytest
from vstudio import footage as F


@pytest.mark.parametrize('count,budget', [(1, 80), (3, 80), (24, 10)])
def test_temporal_context_budget_and_source_identity(tmp_path, monkeypatch, count, budget):
    paths = []
    for i in range(count):
        p = tmp_path / f'clip{i}.mp4'; p.touch(); paths.append(str(p))
    monkeypatch.setattr(F, 'facts', lambda p: dict(file=p, dur=40, w=100, h=80, orientation='horizontal'))
    monkeypatch.setattr(F, 'sheet', lambda p, out, **kw: out)
    calls = []
    def sequence(source, dest, **kw):
        calls.append((source, dest, kw))
        return kw['fid'] + ' ordered .5s', [dest + '/sequence.jpg'], [dict(sample_times=[0,39.9],sampling_gap=.5)]
    monkeypatch.setattr(F, 'sequence_context', sequence)
    text, images, facts = F.context(paths, str(tmp_path/'sheets'), shots=False, temporal=True)
    assert len(calls) == count and all(c[2]['max_frames'] == budget for c in calls)
    assert sum(c[2]['max_frames'] for c in calls) <= 240
    assert len(images) == count * 2
    assert len({c[1] for c in calls}) == count
    assert [c[2]['fid'] for c in calls] == [f'clip{i}' for i in range(count)]
    assert all(f['sampling_gap'] == .5 for f in facts)
    assert 'clip0 ordered' in text


def test_temporal_decode_failure_is_not_silent(tmp_path, monkeypatch):
    p = tmp_path/'clip.mp4'; p.touch()
    monkeypatch.setattr(F, 'facts', lambda p: dict(file=p,dur=10,w=100,h=80,orientation='horizontal'))
    monkeypatch.setattr(F, 'sheet', lambda p,out,**kw: out)
    def fail(*a, **k):
        raise RuntimeError('required frame missing')
    monkeypatch.setattr(F, 'sequence_context', fail)
    assert F.context([str(p)], str(tmp_path/'sheets'), shots=False)[1]
    with pytest.raises(RuntimeError, match='required frame'):
        F.context([str(p)], str(tmp_path/'sheets'), shots=False, temporal=True)
