"""Paragraph shaping, fallback and shared styled drawing; no character reversal or second native stack."""
from functools import lru_cache
from types import SimpleNamespace
from unittest.mock import Mock
import ctypes.util
import sys
import threading

import numpy as np
import pytest
from PIL import Image, ImageDraw

from vstudio import draw as D, textlayout as T


def test_bundled_libraries_take_precedence_over_external_folder(tmp_path, monkeypatch):
    prefix = tmp_path / 'runtime/python'
    native = tmp_path / 'runtime/ffmpeg/lib'
    native.mkdir(parents=True)
    monkeypatch.setattr(T.sys, 'prefix', str(prefix))
    monkeypatch.setattr(T.sys, 'platform', 'darwin')
    monkeypatch.setenv('VSTUDIO_TEXT_LAYOUT_DIR', str(tmp_path / 'external'))
    assert T._library_directory() == native


def test_source_native_folder_is_explicit_and_absolute(tmp_path, monkeypatch):
    monkeypatch.setattr(T.sys, 'prefix', str(tmp_path / 'other/python'))
    monkeypatch.setenv('VSTUDIO_TEXT_LAYOUT_DIR', str(tmp_path))
    assert T._library_directory() == tmp_path
    monkeypatch.setenv('VSTUDIO_TEXT_LAYOUT_DIR', 'relative/native')
    with pytest.raises(RuntimeError, match='absolute path'):
        T._library_directory()


def test_windows_loader_uses_real_locked_cairo_dll_name(tmp_path, monkeypatch):
    from cffi import FFI
    names = ('cairo.dll', 'pango-1.0-0.dll', 'pangocairo-1.0-0.dll', 'gobject-2.0-0.dll')
    for name in names:
        (tmp_path / name).touch()
    loaded = []
    def load(_, path):
        loaded.append(path)
        return SimpleNamespace(pango_version=lambda: 15802)
    with monkeypatch.context() as patch:
        patch.setattr(T.sys, 'platform', 'win32')
        patch.setattr(T, '_library_directory', lambda: tmp_path)
        patch.setattr(T.os, 'add_dll_directory', lambda _: object(), raising=False)
        patch.setattr(FFI, 'dlopen', load)
        T._libraries.cache_clear()
        try:
            T._libraries()
            assert loaded == [str(tmp_path / name) for name in names]
        finally:
            T._libraries.cache_clear()


def test_older_fontconfig_backend_keeps_selected_custom_font(monkeypatch):
    ffi = SimpleNamespace(NULL=None)
    pango = SimpleNamespace(pango_version=lambda: 15200, pango_font_map_changed=Mock(),
                            pango_font_map_add_font_file=Mock(side_effect=AssertionError('requires newer Pango')))
    cairo = SimpleNamespace(pango_cairo_font_map_get_font_type=lambda _: 1)
    fc = SimpleNamespace(FcConfigGetCurrent=lambda: 'process-config', FcConfigAppFontAddFile=Mock(return_value=1))
    monkeypatch.setattr(T, '_libraries', lambda: (ffi, None, pango, cairo, None))
    monkeypatch.setattr(T, '_fontconfig', lambda: fc)
    monkeypatch.setattr(T, '_REGISTERED', set())
    T._register('/fonts/selected.otf', 'fontmap')
    fc.FcConfigAppFontAddFile.assert_called_once_with('process-config', b'/fonts/selected.otf')
    pango.pango_font_map_changed.assert_called_once_with('fontmap')
    T._register('/fonts/selected.otf', 'fontmap')
    assert fc.FcConfigAppFontAddFile.call_count == 1


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
    # Native layout is a product dependency. Missing CI libraries must fail here,
    # rather than turning every actual rendering check into a green skipped suite.
    T._libraries()
    return D.load_font('cjk-bold', 48)


