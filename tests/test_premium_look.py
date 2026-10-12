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
