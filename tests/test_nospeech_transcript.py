"""A music-only clip whose transcript is a whisper hallucination ("Thank you." at 0:00 and 0:33 of a drone vlog with
a music bed) counts as no speech: ``asr`` drops it at the source, the output editor reads no words (so the clip opens
on its timeline) and nothing is captioned from it. Real speech - including a confident sign-off - is untouched.
Synthetic media only, no network.

    PYTHONPATH=lib python3 -m pytest tests/test_nospeech_transcript.py -q
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))

from vstudio import asr  # noqa: E402
from vstudio.project import outputs as O  # noqa: E402

HAS_FF = bool(shutil.which("ffmpeg"))
need_ff = pytest.mark.skipif(not HAS_FF, reason="ffmpeg not installed")

# the words the output editor cached for her 59 s drone vlog (Seattle red leaves, music only)
HALLUCINATED = [dict(w="Thank", t=0.0, te=2.02, p=0.227), dict(w="you.", t=2.02, te=2.76, p=0.997),
                dict(w="Thank", t=33.92, te=35.32, p=0.215), dict(w="you.", t=35.32, te=36.22, p=0.998)]


def _seg(text, start, end, p=None, **stats):
    toks = text.split()
    step = (end - start) / max(1, len(toks))
    return dict(start=start, end=end, text=" " + text, **stats,
                words=[dict(word=" " + w, start=start + k * step, end=start + (k + 1) * step, p=p)
                       for k, w in enumerate(toks)])


def _finish(segs, duration=None):
    raw = dict(language="en", backend="test", segments=segs, **({"duration": duration} if duration else {}))
    return asr._finish(raw, None, False, drop_hallucinated=True)


# ------------------------------------------------------------------ asr: at the source
def test_sparse_confident_sign_offs_over_music_are_no_speech():
    tr = _finish([_seg("Thank you.", 0.0, 2.76, p=0.9, no_speech_prob=0.05, avg_logprob=-0.2),
                  _seg("Thank you.", 33.92, 36.22, p=0.9, no_speech_prob=0.05, avg_logprob=-0.2)], duration=59.0)
    assert tr["words"] == [] and tr["segments"] == []
    assert {d["reason"] for d in tr["dropped"]} == {"sparse-sign-off"}
    assert not asr.has_speech(tr)


def test_a_sign_off_with_one_unsure_word_is_dropped():
    # mean p 0.61 sits over the old 0.6 bar; "Thank" at p 0.23 is not something she said
    tr = _finish([_seg("Thank you.", 0.0, 2.76, no_speech_prob=0.1, avg_logprob=-0.3)
                  | dict(words=[dict(word=" Thank", start=0.0, end=2.02, p=0.227),
                                dict(word=" you.", start=2.02, end=2.76, p=0.997)])])
    assert tr["words"] == [] and tr["dropped"][0]["reason"].startswith("phrase?:")


def test_other_hallucination_phrases():
    for text in ("谢谢观看", "Subtitles by the Amara.org community", "Thanks for watching!"):
        tr = _finish([_seg(text, 10.0, 12.0, p=0.5)], duration=40.0)
        assert tr["words"] == [], text


def test_real_speech_is_untouched():
    talk = [_seg("today I want to show you how we cut a travel vlog", 0.5, 4.0, p=0.92,
                 no_speech_prob=0.01, avg_logprob=-0.2),
            _seg("the trick is to keep every shot short", 4.3, 7.0, p=0.9, no_speech_prob=0.02, avg_logprob=-0.25),
            _seg("Thank you.", 7.4, 8.2, p=0.95, no_speech_prob=0.02, avg_logprob=-0.1)]
    tr = _finish(talk, duration=9.0)
    assert len(tr["segments"]) == 3 and tr["dropped"] == []
    # a short clip that is just a thank-you, said for real, is dense enough to be speech
    short = _finish([_seg("Thank you so much everyone", 0.2, 2.0, p=0.93, no_speech_prob=0.02, avg_logprob=-0.2)],
                    duration=2.5)
    assert len(short["words"]) == 5


def test_word_level_filter_on_a_cached_transcript():
    assert asr.drop_hallucinated_words(HALLUCINATED, duration=59.0) == []
    real = [dict(w=w, t=0.3 + k * 0.4, te=0.3 + k * 0.4 + 0.35, p=0.9)
            for k, w in enumerate("so this is the lake we hiked to this morning".split())]
    real += [dict(w="Thank", t=6.0, te=6.3, p=0.95), dict(w="you.", t=6.3, te=6.6, p=0.97)]
    assert asr.drop_hallucinated_words(real, duration=7.0) == real
    # pipeline words keep no p: a sign-off among real speech stays
    nop = [{k: v for k, v in w.items() if k != "p"} for w in real]
    assert asr.drop_hallucinated_words(nop, duration=7.0) == nop
    assert asr.drop_hallucinated_words([], duration=7.0) == []


# ------------------------------------------------------------------ the output editor on a music-only clip
@pytest.fixture
def music_work(tmp_path, monkeypatch):
    if not HAS_FF:
        pytest.skip("ffmpeg not installed")
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    w = tmp_path / "work"
    (w / "final").mkdir(parents=True)
    f = w / "final" / "vlog.mp4"
    # a "drone vlog": moving picture under a soft chord (music bed), no voice
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=15:d=40",
                    "-f", "lavfi", "-i", "sine=f=220:d=40", "-f", "lavfi", "-i", "sine=f=277:d=40",
                    "-filter_complex", "[1][2]amix=inputs=2,volume=0.4[a]", "-map", "0:v", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(f)], check=True)
    (w / "REPORT.md").write_text("# vlog\n")
    from vstudio.project import works
    works.adopt(str(w))
    calls = []

    def fake(path, language=None):                    # whisper "hears" a sign-off twice in the music
        calls.append(path)
        return [dict(x) for x in HALLUCINATED[:2]] + [dict(x, t=x["t"] - 4, te=x["te"] - 4) for x in HALLUCINATED[2:]]
    monkeypatch.setattr(O, "TRANSCRIBE", fake)
    oid = O.list_outputs(str(w))["outputs"][0]["id"]
    return str(w), oid, calls


@need_ff
def test_music_only_output_has_no_words_and_no_captions(music_work):
    w, oid, calls = music_work
    with pytest.raises(O.OutputError) as e:
        O.edit(w, oid, dict(op="caption_add", from_transcript=True))
    assert e.value.info["code"] == "no-words" and calls  # it listened, heard nothing real, captioned nothing
    s = O.show(w, oid)
    assert s["marks"] == []
    doc = O.Doc(O.resolve(w, oid))
    assert O.words(doc, required=False) == [] and O.cached_words(doc) == []


@need_ff
def test_an_old_cached_hallucination_reads_as_no_speech(music_work):
    w, oid, _calls = music_work
    s = O.show(w, oid)
    path = s["paths"]["transcript"]
    tr = dict(sig=json.load(open(s["paths"]["doc"]))["source_sig"], file="x", words=HALLUCINATED, at="t", joined=1)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(tr, fh)
    s = O.show(w, oid)
    assert s["marks"] == [] and s["words_sig"] == O.words_sig([])
