"""Text layers: bilingual subtitles (**highlight**, balanced no-orphan wrapping), picture labels,
running header with section progress, chapter cards. All return float32 RGBA arrays."""
import math
import re

import numpy as np
from PIL import Image, ImageDraw

from vstudio.subs import balanced_wrap, parse_highlight, strip_markup

from .ctx import font, font_for
from .util import has_cjk as has_cjk_text, layer, soft_shadow, spaced, to_arr

_D = ImageDraw.Draw(Image.new("RGBA", (1, 1)))


def bwrap(d, text, f, maxw):
    """Pixel-measured balanced wrap (fewest lines, similar lengths, no 1-char orphan, latin words whole);
    **highlight** / 【】 markers are closed and reopened on every line."""
    return balanced_wrap(text, maxw, measure=lambda t: d.textlength(t, font=f))


def draw_runs(C, d, x, y, line, f, base, stroke):
    for p, hi in parse_highlight(line):
        if stroke:
            d.text((x, y), p, font=f, fill=(C.GOLD if hi else base) + (255,), stroke_width=stroke,
                   stroke_fill=(0, 0, 0, 210))
        else:
            d.text((x, y), p, font=f, fill=(C.GOLD if hi else base) + (255,))
        x += d.textlength(p, font=f)


def make_sub(C, en, zh):
    """EN line(s) on top, 中文 below (中文 on top when the narration is Chinese), centred in the subtitle band.
    Either may be empty."""
    if hasattr(C, "sub_pair"):
        en, zh = C.sub_pair(en, zh)
    zh = (zh or "").rstrip("，。、：；")
    en = en or ""
    if C.prof is not None or getattr(C, "cinema", False):
        if C.prof is None:          # legacy canvas: the caption box is the subtitle band
            C.CAP = getattr(C, "CAP", (C.t(70), C.SUB_Y0, C.W - C.t(70), C.H))
        return _make_sub_fit(C, en, zh)
    fe = font_for(en, C.t(56), "sans-bold", "cjk-bold")
    fz = font("cjk-bold", C.t(66))
    lay = layer(C.W, C.SUB_H)
    d = ImageDraw.Draw(lay)
    m = C.t(140)
    le = bwrap(d, en, fe, C.W - m) if en else []
    lz = bwrap(d, zh, fz, C.W - m) if zh else []
    LE, LZ = C.t(70), C.t(82)
    G = C.t(14) if le and lz else 0
    stroke = max(1, round(2 * C.S + 0.3))
    y = (lay.height - (LE * len(le) + G + LZ * len(lz))) // 2 - C.t(6)
    blocks = [(le, fe, C.pal["sub_en"], LE), (lz, fz, C.pal["sub_zh"], LZ)]
    if getattr(C, "ZH_LEAD", False):
        blocks.reverse()
    for j, (lines, f, col, lh) in enumerate(blocks):
        if j == 1:
            y += G
        for ln in lines:
            draw_runs(C, d, (C.W - d.textlength(strip_markup(ln), font=f)) / 2, y, ln, f, col, stroke)
            y += lh
    return to_arr(lay)


def _sub_lines(C, d, en, zh, k, maxw, title=False):
    """Font sizes scaled by k -> (fe, fz, le, lz, LE, LZ, G, total height)."""
    if title:      # music mode: 中文 serif first, English italic below
        zs, es = C.ZH_SIZE * k, C.ZH_SIZE * k * 0.62
        fz = font_for(zh, zs, "cjk-serif", "cjk-serif")
        fe = font_for(en, es, "serif-italic", "cjk")
    elif getattr(C, "cinema", False):     # refined: regular weight, a little smaller, no stroke (soft shadow)
        zs, es = C.ZH_SIZE * k * 0.86, C.ZH_SIZE * k * 0.86 * 52 / 66
        fz = font("cjk", zs)
        fe = font_for(en, es, "sans", "cjk")
    else:
        zs, es = C.ZH_SIZE * k, C.ZH_SIZE * k * 56 / 66
        fz = font("cjk-bold", zs)
        fe = font_for(en, es, "sans-bold", "cjk-bold")
    le = bwrap(d, en, fe, maxw) if en else []
    lz = bwrap(d, zh, fz, maxw) if zh else []
    LE, LZ = int(round(es * 1.25)), int(round(zs * (1.5 if title else 1.24)))
    G = int(round(zs * (0.32 if title else 0.21))) if le and lz else 0
    return fe, fz, le, lz, LE, LZ, G, LE * len(le) + G + LZ * len(lz)


