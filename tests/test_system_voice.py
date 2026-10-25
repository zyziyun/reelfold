"""macOS Chinese voice discovery, explicit selection, and local file export."""
import json
from types import SimpleNamespace
from unittest import mock

import pytest
from vstudio import system_voice as S, tts, narration, voicecast


def test_discovery_preserves_spaced_names_and_filters_chinese():
    listing = "Lili (Premium)      zh_CN # 你好\nMeijia     zh_TW # 你好\nSamantha   en_US # Hello\n"
    with mock.patch.object(S.platform, 'system', return_value='Darwin'), mock.patch.object(S.os.path, 'isfile', return_value=True), mock.patch.object(S.subprocess, 'run', return_value=SimpleNamespace(stdout=listing)):
        vs = S.chinese_voices()
        assert [v['id'] for v in vs] == ['Lili (Premium)', 'Meijia']
        assert vs[0]['lang'] == 'zh-CN'
    with mock.patch.object(S.platform, 'system', return_value='Windows'):
        assert S.chinese_voices() == []


def test_explicit_system_preference_reaches_chinese_only(monkeypatch, tmp_path):
    prefs = tmp_path / 'prefs.json'
    prefs.write_text(json.dumps({'zh_engine': 'system', 'system_voice': 'Lili (Premium)'}))
    monkeypatch.setenv(tts.PREFS_ENV, str(prefs))
    monkeypatch.setattr(tts, 'available_engine', lambda e='auto': 'kokoro' if e == 'auto' else e)
    assert narration.voice_plan('zh')['engine'] == 'system'
    assert narration.voice_plan('zh')['narrate'] == 'zh'
    assert narration.voice_plan('en')['engine'] == 'kokoro'
    assert voicecast.narration_engine('zh') == 'system'
    assert tts.zh_voice('system') == 'Lili (Premium)'
    assert tts.default_voice('system') == 'Lili (Premium)'


def test_export_rejects_uninstalled_voice_and_keeps_text_out_of_options(monkeypatch, tmp_path):
    monkeypatch.setattr(S, 'voices', lambda: [dict(id='Lili (Premium)')])
    with pytest.raises(RuntimeError, match='not installed'):
        S.synth('你好', 'not a voice', str(tmp_path/'bad.aiff'), str(tmp_path))
    text = '--voice evil\n中文内容'
    def run(args, **kw):
        assert args[:3] == [S.SAY, '-v', 'Lili (Premium)']
        assert text not in args
        assert (tmp_path/'speech.txt').read_text() == text
        (tmp_path/'out.aiff').write_bytes(b'x' * 256)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(S.subprocess, 'run', run)
    S.synth(text, 'Lili (Premium)', str(tmp_path/'out.aiff'), str(tmp_path))


def test_synth_normalizes_system_audio_and_speed(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, '_cache_dir', lambda: str(tmp_path))
    monkeypatch.setattr(S, 'synth', lambda text, voice, raw, tmp: None)
    calls = []
    def convert(args):
        calls.append(args)
        from pathlib import Path
        _write_audio(args[-1])
    monkeypatch.setattr(tts.media, 'run', convert)
    tts.synth('你好', engine='system', voice='Lili (Premium)', speed=1.2)
    assert 'atempo=1.2000' in calls[0]
    assert ['-ar', '48000'] == calls[0][calls[0].index('-ar'):calls[0].index('-ar')+2]


def test_explainer_approval_names_selected_system_voice_without_paid_key(monkeypatch, tmp_path):
    from vstudio.project.adapters import explainer as E
    monkeypatch.setattr(tts, 'prefs', lambda: {'zh_engine': 'system', 'system_voice': 'Lili (Premium)'})
    monkeypatch.setattr(E, 'voice_engine', lambda p: dict(engine='kokoro', chosen='openai', need='openai', service='OpenAI', env='OPENAI_API_KEY'))
    monkeypatch.setattr(E, 'spoken_minutes', lambda script, speed: (0.1, 0, 12, 'zh'))
    payload = E.voice_payload(SimpleNamespace(item_dir=str(tmp_path), params={}), None)
    assert payload['engine'] == 'system'
    assert payload['default']['voice'] == 'Lili (Premium)'
    assert not payload['paid'] and 'no_key' not in payload
    assert E.voice_apply(SimpleNamespace(value=payload['default'], payload=payload))['project_params']['tts_engine'] == 'system'


def test_language_selection_never_uses_unrelated_preference(monkeypatch):
    monkeypatch.setattr(S, 'voices', lambda: [
        dict(id='Tingting', name='Tingting', lang='zh-CN'),
        dict(id='Thomas', name='Thomas', lang='fr-FR'),
        dict(id='Amelie', name='Amelie', lang='fr-CA'),
    ])
    assert S.voice_for('fr_FR', preferred='Tingting') == 'Thomas'
    assert S.voice_for('fr-CA') == 'Amelie'
    assert S.voice_for('fr', preferred='Amelie') == 'Amelie'
    with pytest.raises(RuntimeError, match='No installed macOS voice for ja'):
        S.voice_for('ja')


