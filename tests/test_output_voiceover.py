"""The ``voiceover`` op of second-pass editing (vstudio.project.outvoice): an intro or a full narration over a finished
clip - written by the AI when only her ask is given, cast per language (lively for a vlog, her named voice wins),
never over her own speech in a full narration, mixed with the clip's sound ducked under it, captioned in each
version's language, one undoable step; the audio source is pluggable (tts | take). Fake TTS / model, synthetic media."""
import json
import os
import shutil

import numpy as np
import pytest

import _batch_helpers as H
from vstudio import audio as A
from vstudio import llm
from vstudio import voicecast as VC
from vstudio.project import outputs as O
from vstudio.project import outrender as R
from vstudio.project import outvoice as VO

HAS_FFMPEG = bool(shutil.which("ffmpeg"))
WORDS = [("大家", .4), ("好", .3), ("今天", .4), ("去", .3), ("迪士尼", .5)]
TAIL = 5.0


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_BATCH_BENCH", str(tmp_path / "bench.json"))
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VSTUDIO_CLIENTS", "VSTUDIO_LLM_PROVIDER",
              "VSTUDIO_LLM_OUTPUT_EDIT_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(O, "TRANSCRIBE", lambda path, language=None: _TRUTH[path])
    monkeypatch.setattr(VC, "narration_engine", lambda lang, engine="auto": "qwen" if lang == "zh" else "kokoro")
    monkeypatch.setattr(VC, "_kokoro_dir", lambda: None)
    said = []

    def fake_voice(text, lang, voice, out):          # a tone per voice: the mix can be measured
        f = 500.0 + 100 * (abs(hash(voice.get("speaker") or "")) % 5)
        n = int(A.SR * VO.seconds_for(text))
        t = np.arange(n) / A.SR
        A.write_wav(out, np.stack([0.3 * np.sin(2 * np.pi * f * t)] * 2, 1).astype(np.float32), A.SR)
        said.append(dict(text=text, lang=lang, speaker=voice.get("speaker"), style=voice.get("style")))
        return out
    monkeypatch.setattr(VO, "VOICE_HOOK", fake_voice)
    monkeypatch.setattr(VO, "WRITE_HOOK", None)
    yield said


_TRUTH = {}


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg not installed")
    d = tmp_path_factory.mktemp("vosynth")
    x, truth, dur = H.synth_speech(WORDS)
    x = np.concatenate([x, np.zeros(int(TAIL * 48000), np.float32)])     # her speech first, then 5 s of picture
    dur += TAIL
    src = H.make_video(str(d / "vlog.mp4"), x, 48000, dur)
    return dict(video=src, truth=[{k: w[k] for k in ("w", "t", "te")} for w in truth], dur=dur)


def work(tmp_path, clip):
    w = tmp_path / "work"
    (w / "final").mkdir(parents=True)
    f = w / "final" / "disney-vlog.mp4"
    shutil.copy(clip["video"], f)
    (w / "REPORT.md").write_text("# disney vlog\n")
    from vstudio.project import works
    works.adopt(str(w))
    _TRUTH[str(f)] = clip["truth"]
    return str(w), "final/disney-vlog.mp4"


# --------------------------------------------------------------------------- pure parts
def test_gaps_and_placing_never_talk_over_her():
    W = [dict(w="a", t=0.0, te=1.0), dict(w="b", t=1.1, te=2.0), dict(w="c", t=6.0, te=7.0)]
    assert VO.gaps(W, 0.0, 10.0) == [[2.15, 5.85], [7.15, 10.0]]
    warns = []
    got = VO.place([dict(start=0.5, text_zh="欢迎来到迪士尼"), dict(start=6.2, text_zh="晚上的烟花真的太美了")], W, 0.0,
                   10.0, warns)
    assert [g["start"] for g in got] == [2.15, 7.15]          # moved out of her speech into the next pause
    assert all(VO._overlap(g["start"], g["end"], VO.speech_spans(W)) == 0 for g in got)
    warns = []
    assert VO.place([dict(start=0.0, text="x " * 40)], W, 0.0, 10.0, warns) == []
    assert warns[0]["code"] == "voiceover-line-dropped"
    intro = VO.place([dict(start=0.0, text_zh="欢迎")], W, 0.0, 10.0, [], avoid=False)
    assert intro[0]["start"] == 0.0                           # an intro stays where she asked (ducked)


