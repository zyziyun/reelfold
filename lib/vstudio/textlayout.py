"""Whole-paragraph styled text using the existing Pango/Cairo stack.

Pango owns BiDi, shaping, graphemes and font fallback. The small ABI bridge uses
our already installed CFFI; no second native stack or string reversal. Ordinary
covered Latin/CJK text can keep the established Pillow path in ``draw``.
"""
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from io import BytesIO
from pathlib import Path
import ctypes.util
import math
from numbers import Integral
import os
import sys
import threading
import unicodedata

_LOCK = threading.RLock()
_REGISTERED = set()


@lru_cache(maxsize=32)
def _coverage(path, index=0):
    from fontTools.ttLib import TTFont
    with TTFont(path, fontNumber=index, lazy=True) as font:
        return frozenset((font.getBestCmap() or {}).keys())


def needed(text, font):
    """Use paragraph layout for complex scripts or glyphs missing in the chosen face."""
    if any(unicodedata.bidirectional(c) in ('R', 'AL', 'AN') or unicodedata.category(c).startswith('M')
           or 0x900 <= ord(c) <= 0x1FFF for c in text):
        return True
    path = getattr(font, 'path', None)
    if isinstance(path, (str, bytes, os.PathLike)):
        cmap = _coverage(path, getattr(font, 'index', 0))
        return any(not c.isspace() and ord(c) not in cmap for c in text)
    return any(ord(c) > 127 for c in text)


@dataclass(frozen=True)
class Run:
    text: str
    color: tuple = (255, 255, 255, 255)
    emphasis: bool = False
    font: object = None


_API = '''
typedef struct { int x, y, width, height; } PangoRectangle;
void *cairo_image_surface_create(int format, int width, int height);
void *cairo_create(void *surface);
void cairo_set_source_rgba(void *cr, double r, double g, double b, double a);
void cairo_move_to(void *cr, double x, double y);
void cairo_set_line_width(void *cr, double width);
void cairo_set_line_join(void *cr, int join);
void cairo_stroke(void *cr);
int cairo_status(void *cr);
int cairo_surface_status(void *surface);
int cairo_surface_write_to_png_stream(void *surface, int (*write)(void*, const unsigned char*, unsigned int), void *closure);
void cairo_destroy(void *cr);
void cairo_surface_destroy(void *surface);
void *pango_cairo_font_map_new(void);
int pango_version(void);
int pango_cairo_font_map_get_font_type(void *fontmap);
void *pango_font_map_create_context(void *fontmap);
int pango_font_map_add_font_file(void *fontmap, const char *filename, void *error);
void *pango_layout_new(void *context);
void pango_layout_set_markup(void *layout, const char *markup, int length);
void pango_layout_get_pixel_extents(void *layout, PangoRectangle *ink, PangoRectangle *logical);
void pango_layout_index_to_pos(void *layout, int index, PangoRectangle *pos);
int pango_layout_get_unknown_glyphs_count(void *layout);
void *pango_font_description_from_string(const char *str);
void pango_font_description_set_family(void *desc, const char *family);
void pango_font_description_set_absolute_size(void *desc, double size);
void pango_layout_set_font_description(void *layout, void *desc);
void pango_font_description_free(void *desc);
void pango_cairo_update_layout(void *cr, void *layout);
void pango_cairo_show_layout(void *cr, void *layout);
void pango_cairo_layout_path(void *cr, void *layout);
void g_object_unref(void *object);
void *CFURLCreateFromFileSystemRepresentation(void *allocator, const unsigned char *bytes, long length, unsigned char is_directory);
void CFRelease(void *object);
long CFErrorGetCode(void *error);
unsigned char CTFontManagerRegisterFontsForURL(void *url, int scope, void **error);
'''


