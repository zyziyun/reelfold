"""Filmed performances: source-bound edits, independent sources and real media."""
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from vstudio import media, performance as P
from vstudio.project.adapters import performance as A


def document():
    return dict(title="A filmed performance", summary="Setup, surprise, reaction.",
                segments=[dict(start=0, end=1, reason="Keep setup"),
                          dict(start=2, end=4, reason="Keep payoff and reaction")],
                beats=[dict(start=0, end=1, role="setup", evidence="The actor sets the cup down"),
                       dict(start=2, end=3, role="payoff", evidence="The cup falls"),
                       dict(start=3, end=4, role="reaction", evidence="The actor reacts")])


@pytest.mark.parametrize("change", [
    lambda d: d["segments"][0].update(start=True),
    lambda d: d["segments"][0].update(end=float("nan")),
    lambda d: d["segments"][1].update(start=.5),
    lambda d: d["segments"][1].update(end=5),
    lambda d: d["segments"].reverse(),
    lambda d: d["segments"][1].update(end=3.5),
    lambda d: d["beats"][1].update(role="development"),
    lambda d: d["beats"][0].update(evidence=""),
    lambda d: d.update(summary=""),
])
def test_invalid_cut_cannot_proceed(change):
    d = document(); change(d)
    with pytest.raises(ValueError):
        P.validate(d, 4)


def planner_context(monkeypatch, audio=False):
    from vstudio import footage, asr
    monkeypatch.setattr(P, "review_boundaries", lambda source, doc, work, complete: doc)
    monkeypatch.setattr(footage, "sequence_context", lambda *a, **k: ("Public synthetic performance, 4s", ["synthetic-sheet.jpg"], []))
    monkeypatch.setattr(media, "probe", lambda p: dict(duration=4, has_audio=audio))
    monkeypatch.setattr(asr, "transcribe", lambda *a, **k: pytest.fail("Silent or speech-disabled footage must not call ASR"))


@pytest.mark.parametrize("has_audio,speech", [(False, True), (False, False), (True, False)])
def test_silent_or_music_only_source_needs_no_transcription(tmp_path, monkeypatch, has_audio, speech):
    planner_context(monkeypatch, has_audio)
    result = P.plan("synthetic.mp4", "Edit the actual performance", str(tmp_path), speech=speech,
                    complete=lambda *a, **k: dict(json=document(), provider="test"))
    assert result["source_has_audio"] == has_audio and result["speed"] == 1