def test_system_language_reaches_synth_without_chinese_default(monkeypatch, tmp_path):
    from pathlib import Path
    from vstudio.project import outvoice, outrender
    monkeypatch.setattr(tts, '_cache_dir', lambda: str(tmp_path))
    monkeypatch.setattr(tts, 'prefs', lambda: {'system_voice': 'Tingting'})
    monkeypatch.setattr(S, 'voices', lambda: [dict(id='Thomas', name='Thomas', lang='fr-FR')])
    selected = []
    monkeypatch.setattr(S, 'synth', lambda text, voice, raw, tmp: selected.append(voice))
    monkeypatch.setattr(tts.media, 'run', lambda args: _write_audio(args[-1]))
    monkeypatch.setattr(tts, 'available_engine', lambda: 'system')
    assert outrender._voice_for('fr') == ('system', None)
    outvoice._tts_line(dict(lang='fr', voice={'engine': 'system'}), 'Bonjour.', str(tmp_path/'fr.wav'), str(tmp_path), 0)
    assert selected == ['Thomas']
    tts.synth('Bonjour.', engine='system', voice='Explicit', language='fr', cache=False)
    assert selected[-1] == 'Explicit'


@pytest.mark.parametrize('lang', ['ja', 'ko'])
def test_translated_version_uses_native_voice_route(monkeypatch, lang):
    from vstudio.project import outrender
    monkeypatch.setattr(tts, 'available_engine', lambda: 'kokoro')
    monkeypatch.setattr(tts, 'qwen_ready', lambda: True)
    engine, speaker = outrender._voice_for(lang)
    assert engine == 'qwen'
    assert voicecast.find(speaker, engine) in voicecast.candidates(engine, lang)


def test_translated_chinese_honors_system_preference(monkeypatch):
    from vstudio.project import outrender
    monkeypatch.setattr(tts, 'available_engine', lambda: 'kokoro')
    monkeypatch.setattr(tts, 'prefs', lambda: dict(zh_engine='system', system_voice='Lili (Premium)'))
    assert outrender._voice_for('zh') == ('system', None)


def test_translated_named_voice_selects_its_engine(monkeypatch):
    from vstudio.project import outrender
    monkeypatch.setattr(tts, 'available_engine', lambda: 'kokoro')
    assert outrender._voice_for('zh', 'qwen:serena') == ('qwen', 'serena')


def _write_audio(path):
    import wave
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\x00\x10' * 4800)


@pytest.mark.parametrize('invalid', ['empty', 'silence', 'truncated', 'garbage'])
def test_invalid_speech_never_replaces_export_and_cache_is_repaired(monkeypatch, tmp_path, invalid):
    import wave
    from pathlib import Path
    monkeypatch.setattr(tts, '_cache_dir', lambda: str(tmp_path))
    monkeypatch.setattr(S, 'synth', lambda *args: None)
    destination = tmp_path/'export.wav'
    destination.write_bytes(b'previous export')
    def corrupt(path):
        path = Path(path)
        if invalid == 'garbage':
            path.write_bytes(b'not audio')
        else:
            with wave.open(str(path), 'wb') as wav:
                wav.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\x00\x00' * (4800 if invalid != 'empty' else 0))
            if invalid == 'truncated':
                path.write_bytes(path.read_bytes()[:-200])
    monkeypatch.setattr(tts.media, 'run', lambda args: corrupt(args[-1]))
    with pytest.raises(RuntimeError, match='empty or invalid speech audio'):
        tts.synth('Test.', engine='system', voice='Test', out=str(destination))
    assert destination.read_bytes() == b'previous export'
    assert not list(tmp_path.glob('*.part.wav'))
    monkeypatch.setattr(tts.media, 'run', lambda args: _write_audio(args[-1]))
    cached = tts.synth('Test.', engine='system', voice='Test')
    assert tts._has_audio(cached)
    corrupt(cached)  # old invalid cache must regenerate even when cache=True
    tts.synth('Test.', engine='system', voice='Test', out=str(destination))
    assert tts._has_audio(cached) and tts._has_audio(str(destination))
    monkeypatch.setattr(tts.media, 'run', lambda args: pytest.fail('valid cache should be reused'))
    assert tts.synth('Test.', engine='system', voice='Test') == cached


def test_translation_rejects_unavailable_native_voice(monkeypatch):
    from vstudio.project import outrender, outputs
    monkeypatch.setattr(voicecast, 'narration_engine', lambda lang: 'kokoro')
    monkeypatch.setattr(voicecast, 'rule_cast', lambda *args: None)
    with pytest.raises(outputs.OutputError, match='No installed narration voice for ko'):
        outrender._voice_for('ko')
