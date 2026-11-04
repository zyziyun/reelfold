"""Story-vlog overlays (vstudio.storyfx), story covers (vstudio.cover_styles), photo-story own_voice helpers.
Covers the passes facecam.py, textfx.py, finish.py, own_voice.py and cover.py story_cover through their pure parts."""
import pathlib
import sys

import numpy as np
import pytest
from PIL import Image

from vstudio import cover_styles as CS
from vstudio import storyfx as S
from vstudio.config import MissingAsset, font

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "workflows" / "photo-story" / "scripts"))


def _fonts_ok(*roles):
    try:
        for r in roles:
            font(r)
        return True
    except MissingAsset:
        return False


FONTS = pytest.mark.skipif(not _fonts_ok("cjk-bold", "cjk-serif-bold", "display-latin", "mono"),
                           reason="cover fonts not installed (./install.sh)")


def _photo(w=640, h=480, seed=0):
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 255, (h, w, 3), dtype=np.uint8))


@pytest.mark.parametrize("style", ["circle", "round", "polaroid"])
def test_face_card_shapes(style):
    face = np.full((S.D, S.D, 3), 128, np.uint8)
    card = S.face_card(face, style)
    assert card.dtype == np.float32 and card.shape[2] == 4
    if style == "polaroid":
        assert card.shape[0] > card.shape[1] == S.D + 28           # deeper bottom margin
        assert card[..., 3].min() == 255
    else:
        assert card.shape[:2] == (S.D, S.D)
        assert card[0, 0, 3] == 0 and card[S.D // 2, S.D // 2, 3] == 255   # transparent corner, solid centre


def test_glide_holds_then_moves_between_slots():
    pts = [(0.0, 0.0), (500.0, 900.0)]
    assert S.glide(pts, 0.0, 20.0) == (0.0, 0.0)
    x, y = S.glide(pts, 20.0, 20.0)
    assert (round(x), round(y)) == (500, 900)
    mid = S.glide(pts, 10.0, 20.0)                     # the glide is centred on the unit's midpoint
    assert 0 < mid[0] < 500


def test_pop_fades_in_and_out_and_grows():
    s0, a0 = S.pop(0.0, 5.0)
    s1, a1 = S.pop(1.0, 5.0)
    assert a0 == 0.0 and a1 == 1.0 and s1 == pytest.approx(1.0)
    assert S.pop(4.99, 0.01)[1] < 0.1                  # fading out at the end
    g0 = S.pop(1.0, 9.0, grow=(0.85, 1.05), dur=10.0)[0]
    g1 = S.pop(9.0, 1.0, grow=(0.85, 1.05), dur=10.0)[0]
    assert g1 > g0


def test_slots_keep_bottom_right_above_captions():
    sl = S.slots(1080, 1920, cap_top=1420, box=720)
    assert sl["BR"][1] + 720 <= 1420 + 60
    assert sl["TL"][0] < sl["TR"][0]


def test_design_card_ends_above_captions():
    im = S.design_card(_photo(1080, 1920), (1080, 1920), bottom=1380, angle=-2.5)
    a = np.asarray(im.getchannel("A"))
    rows = np.where(a.max(1) > 200)[0]
    assert im.size == (1080, 1920)
    assert rows.max() < 1380 + 40                      # tilt and shadow allowed, never into the caption box


@FONTS
def test_text_card_draws_one_centred_line():
    im = S.text_card("50 个起批", "num", (1080, 1920), font("cjk-bold"))
    a = np.asarray(im.getchannel("A"))
    ys, xs = np.where(a > 0)
    assert im.size == (1080, 1920)
    assert abs((xs.min() + xs.max()) / 2 - 540) < 20
    assert 0.3 * 1920 < ys.mean() < 0.55 * 1920        # num style sits in the middle


@FONTS
def test_story_covers_render_at_size():
    size = (540, 960)
    rec = CS.receipt(_photo(), dict(title="Building my own AI toy", head=["SHOP", "RECEIPT"], stamp="2026-01-01",
                                    rows=[("Cat x1", "¥160"), ("Chip", "ESP32")], total=("TOTAL", "build my own")), size)
    mag = CS.magazine(_photo(), dict(masthead="TOWN", issue="ISSUE 1", lines=[("ESP32", "inside")], title="t",
                                     subtitle="s"), size)
    io = CS.inside_outside(_photo(seed=1), _photo(seed=2), dict(labels=("OUTSIDE", "INSIDE"), line1="a", line2="b"),
                           size)
    cut = Image.new("RGBA", (400, 500), (200, 150, 120, 0))
    cut.paste((200, 150, 120, 255), (100, 100, 300, 500))
    stk = CS.narrator_sticker(cut, _photo(), dict(title=("Building my", "own AI toy"), subtitle="first stop"), size)
    for im in (rec, mag, io, stk):
        assert im.size == size and im.mode == "RGB"


def test_thermal_print_is_two_tone():
    im = CS.thermal(_photo(), 120, 90)
    assert len(set(map(tuple, np.asarray(im).reshape(-1, 3)))) == 2


def test_char_spans_find_glued_connectors():
    from photostory.own_voice import char_spans
    words = [dict(w="然后如果", t=1.0, te=2.0), dict(w="是", t=2.0, te=2.2), dict(w="然后", t=3.0, te=3.4)]
    sp = char_spans(words, "然后")
    assert len(sp) == 2
    assert sp[0][0] == pytest.approx(0.97) and sp[0][1] == pytest.approx(1.53)   # the first half of "然后如果"
    assert sp[1] == pytest.approx((2.97, 3.43))