def test_bounded_repair_retains_source_context(tmp_path, monkeypatch):
    planner_context(monkeypatch)
    calls = []
    def complete(task, system, prompt, **kwargs):
        calls.append(prompt)
        d = document()
        if len(calls) == 1:
            d["segments"][1]["end"] = 3.5
        return dict(json=d, provider="test")
    result = P.plan("synthetic.mp4", "Keep the reaction", str(tmp_path), complete=complete)
    assert len(calls) == 2 and len(result["repairs"]) == 1
    assert "Public synthetic performance" in calls[1] and "reaction was cut" in calls[1]
    with pytest.raises(ValueError, match="still invalid"):
        P.plan("synthetic.mp4", "Edit", str(tmp_path), complete=lambda *a, **k: dict(json={}))
    with pytest.raises(RuntimeError, match="provider unavailable"):
        P.plan("synthetic.mp4", "Edit", str(tmp_path),
               complete=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider unavailable")))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
@pytest.mark.parametrize("audio", [False, True])
def test_real_cuts_preserve_chronology_geometry_and_sound(tmp_path, audio):
    import numpy as np
    source, dest = str(tmp_path / "source.mp4"), str(tmp_path / "cut.mp4")
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=red:s=320x240:r=20:d=4"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=700:sample_rate=48000:duration=4"]
    cmd += ["-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='gte(t,2)'",
            *media.delivery_args(preset="ultrafast", audio=audio, encoder="libx264"), source]
    media.run(cmd)
    result = P.render(source, document(), dest, preset="ultrafast")
    info = media.probe(dest)
    assert abs(info["duration"] - 3) < .1
    assert result["source_geometry"] == [320, 240]
    assert info["has_audio"] == audio
    for t, channel in [(.4, 0), (1.4, 2), (2.7, 2)]:
        raw = subprocess.check_output([media.ffmpeg_bin(), "-v", "error", "-ss", str(t), "-i", dest,
                         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        pixel = np.frombuffer(raw, np.uint8).reshape(240, 320, 3).mean(axis=(0, 1))
        assert pixel[channel] > 200
    if audio:
        from vstudio import audio as sound
        wav = str(tmp_path / "sound.wav")
        media.run(["ffmpeg", "-y", "-i", dest, "-vn", wav])
        samples, sr = sound.read_wav(wav)
        assert np.sqrt(np.mean(samples ** 2)) > .01


def test_performance_review_uses_ui_messages():
    review = A._review(document())
    assert all(line["code"] == "draft.line" and line["params"]["label"] for line in review["lines"])


def test_quality_red_never_has_auto_approval(monkeypatch, tmp_path):
    from vstudio import flicker
    from vstudio.project.adapters import common
    monkeypatch.setattr(media, "probe", lambda p: dict(has_audio=True))
    monkeypatch.setattr(flicker, "analyze", lambda *a, **k: dict(ok=False))
    monkeypatch.setattr(flicker, "describe", lambda r: "Visible flash in the source")
    env = SimpleNamespace(item_dir=str(tmp_path), inputs=dict(compose=dict(source_has_audio=True),
                           export=dict(exports=[dict(file=str(tmp_path / "clip.mp4"), platform="youtube")])))
    env.inputs["qc"] = A.qc(env)
    monkeypatch.setattr(common, "publish_copy", lambda env: {})
    monkeypatch.setattr(common, "_exports_of", lambda env: [])
    payload = common.publish_payload(env, {})
    assert payload["qc"]["status"] == "red" and payload["default"] is None


# Reuse the real matrix/range fixtures; these decode via colour-aware FFmpeg.
from test_export_colour import sources, rgb_frame, patch_colours  # noqa: E402,F401


@pytest.mark.parametrize("kind", ["untagged", "601", "709", "full709"])
def test_trim_pipeline_converts_pixels_before_tagging_709(tmp_path, sources, kind):
    import numpy as np
    doc = dict(title="Colour", summary="Keep original frame", segments=[dict(start=0, end=1, reason="Whole action")],
               beats=[dict(start=0, end=.5, role="setup", evidence="First half"),
                      dict(start=.5, end=1, role="payoff", evidence="Second half")])
    dest = tmp_path / "native.mp4"
    P.render(str(sources[kind]), doc, str(dest), preset="ultrafast")
    before, after = patch_colours(rgb_frame(sources[kind])), patch_colours(rgb_frame(dest))
    assert np.max(np.abs(before - after)) <= 6, (kind, before.tolist(), after.tolist())


def test_unavailable_source_frames_stop_planning(tmp_path, monkeypatch):
    from vstudio import footage
    monkeypatch.setattr(footage, "sequence_context", lambda *a, **k: ("4s", [], []))
    with pytest.raises(ValueError, match="source frames are unavailable"):
        P.plan("missing.mp4", "Edit", str(tmp_path), complete=lambda *a, **k: pytest.fail("No source evidence"))


def test_dialogue_transcript_is_local_and_source_bound(tmp_path, monkeypatch):
    from vstudio import asr
    planner_context(monkeypatch, audio=True)
    calls = []
    def transcribe(path, **kw):
        assert kw == dict(cache=False, language="auto")
        return dict(segments=[dict(start=0, end=1, text="An actual source line")])
    monkeypatch.setattr(asr, "transcribe", transcribe)
    def complete(task, system, prompt, **kw):
        assert task == "segment_plan"
        calls.append(prompt)
        return dict(json=document())
    P.plan("spoken.mp4", "Preserve dialogue", str(tmp_path), speech=True, complete=complete)
    assert "0.000–1.000 An actual source line" in calls[0]


@pytest.mark.parametrize("target", ["youtube", "xiaohongshu", "tiktok"])
@pytest.mark.parametrize("geometry", [(958, 720), (360, 640)])
def test_native_export_metadata_stays_inside_original_canvas(target, geometry):
    from vstudio import platform
    w, h = geometry
    p = A.native_profile(target, w, h)
    assert (p.w, p.h) == (w, h) == platform.cover_size(p)
    for x0, y0, x1, y1 in [platform.safe_box(p), platform.caption_box(p)]:
        assert 0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h
    with pytest.raises(ValueError, match="not a Short"):
        A.native_profile("youtube-shorts", 958, 720)


@pytest.mark.parametrize('duration', [60, 600])
def test_sequence_evidence_covers_full_source_in_bounded_pages(tmp_path, monkeypatch, duration):
    from vstudio import footage
    monkeypatch.setattr(footage, 'facts', lambda p: dict(file=p, dur=duration, w=320, h=240, orientation='horizontal'))
    sampled = []
    def sheet(source, out, **kw):
        assert len(kw['times']) <= 20
        sampled.extend(kw['times'])
        return out
    monkeypatch.setattr(footage, 'sheet', sheet)
    text, images, facts = footage.sequence_context('public.mp4', str(tmp_path))
    assert 100 < len(sampled) <= 240 and len(images) <= 12
    assert sampled[0] == 0 and sampled[-1] == pytest.approx(duration - .1)
    assert sampled == sorted(set(sampled))
    assert max(b-a for a,b in zip(sampled, sampled[1:])) == pytest.approx(facts[0]['sampling_gap'], abs=.0001)
    assert 'actual sampling gap' in text and 'not continuous playback' in text


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg not installed')
def test_sequence_sheet_captures_brief_action_and_invalidates_cache(tmp_path):
    from PIL import Image
    from vstudio import footage
    source = str(tmp_path / 'brief-action.mp4')
    media.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=black:s=320x240:r=20:d=3',
               '-vf', "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,0.9,1.1)'",
               *media.delivery_args(preset='ultrafast', audio=False, encoder='libx264'), source])
    # The old six whole-clip samples all miss this short visible action.
    assert not any(.9 <= t <= 1.1 for t in footage.tiles_for(3, every=2))
    _, images, facts = footage.sequence_context(source, str(tmp_path / 'sheets'))
    index = next(i for i,t in enumerate(facts[0]['sample_times']) if .9 <= t <= 1.1)
    with Image.open(images[0]) as image:
        assert min(image.getpixel(((index % 5)*320+160, (index//5)*264+120))) > 220
    path = str(tmp_path / 'cache.jpg')
    footage.sheet(source, path, times=[0])
    with Image.open(path) as image:
        assert max(image.getpixel((160,120))) < 20
    footage.sheet(source, path, times=[1])
    with Image.open(path) as image:
        assert min(image.getpixel((160,120))) > 220


def test_sequence_decode_failure_does_not_silently_remove_evidence(tmp_path, monkeypatch):
    from vstudio import footage
    source = tmp_path / 'source.mp4'; source.write_bytes(b'test')
    monkeypatch.setattr(media, 'probe', lambda p: dict(duration=3))
    monkeypatch.setattr(footage, '_frame', lambda *a: None)
    with pytest.raises(RuntimeError, match='requested sequence frame'):
        footage.sheet(str(source), str(tmp_path/'sheet.jpg'), times=[0,1,2])