def test_mix_ducks_the_clip_under_the_voice(tmp_path):
    n = A.SR * 4
    base = np.full((n, 2), 0.2, np.float32)
    take = tmp_path / "take.wav"
    t = np.arange(A.SR) / A.SR
    A.write_wav(str(take), np.stack([0.3 * np.sin(2 * np.pi * 440 * t)] * 2, 1).astype(np.float32), A.SR)
    v = dict(id="vo1", source="take", take=str(take), at=1.0, until=2.0, duck_db=-14.0, lines=[])
    out = VO.mix_in(base, [v], 4.0, str(tmp_path))
    under = out[int(1.4 * A.SR):int(1.6 * A.SR), 0]
    away = out[int(3.2 * A.SR):int(3.5 * A.SR), 0]
    assert np.allclose(away, 0.2, atol=1e-3)                  # untouched where nobody narrates
    voice = 0.3 * np.sin(2 * np.pi * 440 * (np.arange(len(under)) / A.SR + 0.4))
    assert abs(np.mean(under - voice) - 0.2 * 10 ** (-14 / 20)) < 0.01      # the clip -14 dB under the voice


# --------------------------------------------------------------------------- the op on a clip
def test_intro_with_text_cast_lively_for_a_vlog_one_undoable_step(tmp_path, clip, _iso):
    w, oid = work(tmp_path, clip)
    r = O.edit(w, oid, [dict(op="voiceover", mode="intro", text_zh="今天带大家玩迪士尼！", text="A day at Disneyland!")])
    st = O.show(w, oid)["state"]
    vo = st["voiceovers"][0]
    assert vo["mode"] == "intro" and vo["lines"][0]["start"] == 0.0
    assert vo["voices"]["zh"]["speaker"] == "vivian" and vo["voices"]["zh"]["by"] == "rules"    # vlog: lively
    d = r["step"]["describe"][0]                       # the step's row: "Voice-over 0:00–0:0x"
    assert d["code"] == "op-voiceover" and d["params"]["start"] == 0.0 and d["message"].startswith("Voice-over 0:00")
    assert any(x["code"] == "voiceover-over-speech" for x in r["warnings"])    # her voice ducked under the intro
    O.undo(w, oid)
    assert not O.show(w, oid)["state"].get("voiceovers")


def test_render_mixes_the_voice_and_captions_it(tmp_path, clip, _iso):
    w, oid = work(tmp_path, clip)
    O.edit(w, oid, [dict(op="voiceover", mode="intro", text_zh="今天带大家玩迪士尼", duck_db=-12)])
    rec, doc = O._load(w, oid)
    st = doc.state()
    tg = R.targets_of(rec, st)[0]
    p = R.plan(rec, doc, st, tg, "preview")
    assert p["audio"]["vo"][0]["lines"][0][2] == "今天带大家玩迪士尼" and p["audio"]["op"] == "mix"
    assert any(c[2] == "今天带大家玩迪士尼" for c in p["final"]["visual"]["captions"])
    res = R.render(w, oid, quality="preview")
    out = next(x for x in res["targets"] if x["target"] == "primary")["file"]
    y = A.decode_audio(out, sr=A.SR, channels=1)
    assert np.sqrt(np.mean(y[int(0.1 * A.SR):int(1.5 * A.SR)] ** 2)) > 0.05     # the narration is in the mix
    assert _iso and _iso[0]["speaker"] == "vivian" and _iso[0]["lang"] == "zh" and _iso[0]["style"]


def test_full_narration_written_by_the_ai_around_her_speech(tmp_path, clip, _iso, monkeypatch):
    w, oid = work(tmp_path, clip)
    asked = {}

    def write(system, prompt):
        asked.update(json.loads(prompt))
        return dict(lines=[dict(start=0.5, text_zh="大家好呀"), dict(start=3.2, text_zh="第一站是城堡"),
                           dict(start=5.0, text_zh="晚上还有烟花")])
    monkeypatch.setattr(VO, "WRITE_HOOK", write)
    r = O.edit(w, oid, [dict(op="voiceover", mode="full", ask="全程加一个好玩的vlog旁白")])
    vo = O.show(w, oid)["state"]["voiceovers"][0]
    assert asked["mode"] == "full" and asked["gaps"] and "Chinese (text_zh)" in asked["languages"]
    W = clip["truth"]
    assert vo["lines"] and all(VO._overlap(x["start"], x["end"], VO.speech_spans(W)) == 0 for x in vo["lines"])
    assert vo["lines"][0]["start"] >= W[-1]["te"]             # the first line waited for her to finish
    assert r


def test_her_named_voice_wins_and_versions_get_their_language(tmp_path, clip, _iso):
    w, oid = work(tmp_path, clip)
    O.edit(w, oid, [dict(op="export_add", target="youtube")])
    O.edit(w, oid, [dict(op="voiceover", mode="intro", text="Welcome to Disneyland", text_zh="欢迎来到迪士尼",
                         voice="uncle_fu")])
    rec, doc = O._load(w, oid)
    st = doc.state()
    vo = st["voiceovers"][0]
    assert vo["voices"]["zh"]["speaker"] == "uncle_fu" and vo["voices"]["zh"]["by"] == "you"
    assert vo["voices"]["en"]["engine"] == "kokoro"            # English: a Kokoro voice cast for the vlog
    plans = {tg["target"]: R.plan(rec, doc, st, tg, "preview") for tg in R.targets_of(rec, st)}
    assert plans["primary"]["audio"]["vo"][0]["lines"][0][2] == "欢迎来到迪士尼"
    yt = plans["youtube:horizontal"]["audio"]["vo"][0]
    assert yt["lines"][0][2] == "Welcome to Disneyland" and yt["voice"]["engine"] == "kokoro"


