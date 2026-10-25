"""Final captions use the shared local correction before translation and export."""
import json

from vstudio import clipkit as CK, export as EX, subs as S, proofread as PR


def test_final_caption_correction_reaches_translation_sidecar_and_burn_input(tmp_path, monkeypatch):
    raw = S.Cue(0.2, 1.8, 'Try trace hook today.', meta={'source': 'asr'})
    monkeypatch.setattr(CK, 'canvases', lambda _: {(1920, 1080): ['youtube']})
    monkeypatch.setattr(CK, 'render_clip', lambda *a, **k: dict(
        cues=[raw], master='master.mp4', keepouts=[], timeline=[], duration=2,
        mask_report=[], content_policy={}, deferred_overlays=[], geometry={}))
    monkeypatch.setattr(CK, '_covers', lambda *a: [])
    def no_model(*a, **k):
        raise AssertionError('Local correction must not request a model')
    monkeypatch.setattr(PR, '_call_llm', no_model)
    monkeypatch.setattr(PR, '_call_claude', no_model)
    monkeypatch.setattr(PR, '_call_openai', no_model)
    def translate(cues, src, tgt):
        assert cues[0].text == 'Try TraceHook today.'
        return [S.Cue(c.start, c.end, c.text, '试用 TraceHook', c.meta) for c in cues], {}
    def export(master, keys, directory, **kw):
        burn = json.loads(open(kw['cues']).read())['cues'][0]
        assert burn['text'] == 'Try TraceHook today.'
        assert (burn['start'], burn['end']) == (.2, 1.8)
        assert burn['meta'] == {'source': 'asr'}
        return {'exports': []}
    monkeypatch.setattr(EX, 'export', export)
    report = CK.deliver({'id': 'p01'}, [], ['youtube'], str(tmp_path),
                        CK.caption_config('bilingual', 'en', 'zh',
                                          term_fixes={'trace hook': 'TraceHook'}, proofread={'provider': 'none'}),
                        firstpass=False, translate=translate)
    assert 'Try TraceHook today.' in (tmp_path / 'p01.en.srt').read_text()
    assert report['proofread'][0]['changes'][0]['source'] == 'term_fix'
    assert raw.text == 'Try trace hook today.'


def test_configured_proofread_receives_confidence_once_for_both_canvases(tmp_path, monkeypatch):
    monkeypatch.setattr(CK, 'canvases', lambda _: {(1920, 1080): ['youtube'], (1080, 1920): ['tiktok']})
    monkeypatch.setattr(CK, 'render_clip', lambda *a, **k: dict(
        cues=[S.Cue(.2, 1.8, 'trace hook')], words=[dict(w='trace', t=.2, te=.8, p=.2)],
        master='master.mp4', keepouts=[], timeline=[], duration=2, mask_report=[],
        content_policy={}, deferred_overlays=[], geometry={}))
    monkeypatch.setattr(CK, '_covers', lambda *a: [])
    monkeypatch.setattr(EX, 'export', lambda *a, **k: {'exports': []})
    calls = []
    def proofread(cues, **kw):
        calls.append(kw)
        return dict(cues=[S.Cue(.2, 1.8, 'TraceHook').to_dict()], provider='codex',
                    changes=[], rejected=[], warnings=[{'source': 'provider', 'message': 'review this term'}], low_confidence=[{'i': 0}],
                    usage={'input': 10}, cost_usd=0)
    monkeypatch.setattr(PR, 'proofread', proofread)
    report = CK.deliver(dict(id='p01', title='Tracing', terms=[dict(term='TraceHook')]), [], [], str(tmp_path),
                        CK.caption_config('mono', 'en'), firstpass=False)
    assert len(calls) == 1
    assert calls[0]['provider'] == 'auto'
    assert calls[0]['words'][0]['p'] == .2
    assert calls[0]['context']['glossary'] == ['TraceHook']
    assert [p['reused'] for p in report['proofread']] == [False, True]
    assert all(p['provider'] == 'codex' for p in report['proofread'])
    assert 'review this term' in report['warnings']
    assert 'TraceHook' in (tmp_path / 'p01.en.srt').read_text()


def test_source_normalization_keeps_low_confidence_subwords():
    from vstudio.cleanup import load_words
    words = load_words({'segments': [{'start': 10, 'words': [
        {'word': ' count', 'start': 10, 'end': 10.2, 'probability': .96},
        {'word': 'er', 'start': 10.2, 'end': 10.3, 'probability': .21},
        {'word': ' line', 'start': 10.4, 'end': 10.6, 'p': .7},
        {'word': ' unknown', 'start': 10.7, 'end': 10.9},
    ]}]})
    assert [(w['w'], w.get('p')) for w in words] == [('counter', .21), ('line', .7), ('unknown', None)]
    assert 'p' not in load_words([dict(w='invalid', t=0, te=1, p=float('nan'))])[0]
