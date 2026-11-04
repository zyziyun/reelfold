"""Story covers that carry the video's own facts: thermal receipt, magazine, inside / outside, narrator sticker.

Pure PIL. Each style takes images (PIL or path) and a text dict and returns an RGB image of ``size``.
photo-story's ``cover.py`` picks one with ``COVER["style"]``; the same images make in-video design cards
(``storyfx.design_card``).

    from vstudio import cover_styles as CS
    CS.receipt(photo, dict(title="Building my own AI toy", head=["SHOP", "RESEARCH · RECEIPT"],
               rows=[("Panda x1", "¥340"), ("Chip", "ESP32")], total=("TOTAL", "build my own")), (1080, 1920))
    CS.magazine(photo, dict(masthead="YIWU", issue="AI TOY ISSUE", lines=[("ESP32", "hidden in the plush")],
                title="...", subtitle="..."), (1080, 1920))
    CS.inside_outside(outside_img, inside_img, dict(labels=("OUTSIDE", "INSIDE"), line1="...", line2="..."), size)
    CS.narrator_sticker(face_cutout_rgba, photo, dict(title=("Building my", "own AI toy"), subtitle="..."), size)

Taste notes: the receipt prints the photo dithered in blue-black like a thermal camera, rows are the video's
real numbers; inside / outside works when the video opens something up (a teardown, a before / after);
the narrator sticker puts the creator's face on the cover (pick a frame with the mouth closed).
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .config import font

YELLOW = (255, 214, 120)
INK = (34, 46, 92)


def _is_latin(s):
    return all(ord(c) < 0x2E80 for c in str(s))


def _f(role, size):
    return ImageFont.truetype(font(role), size)


def _title_font(text, size):
    return _f("display-latin" if _is_latin(text) else "cjk-serif-bold", size)


def fit(image, w, h, focus=(0.5, 0.5)):
    """Cover-crop to (w, h) around ``focus`` (fractions)."""
    im = (Image.open(image) if isinstance(image, str) else image).convert("RGB")
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x = int(np.clip(focus[0] * im.width - w / 2, 0, im.width - w))
    y = int(np.clip(focus[1] * im.height - h / 2, 0, im.height - h))
    return im.crop((x, y, x + w, y + h))


def _center(d, cx, y, s, f, fill=(255, 255, 255), shadow=True):
    x = cx - d.textlength(s, font=f) / 2
    if shadow:
        d.text((x + 2, y + 4), s, font=f, fill=(0, 0, 0, 150))
    d.text((x, y), s, font=f, fill=fill)


def paste_rot(base, im, cx, cy, angle, shadow=0.55):
    im = im.convert("RGBA").rotate(angle, resample=Image.BICUBIC, expand=True)
    sh = Image.new("L", base.size, 0)
    sh.paste(im.getchannel("A"), (int(cx - im.width / 2 + 10), int(cy - im.height / 2 + 18)))
    base.paste((0, 0, 0), (0, 0), sh.filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * shadow)))
    base.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)
    return base


def thermal(image, w, h, focus=(0.5, 0.5), ink=INK, paper=(252, 251, 247)):
    """A photo as a thermal print: grayscale, autocontrast, Floyd-Steinberg dither, tinted ink."""
    pic = ImageOps.autocontrast(ImageOps.grayscale(fit(image, w, h, focus)), cutoff=2)
    pic = pic.convert("1", dither=Image.FLOYDSTEINBERG)
    out = Image.new("RGB", (w, h), paper)
    out.paste(ink, (0, 0), ImageOps.invert(pic.convert("L")))
    return out


def receipt(photo, cfg, size=(1080, 1920), focus=(0.5, 0.3)):
    """A torn thermal receipt on a warm ground: header lines, the photo printed, item rows, a total, a barcode.
    cfg: title, head=[shop, subtitle], stamp (date / number line), rows=[(item, value)], total=(label, value)."""
    W, H = size
    k = W / 1080
    q = lambda v: int(round(v * k))
    bg = Image.new("RGB", (W, H), (236, 214, 196))
    yy = np.linspace(0, 1, H)[:, None, None]
    bg = Image.fromarray((np.asarray(bg, np.float32) * (1.02 - 0.18 * yy)).clip(0, 255).astype(np.uint8))
    rw, rh = q(780), q(1640)
    rc = Image.new("RGB", (rw, rh), (252, 251, 247))
    d = ImageDraw.Draw(rc)
    head = list(cfg.get("head") or [])
    y = q(40)
    for i, s in enumerate(head + [cfg.get("stamp", "")]):
        if not s:
            continue
        fs = q((44 if not _is_latin(s) else 34) if i == 0 else (34 if not _is_latin(s) else 28)) if i < len(head) else q(26)
        f = _f("mono", fs) if i >= len(head) else _f("cjk-bold", fs)
        d.text((rw / 2 - f.getlength(s) / 2, y), s, font=f, fill=INK)
        y += fs + q(18)
    rule = "-" * 40
    d.text((q(40), y), rule, font=_f("mono", q(26)), fill=INK)
    y += q(44)
    rc.paste(thermal(photo, q(660), q(560), focus), (q(60), y))
    y += q(590)
    for a, b in cfg.get("rows", []):
        d.text((q(60), y), a, font=_f("cjk-bold", q(38)), fill=INK)
        fb = _f("mono", q(38)) if _is_latin(b) else _f("cjk-bold", q(38))
        d.text((rw - q(60) - fb.getlength(b), y + 2), b, font=fb, fill=INK)
        y += q(58)
    d.text((q(40), y), rule, font=_f("mono", q(26)), fill=INK)
    y += q(46)
    if cfg.get("total"):
        lab, val = cfg["total"]
        fb = _f("cjk-bold", q(48))
        d.text((q(60), y), lab, font=fb, fill=INK)
        d.text((rw - q(60) - fb.getlength(val), y), val, font=fb, fill=INK)
        y += q(92)
    rng = np.random.default_rng(7)
    x = q(90)
    while x < rw - q(90):
        bw = int(rng.integers(2, 9))
        d.rectangle((x, y, x + bw, y + q(90)), fill=INK)
        x += bw + int(rng.integers(3, 9))
    m = Image.new("L", (rw, rh), 255)
    pts = [(0, rh)] + [(i, rh - q(18) - (q(14) if (i // q(20)) % 2 else 0)) for i in range(0, rw + q(20), q(20))] + [(rw, rh)]
    ImageDraw.Draw(m).polygon(pts, fill=0)
    card = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
    card.paste(rc, (0, 0), m)
    paste_rot(bg, card, W / 2 + q(20), q(980), -3)
    title = cfg.get("title", "")
    if title:
        _center(ImageDraw.Draw(bg, "RGBA"), W / 2, q(50), title, _title_font(title, q(92 if not _is_latin(title) else 104)),
                fill=(40, 30, 26), shadow=False)
    return bg


def magazine(photo, cfg, size=(1080, 1920), focus=(0.5, 0.42)):
    """Full-bleed photo, huge serif masthead, an issue line, accent cover lines, title at the foot.
    cfg: masthead, issue, lines=[(big, small)], title, subtitle."""
    W, H = size
    k = W / 1080
    q = lambda v: int(round(v * k))
    arr = np.asarray(fit(photo, W, H, focus), np.float32)
    yy = np.linspace(0, 1, H)[:, None, None]
    arr = arr * (1 - 0.55 * np.clip((0.22 - yy) / 0.22, 0, 1)) * (1 - 0.6 * np.clip((yy - 0.62) / 0.38, 0, 1))
    im = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im, "RGBA")
    mast = cfg.get("masthead", "")
    fm = _f("display-latin", q(330))
    d.text((W / 2 - fm.getlength(mast) / 2, -q(30)), mast, font=fm, fill=(250, 246, 238))
    if cfg.get("issue"):
        d.text((q(60), q(330)), cfg["issue"], font=_f("mono", q(28)), fill=YELLOW)
    y = q(1080)
    for big, small in cfg.get("lines", []):
        d.text((q(60), y), big, font=_f("cjk-bold", q(54)), fill=YELLOW)
        d.text((q(60), y + q(66)), small, font=_f("cjk-bold", q(34)), fill=(245, 240, 230))
        y += q(130)
    t, s = cfg.get("title", ""), cfg.get("subtitle", "")
    if t:
        _center(d, W / 2 + q(160), q(1600), t, _title_font(t, q(76 if not _is_latin(t) else 86)))
    if s:
        _center(d, W / 2 + q(160), q(1700), s, _title_font(s, q(46 if not _is_latin(s) else 56)), fill=(240, 232, 214))
    return im


def inside_outside(outside, inside, cfg, size=(1080, 1920), focus_out=(0.5, 0.32), focus_in=(0.5, 0.5)):
    """A diagonal cut: the cute outside top-left, what is inside bottom-right, a label on each side, a line under.
    cfg: labels=(outside, inside), line1, line2."""
    W, H = size
    k = W / 1080
    q = lambda v: int(round(v * k))
    a, b = fit(outside, W, H, focus_out), fit(inside, W, H, focus_in)
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon([(0, 0), (W, 0), (W, int(H * 0.40)), (0, int(H * 0.62))], fill=255)
    im = Image.composite(a, b, m)
    d = ImageDraw.Draw(im, "RGBA")
    d.line([(0, int(H * 0.62)), (W, int(H * 0.40))], fill=(255, 255, 255), width=q(14))
    lo, li = cfg.get("labels", ("外面", "里面"))
    lf = _f("cjk-bold", q(120 if not _is_latin(lo) else 92))
    for s, x, y in ((lo, q(70), q(120)), (li, None, H * 0.62 + q(60))):
        tw = lf.getlength(s)
        x = W - q(70) - tw if x is None else x
        d.rounded_rectangle((x - q(20), y - q(6), x + tw + q(20), y + q(150)), q(26), fill=(12, 10, 8, 170))
        d.text((x, y), s, font=lf, fill=YELLOW)
    d.rectangle((0, q(1500), W, q(1800)), fill=(10, 8, 6, 165))
    for s, y, base, sub in ((cfg.get("line1", ""), q(1530), 78, False), (cfg.get("line2", ""), q(1650), 52, True)):
        if s:
            _center(d, W / 2, y, s, _title_font(s, q(base if not _is_latin(s) else base + 14)),
                    fill=(240, 232, 214) if sub else (255, 255, 255))
    return im


def outline(rgba, px=31):
    """A white sticker outline around an RGBA cutout."""
    import cv2
    al = np.asarray(rgba.getchannel("A"))
    ring = cv2.dilate((al > 128).astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (px, px)))
    st = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
    st.putalpha(Image.fromarray(ring).filter(ImageFilter.GaussianBlur(1.5)))
    st.alpha_composite(rgba)
    return st


def narrator_sticker(cutout, photo, cfg, size=(1080, 1920), focus=(0.5, 0.38), ground=(255, 220, 120)):
    """The creator as a cutout sticker next to a framed photo of the subject, on a bright ground.
    cutout: RGBA head-and-shoulders (outline added here). cfg: title=(line1, line2), subtitle."""
    W, H = size
    k = W / 1080
    q = lambda v: int(round(v * k))
    bg = Image.new("RGB", (W, H), ground)
    yy = np.linspace(0, 1, H)[:, None, None]
    bg = Image.fromarray((np.asarray(bg, np.float32) * (1.0 - 0.12 * yy)).clip(0, 255).astype(np.uint8))
    frame = Image.new("RGB", (q(520), q(620)), (255, 255, 255))
    frame.paste(fit(photo, q(480), q(580), focus), (q(20), q(20)))
    paste_rot(bg, frame, q(790), q(720), 7)
    st = outline(cutout)
    s = q(830) / st.width
    st = st.resize((int(st.width * s), int(st.height * s)), Image.LANCZOS)
    paste_rot(bg, st, q(360), q(1180), -3)
    d = ImageDraw.Draw(bg, "RGBA")
    l1, l2 = (list(cfg.get("title", ("", ""))) + ["", ""])[:2]
    lat = _is_latin(l1 + l2)
    d.text((q(80), q(140)), l1, font=_f("cjk-bold", q(104 if lat else 120)), fill=(30, 24, 20))
    d.text((q(80), q(280)), l2, font=_f("cjk-bold", q(118 if lat else 150)), fill=(30, 24, 20))
    if cfg.get("subtitle"):
        d.rounded_rectangle((q(70), q(1650), q(1010), q(1800)), q(30), fill=(30, 24, 20))
        _center(d, W / 2, q(1680), cfg["subtitle"], _f("cjk-bold", q(64)), fill=ground, shadow=False)
    return bg


def cutout_from_video(video, at, crop=(60, 380, 960, 1320)):
    """One frame of a talking-head recording -> RGBA head-and-shoulders cutout (MediaPipe selfie matte)."""
    import subprocess
    import tempfile
    import cv2
    from . import matte as M
    with tempfile.TemporaryDirectory() as td:
        p = f"{td}/f.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at}", "-i", video, "-frames:v", "1", p], check=True)
        bgr = cv2.imread(p)
    h, w = bgr.shape[:2]
    a = M.mediapipe_alpha(cv2.resize(bgr, (w // 2, h // 2)))
    a = np.clip((cv2.resize(a.astype(np.float32), (w, h)) - 0.12) / 0.88, 0, 1)
    im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    im.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    x, y, cw, ch = crop
    return im.crop((x, y, x + cw, y + ch))


STYLES = ("receipt", "magazine", "inside-outside", "narrator-sticker")
