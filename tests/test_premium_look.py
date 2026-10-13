"""Premium-by-default look (2026-10-12 review of the six DJI films: "有点俗气，不够高端大气", "屏闪有点厉害").

photo-story LOOK "cinema": no running header, dissolves only, subtitles crossfade (never cut out for a frame), the
shade behind them eases instead of popping per cue, the year marker moves on from the last year; captions burned by
vstudio.export / the output editor crossfade too."""
import pathlib
import sys
import types

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "workflows" / "photo-story" / "scripts"))

from vstudio.subs import CUE_FADE, cue_opacity  # noqa: E402


def test_burned_cues_crossfade_without_a_dip():
    a, b, c = (0.0, 3.0), (3.0, 6.0), (8.0, 9.0)
    for t in np.arange(2.5, 3.5, 1 / 30):
        total = cue_opacity(*a, t) + cue_opacity(*b, t)
        assert total == pytest.approx(1.0, abs=1e-6), t           # the band never drops between adjacent cues
    assert cue_opacity(*c, 8.0) == pytest.approx(0.5)
    assert cue_opacity(*c, 8.0 - CUE_FADE) == 0.0 and cue_opacity(*c, 8.5) == 1.0


def test_photostory_cue_and_backdrop_alpha():
    from photostory.render import backdrop_alpha, cue_alpha
    subs = [dict(start=1.0, end=4.0), dict(start=4.0, end=7.0), dict(start=12.0, end=14.0)]
    for t in np.arange(3.5, 4.5, 1 / 30):
        assert cue_alpha(subs[0], t) + cue_alpha(subs[1], t) == pytest.approx(1.0, abs=1e-6)
    assert backdrop_alpha(subs, 5.0) == 1.0
    assert backdrop_alpha(subs, 10.0) == 0.0                      # a long gap: the shade eases away
    vals = [backdrop_alpha(subs, t) for t in np.arange(7.0, 12.0, 1 / 30)]
    assert max(abs(x - y) for x, y in zip(vals, vals[1:])) < 0.12   # eased, no pop


def _ctx(cinema=True):
    sections = ["A", "B"]
    return types.SimpleNamespace(cinema=cinema, SECTIONS=sections, spec=types.SimpleNamespace(
        PACING={}, SCRIPT=[
            (0, [("one", "一")], [("v1", 1, "still", dict(tl=1851)), ("v2", 1, "still", dict(tr="whip", tl=1893))]),
            (1, [("two", "二")], [("v3", 1, "still", dict(tr="flash", tl=1911)), ("v4", 1, "still", dict(tr="cut"))]),
        ]))


def test_cinema_timeline_dissolves_and_moves_the_year_on():
    from photostory.timeline import CINEMA_FADE, Timeline
    timing = {0: dict(dur=8.0, path=None, chunks=[dict(start=0, end=8)]),
              1: dict(dur=8.0, path=None, chunks=[dict(start=0, end=8)])}
    T = Timeline(_ctx(True), timing)
    assert [s["tr"] for s in T.shots] == [None, "fade", "fade", "cut"]
    assert T.shots[1]["_tr_asked"] == "whip" and T.shots[1]["trd"] == pytest.approx(CINEMA_FADE)
    assert T.shots[3]["trd"] == 0.0
    assert [s.get("_tl_from") for s in T.shots[:3]] == [None, 1851, 1893]
    T = Timeline(_ctx(False), timing)                             # classic look keeps what the spec asked
    assert [s["tr"] for s in T.shots] == [None, "whip", "flash", "cut"]


def _has_fonts():
    from vstudio import config as VC
    try:
        VC.font("cjk-serif")
        VC.font("cjk")
        return True
    except Exception:  # noqa: BLE001 - fonts come from install.sh
        return False


def test_cinema_cover_is_a_full_bleed_frame_with_quiet_type(tmp_path):
    """P8: no heavy stroke / band; a long dashed title becomes title + a small line; her '|' breaks are kept."""
    from PIL import Image
    from vstudio.batch.edits import _cover_parts, _text_cover
    assert _cover_parts("Eastern Washington|华盛顿东部 · 公路旅行") == (["Eastern Washington"], "华盛顿东部 · 公路旅行")
    assert _cover_parts("Eastern Washington Road Trip — Columbia River, Dusk Deer") == (
        ["Eastern Washington Road Trip"], "Columbia River, Dusk Deer")
    src = tmp_path / "f.jpg"
    Image.new("RGB", (1920, 1080), (90, 130, 170)).save(src)
    _text_cover(str(src), "Golden Hour|Elliott Bay, Seattle", str(tmp_path / "c.jpg"), style="cinema")
    a = np.asarray(Image.open(tmp_path / "c.jpg").convert("RGB")).astype(int)
    assert a.shape[:2] == (1080, 1920)
    assert abs(a[100, 960] - [90, 130, 170]).max() < 6               # the top of the frame is untouched
    edge = a[540:, :120]                                             # away from the type: a soft gradient only,
    assert edge.min() > 18 and (np.abs(np.diff(edge[:, 60, 2])) <= 3).all()  # never a black band or a hard band edge
    if _has_fonts():                                                 # CI without ./install.sh fonts: layout only
        assert (a[700:1000].min(axis=2) > 200).mean() > 0.002        # light title type in the lower part