def test_real_fontconfig_registration_loads_selected_font(native_font, monkeypatch):
    ffi, _, _, pc, go = T._libraries()
    fontmap = pc.pango_cairo_font_map_new_for_font_type(1)  # CAIRO_FONT_TYPE_FT
    if fontmap == ffi.NULL:
        pytest.skip('This Pango build has no FreeType backend')
    fontmap = ffi.gc(fontmap, go.g_object_unref)
    monkeypatch.setattr(T, '_REGISTERED', set())
    monkeypatch.setattr(T, '_fontmap', lambda: fontmap)
    with T.Layout([T.Run('مرحبا Reelfold 2026')], native_font) as layout:
        assert layout.width > 100
        assert layout.image().getbbox()
    assert str(native_font.path) in T._REGISTERED


def test_windows_uses_the_font_backend_supported_by_locked_harfbuzz(monkeypatch):
    pc = SimpleNamespace(pango_cairo_font_map_new_for_font_type=Mock(return_value='freetype'),
                         pango_cairo_font_map_new=Mock(side_effect=AssertionError('DirectWrite is unsupported')))
    ffi = SimpleNamespace(NULL=None, gc=lambda obj, cleanup: obj)
    with monkeypatch.context() as patch:
        patch.setattr(T.sys, 'platform', 'win32')
        patch.setattr(T, '_libraries', lambda: (ffi, None, None, pc, SimpleNamespace(g_object_unref=Mock())))
        T._fontmap.cache_clear()
        try:
            assert T._fontmap() == 'freetype'
            pc.pango_cairo_font_map_new_for_font_type.assert_called_once_with(1)
        finally:
            T._fontmap.cache_clear()



@lru_cache(maxsize=1)
def _native_debug_api():
    ffi, _, pa, _, _ = T._libraries()
    ffi.cdef('''
        void *pango_layout_serialize(void *layout, int flags);
        const void *g_bytes_get_data(void *bytes, size_t *size);
        void g_bytes_unref(void *bytes);
    ''')
    # GBytes belongs to GLib. Windows DLL symbol lookup does not search the
    # dependencies of GObject, unlike the transitive lookup on Unix systems.
    root = T._library_directory()
    if root is not None and sys.platform in ('darwin', 'win32'):
        names = ('libglib-2.0.0.dylib',) if sys.platform == 'darwin' else ('glib-2.0-0.dll', 'libglib-2.0-0.dll')
        library = next((str(root / name) for name in names if (root / name).is_file()), None)
    else:
        library = ctypes.util.find_library('glib-2.0')
    assert library, 'Native layout diagnostics require the existing GLib library'
    return ffi, pa, ffi.dlopen(library)


def _native_debug(layout):
    # Pango's own testing/debug format records actual fallback faces and glyph
    # positions. Keep strict pixel assertions; explain an OS-specific failure
    # with native evidence instead of guessing from its platform name.
    ffi, pa, go = _native_debug_api()
    if pa.pango_version() < 15000:
        return f'Pango {pa.pango_version()} (layout serialization needs 1.50)'
    blob = pa.pango_layout_serialize(layout.layout, 3)  # CONTEXT | OUTPUT
    assert blob != ffi.NULL
    try:
        length = ffi.new('size_t *')
        data = go.g_bytes_get_data(blob, length)
        return bytes(ffi.buffer(data, length[0])).decode('utf-8')
    finally:
        go.g_bytes_unref(blob)


def test_plain_and_equivalent_styled_runs_keep_the_same_shaped_glyphs(native_font):
    text = 'مرحبا Reelfold 2026'
    with T.Layout([T.Run(text)], native_font) as whole:
        expected = np.asarray(whole.image())
        whole_debug = _native_debug(whole)
    with T.Layout([T.Run('مر'), T.Run('حبا '), T.Run('Reelfold '), T.Run('2026')], native_font) as styled:
        actual = np.asarray(styled.image())
        styled_debug = _native_debug(styled)
    np.testing.assert_array_equal(actual, expected, err_msg=f'Whole native layout: {whole_debug}\nStyled native layout: {styled_debug}')