def test_a_take_is_the_same_op_with_another_source(tmp_path, clip, _iso):
    w, oid = work(tmp_path, clip)
    take = tmp_path / "my-take.wav"
    A.write_wav(str(take), np.zeros((A.SR * 2, 2), np.float32), A.SR)
    O.edit(w, oid, [dict(op="voiceover", mode="span", start=3.0, source="take", take=str(take),
                         lines=[dict(start=3.0, text_zh="这是我自己录的")])])
    vo = O.show(w, oid)["state"]["voiceovers"][0]
    assert vo["source"] == "take" and vo["take"] == str(take) and abs(vo["end"] - 5.0) < 0.05
    assert "voices" not in vo and not _iso                      # nothing synthesised


def test_the_ai_proposal_is_applied_as_proposed(tmp_path, clip, _iso, monkeypatch):
    w, oid = work(tmp_path, clip)
    monkeypatch.setenv("VSTUDIO_LLM_OUTPUT_EDIT_PROVIDER", "claude-code")
    seen = {}

    def fake_complete(task, system, prompt, schema=None, provider=None, model=None, **kw):
        seen["prompt"] = prompt
        return dict(text="", json=dict(summary="intro", ops=[dict(op="voiceover", mode="intro", text_zh="走，去迪士尼！",
                                                                  text="Let's go to Disneyland!")]),
                    usage={}, cost_usd=0.0, provider="claude-code", model="m")
    monkeypatch.setattr(llm, "complete", fake_complete)
    r = O.ai(w, oid, "加一下好玩的vlog的介绍tts", apply=True)
    assert '"voiceover"' in seen["prompt"]                        # the planner knows the op
    p = r["proposed"][0]
    assert p["op"]["lines"] and p["op"]["voices"]["zh"]["speaker"] == "vivian"
    assert p["describe"]["code"] == "op-voiceover"
    assert O.show(w, oid)["state"]["voiceovers"][0]["lines"][0]["text_zh"] == "走，去迪士尼！"
    # no model at all: her words become the op, and writing it says it needs a model (no fake narration)
    monkeypatch.delenv("VSTUDIO_LLM_OUTPUT_EDIT_PROVIDER")
    monkeypatch.setattr(llm, "route", lambda *a, **k: llm.Route("none", None, {}, "test"))
    r = O.ai(w, oid, "全程加个配音")
    assert not r["proposed"] and r["dropped"][0]["error"]["code"] == "needs-model"
    assert r["dropped"][0]["op"]["mode"] == "full"


def test_an_xhs_file_without_platform_metadata_is_chinese_even_over_whisper_music():
    music = [dict(w="Music", t=2.76 + i, te=3.7 + i, p=0.2) for i in range(6)]
    assert VO.speech_words(music + [dict(w="[Applause]", t=9, te=10)]) == []
    rec = dict(id="final/disney_vlog_xhs.mp4", platform=None, profile=None)
    assert VO.name_platform(rec) == "xiaohongshu"
    assert VO.version_langs(rec, dict(exports=[]), music) == ["zh"]           # not "en" from "Music Music"
    assert VO.name_platform(dict(id="final/trip_youtube.mp4")) == "youtube"
    assert VO.name_platform(dict(id="final/clip.mp4")) is None
    assert VO.version_langs(dict(id="final/clip.mp4"), dict(exports=[]), music) == ["en"]


def test_a_step_cast_for_english_renders_the_chinese_version_in_a_cast_chinese_voice(tmp_path, clip, _iso):
    """Her 04-disney-vlog step: voices only {en} on the 小红书 file - the re-render casts the zh voice (no new edit)."""
    w = tmp_path / "work"
    (w / "final").mkdir(parents=True)
    f = w / "final" / "disney_vlog_xhs.mp4"
    shutil.copy(clip["video"], f)
    from vstudio.project import works
    works.adopt(str(w))
    _TRUTH[str(f)] = clip["truth"]
    oid = "final/disney_vlog_xhs.mp4"
    O.edit(str(w), oid, [dict(op="voiceover", mode="intro", lines=[dict(start=0.0, text="Off to Disney",
                                                                       text_zh="今天去迪士尼")],
                              voices=dict(en=dict(engine="kokoro", speaker="af_bella", by="rules")))])
    rec, doc = O._load(str(w), oid)
    st = doc.state()
    v = R.plan(rec, doc, st, R.targets_of(rec, st)[0], "preview")["audio"]["vo"][0]
    assert v["lang"] == "zh" and v["lines"][0][2] == "今天去迪士尼" and v["voice"]["speaker"] == "vivian"
