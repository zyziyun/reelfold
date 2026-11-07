"""Exercise the photo-story voice command and take cache with explicit locales."""
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'workflows/photo-story/scripts'))
PT = importlib.import_module('photostory.tts')


@pytest.mark.parametrize('engine', ['system', 'qwen', 'openai'])
def test_voice_command_passes_locale_and_invalidates_take_cache(tmp_path, monkeypatch, engine):
    spec = SimpleNamespace(TTS=dict(language='fr-FR', engine=engine, voice='test-voice'),
                           SCRIPT=[(0, [('Bonjour.', '')], [])])
    monkeypatch.setattr(PT, 'load_spec', lambda _: spec)
    monkeypatch.setattr(PT, 'Ctx', lambda s: s)
    monkeypatch.setattr(PT, 'tts_dir', lambda _: str(tmp_path))
    monkeypatch.setattr(PT.vtts, 'prefs', lambda: {})
    monkeypatch.setattr(PT.vtts, 'missing_key', lambda _: False)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only')
    monkeypatch.setattr(sys, 'argv', ['tts.py', 'spec.py'])
    requests = []
    def synth(text, **kw):
        requests.append((text, kw))
        sf.write(kw['out'], np.full(4800, .1), 48000)
    monkeypatch.setattr(PT.vtts, 'synth', synth)
    languages = []
    def transcribe(path, **kw):
        languages.append(kw['language'])
        return {'words': [{'w':'Bonjour.', 't':0, 'te':.1}]}
    monkeypatch.setattr(PT.asr, 'transcribe', transcribe)
    PT.main()
    assert requests[0][1]['language'] == 'fr-fr'
    assert languages == ['fr']
    PT.main()
    assert len(requests) == 1
    spec.TTS['language'] = 'de-DE'
    PT.main()
    assert len(requests) == 2
    assert requests[-1][1]['language'] == 'de-de'
    assert languages == ['fr', 'de']


def test_system_voice_selection_uses_declared_language(tmp_path, monkeypatch):
    from vstudio import system_voice
    spec = SimpleNamespace(TTS=dict(language='fr-FR', engine='system'), SCRIPT=[])
    monkeypatch.setattr(PT, 'load_spec', lambda _: spec)
    monkeypatch.setattr(PT, 'Ctx', lambda s: s)
    monkeypatch.setattr(PT, 'tts_dir', lambda _: str(tmp_path))
    monkeypatch.setattr(sys, 'argv', ['tts.py','spec.py'])
    monkeypatch.setattr(PT.vtts, 'prefs', lambda: {})
    monkeypatch.setattr(system_voice, 'voices', lambda: [dict(id='French', name='French', lang='fr-FR')])
    monkeypatch.setattr(PT.vtts, 'zh_voice', lambda _: pytest.fail('Must not select a Chinese voice for French'))
    PT.main()


@pytest.mark.parametrize('locale', ['zh', 'zh-CN', 'zh_TW'])
def test_chinese_pronunciation_overrides_preserve_display_and_identifiers(locale):
    original='先检查API，再导出MP4；保留CAPITable。'
    spoken,display=PT.narration_texts([('fallback',original)],{'API':'A P I','MP4':'M P four'},locale)
    assert spoken==['先检查A P I，再导出M P four；保留CAPITable。']
    assert display==[original]


def test_chinese_fallback_and_literal_override():
    spoken,display=PT.narration_texts([('API','')],{'API':r'A \ P I'},'zh')
    assert spoken==[r'A \ P I'] and display==['API']


def test_english_pronunciation_word_boundaries_unchanged():
    spoken,display=PT.narration_texts([('API CAPITable','')],{'API':'A P I'},'en')
    assert spoken==['A P I CAPITable'] and display==['API CAPITable']


@pytest.mark.parametrize('engine,voice,expected', [
    ('system', 'test-voice', 'Visit pyoo jet.'),
    ('qwen', 'test-voice', 'Visit pyoo jet.'),
    ('kokoro', 'af_heart', 'Visit Puget.'),
])
def test_pronunciation_lexicon_only_overrides_its_own_engine(tmp_path, monkeypatch, engine, voice, expected):
    spec = SimpleNamespace(TTS=dict(language='en', engine=engine, voice=voice),
                           SAY_TTS={'Puget': 'pyoo jet'}, SCRIPT=[(0, [('Visit Puget.', '')], [])])
    monkeypatch.setattr(PT, 'load_spec', lambda _: spec)
    monkeypatch.setattr(PT, 'Ctx', lambda s: s)
    monkeypatch.setattr(PT, 'tts_dir', lambda _: str(tmp_path))
    monkeypatch.setattr(PT.vtts, 'prefs', lambda: {})
    monkeypatch.setattr(sys, 'argv', ['tts.py', 'spec.py'])
    requests = []
    def synth(text, **kw):
        requests.append(text)
        sf.write(kw['out'], np.full(4800, .1), 48000)
    monkeypatch.setattr(PT.vtts, 'synth', synth)
    monkeypatch.setattr(PT.asr, 'transcribe', lambda *a, **kw: {'words': [{'w': expected, 't': 0, 'te': .1}]})
    PT.main()
    assert requests == [expected]