@lru_cache(maxsize=1)
def _libraries():
    from cffi import FFI
    ffi = FFI()
    ffi.cdef(_API)
    names = {
        'darwin': ('libcairo.2.dylib', 'libpango-1.0.0.dylib', 'libpangocairo-1.0.0.dylib', 'libgobject-2.0.0.dylib'),
        'win32': ('cairo-2.dll', 'pango-1.0-0.dll', 'pangocairo-1.0-0.dll', 'gobject-2.0-0.dll'),
    }
    root = Path(sys.prefix).resolve().parent / 'ffmpeg' / ('bin' if sys.platform == 'win32' else 'lib')
    bundled = root.is_dir()
    if not bundled and sys.platform == 'darwin':
        # Source installations: standard package-manager library folders, not the cwd or arbitrary PATH entries.
        root = next((p for p in (Path(sys.prefix) / 'lib', Path('/opt/homebrew/lib'), Path('/usr/local/lib'))
                     if all((p / n).is_file() for n in names['darwin'])), root)
    libraries = []
    for i, system_name in enumerate(('cairo', 'pango-1.0', 'pangocairo-1.0', 'gobject-2.0')):
        if root.is_dir() and sys.platform in names:
            base = names[sys.platform][i]
            candidates = (root / base, root / ('lib' + base)) if sys.platform == 'win32' else (root / base,)
            file = next((str(p) for p in candidates if p.is_file()), None)
        else:
            file = ctypes.util.find_library(system_name)
        if not file:
            raise RuntimeError('Complex text layout requires Pango/Cairo; use the bundled app or install Pango 1.56 or newer')
        try:
            libraries.append(ffi.dlopen(file))
        except OSError as exc:
            raise RuntimeError('The text layout library could not load; repair the engine runtime') from exc
    if libraries[1].pango_version() < 15600:
        raise RuntimeError('Complex text layout requires Pango 1.56 or newer')
    return ffi, *libraries


@lru_cache(maxsize=1)
def _fontmap():
    ffi, _, _, pc, go = _libraries()
    fontmap = pc.pango_cairo_font_map_new()
    if fontmap == ffi.NULL:
        raise RuntimeError('Could not allocate the font map')
    return ffi.gc(fontmap, go.g_object_unref)


