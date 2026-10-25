import numpy as np
import pytest

from vstudio import audio, audio_joins as J


def setup(monkeypatch, values):
    monkeypatch.setattr(J.media, 'probe', lambda _: dict(duration=4, has_audio=True))
    def decode(path, start, dur, **kw):
        index = min(3, int(round(start * 10)))
        return np.full((round(dur * audio.SR),2), values[index],dtype=np.float32)
    monkeypatch.setattr(audio,'decode_audio',decode)


def test_edit_jump_compared_with_both_original_boundaries(monkeypatch):
    setup(monkeypatch,[.5,.5,.02,.02])
    r=J.inspect('source',[dict(start=0,end=.1),dict(start=.3,end=.4)])
    assert r['joins'][0]['needs_review']
    assert r['joins'][0]['change_db'][0] == pytest.approx(-27.9588,abs=.01)
    assert r['listening_verified'] is False
    # The original already has the same strong transition; do not call it edit-created.
    setup(monkeypatch,[.5,.02,.5,.02])
    assert not J.inspect('source',[dict(start=0,end=.1),dict(start=.3,end=.4)])['joins'][0]['needs_review']


def test_contiguous_and_silence_are_not_false_alarms(monkeypatch):
    setup(monkeypatch,[0,0,.0001,.0001])
    assert not J.inspect('source',[dict(start=0,end=.1),dict(start=.3,end=.4)])['joins'][0]['needs_review']
    assert J.inspect('source',[dict(start=0,end=.1),dict(start=.1,end=.4)])['joins']==[]


def test_short_audio_decode_fails_instead_of_pass(monkeypatch):
    setup(monkeypatch,[.5]*4)
    monkeypatch.setattr(audio,'decode_audio',lambda *a,**kw: np.zeros((1,2)))
    with pytest.raises(ValueError,match='ended before'):
        J.inspect('source',[dict(start=0,end=.1),dict(start=.3,end=.4)])


def test_anti_phase_stereo_is_measured_per_channel(monkeypatch):
    setup(monkeypatch,[.5,.5,.02,.02])
    decode=audio.decode_audio
    monkeypatch.setattr(audio,'decode_audio',lambda *a,**kw:decode(*a,**kw)*[1,-1])
    assert J.inspect('source',[dict(start=0,end=.1),dict(start=.3,end=.4)])['joins'][0]['needs_review']


@pytest.mark.parametrize('segments',[[dict(start=True,end=2)],[dict(start=0,end=float('nan'))],
    [dict(start=0,end=2),dict(start=1,end=3)]])
def test_bad_ranges_rejected(monkeypatch,segments):
    setup(monkeypatch,[.5]*4)
    with pytest.raises(ValueError): J.inspect('source',segments)


def test_native_short_windows_do_not_use_input_seek(tmp_path):
    import subprocess
    from vstudio import media
    path=tmp_path/'source.mkv'
    subprocess.run([media.ffmpeg_bin(),'-v','error','-f','lavfi','-i',
        r'aevalsrc=0.5*sin(2*PI*440*t)*(1-0.96*gte(t\,1)):s=48000:d=2',
        '-c:a','pcm_f32le',str(path)],check=True)
    result=J.inspect(str(path),[dict(start=0,end=.5),dict(start=1.5,end=2)])
    assert result['joins'][0]['needs_review']
    assert result['joins'][0]['change_db'][0] == pytest.approx(-27.9588,abs=.1)