def _make_sub_fit(C, en, zh, title=False):
    """Platform layout: bilingual cue fitted into the caption box (width and band height); the 中文 size
    starts from the profile's caption size range and shrinks until both languages fit."""
    x0, _, x1, _ = C.CAP
    lay = layer(C.W, C.SUB_H)
    d = ImageDraw.Draw(lay)
    maxw = x1 - x0
    k = 1.0
    while True:
        fe, fz, le, lz, LE, LZ, G, tot = _sub_lines(C, d, en, zh, k, maxw, title)
        if (tot <= C.SUB_H * 0.94 and len(le) <= 2 and len(lz) <= 2) or k < 0.55:
            break
        k -= 0.05
    cine = getattr(C, "cinema", False)
    stroke = 0 if title or cine else max(1, round(2 * C.S + 0.3))
    y = (lay.height - tot) // 2
    # 中文 first in a title, and when the narrator speaks Chinese (the English is then the translation under it)
    order = [(lz, fz, C.pal["sub_zh"], LZ), (le, fe, (214, 198, 168) if title else C.pal["sub_en"], LE)] \
        if title or getattr(C, "ZH_LEAD", False) else [(le, fe, C.pal["sub_en"], LE), (lz, fz, C.pal["sub_zh"], LZ)]
    for j, (lines, f, col, lh) in enumerate(order):
        if j == 1:
            y += G
        for ln in lines:
            draw_runs(C, d, (x0 + x1 - d.textlength(strip_markup(ln), font=f)) / 2, y, ln, f, col, stroke)
            y += lh
    if cine or title:
        lay = soft_shadow(lay, radius=max(3, C.t(10)), alpha=0.7 if cine else 0.5)
    return to_arr(lay)


def make_title_text(C, en, zh):
    """MODE "music": a spec line as quiet title text (中文 serif + English italic), no speech-style stroke."""
    if hasattr(C, "sub_pair"):
        en, zh = C.sub_pair(en, zh)
    zh = (zh or "").rstrip("，。、：；")
    return _make_sub_fit(C, en or "", zh, title=True)


def sub_backdrop(C):
    """Soft dark gradient behind subtitles when they are overlaid on the picture (landscape)."""
    h = C.SUB_H if C.prof is None else C.H - C.SUB_Y0 + int(0.35 * C.SUB_H)   # platform: band to the bottom edge
    peak = 120 if getattr(C, "cinema", False) else 200     # cinema: a breath of shade, the type has its own shadow
    a = (np.linspace(0, 1, h) ** 1.6 * peak).astype(np.float32)
    arr = np.zeros((h, C.W, 4), np.float32)
    arr[..., 3] = a[:, None]
    return arr


def english_only(text):
    """"PHOTOS · 张照片" -> "PHOTOS": the parts of a bilingual label with no Chinese ("" when none is left)."""
    parts = [x.strip() for x in re.split(r"\s*[·•/／|｜]\s*", str(text or "")) if x.strip()]
    return " · ".join(x for x in parts if not re.search(r"[\u3400-\u9fff]", x))


def make_label(C, text):
    """Rounded dark tag with an accent tick, bottom-left of the picture. Cinema look: no box - small letter-spaced
    type over a thin accent rule, on a soft shadow (a documentary place caption). English only on YouTube (C.SUBS)."""
    if hasattr(C, "shown"):
        text = C.shown(text)
    if getattr(C, "cinema", False):
        size = max(12, C.b(34))
        f = font_for(text, size, "sans", "cjk")
        tr = 0.14 if not has_cjk_text(text) else 0.08
        txt = text.upper() if not has_cjk_text(text) else text
        w = int(sum(_D.textlength(ch, font=f) for ch in txt) + size * tr * len(txt)) + C.b(8)
        pad = C.b(14)
        lay = layer(w + 2 * pad, size * 2 + 2 * pad)
        d = ImageDraw.Draw(lay)
        d.line((pad, pad, pad + C.b(56), pad), fill=C.GOLD + (235,), width=max(1, C.b(2)))
        spaced(d, (pad, pad + C.b(16)), txt, f, (246, 242, 234, 255), tr)
        return to_arr(soft_shadow(lay, radius=max(2, C.b(8)), alpha=0.75))
    f = font_for(text, C.b(38), "sans", "cjk")
    tw = int(_D.textlength(text, font=f))
    h, pad = C.b(74), C.b(30)
    lay = layer(tw + 2 * pad, h)
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((0, 0, tw + 2 * pad - 1, h - 1), C.b(14), fill=(18, 14, 10, 185))
    d.rectangle((0, int(h * 0.22), C.b(5), int(h * 0.78)), fill=C.GOLD + (255,))
    d.text((pad + C.b(2), h / 2), text, font=f, fill=(242, 234, 220, 255), anchor="lm")
    return to_arr(lay)