def _register(path, fontmap):
    if path in _REGISTERED:
        return
    ffi, _, pa, pc, _ = _libraries()
    if sys.platform == 'darwin' and pc.pango_cairo_font_map_get_font_type(fontmap) == 3:
        # Pango's CoreText backend uses process-local registration (its generic file method is not implemented).
        cf = ffi.dlopen('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        ct = ffi.dlopen('/System/Library/Frameworks/CoreText.framework/CoreText')
        encoded = os.fsencode(path)
        url = cf.CFURLCreateFromFileSystemRepresentation(ffi.NULL, encoded, len(encoded), 0)
        if url == ffi.NULL:
            raise RuntimeError('Could not create the selected font URL')
        error = ffi.new('void **')
        try:
            ok = bool(ct.CTFontManagerRegisterFontsForURL(url, 1, error))
            if not ok and error[0] != ffi.NULL:
                ok = cf.CFErrorGetCode(error[0]) == 105  # kCTFontManagerErrorAlreadyRegistered
        finally:
            if error[0] != ffi.NULL:
                cf.CFRelease(error[0])
            cf.CFRelease(url)
    else:
        ok = bool(pa.pango_font_map_add_font_file(fontmap, os.fsencode(path), ffi.NULL))
    if not ok:
        raise RuntimeError('The selected font could not be loaded for paragraph layout')
    _REGISTERED.add(path)


class Layout:
    """One full shaped paragraph. Keep all native objects scoped to a with block."""
    def __init__(self, runs, font):
        self.runs = tuple(runs)
        self.font = font
        self.text = ''.join(r.text for r in self.runs)
        if len(self.text) > 10000 or '\0' in self.text:
            raise ValueError('Text layout is too long or contains a NUL character')
        if not 0 < font.size <= 4096:
            raise ValueError('Text font size must be between 1 and 4096 pixels')
        for run in self.runs:
            if len(run.color) not in (3, 4) or any(not isinstance(c, Integral) or not 0 <= c <= 255 for c in run.color):
                raise ValueError('Text colours must contain three or four integer channels between 0 and 255')
        self._objects = []

    def __enter__(self):
        _LOCK.acquire()
        try:
            self.ffi, self.ca, self.pa, self.pc, self.go = _libraries()
            fontmap = _fontmap()
            fonts = [self.font] + [r.font for r in self.runs if r.font is not None]
            for path in {str(f.path) for f in fonts if isinstance(getattr(f, 'path', None), (str, os.PathLike))}:
                _register(path, fontmap)
            context = self._own(self.pa.pango_font_map_create_context(fontmap))
            self.layout = self._own(self.pa.pango_layout_new(context))
            family, style = self.font.getname()
            desc = self.pa.pango_font_description_from_string(style.encode())
            if desc == self.ffi.NULL:
                raise RuntimeError('Could not create the text font description')
            try:
                self.pa.pango_font_description_set_family(desc, family.encode())
                self.pa.pango_font_description_set_absolute_size(desc, self.font.size * 1024)
                self.pa.pango_layout_set_font_description(self.layout, desc)
            finally:
                self.pa.pango_font_description_free(desc)
            spans = []
            for run in self.runs:
                color = tuple(run.color) + (255,) if len(run.color) == 3 else run.color
                attrs = f'foreground="#{color[0]:02x}{color[1]:02x}{color[2]:02x}" alpha="{round(color[3] * 257)}"'
                if run.font is not None:
                    name, face = run.font.getname()
                    attrs += f' font_desc="{escape(face, quote=True)}" font_family="{escape(name, quote=True)}"'
                spans.append(f'<span {attrs}>{escape(run.text)}</span>')
            markup = ''.join(spans).encode()
            self.pa.pango_layout_set_markup(self.layout, markup, len(markup))
            unknown = self.pa.pango_layout_get_unknown_glyphs_count(self.layout)
            if unknown:
                raise RuntimeError(f'The available fonts are missing {unknown} text glyphs; choose or install fonts for this language')
            ink, logical = self.ffi.new('PangoRectangle *'), self.ffi.new('PangoRectangle *')
            self.pa.pango_layout_get_pixel_extents(self.layout, ink, logical)
            self.left, self.top = min(ink.x, logical.x), min(ink.y, logical.y)
            self.width = max(1, max(ink.x + ink.width, logical.x + logical.width) - self.left)
            self.height = max(1, max(ink.y + ink.height, logical.y + logical.height) - self.top)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _own(self, obj):
        if obj == self.ffi.NULL:
            raise RuntimeError('Could not allocate the text layout')
        self._objects.append(obj)
        return obj

    def __exit__(self, *_):
        for obj in reversed(self._objects):
            self.go.g_object_unref(obj)
        self._objects.clear()
        _LOCK.release()

    def emphasis_boxes(self):
        """Native grapheme positions, including RTL and fallback fonts; no guessed character widths."""
        offset = 0
        boxes = []
        rect = self.ffi.new('PangoRectangle *')
        for run in self.runs:
            for char in run.text:
                if run.emphasis:
                    self.pa.pango_layout_index_to_pos(self.layout, offset, rect)
                    x0, x1 = sorted((rect.x / 1024, (rect.x + rect.width) / 1024))
                    if x1 > x0:
                        boxes.append((x0 - self.left, rect.y / 1024 - self.top, x1 - self.left, (rect.y + rect.height) / 1024 - self.top))
                offset += len(char.encode())
        # Merge visual neighbours of the same line, including repeated boxes for combining marks.
        merged = []
        for box in sorted(set(boxes), key=lambda r: (r[1], r[0])):
            if merged and abs(merged[-1][1] - box[1]) < .01 and abs(merged[-1][3] - box[3]) < .01 and box[0] <= merged[-1][2] + 1:
                a = merged[-1]; merged[-1] = (a[0], a[1], max(a[2], box[2]), a[3])
            else:
                merged.append(box)
        return merged

    def image(self, stroke=0, stroke_fill=(0, 0, 0, 255)):
        from PIL import Image
        border = max(0, math.ceil(stroke))
        w, h = self.width + 2 * border, self.height + 2 * border
        if w * h > 16_777_216:
            raise ValueError('Text layout is too large; use a smaller font or shorter lines')
        surface = self.ca.cairo_image_surface_create(0, w, h)
        cr = self.ca.cairo_create(surface)
        try:
            if self.ca.cairo_surface_status(surface) or self.ca.cairo_status(cr):
                raise RuntimeError('Could not create the text canvas')
            self.ca.cairo_move_to(cr, border - self.left, border - self.top)
            self.pc.pango_cairo_update_layout(cr, self.layout)
            if stroke:
                self.ca.cairo_set_source_rgba(cr, *(c / 255 for c in stroke_fill))
                self.ca.cairo_set_line_width(cr, 2 * stroke)
                self.ca.cairo_set_line_join(cr, 1)
                self.pc.pango_cairo_layout_path(cr, self.layout)
                self.ca.cairo_stroke(cr)
                self.ca.cairo_move_to(cr, border - self.left, border - self.top)
            self.pc.pango_cairo_show_layout(cr, self.layout)
            chunks = []

            @self.ffi.callback('int(void *, const unsigned char *, unsigned int)')
            def write(_, data, length):
                chunks.append(bytes(self.ffi.buffer(data, length)))
                return 0

            if self.ca.cairo_status(cr) or self.ca.cairo_surface_write_to_png_stream(surface, write, self.ffi.NULL):
                raise RuntimeError('Could not render the text canvas')
            with Image.open(BytesIO(b''.join(chunks))) as image:
                return image.convert('RGBA')
        finally:
            self.ca.cairo_destroy(cr)
            self.ca.cairo_surface_destroy(surface)


def measure(text, font):
    with Layout([Run(text)], font) as layout:
        return layout.width, layout.height


def block(lines, font, *, pad=0, stroke=0, stroke_fill=(0, 0, 0, 255), line_gap=1.15, align='left',
          shadow_alpha=0, shadow_blur=4, marker=None, sweep=1.0):
    """Render styled lines; decoration uses native visual positions and the existing Pillow compositor."""
    from PIL import Image, ImageDraw, ImageFilter
    if sum(len(run.text) for row in lines for run in row) > 10000:
        raise ValueError('Text layout is too long')
    rows, boxes = [], []
    for runs in lines:
        with Layout(runs, font) as layout:
            rows.append(layout.image(stroke, stroke_fill))
            boxes.append(layout.emphasis_boxes())
    if not rows:
        return Image.new('RGBA', (1, 1))
    border = max(0, math.ceil(stroke))
    width = max(r.width for r in rows) + 2 * pad
    offsets, y = [], pad
    for row in rows:
        x = pad + ((width - 2 * pad - row.width) / 2 if align == 'center' else
                   width - 2 * pad - row.width if align == 'right' else 0)
        offsets.append((round(x), round(y)))
        y += row.height * line_gap
    height = max(1, math.ceil(offsets[-1][1] + rows[-1].height + pad + (4 if shadow_alpha else 0)))
    if width * height > 16_777_216:
        raise ValueError('Text layout is too large; use a smaller font or shorter lines')
    image = Image.new('RGBA', (width, height))
    if marker and sweep > 0:
        mode, color = marker
        draw = ImageDraw.Draw(image)
        for rects, (x, y) in zip(boxes, offsets):
            for x0, y0, x1, y1 in rects:
                top = y + border + y0 + (y1-y0) * (.90 if mode == 'underline' else .52)
                bottom = top + max(2, font.size * .07) if mode == 'underline' else y + border + y0 + (y1-y0)*.94
                draw.rectangle((x+border+x0, top, x+border+x0+(x1-x0)*min(1, sweep), bottom), fill=color)
    foreground = Image.new('RGBA', image.size)
    for row, pos in zip(rows, offsets):
        foreground.alpha_composite(row, pos)
    if shadow_alpha:
        shadow = Image.new('RGBA', image.size, (0, 0, 0, 0))
        shadow.putalpha(foreground.getchannel('A').point(lambda a: round(a * shadow_alpha / 255)))
        image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(shadow_blur)), (3, 4))
    image.alpha_composite(foreground)
    return image
