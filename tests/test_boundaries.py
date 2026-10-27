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


def test_performance_boundary_review_repairs_false_black_claim(tmp_path, monkeypatch):
    from vstudio import performance as P
    from test_performance import document
    doc = document(); doc['source_duration'] = 4
    records = [dict(id=f'{i}{e}', segment=i, edge=e, time=s[e], near_black=e == 'start')
               for i, s in enumerate(doc['segments']) for e in ('start', 'end')]
    monkeypatch.setattr(B, 'context', lambda *a, **kw: ('Measured samples', ['sheet.jpg'], records))
    calls = []
    def complete(task, system, prompt, **kw):
        calls.append(prompt)
        choices = [{e: dict(id=f'{i}{e}', near_black=e == 'start', reason='Keep the complete action')
                    for e in ('start', 'end')} for i in range(2)]
        if len(calls) == 1:
            choices[0]['start']['near_black'] = False
        return dict(json=dict(choices=choices, beats=doc['beats']))
    result = P.review_boundaries('source', doc, str(tmp_path), complete, precise=True)
    assert result['segments'] == doc['segments']
    assert len(calls) == 2 and 'contradicts' in calls[1]
    assert len(result['boundary_review']['repairs']) == 1


def test_performance_boundary_review_cannot_drop_a_reaction(tmp_path, monkeypatch):
    from vstudio import performance as P
    from test_performance import document
    doc = document(); doc['source_duration'] = 4
    records = [dict(id=f'{i}{e}', segment=i, edge=e, time=s[e], near_black=False)
               for i, s in enumerate(doc['segments']) for e in ('start', 'end')]
    monkeypatch.setattr(B, 'context', lambda *a, **kw: ('Measured samples', ['sheet.jpg'], records))
    choices = [{e: dict(id=f'{i}{e}', near_black=False, reason='Keep') for e in ('start', 'end')} for i in range(2)]
    with pytest.raises(ValueError, match='cannot remove protected'):
        P.review_boundaries('source', doc, str(tmp_path), lambda *a, **kw:
                            dict(json=dict(choices=choices, beats=doc['beats'][:-1])))


def test_exact_decode_preserves_frame_timestamps(tmp_path):
    import shutil
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg unavailable')
    source = str(tmp_path / 'frames.mp4')
    B.media.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=black:s=320x180:r=24:d=1',
                 '-vf', "drawbox=color=white:t=fill:enable='gte(t,0.25)'",
                 *B.media.delivery_args(preset='ultrafast', audio=False, encoder='libx264'), source])
    frames = B.decoded_window(source, .18, .35)
    assert len(frames) == 4
    assert [t for t, _ in frames] == pytest.approx([5/24, 6/24, 7/24, 8/24], abs=.000001)
    assert frames[0][1].getpixel((0, 0))[0] < 5
    assert frames[1][1].getpixel((0, 0))[0] > 245


def test_planner_runs_coarse_and_exact_boundary_review(tmp_path, monkeypatch):
    from vstudio import performance as P
    from test_performance import document
    monkeypatch.setattr(B.media, 'probe', lambda _: dict(duration=4, has_audio=False))
    monkeypatch.setattr(B.footage, 'sequence_context', lambda *a: ('sequence', ['full.jpg'], []))
    phases = []
    records = [dict(id=f'{i}{e}', segment=i, edge=e, time=s[e], near_black=False)
               for i, s in enumerate(document()['segments']) for e in ('start', 'end')]
    def context(*a, **kw):
        phases.append(kw['precise']); return 'measured', ['boundary.jpg'], records
    monkeypatch.setattr(B, 'context', context)
    def complete(*a, **kw):
        if 'choices' not in kw['schema']['properties']:
            return dict(json=document())
        return dict(json=dict(choices=[{e: dict(id=f'{i}{e}', near_black=False, reason='Complete action')
                for e in ('start', 'end')} for i in range(2)], beats=document()['beats']))
    result = P.plan('source', 'Keep the story', str(tmp_path), complete=complete)
    assert phases == [False, True] and result['boundary_review']['frame_pts']


@pytest.mark.parametrize("fps", [24, 30, 60])
def test_coarse_boundary_review_can_sample_last_frame(tmp_path, fps):
    """Rounding the 24fps final frame to .96 seeks past its PTS (.958333)."""
    import shutil
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg unavailable')
    source = str(tmp_path / 'last-frame.mp4')
    B.media.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', f'color=black:s=320x180:r={fps}:d=1',
                 '-vf', f"drawbox=color=white:t=fill:enable='gte(n,{fps - 1})'",
                 *B.media.delivery_args(preset='ultrafast', audio=False, encoder='libx264'), source])
    _, images, records = B.context(source, [dict(start=0, end=1)], str(tmp_path / 'sheets'))
    eof = next(r for r in records if r['edge'] == 'end' and r['time'] == 1)
    assert len(images) == 2
    assert eof['sampled_time'] == pytest.approx((fps - 1)/fps)
    assert eof['mean_luma'] > 245


def test_both_boundary_passes_receive_nearby_source_dialogue(tmp_path, monkeypatch):
    import json
    from vstudio import performance as P
    from test_performance import document
    doc = document()
    doc.update(source_duration=4, source_dialogue=[
        dict(start=.8, end=1.2, text="Keep my whole phrase"),
        dict(start=90, end=91, text="Unrelated distant phrase")])
    records = [dict(id=f'{i}{e}', segment=i, edge=e, time=s[e], near_black=False)
               for i, s in enumerate(doc['segments']) for e in ('start', 'end')]
    monkeypatch.setattr(B, 'context', lambda *a, **kw: ('measured', ['sheet.jpg'], records))
    prompts = []
    def complete(task, system, prompt, **kw):
        prompts.append(prompt)
        assert 'approximate phrase times' in system
        assert 'Keep my whole phrase' in prompt
        assert 'Unrelated distant phrase' not in prompt
        nearby = json.loads(prompt.split('NEARBY SOURCE DIALOGUE (empty means unavailable):\n')[1])
        assert nearby == doc['source_dialogue'][:1]
        return dict(json=dict(choices=[{e: dict(id=f'{i}{e}', near_black=False, reason='Whole phrase')
            for e in ('start', 'end')} for i in range(2)], beats=doc['beats']))
    result = P.review_boundaries('source', doc, str(tmp_path), complete)
    assert len(prompts) == 2
    assert result['source_dialogue'] == doc['source_dialogue']
    assert result['segments'] == doc['segments']
