"""Recorder ingest: a synthetic session (ffmpeg testsrc + sine as camera / mic WebM, retake marks) -> the last good
take per line, studio sound, a talking-head project; crash recovery of a locked session; path confinement."""
import json
import os
import subprocess

import pytest

from _create_helpers import home, needs_ffmpeg  # noqa: F401

from vstudio.create import record as RE, store
from vstudio.create.i18n import CreateError


def _webm(path, seconds, video=True):
    src = ["-f", "lavfi", "-i", f"testsrc2=size=180x320:rate=24:duration={seconds}"] if video else \
        ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    codec = ["-c:v", "libvpx-vp9", "-b:v", "200k", "-deadline", "realtime"] if video else ["-c:a", "libopus"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *src, *codec, path], check=True)


def session(root, marks, seconds=6, lock=False):
    d = os.path.join(root, "recordings", "20261006-1200-side-hustle")
    os.makedirs(d, exist_ok=True)
    _webm(os.path.join(d, "camera.webm"), seconds)
    _webm(os.path.join(d, "mic.webm"), seconds, video=False)
    json.dump(dict(id="s1", slug="side-hustle", title="Side hustle", script=["Line one.", "Line two.", "Line three."],
                   tracks=dict(camera=dict(file="camera.webm", start_ms=1000), mic=dict(file="mic.webm", start_ms=1000))),
              open(os.path.join(d, "session.json"), "w"))
    json.dump(marks, open(os.path.join(d, "takes.json"), "w"))
    if lock:
        open(os.path.join(d, "recording.lock"), "w").write("live")
    return d


def test_attempts_and_last_take_per_line():
    marks = [dict(t=0.0, kind="line", line=0), dict(t=1.5, kind="retake", line=0), dict(t=3.0, kind="line", line=1),
             dict(t=4.0, kind="line", line=2), dict(t=4.6, kind="retake", line=2)]
    atts = RE.attempts(marks, 6.0, 3)
    assert atts[0] == [(0.0, 1.5), (1.5, 3.0)] and atts[2] == [(4.0, 4.6), (4.6, 6.0)]
    edl = RE.pick_best(atts)
    assert [(e["line"], e["start"], e["end"], e["attempts"]) for e in edl] == [(0, 1.5, 3.0, 2), (1, 3.0, 4.0, 1),
                                                                              (2, 4.6, 6.0, 2)]


def test_pick_best_with_words_skips_an_empty_retake():
    atts = {0: [(0.0, 2.0), (2.0, 3.0)]}
    words = [dict(word="hello", start=0.4, end=0.8), dict(word="world", start=0.9, end=1.5)]
    e = RE.pick_best(atts, words)[0]
    assert e["start"] == pytest.approx(0.25) and e["end"] == pytest.approx(1.75)    # tightened, the empty retake skipped


@needs_ffmpeg
def test_ingest_creates_talkinghead_project(home):
    d = session(str(home), [dict(t=0.0, kind="line", line=0), dict(t=1.5, kind="retake", line=0),
                            dict(t=3.0, kind="line", line=1), dict(t=4.0, kind="line", line=2),
                            dict(t=4.6, kind="retake", line=2)])
    res = RE.ingest(d)
    assert os.path.exists(res["assembled"]) and res["retakes"] == 2
    assert 3.0 < res["duration"] < 4.6                    # 1.5 + 1.0 + 1.4 s kept out of 6 s
    assert [ln["text"] for ln in res["lines"]] == ["Line one.", "Line two.", "Line three."]
    from vstudio.project import home as H
    from vstudio.project.core import Project
    p = Project(res["project_dir"])
    assert p.data["recipe"] == "talkinghead" and p.data["items"]
    assert any(os.path.realpath(x["dir"]) == os.path.realpath(res["project_dir"]) for x in H.projects())


@needs_ffmpeg
def test_ingest_assembled_only_makes_no_project_and_keeps_raw_sound(home, monkeypatch):
    d = session(str(home), [dict(t=0.0, kind="line", line=0)])
    sess = json.load(open(os.path.join(d, "session.json")))
    json.dump(dict(sess, studio=False), open(os.path.join(d, "session.json"), "w"))
    from vstudio import studiosound
    monkeypatch.setattr(studiosound, "enhance", lambda *a, **k: (_ for _ in ()).throw(AssertionError("studio sound")))
    res = RE.ingest(d, "assembled")
    assert os.path.exists(res["assembled"]) and "project_dir" not in res
    assert not os.path.exists(os.path.join(d, "project"))


