import pytest
from PIL import Image
from vstudio import boundaries as B


def test_measured_black_evidence_and_frame_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(B.media, 'probe', lambda _: dict(duration=3, fps=20))
    monkeypatch.setattr(B.footage, '_frame', lambda s, t, w: Image.new('RGB', (320, 180), 'black' if t < 1 else 'white'))
    text, images, records = B.context('fixture', [dict(start=1, end=2)], str(tmp_path))
    assert len(images) == 2 and 'not continuous playback' in text
    assert all(r['near_black'] == (r['time'] < 1) for r in records)
    assert len({r['id'] for r in records}) == len(records)
    for r in records:
        assert r['mean_luma'] == (0 if r['time'] < 1 else 255)
    start = next(r for r in records if r['edge'] == 'start' and r['time'] == .9)
    end = next(r for r in records if r['edge'] == 'end' and r['time'] == 2)
    picks = [dict(start=dict(id=start['id'], near_black=True, reason='Retain intentional pause'),
                  end=dict(id=end['id'], near_black=False, reason='Complete reaction'))]
    assert B.resolve(picks, records, [dict(start=1, end=2)])[0]['start'] == .9
    picks[0]['start']['near_black'] = False
    with pytest.raises(ValueError, match='contradicts'):
        B.resolve(picks, records, [dict(start=1, end=2)])
    picks[0]['start']['id'] = end['id']
    with pytest.raises(ValueError, match='unrelated'):
        B.resolve(picks, records, [dict(start=1, end=2)])


def test_missing_boundary_frame_is_not_silently_omitted(tmp_path, monkeypatch):
    monkeypatch.setattr(B.media, 'probe', lambda _: dict(duration=3, fps=20))
    monkeypatch.setattr(B.footage, '_frame', lambda *a: None)
    with pytest.raises(ValueError, match='decode'):
        B.context('fixture', [dict(start=1, end=2)], str(tmp_path))
