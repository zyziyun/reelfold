"""Native decoder regressions: actual compressed packets, timing and output samples."""
import numpy as np
import pytest
from vstudio import audio, media


@pytest.fixture(params=[44100,48000])
def source(tmp_path,request):
    sr = request.param
    t = np.arange(sr * 4) / sr
    # Distinct stereo channels and a changing amplitude expose wrong positions,
    # not just short buffers. No speech or user media is needed.
    x = np.column_stack([(.1 + .08*t)*np.sin(2*np.pi*(270*t+20*t*t)),
                         (.4 - .07*t)*np.sin(2*np.pi*(410*t+13*t*t))])
    path = tmp_path / 'source.wav'
    audio.write_wav(str(path), x, sr)
    return path


@pytest.mark.parametrize('codec,ext', [('pcm_s16le','mkv'), ('aac','m4a'), ('vorbis','webm')])
def test_short_compressed_windows_match_decoded_source(source, tmp_path, codec, ext):
    path = tmp_path / ('compressed.' + ext)
    media.run(['ffmpeg', '-y', '-i', str(source), '-c:a', codec, '-strict', '-2', str(path)])
    sr = audio.read_wav(str(source))[1]
    for start in (.153, .253, 1.153, 1.253, 2.253):
        # Independent output seek reference decodes before discarding samples.
        raw = media.run(['ffmpeg','-i',str(path),'-ss',str(start),'-t','0.1',
                         '-map','0:a:0','-vn','-ar',str(sr),'-ac','2','-f','f32le','-'],capture=True)
        ref = np.frombuffer(raw.stdout,np.float32).reshape(-1,2)
        actual = audio.decode_audio(str(path),sr=sr,start=start,dur=.1)
        assert actual.shape == ref.shape == (round(sr*.1),2)
        np.testing.assert_allclose(actual,ref,atol=1e-6)


def test_source_selection_precedes_filters_and_output_duration(source):
    # Start refers to source time even when a filter changes the playback speed.
    actual = audio.decode_audio(str(source), start=1, dur=.125, af='asetrate=96000')
    full = audio.decode_audio(str(source), af='asetrate=96000')
    offset = audio.read_wav(str(source))[1] // 2
    assert actual.shape == (6000,2)
    np.testing.assert_allclose(actual[100:-100],full[offset+100:offset+6000-100],atol=1e-6)


def test_fractional_sample_boundaries_and_eof(source):
    sr = audio.read_wav(str(source))[1]
    actual = audio.decode_audio(str(source),sr=sr,start=1001/sr,dur=101/sr)
    full = audio.decode_audio(str(source),sr=sr)
    assert actual.shape == (101,2)
    np.testing.assert_array_equal(actual,full[1001:1102])
    assert audio.decode_audio(str(source),start=3.95,dur=1).shape == (2400,2)
    assert audio.decode_audio(str(source),start=5,dur=.1).shape == (0,2)
    assert audio.decode_audio(str(source),dur=0).shape == (0,2)


@pytest.mark.parametrize('key,value',[('start',-1),('start',float('nan')),('dur',float('inf')),('dur',True)])
def test_invalid_time_rejected_before_decode(key,value):
    with pytest.raises(ValueError,match='finite and non-negative'):
        audio.decode_audio('does-not-exist',**{key:value})
