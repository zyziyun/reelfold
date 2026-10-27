"""Real compose media + cleanup sidecar language/timing survives speed and hooks."""
import json
import shutil
from types import SimpleNamespace

import pytest
from vstudio import cleanup, media
from vstudio.batch import stages


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg unavailable')
@pytest.mark.parametrize('language,text', [
    ('en', 'Show a concrete example. Before publishing, check the captions.'),
    ('fr', 'Expliquez votre idée avec un exemple concret.'),
])
def test_compose_keeps_source_language_and_word_clocks(tmp_path, language, text):
    if language == 'en':
        pytest.importorskip('en_core_web_sm')
    source = str(tmp_path / 'source.mp4')
    media.run(['ffmpeg','-y','-f','lavfi','-i','color=c=gray:s=160x90:r=25:d=4',
               '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=4',
               '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',source])
    words = [dict(w=t,t=i*.4,te=(i+1)*.4) for i,t in enumerate(text.split())]
    side = cleanup.write_sidecar(source, source, [(0,4)], words, language=language)
    ctx = SimpleNamespace(params={'speed':1.25,'hook_speed':2,'max_chars':100},
                          inputs={'apply':dict(body=source,body_sidecar=side,
                                               hook=source,hook_sidecar=side,hook_dur=4)},
                          path=lambda name: str(tmp_path/name))
    result = stages.run_compose(ctx)
    cues = json.load(open(result['cues']))['cues']
    assert cues and all(c['meta']['lang']==language for c in cues)
    hook = [c for c in cues if c['meta'].get('kind')=='hook']
    body = [c for c in cues if c['meta'].get('kind')!='hook']
    assert body[0]['start']==2
    assert all(c['end'] <= result['duration']+.05 for c in cues)
    assert media.duration(result['master'])==pytest.approx(5.2,abs=.1)
    if language=='en':
        assert len(hook)==len(body)==2
        assert hook[1]['start']==pytest.approx(1.6/2)
        assert body[1]['start']==pytest.approx(2+1.6/1.25)
    else:
        assert len(hook)==len(body)==1
