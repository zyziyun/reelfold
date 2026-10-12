"""Brand -> theme tokens, font faces and measured text fitting, shared by the videos and the stills.

    T = theme(cfg)                         # vstudio.theme preset + the brand's colours (paper / ink / accent / marker)
    faces = stage_fonts(cfg, dst, text)    # copies / subsets fonts into dst -> {"display": (family, file), ...}
    px, lines = fit(text, role_file, (56, 40), width, max_lines, lang)

Fonts: ``brand.fonts.display`` / ``brand.fonts.text`` (any OFL font file: .woff2/.ttf/.otf) for Latin; Chinese text
always uses the engine's Noto Sans SC (vstudio.config.FONTS), subset to the characters on screen. Without brand fonts
the headlines are set in Inter (bundled here, fonts/OFL-Inter.txt) and the small text in Noto Sans SC.

Backdrop (``brand.backdrop``): the films sit the product window on a soft gradient tinted with the accent, never on
black: ``studio`` (light, default: bright, crisp around dark or light UI), ``deep`` (dark teal-black, white type) or
``paper`` (the theme's flat paper colour).
"""
import functools
import os
import re
import shutil
import tempfile

from vstudio import config as VC
from vstudio import theme as TH

COLOR_KEYS = ("paper", "ink", "ink2", "rule", "accent", "accent_ink", "marker", "card", "card_ink")
# a few brand colours read as "red" (the old look she rejected); warn instead of silently shipping them
RED_HUES = ((345, 360), (0, 15))
INTER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Inter-latin-wght.woff2")
INTER_W = 660                 # headline weight when the bundled Inter sets them
BACKDROPS = ("studio", "deep", "paper")


def theme(cfg):
    b = cfg.get("brand") or {}
    layer = {"theme": b.get("theme") or "editorial"}
    layer.update({k: v for k, v in (b.get("colors") or {}).items() if k in COLOR_KEYS and v})
    return TH.resolve(layer)


def is_reddish(hex_color):
    import colorsys
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    deg = hue * 360
    return sat > 0.45 and 0.25 < light < 0.75 and any(lo <= deg <= hi for lo, hi in RED_HUES)


def warnings(cfg):
    T = theme(cfg)
    out = []
    if is_reddish(T["accent"]):
        out.append(f"brand accent {T['accent']} reads as red; the editorial look keeps red out of overlays")
    c = TH.contrast(TH.rgb(T, "ink"), TH.rgb(T, "paper"))
    if c < 7:
        out.append(f"ink {T['ink']} on paper {T['paper']}: contrast {c:.1f} < 7")
    return out


def _engine_font(role):
    """The engine's font for ``role``; when ./install.sh has not fetched it (a fresh checkout, CI) the bundled Inter
    stands in (config.font already warned), so building a project never fails on a missing font file: glyphs Inter
    lacks (Chinese) fall back to the system's fonts in the browser."""
    try:
        return VC.font(role)
    except VC.MissingAsset:
        return INTER


def font_files(cfg, lang):
    """{display, text, text_bold} -> font file paths for ``lang``."""
    f = (cfg.get("brand") or {}).get("fonts") or {}
    if lang == "zh":
        return dict(display=_engine_font("cjk-bold"), text=_engine_font("cjk"), text_bold=_engine_font("cjk-bold"))
    disp = f.get("display") or (INTER if os.path.exists(INTER) else _engine_font("serif"))
    return dict(display=disp, text=f.get("text") or _engine_font("cjk"),
                text_bold=f.get("text_bold") or f.get("text") or _engine_font("cjk-bold"))


def display_weight(cfg, lang, default=560):
    """CSS weight of the headlines (also used when measuring them): the bundled Inter is set semibold-bold."""
    return INTER_W if lang != "zh" and font_files(cfg, lang)["display"] == INTER else default


def _hex(c):
    h = c.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """Colour a -> b by t (0..1), '#RRGGBB'."""
    ra, rb = _hex(a), _hex(b)
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ra, rb))


def rgba(c, alpha):
    r, g, b = _hex(c)
    return f"rgba({r},{g},{b},{alpha})"