def test_effect_texts_per_version_language():
    """YouTube shows English, Xiaohongshu / Bilibili Chinese: text_zh / sub_zh params of an output effect."""
    from vstudio import platform as P
    from vstudio.project import outfx as FX
    from vstudio.project import outrender as OR
    clean, warns = FX.validate("quote-card", dict(text="Gold settles on the water.", text_zh="金色，落在水面",
                                                  sub_en="x", bogus_zh="y"))
    assert clean["text_zh"] == "金色，落在水面" and "bogus_zh" not in clean and any("bogus_zh" in w for w in warns)
    assert FX.localize(clean, "zh")["text"] == "金色，落在水面"
    assert FX.localize(clean, "en")["text"] == "Gold settles on the water." and "text_zh" not in FX.localize(clean, "en")
    assert OR.target_lang(dict(profile=P.profile("youtube"))) == "en"
    assert OR.target_lang(dict(profile=P.profile("youtube-shorts"))) == "en"
    assert OR.target_lang(dict(profile=P.profile("bilibili"))) == "zh"
    assert OR.target_lang(dict(profile=P.profile("xiaohongshu:full"))) == "zh"
    assert OR.target_lang(dict(profile=None)) is None


def test_planner_never_keeps_a_paid_voice_without_its_key(monkeypatch):
    """No paid generation by surprise: a planned tts_engine "openai" with no OPENAI_API_KEY is dropped (the voice
    rules then pick the free voice / English narration with Chinese subtitles)."""
    from vstudio.intake import plan as PL
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    m = dict(id="photo-story", params=dict(properties=dict(tts_engine=dict(type="string"))))
    params, sources = dict(tts_engine="openai"), dict(tts_engine="planner")
    PL._apply_ctx_defaults(m, params, sources, dict(language="en", source="request"), {}, dict(files=[]))
    assert "tts_engine" not in params and "tts_engine" not in sources
    params = dict(tts_engine="kokoro")
    PL._apply_ctx_defaults(m, params, {}, dict(language="en", source="request"), {}, dict(files=[]))
    assert params["tts_engine"] == "kokoro"


def test_captions_are_one_language_per_platform(monkeypatch):
    """2026-10-12: no bilingual stacked captions by default - English on YouTube / TikTok, Chinese on 小红书 / B站."""
    from vstudio import export as X
    from vstudio import platform as P
    from vstudio import subs as S
    from vstudio.project import outrender as OR
    monkeypatch.setattr(S, "_persona_subs", lambda: {})
    cues = [S.Cue(0, 2, "塔高 605 英尺", "It rises 605 feet"), S.Cue(2, 4, "Built in a year", "约一年建成"),
            S.Cue(4, 6, "只有中文", "")]
    zh, w = X.cues_for_platform(P.profile("xiaohongshu:full"), cues)
    assert [c.text for c in zh] == ["塔高 605 英尺", "约一年建成", "只有中文"] and all(not c.alt for c in zh) and not w
    en, w = X.cues_for_platform(P.profile("tiktok"), cues)
    assert [c.text for c in en][:2] == ["It rises 605 feet", "Built in a year"] and w and "1 cue" in w[0]
    keep, _ = X.cues_for_platform(P.profile("bilibili"), cues, bilingual=True)
    assert keep[0].alt == "It rises 605 feet"
    yt, _ = X.cues_for_platform(P.profile("youtube"), cues, bilingual=True)
    assert yt[0].text == "It rises 605 feet" and not yt[0].alt                 # YouTube: English, always
    assert S.bilingual_wanted("Add bilingual subtitles") and S.bilingual_wanted("加中英字幕")
    assert not S.bilingual_wanted("Narrate in English for YouTube")
    assert OR.mono_caption("夜幕下的西雅图\nSeattle at night", None, "en") == "Seattle at night"
    assert OR.mono_caption("Seattle at night", "夜幕下的西雅图", "zh") == "夜幕下的西雅图"
    assert OR.mono_caption("Seattle at night", "夜幕下的西雅图", "zh", both=True) == "Seattle at night"


def test_photostory_subtitles_follow_the_platform(tmp_path):
    from photostory.ctx import Ctx, load_spec
    spec = tmp_path / "spec.py"
    spec.write_text('TITLE_ZH = "为1962而建"\nTITLE_EN = "Built for 1962"\nSECTIONS = ["序"]\nSCRIPT = []\n'
                    'TTS = dict(language="en")\nSUB_LEAD = "zh"\n')
    for plat, want in (("youtube", "en"), ("xiaohongshu:vertical", "zh"), ("bilibili", "zh"), ("tiktok", "en")):
        sp = load_spec(str(spec))
        sp.PLATFORM = plat
        C = Ctx(sp)
        assert C.SUBS == want, plat
        en, zh = C.sub_pair("It rises 605 feet", "塔高 605 英尺")
        assert (en, zh) == (("It rises 605 feet", "") if want == "en" else ("", "塔高 605 英尺"))
        assert C.shown("Space Needle · 太空针塔") == ("Space Needle" if want == "en" else "太空针塔")


def test_a_slow_still_never_sinks_the_spec_draft(monkeypatch, tmp_path):
    import subprocess
    from vstudio.project.adapters import photostory as PS

    def slow(*a, **k):
        raise subprocess.TimeoutExpired(a[0], 300)
    monkeypatch.setattr(PS.subprocess, "run", slow)
    assert PS._frame("clip.mp4", 4.2, str(tmp_path / "f.jpg")) is False


def test_project_yaml_saves_numpy_values():
    import numpy as np
    from vstudio.project.core import _plain
    v = _plain({"a": [np.float64(0.0778), {"b": np.int64(3)}], "c": np.array([1.5])})
    assert v == {"a": [0.0778, {"b": 3}], "c": [1.5]} and type(v["a"][0]) is float