def make_tag(C, txt):
    f = font_for(txt, C.b(40), "sans-bold", "cjk-bold")
    tw = int(_D.textlength(txt, font=f))
    h, pad = C.b(76), C.b(30)
    lay = layer(tw + 2 * pad, h)
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((0, 0, tw + 2 * pad - 1, h - 1), C.b(16), fill=(20, 14, 10, 200))
    d.text((pad, h / 2), txt, font=f, fill=C.GOLD + (255,), anchor="lm")
    return to_arr(lay)


def _fit(text, role, size, maxw):
    f = font_for(text, size, role, "cjk")
    while size > 10 and _D.textlength(text, font=f) > maxw:
        size -= 1
        f = font_for(text, size, role, "cjk")
    return f


class Header:
    """Section names (current one highlighted) + per-section progress bars + bilingual title.
    Portrait: names + bars on top, title centred below. Landscape: title left, sections right."""

    def __init__(self, C):
        self.C = C
        hs = C.HS
        n = len(C.SECTIONS)
        self.oy = C.HDR_Y0
        x0, x1 = max(C.t(70), C.SAFE[0]), min(C.W - C.t(70), C.SAFE[2])
        self.tx0, self.tx1 = x0, x1
        self.wide = not C.portrait
        self.g = max(4, C.t(14))
        if self.wide:
            hc = C.HDR - self.oy
            self.title_w = self._title_w(hc)
            self.x0 = max(x0 + self.title_w + int(0.05 * C.W), int(x0 + (x1 - x0) * 0.42))
            self.sw = (x1 - self.x0 - self.g * (n - 1)) / n
            self.bar_y = self.oy + int(0.36 * hc)
            self.bar_h = max(3, int(0.04 * hc))
        else:
            self.x0 = x0
            self.sw = (x1 - self.x0 - self.g * (n - 1)) / n
            self.bar_y = self.oy + int(56 * hs)
            self.bar_h = max(3, int(7 * hs))
        self.layers = [self._make(k) for k in range(n)]

    def _title_fonts(self, hc):
        C = self.C
        fz = font_for(C.HEAD_MAIN, 0.30 * hc, "cjk-serif", "cjk-serif") if C.HEAD_MAIN else None
        fe = font_for(C.HEAD_SUB, 0.15 * hc, "serif-italic", "cjk") if C.HEAD_SUB else None
        return fz, fe

    def _title_w(self, hc):
        fz, fe = self._title_fonts(hc)
        w = max([_D.textlength(self.C.HEAD_MAIN, font=fz) if fz else 0,
                 _D.textlength(self.C.HEAD_SUB, font=fe) if fe else 0])
        return int(min(w, (self.tx1 - self.tx0) * 0.5))

    def _make(self, cur):
        C, hs, oy = self.C, self.C.HS, self.oy
        lay = layer(C.W, C.HDR)
        d = ImageDraw.Draw(lay)
        if self.wide:
            hc = C.HDR - oy
            for k, name in enumerate(C.HEAD_SECTIONS):
                col = C.GOLD if k == cur else (150, 140, 125) if k < cur else (95, 90, 82)
                fl = _fit(name, "cjk", max(14, 0.17 * hc), self.sw)
                d.text((self.x0 + k * (self.sw + self.g), self.bar_y + self.bar_h + int(0.08 * hc)), name, font=fl,
                       fill=col + (255,))
            fz, fe = self._title_fonts(hc)
            mw = self.title_w
            y = oy + int(0.22 * hc)
            if fz:
                fz = _fit(C.HEAD_MAIN, "cjk-serif", fz.size, mw)
                d.text((self.tx0, y), C.HEAD_MAIN, font=fz, fill=C.pal["ink"] + (255,))
                y = d.textbbox((self.tx0, y), C.HEAD_MAIN, font=fz)[3] + int(0.08 * hc)
            if fe:
                fe = _fit(C.HEAD_SUB, "serif-italic", fe.size, mw) if not has_cjk_text(C.HEAD_SUB) else fe
                d.text((self.tx0, y), C.HEAD_SUB, font=fe, fill=(190, 172, 140, 255))
            return to_arr(lay)
        size = max(14, 28 * hs) if C.prof is None else max(28 * hs, 0.017 * C.H)   # platform: readable on a phone
        extra = 0 if C.prof is None else max(0.0, size - 28 * hs) * 1.2              # push the title below them
        for k, name in enumerate(C.HEAD_SECTIONS):
            col = C.GOLD if k == cur else (150, 140, 125) if k < cur else (95, 90, 82)
            fl = _fit(name, "cjk", size, self.sw)
            d.text((self.x0 + k * (self.sw + self.g), oy + int(74 * hs)), name, font=fl, fill=col + (255,))
        y = oy + int(118 * hs + extra)
        if C.HEAD_MAIN:
            ft = _fit(C.HEAD_MAIN, "cjk-serif", 80 * hs - extra * 0.6, self.tx1 - self.tx0)
            d.text((C.W / 2, y), C.HEAD_MAIN, font=ft, fill=C.pal["ink"] + (255,), anchor="mt")
            y = d.textbbox((C.W / 2, y), C.HEAD_MAIN, font=ft, anchor="mt")[3] + int(16 * hs)
        if C.HEAD_SUB:
            fe = font_for(C.HEAD_SUB, max(12, 34 * hs), "serif-italic", "cjk")
            d.text((C.W / 2, min(y, C.HDR - int(46 * hs))), C.HEAD_SUB, font=fe, fill=(190, 172, 140, 255), anchor="mt")
        return to_arr(lay)

    def draw(self, frame, sec, gt, sec_bounds):
        from .util import paste_rgba
        paste_rgba(frame, self.layers[sec], 0, 0)
        y0, y1 = self.bar_y, self.bar_y + self.bar_h
        for j in range(len(self.C.SECTIONS)):
            sx = int(self.x0 + j * (self.sw + self.g))
            frame[y0:y1, sx:int(sx + self.sw)] = (70, 64, 56)
            if j < sec:
                fill = 1.0
            elif j == sec:
                fill = (gt - sec_bounds[j]) / max(1e-6, sec_bounds[j + 1] - sec_bounds[j])
            else:
                fill = 0
            if fill > 0:
                frame[y0:y1, sx:sx + int(self.sw * min(fill, 1))] = self.C.GOLD