def backdrop(cfg):
    """The film's backdrop + type colours from the accent -> {kind, top, bottom, glow, ink, ink2, accent, accent_ink,
    shadow, mark}. ``mark`` = which brand symbol reads on it (on-light / on-dark)."""
    T = theme(cfg)
    kind = (cfg.get("brand") or {}).get("backdrop") or "studio"
    if kind not in BACKDROPS:
        kind = "studio"
    ac = T["accent"]
    if kind == "studio":
        return dict(kind=kind, top=mix("#FFFFFF", ac, 0.05), bottom=mix("#FFFFFF", ac, 0.2), glow=rgba(ac, 0.34),
                    glow2=rgba(mix(ac, "#FFFFFF", 0.3), 0.5), ink=mix("#0B0F0F", ac, 0.1),
                    ink2=mix("#0B0F0F", "#FFFFFF", 0.38), accent=ac, accent_text=mix(ac, "#0B0F0F", 0.42),
                    shadow="8,40,36", mark="on-light")
    if kind == "deep":
        return dict(kind=kind, top=mix("#07090A", ac, 0.1), bottom=mix("#07090A", ac, 0.26), glow=rgba(ac, 0.3),
                    glow2=rgba(ac, 0.18), ink="#F4F7F6", ink2=mix("#F4F7F6", ac, 0.25), accent=ac,
                    accent_text=mix(ac, "#FFFFFF", 0.2), shadow="0,0,0", mark="on-dark")
    return dict(kind=kind, top=T["paper"], bottom=T["paper"], glow="transparent", glow2="transparent", ink=T["ink"],
                ink2=T["ink2"], accent=ac, accent_text=ac, shadow="20,20,20", mark="on-light")


@functools.lru_cache(maxsize=32)
def _pil_path(path):
    """PIL cannot always read .woff2: convert once to a temp .ttf with fontTools."""
    if not path.lower().endswith((".woff2", ".woff")):
        return path
    from fontTools.ttLib import TTFont
    ft = TTFont(path)
    ft.flavor = None
    out = os.path.join(tempfile.gettempdir(), "vstudio-launch-" + os.path.basename(path) + ".ttf")
    ft.save(out)
    return out


@functools.lru_cache(maxsize=256)
def _font(path, px, weight=None):
    """PIL font set up like the browser renders it: variable fonts get the CSS weight and opsz = the font size
    (font-optical-sizing: auto), so measured widths match the page."""
    from PIL import ImageFont
    f = ImageFont.truetype(_pil_path(path), int(px))
    try:
        axes = f.get_variation_axes()
    except Exception:                                 # noqa: BLE001 - a static font has no axes
        axes = []
    if axes:
        vals = [a["default"] for a in axes]
        for i, a in enumerate(axes):
            name = a.get("name")
            name = name.decode() if isinstance(name, bytes) else str(name)
            if name.lower() == "weight" and weight:
                vals[i] = weight
            elif name.lower() == "optical size":
                vals[i] = max(a["minimum"], min(a["maximum"], px))
        f.set_variation_by_axes(vals)
    return f


def measure(text, path, px, weight=None):
    return _font(path, px, weight).getlength(re.sub(r"[【】]", "", text))


def _tokens(text, lang):
    """Breakable units: words (+ their trailing space) for Latin, characters for CJK; 【...】 stays one unit."""
    if lang == "zh":
        out, i = [], 0
        while i < len(text):
            if text[i] == "【":
                j = text.find("】", i)
                j = len(text) - 1 if j < 0 else j
                out.append(text[i:j + 1])
                i = j + 1
            else:
                out.append(text[i])
                i += 1
        # keep closing punctuation with the previous unit
        merged = []
        for t in out:
            if merged and t in "，。、！？；：）」》,.!?;:":
                merged[-1] += t
            else:
                merged.append(t)
        return merged
    return re.findall(r"【[^】]*】\S*\s*|\S+\s*", text)


def wrap(text, path, px, width, lang, weight=None):
    lines, cur = [], ""
    for tok in _tokens(text, lang):
        trial = cur + tok
        if cur and measure(trial.rstrip(), path, px, weight) > width:
            lines.append(cur.rstrip())
            cur = tok.lstrip() if lang != "zh" else tok
        else:
            cur = trial
    if cur.strip():
        lines.append(cur.rstrip())
    return lines


