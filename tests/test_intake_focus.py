"""Autopilot resolves paraphrased topics against real transcript indices before creating projects."""
import json
from vstudio.intake import focus as F, apply as A


def test_only_verified_sentence_indices_can_become_clip_times():
    sentences = [dict(t=i*10, te=(i+1)*10, text='Source sentence') for i in range(12)]
    rows = [dict(id=x, params={'title':x}) for x in ['a','b','c','d']]
    def call(system, body):
        assert len(json.loads(body)['sentences']) == 12
        return {'json': {'selections': [dict(id='a', start_sentence=1, end_sentence=4),
            dict(id='b', start_sentence=8, end_sentence=99), dict(id='c', start_sentence=True, end_sentence=4),
            dict(id='d', start_sentence=7, end_sentence=6), dict(id='invented', start_sentence=0, end_sentence=4)]}}
    assert F.resolve(rows, sentences, call=call) == {'a':[10.0,50.0]}


def test_apply_uses_full_transcript_for_semantic_topics_without_touching_source(monkeypatch, tmp_path):
    transcript = tmp_path/'full.json'
    transcript.write_text(json.dumps({'sentences':[dict(t=i*10, te=(i+1)*10, text='A complete source thought') for i in range(20)]}))
    analysis = {'files':[{'path':'original.mp4', 'id':'f1', 'duration':200, 'transcript':str(transcript)}]}
    monkeypatch.setattr(A.I, 'analyze', lambda paths, **kw: analysis if kw['asr'] == 'full' else None)
    monkeypatch.setattr(A.PL, 'context', lambda client: {})
    p = dict(id='p1', recipe='longform-to-short', inputs={'source':'original.mp4'}, params={},
             items={'method':'focus', 'unresolved':True, 'rows':[dict(id=f'topic-{i}', inputs={}, params={'title':f'Paraphrased {i}'}) for i in range(4)]})
    def call(system, body):
        return {'json':{'selections':[dict(id=f'topic-{i}',start_sentence=i*5,end_sentence=i*5+3) for i in range(4)]}}
    A._resolve_unresolved(dict(prompt='Make four topic clips', projects=[p], planner={'provider':'none'}), call=call)
    assert not p['items'].get('unresolved')
    assert [r['params']['range'] for r in p['items']['rows']] == [[0.,40.],[50.,90.],[100.,140.],[150.,190.]]
    kw = A._create_kwargs(p,{})
    assert len(kw['items']) == 4
    assert all(r['inputs']['source'] == 'original.mp4' for r in kw['items'])
