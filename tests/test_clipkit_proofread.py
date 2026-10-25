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
                                          term_fixes={'trace hook': 'TraceHook'}),
                        firstpass=False, translate=translate)
    assert 'Try TraceHook today.' in (tmp_path / 'p01.en.srt').read_text()
    assert report['proofread'][0]['changes'][0]['source'] == 'term_fix'
    assert raw.text == 'Try trace hook today.'