def fit(text, path, px_range, width, max_lines, lang="en", weight=None):
    """Largest font size in px_range (hi, lo) at which ``text`` wraps into <= max_lines within ``width``.
    -> (px, lines). Raises ValueError when even the smallest size needs more lines (shorten the caption)."""
    hi, lo = px_range
    for px in range(int(hi), int(lo) - 1, -2):
        lines = wrap(text, path, px, width, lang, weight)
        if len(lines) <= max_lines and all(measure(ln, path, px, weight) <= width for ln in lines):
            if lang == "zh" and len(lines) > 1:
                # Chinese breaks after its punctuation (说一句，/ 拖一个文件夹。), even a little smaller
                for p2 in range(px, max(int(lo), int(px * 0.8)) - 1, -2):
                    ph = _phrase_lines(text, path, p2, width, max_lines, weight)
                    if ph:
                        return p2, ph
            return px, _balance(lines, text, path, px, width, lang, weight)
    raise ValueError(f"caption too long for {max_lines} line(s) at {lo}px in {width}px: {text!r}")


def _phrase_lines(text, path, px, width, max_lines, weight=None):
    """Chinese text cut only after ，、；：！？ into <= max_lines lines that each fit ``width``, or None."""
    parts = [p for p in re.split(r"(?<=[，、；：！？,;:])", text) if p]
    if len(parts) < 2:
        return None
    lines = []
    for p in parts:
        if lines and measure(lines[-1] + p, path, px, weight) <= width:
            lines[-1] += p
        else:
            lines.append(p)
    if len(lines) < 2 or len(lines) > max_lines or any(measure(ln, path, px, weight) > width for ln in lines):
        return None
    return lines


def _balance(lines, text, path, px, width, lang, weight):
    """Same number of lines, more even lengths (no lonely last word): the narrowest width that still wraps into
    as many lines."""
    n = len(lines)
    if n < 2:
        return lines
    w = measure(text, path, px, weight) / n
    while w < width:
        cand = wrap(text, path, px, w, lang, weight)
        if len(cand) <= n:
            return cand
        w += px * 0.5
    return lines


def stage_fonts(cfg, dst, text, langs):
    """Copy (Latin brand fonts) / subset (CJK) the fonts a project uses into ``dst`` (assets/fonts) ->
    {(lang, role): (css_family, filename)}."""
    os.makedirs(dst, exist_ok=True)
    out = {}
    from vstudio import render as R
    for lang in langs:
        for role, path in font_files(cfg, lang).items():
            fam = f"LK-{lang}-{role}"
            base = os.path.splitext(os.path.basename(path))[0]
            if lang == "zh" or path.lower().endswith((".otf", ".ttf", ".ttc")):
                name = R.subset_font(path, text, os.path.join(dst, f"{lang}-{role}-{base}.woff2"))
            else:
                name = os.path.join(dst, os.path.basename(path))
                if not os.path.exists(name) or os.path.getsize(name) != os.path.getsize(path):
                    shutil.copy2(path, name)
            out[(lang, role)] = (fam, os.path.basename(name))
    return out


def font_css(faces, url_prefix="assets/fonts/"):
    fmt = {".woff2": "woff2", ".woff": "woff", ".otf": "opentype", ".ttf": "truetype"}
    rules = []
    for (lang, role), (fam, fn) in faces.items():
        f = fmt.get(os.path.splitext(fn)[1].lower(), "opentype")
        rules.append(f'@font-face {{ font-family: "{fam}"; src: url("{url_prefix}{fn}") format("{f}"); '
                     f'font-weight: 100 900; font-display: block; }}')
    return "\n".join(rules)


def families(faces, lang, role):
    """CSS font-family list for a role: the language's face first, then the other language's same role."""
    fams = [faces[(lang, role)][0]] if (lang, role) in faces else []
    fams += [fam for (lg, r), (fam, _) in faces.items() if r == role and lg != lang]
    return ", ".join(f'"{f}"' for f in fams) + (", serif" if role == "display" else ", sans-serif")
