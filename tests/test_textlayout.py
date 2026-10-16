"""Paragraph shaping, fallback and shared styled drawing; no character reversal or second native stack."""
from types import SimpleNamespace
import threading

import numpy as np
import pytest
from PIL import Image, ImageDraw

from vstudio import draw as D, textlayout as T


def test_covered_latin_and_cjk_stay_on_the_existing_renderer(monkeypatch):
    monkeypatch.setattr(T, '_coverage', lambda *_: set(map(ord, 'Hello你好 !')))
    f = SimpleNamespace(path='selected.otf')
    assert not T.needed('Hello 你好!', f)
    assert T.needed('łódź', f)  # missing glyphs, not just a script/language label
    assert T.needed('مرحبا', f)
    assert T.needed('नमस्ते', f)
    assert T.needed('Cafe\u0301', f)


def test_font_collection_coverage_uses_the_selected_face(tmp_path):
    from io import BytesIO
    from fontTools.ttLib import TTFont, TTCollection
    from PIL import ImageFont
    data = ImageFont.load_default(size=30).font_bytes
    collection = TTCollection()
    collection.fonts = [TTFont(BytesIO(data)), TTFont(BytesIO(data))]
    for table in collection.fonts[1]['cmap'].tables:
        if table.isUnicode():
            table.cmap.pop(ord('h'), None)
    path = tmp_path / 'faces.ttc'
    collection.save(path)
    first = ImageFont.truetype(str(path), 30, index=0)
    second = ImageFont.truetype(str(path), 30, index=1)
    assert not T.needed('hello', first)
    assert T.needed('hello', second)


@pytest.mark.parametrize('text', ['x\0y', 'x' * 10001])
def test_invalid_paragraph_never_enters_the_native_renderer(text, monkeypatch):
    monkeypatch.setattr(T, '_libraries', lambda: pytest.fail('must validate before loading native code'))
    with pytest.raises(ValueError):
        T.Layout([T.Run(text)], SimpleNamespace(size=40))


@pytest.mark.parametrize('color', [(999, 0, 0), (0, 0), (1.5, 0, 0, 255)])
def test_invalid_color_is_not_silently_dropped_by_markup_parser(color):
    with pytest.raises(ValueError, match='colours'):
        T.Layout([T.Run('hello', color)], SimpleNamespace(size=40))


def test_failed_library_load_releases_the_render_lock(monkeypatch):
    def unavailable():
        raise RuntimeError('native library missing')
    monkeypatch.setattr(T, '_libraries', unavailable)
    with pytest.raises(RuntimeError, match='native library missing'):
        with T.Layout([T.Run('مرحبا')], SimpleNamespace(size=40)):
            pass
    acquired = []
    def check():
        ok = T._LOCK.acquire(timeout=.5)
        acquired.append(ok)
        if ok:
            T._LOCK.release()
    worker = threading.Thread(target=check)
    worker.start(); worker.join(1)
    assert acquired == [True]


@pytest.fixture
def native_font():
    try:
        T._libraries()
    except RuntimeError as exc:
        pytest.skip(str(exc))
    return D.load_font('cjk-bold', 48)


def test_plain_and_equivalent_styled_runs_keep_the_same_shaped_glyphs(native_font):
    text = 'مرحبا Reelfold 2026'
    with T.Layout([T.Run(text)], native_font) as whole:
        expected = np.asarray(whole.image())
    with T.Layout([T.Run('مر'), T.Run('حبا '), T.Run('Reelfold '), T.Run('2026')], native_font) as styled:
        actual = np.asarray(styled.image())
    np.testing.assert_array_equal(actual, expected)


def test_foreground_emphasis_keeps_arabic_joining_and_geometry(native_font):
    with T.Layout([T.Run('مرحبا')], native_font) as plain:
        expected = np.asarray(plain.image())[..., 3]
    with T.Layout([T.Run('مر'), T.Run('ح', (255, 100, 0, 255), True), T.Run('با')], native_font) as styled:
        actual = np.asarray(styled.image())
        assert styled.emphasis_boxes()
    # Different foreground runs composite antialiasing separately at shared joining edges;
    # ink coverage/placement must still be identical (no tolerance for detached or moved glyphs).
    np.testing.assert_array_equal(actual[..., 3] > 0, expected > 0)
    assert np.any((actual[..., 0] > actual[..., 1]) & (actual[..., 3] > 0))


def test_missing_glyph_is_an_error_instead_of_a_successful_tofu_image(native_font):
    with pytest.raises(RuntimeError, match='missing .* glyphs'):
        with T.Layout([T.Run('\u0378')], native_font):
            pass


def test_visual_emphasis_boxes_remain_inside_mixed_direction_line(native_font):
    with T.Layout([T.Run('مرحبا '), T.Run('Reelfold', emphasis=True), T.Run(' بالعالم')], native_font) as layout:
        boxes = layout.emphasis_boxes()
        assert boxes
        assert all(0 <= x0 < x1 <= layout.width + 1 and 0 <= y0 < y1 <= layout.height + 1 for x0, y0, x1, y1 in boxes)


@pytest.mark.parametrize('mode', ['color', 'marker', 'underline'])
def test_existing_theme_decorations_render_on_full_paragraph(native_font, mode):
    image = D.emph_layer('احتفظ 【بصوتك】', native_font, emphasis=mode, max_w=500)
    alpha = np.asarray(image)[..., 3]
    assert image.width <= 550 and 0 < image.height < 200
    assert alpha.max() > 0 and alpha.min() == 0


def test_wrapped_overlay_composites_without_losing_target_image(native_font):
    image = Image.new('RGBA', (600, 300), '#172238')
    original = np.asarray(image).copy()
    y = D.wrap_draw(ImageDraw.Draw(image), (20, 20), 'احتفظ 【بصوتك】 قبل النشر', native_font, 450)
    assert 20 < y < 300
    assert np.any(np.asarray(image) != original)
    np.testing.assert_array_equal(np.asarray(image)[-1], original[-1])