def make_chapter(C, s):
    """Full-box chapter card: number, accent rule, 中文 + English section names over a dark band. Cinema look: no
    band - a small spaced number, a short rule and the name in the serif, centred, on a soft shadow."""
    W, H = C.BOX_W, C.BOX_H
    if getattr(C, "cinema", False):
        return _chapter_cinema(C, s)
    lay = layer(W, H)
    d = ImageDraw.Draw(lay)
    d.rectangle((0, 0, W, H), fill=(8, 6, 4, 120))
    bh = min(H, C.b(560))
    band = Image.new("L", (W, bh), 0)
    bd = ImageDraw.Draw(band)
    for y in range(bh):
        bd.line((0, y, W, y), fill=int(150 * math.sin(math.pi * y / bh)))
    lay.paste(Image.new("RGBA", (W, bh), (8, 6, 4, 255)), (0, H // 2 - bh // 2), band)
    d = ImageDraw.Draw(lay)
    name, name_en = C.SECTIONS[s], C.SECTIONS_EN[s] if s < len(C.SECTIONS_EN) else ""
    if getattr(C, "EN_LEAD", False) and name_en:          # English narration: the English name leads
        name, name_en = name_en, name
    if getattr(C, "SUBS", "both") == "en" and re.search(r"[\u4e00-\u9fff]", name_en or ""):
        name_en = ""                                       # English only (YouTube): no Chinese chapter name
    fn = font("serif-italic", C.b(120))
    fz = _fit(name, "cjk-serif", C.b(120), min(W * 0.9, (C.SAFE[2] - C.SAFE[0]) * 0.92))
    fe = font_for(name_en, C.b(54), "serif-italic", "cjk")
    num = f"{s:02d}"
    cy = H // 2
    d.text(((W - d.textlength(num, font=fn)) / 2, cy - C.b(270)), num, font=fn, fill=C.GOLD + (255,))
    d.line((W / 2 - C.b(90), cy - C.b(115), W / 2 + C.b(90), cy - C.b(115)), fill=C.GOLD + (255,), width=max(1, C.b(3)))
    d.text(((W - d.textlength(name, font=fz)) / 2, cy - C.b(90)), name, font=fz, fill=(250, 244, 232, 255))
    if name_en:
        d.text(((W - d.textlength(name_en, font=fe)) / 2, cy + C.b(60)), name_en, font=fe, fill=(214, 198, 168, 255))
    return to_arr(lay)


def _chapter_cinema(C, s):
    W, H = C.BOX_W, C.BOX_H
    lay = layer(W, H)
    d = ImageDraw.Draw(lay)
    name, name_en = C.SECTIONS[s], C.SECTIONS_EN[s] if s < len(C.SECTIONS_EN) else ""
    if getattr(C, "EN_LEAD", False) and name_en:
        name, name_en = name_en, name
    if getattr(C, "SUBS", "both") == "en" and re.search(r"[\u4e00-\u9fff]", name_en or ""):
        name_en = ""                                       # English only (YouTube): no Chinese chapter name
    maxw = min(W * 0.8, (C.SAFE[2] - C.SAFE[0]) * 0.86)
    fz = _fit(name, "cjk-serif", C.b(84), maxw)
    fn = font("sans", C.b(28))
    fe = font_for(name_en, C.b(36), "serif-italic", "cjk")
    cy = H // 2
    spaced(d, (W / 2, cy - C.b(130)), f"{s:02d}", fn, C.GOLD + (255,), 0.4, anchor="ma")
    d.line((W / 2 - C.b(40), cy - C.b(78), W / 2 + C.b(40), cy - C.b(78)), fill=C.GOLD + (220,), width=max(1, C.b(2)))
    d.text((W / 2, cy - C.b(50)), name, font=fz, fill=C.pal["ink"] + (255,), anchor="ma")
    if name_en:
        d.text((W / 2, cy + C.b(70)), name_en, font=fe, fill=(222, 214, 198, 255), anchor="ma")
    return to_arr(soft_shadow(lay, radius=max(4, C.b(14)), alpha=0.8))


def make_title_card(C):
    """Cinema look: the film's title over the opening shot (the header no longer carries it) - the lead title in the
    serif, generously spaced, the other language small and letter-spaced under a short rule."""
    W, H = C.BOX_W, C.BOX_H
    main, sub = C.HEAD_MAIN, C.HEAD_SUB
    if not (main or sub):
        return None
    lay = layer(W, H)
    maxw = min(W * 0.84, (C.SAFE[2] - C.SAFE[0]) * 0.9)
    cy = int(H * 0.46)
    from PIL import ImageFilter               # a breath of shade behind the title (busy skylines stay readable)
    shade = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shade).ellipse((W * 0.12, cy - H * 0.2, W * 0.88, cy + H * 0.16), fill=70)
    lay.putalpha(shade.filter(ImageFilter.GaussianBlur(max(8, H // 10))))
    d = ImageDraw.Draw(lay)
    if sub and getattr(C, "EN_LEAD", False) and has_cjk_text(sub) and not has_cjk_text(main or ""):
        sub = ""                  # an English film (YouTube) opens on English only
    if main:
        cj = has_cjk_text(main)
        size = C.b(92 if cj else 80)
        fm = font_for(main, size, "cjk-serif", "cjk-serif")
        lines = [main]
        if _D.textlength(main, font=fm) > W * 0.62:          # a long title breaks after its colon / dash
            for sep in (": ", "：", " — ", " - ", "｜", " | "):
                if sep in main:
                    a, b = main.split(sep, 1)
                    lines = [a.strip() + (sep.strip() if sep.strip() in (":", "：") else ""), b.strip()]
                    break
        fm = font_for(main, size, "cjk-serif", "cjk-serif")
        while size > 20 and max(_D.textlength(ln, font=fm) for ln in lines) > maxw:
            size -= 2
            fm = font_for(main, size, "cjk-serif", "cjk-serif")
        lh = int(fm.size * 1.28)
        y = cy - lh * len(lines)
        for ln in lines:
            if cj:
                spaced(d, (W / 2, y), ln, fm, C.pal["ink"] + (255,), 0.12, anchor="ma")
            else:
                d.text((W / 2, y), ln, font=fm, fill=C.pal["ink"] + (255,), anchor="ma")
            y += lh
    if sub:
        d.line((W / 2 - C.b(36), cy + C.b(34), W / 2 + C.b(36), cy + C.b(34)), fill=C.GOLD + (220,), width=max(1, C.b(2)))
        fs = font_for(sub, C.b(30), "sans", "cjk")
        txt = sub if has_cjk_text(sub) else sub.upper()
        size = C.b(30)
        while size > 12 and _D.textlength(txt, font=fs) * 1.25 > maxw:
            size -= 1
            fs = font_for(sub, size, "sans", "cjk")
        spaced(d, (W / 2, cy + C.b(58)), txt, fs, (232, 226, 214, 255), 0.18 if not has_cjk_text(sub) else 0.1,
               anchor="ma")
    return to_arr(soft_shadow(lay, radius=max(4, C.b(16)), alpha=0.85))