@needs_ffmpeg
def test_recover_locked_session(home):
    d = session(str(home), [], seconds=2, lock=True)
    out = RE.recover()
    assert out and out[0]["id"] == os.path.basename(d) and "camera" in out[0]["tracks"]
    assert not os.path.exists(os.path.join(d, "recording.lock"))


def test_session_must_be_inside_recordings(home, tmp_path):
    os.makedirs(tmp_path / "elsewhere", exist_ok=True)
    (tmp_path / "elsewhere" / "session.json").write_text("{}")
    with pytest.raises(CreateError):
        RE.need_session(str(tmp_path / "elsewhere"))
    with pytest.raises(CreateError):
        RE.need_session(os.path.join(store.recordings_root(), "..", "series"))


def test_recorder_transcript_words_reads_words_of_keys(monkeypatch):
    from vstudio import asr
    monkeypatch.setattr(asr, "transcribe", lambda p, language=None: dict(segments=[dict(words=[
        dict(word=" 你好", start=0.4, end=0.8), dict(word="世界", start=0.9, end=1.5)])]))
    w = RE.transcript_words("x.mp4")
    assert w == [dict(word="你好", start=0.4, end=0.8), dict(word="世界", start=0.9, end=1.5)]


def test_ffmpeg_never_reads_the_callers_stdin(monkeypatch):
    # Windows: ffmpeg stalls on an inherited stdin pipe nobody writes to (the desk engine's) - the stitch never ended
    seen = {}

    def fake_run(args, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(args, 0, b"", b"")
    monkeypatch.setattr(RE.subprocess, "run", fake_run)
    RE._run(["ffmpeg", "-version"])
    assert seen.get("stdin") is subprocess.DEVNULL

@needs_ffmpeg
def test_screen_recording_composes_camera_at_bottom_right(home):
    from PIL import Image
    from vstudio import media
    d = session(str(home), [], seconds=1)
    screen = os.path.join(d, "screen.webm")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=blue:size=640x360:rate=24:duration=1", "-c:v", "libvpx-vp9", "-deadline", "realtime", screen], check=True)
    sess = store.read_json(os.path.join(d, "session.json"))
    sess["tracks"]["screen"] = dict(file="screen.webm", start_ms=1000)
    movie = RE.mux(d, sess, os.path.join(d, "screen-pip.mp4"))
    info = media.probe(movie)
    assert (info["w"], info["h"]) == (640, 360)
    image = os.path.join(d, "frame.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", movie, "-frames:v", "1", image], check=True)
    pixels = Image.open(image).convert("RGB")
    center = pixels.getpixel((320, 180))
    assert center[2] > 180 and center[0] < 50
    inset = pixels.crop((500, 260, 620, 340))
    assert len(inset.getcolors(100000)) > 10  # camera test pattern, not the blue screen
    assert os.path.isfile(screen) and os.path.isfile(os.path.join(d, "camera.webm"))


@needs_ffmpeg
def test_screen_recording_without_webm_duration_tags_is_playable(home):
    """MediaRecorder's streaming WebM is complete but lacks seek/duration metadata; preserve its actual frames."""
    from vstudio import media
    d = session(str(home), [], seconds=1.5)
    screen = os.path.join(d, "screen.webm")
    _webm(screen, 1.5)
    for name in ("camera", "screen", "mic"):
        src = os.path.join(d, name + ".webm")
        streamed = os.path.join(d, name + ".stream.webm")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-c", "copy", "-live", "1", streamed], check=True)
        os.replace(streamed, src)
        assert RE.duration(src) == 0
    sess = store.read_json(os.path.join(d, "session.json"))
    sess["tracks"]["screen"] = dict(file="screen.webm", start_ms=1000)
    movie = RE.mux(d, sess, os.path.join(d, "screen-stream.mp4"))
    info = media.probe(movie)
    assert info["w"] and info["h"] and info["has_audio"]
    assert 1.3 < media.duration(movie) < 1.8
    assert RE.duration(os.path.join(d, "camera.webm")) == 0  # raw tracks are not rewritten