def _caret_positions(layout):
    rect = layout.ffi.new('PangoRectangle *')
    offset = 0
    positions = []
    for char in layout.text:
        layout.pa.pango_layout_index_to_pos(layout.layout, offset, rect)
        positions.append((rect.x, rect.y, rect.width, rect.height))
        offset += len(char.encode())
    return positions


def test_foreground_emphasis_keeps_arabic_joining_and_geometry(native_font):
    with T.Layout([T.Run('مرحبا')], native_font) as plain:
        plain_image = plain.image()
        expected = np.asarray(plain.image(stroke=1))[..., 3]
        expected_positions = _caret_positions(plain)
        plain_debug = _native_debug(plain)
    with T.Layout([T.Run('مر'), T.Run('ح', (255, 100, 0, 255), True), T.Run('با')], native_font) as styled:
        styled_image = styled.image()
        actual = np.asarray(styled.image(stroke=1))
        assert styled.emphasis_boxes()
        actual_positions = _caret_positions(styled)
        styled_debug = _native_debug(styled)
    assert actual_positions == expected_positions
    assert styled_image.size == plain_image.size
    assert styled_image.getbbox() == plain_image.getbbox()
    # Foreground runs composite antialiasing separately at shared glyph edges.
    # That alpha is not a shaping invariant. Compare the unified native stroked
    # outline exactly, alongside every logical position and the unstroked bounds.
    np.testing.assert_array_equal(actual[..., 3] > 0, expected > 0, err_msg=f'Plain native layout: {plain_debug}\nStyled native layout: {styled_debug}')
    foreground = np.asarray(styled_image)
    assert np.any((foreground[..., 0] > foreground[..., 1]) & (foreground[..., 3] > 0))


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


def test_unspaced_thai_uses_dictionary_breaks_and_keeps_every_character(native_font):
    text = 'การตัดต่อวิดีโอช่วยให้ผู้สร้างสามารถเล่าเรื่องราวที่น่าสนใจและแบ่งปันความรู้กับผู้ชมได้อย่างชัดเจน'
    lines = D.wrap(text, native_font, 430, balance=True)
    assert len(lines) > 1
    assert ''.join(lines) == text
    assert all(D.text_width(line, native_font) <= 430 for line in lines)
    assert any('วิดีโอ' in line for line in lines)
    from vstudio.textbreak import dictionary_words
    boundaries = set(dictionary_words(text).values())
    end = 0
    for line in lines:
        end += len(line)
        assert end in boundaries  # only break at dictionary boundaries, independent of fallback font metrics


def test_dictionary_wrapping_preserves_emphasis_across_line_boundaries(native_font):
    text = 'การตัดต่อ【วิดีโอช่วยให้ผู้สร้างสามารถเล่าเรื่องราวที่น่าสนใจ】และแบ่งปันความรู้'
    lines = D.wrap(text, native_font, 300)
    assert ''.join(D.plain(line) for line in lines) == D.plain(text)
    assert all(line.count('【') == line.count('】') for line in lines)
    highlighted = ''.join(t for line in lines for t, h in D.runs(line) if h)
    assert highlighted == 'วิดีโอช่วยให้ผู้สร้างสามารถเล่าเรื่องราวที่น่าสนใจ'


def test_dictionary_indexes_preserve_non_bmp_characters_and_no_spaced_script_dependency():
    from vstudio.textbreak import dictionary_words
    assert dictionary_words('مرحبا Reelfold 안녕하세요') == {}
    text = '🎥การตัดต่อวิดีโอ 🎞️'
    spans = dictionary_words(text)
    assert [text[a:b] for a, b in spans.items()] == ['การ', 'ตัด', 'ต่อ', 'วิดีโอ']
    assert all(0 < a < b <= len(text) for a, b in spans.items())