@pytest.mark.parametrize("microphone", [True, False])
def test_screen_playback_audio_survives_mux_with_separate_microphone(home, microphone):
    """500 Hz app playback + 440 Hz mic remain audible; raw sources stay byte-identical."""
    import hashlib
    import numpy as np
    d = session(home, [], seconds=1.5)
    sess = json.load(open(os.path.join(d, "session.json")))
    screen = os.path.join(d, "screen.webm")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=blue:size=640x360:rate=24:duration=1.5", "-f", "lavfi", "-i",
                    "sine=frequency=500:duration=1.5", "-c:v", "libvpx-vp9", "-deadline", "realtime",
                    "-c:a", "libopus", screen], check=True)
    sess["tracks"]["screen"] = dict(file="screen.webm", start_ms=1000)
    if not microphone:
        os.rename(os.path.join(d, "mic.webm"), os.path.join(d, "mic-original.webm"))
        del sess["tracks"]["mic"]
    originals = {f: hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest()
                 for f in os.listdir(d) if f.endswith(".webm")}
    movie = RE.mux(d, sess, os.path.join(d, "with-material-sound.mp4"))
    pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-i", movie, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"])
    samples = np.frombuffer(pcm, dtype="<i2").astype(float) / 32768
    clock = np.arange(len(samples)) / 8000
    def magnitude(hz):
        return abs(np.sum(samples * np.exp(-2j * np.pi * hz * clock))) * 2 / len(samples)
    assert magnitude(500) > 0.06
    assert (magnitude(440) > 0.06) if microphone else (magnitude(440) < 0.01)
    assert all(hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest() == sha for f, sha in originals.items())


def test_automatic_cleanup_keeps_a_filler_too_short_for_a_safe_cut():
    words = [dict(w="hello", t=0.3, te=0.48), dict(w="um", t=0.487, te=0.514),
             dict(w="world", t=0.52, te=0.7)]
    ops, counts = RE.auto_cuts(words, 1.0, [(0, 1.0)])
    assert not ops
    assert counts["filler"] == 0
    words[1].update(t=0.49, te=0.7)
    words[2].update(t=0.8, te=0.95)
    ops, counts = RE.auto_cuts(words, 1.0, [(0, 1.0)])
    assert ops == [dict(op="cut", words=[1, 1], why="filler")]
    assert counts["filler"] == 1


@needs_ffmpeg
@pytest.mark.parametrize('target', ['prepare', 'edit', 'assembled'])
def test_partial_camera_take_without_mic_remains_editable(home, target):
    from vstudio import media
    d = session(str(home), [], seconds=1)
    os.remove(os.path.join(d, 'mic.webm'))
    # A failed mic startup leaves its declared track in session metadata.
    sess = store.read_json(os.path.join(d, 'session.json'))
    sess['tracks']['mic']['start_ms'] = None
    sess['studio'] = True
    store.write_json(os.path.join(d, 'session.json'), sess)
    if target == 'prepare':
        movie = RE.prepare(d, os.path.join(d, 'prepared.mp4'))
    elif target == 'edit':
        movie = RE.edit(d)['file']
    else:
        movie = RE.ingest(d, 'assembled')['assembled']
    info = media.probe(movie)
    assert info['w'] == 180 and info['h'] == 320
    assert not info['has_audio']
    assert media.duration(movie) > .8
    assert os.path.isfile(os.path.join(d, 'camera.webm'))


@needs_ffmpeg
@pytest.mark.parametrize('camera_start', [0, 2000])
def test_screen_camera_inset_uses_capture_start_time(home, camera_start):
    """A colour change is a visible sync marker, independent of mux metadata."""
    from PIL import Image
    import io
    d = session(str(home), [], seconds=3)
    cam = os.path.join(d, 'camera.webm')
    camera_duration = 4 if camera_start == 0 else 2
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    f"color=red:size=180x320:rate=24:duration={camera_duration},drawbox=color=lime:t=fill:enable='gte(t,1)'",
                    '-c:v', 'libvpx-vp9', '-deadline', 'realtime', cam], check=True)
    screen = os.path.join(d, 'screen.webm')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'color=blue:size=640x360:rate=24:duration=3',
                    '-c:v', 'libvpx-vp9', '-deadline', 'realtime', screen], check=True)
    sess = store.read_json(os.path.join(d, 'session.json'))
    sess['tracks']['camera']['start_ms'] = camera_start
    sess['tracks']['screen'] = dict(file='screen.webm', start_ms=1000)
    movie = RE.mux(d, sess, os.path.join(d, 'aligned.mp4'))
    def pixel(t):
        png = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', movie,
                                       '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'])
        return Image.open(io.BytesIO(png)).convert('RGB').getpixel((560, 300))
    r, g, b = pixel(.25)
    if camera_start == 0:
        assert g > 180 and r < 50 and b < 50, 'early camera should have reached green already'
    else:
        assert b > 180 and r < 50 and g < 50, 'late camera should not appear before it starts'
        r, g, b = pixel(1.25)
        assert r > 180 and g < 50 and b < 50
    # All streams stop at the same wall-clock instant despite different starts.
    assert RE.duration(movie) > 2.8
    r, g, b = pixel(2.75)
    assert g > 180 and r < 50 and b < 50
