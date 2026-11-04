"""Story-vlog overlays: the creator's face as a moving card or cutout sticker, big text, design cards.

Pure functions on PIL / numpy, no photo-story ``Ctx``. The photo-story passes ``photostory/facecam.py`` and
``photostory/textfx.py`` drive them over a rendered film; anything else can call them directly.

    from vstudio import storyfx as S
    card = S.face_card(rgb, "polaroid")                     # RGBA card from one face frame (circle | round | polaroid)
    cut = S.Sticker(); rgba = cut(bgr)                       # head-and-shoulders cutout with a white outline (EMA matte)
    x, y = S.glide([(0, 0), (500, 900)], t, dur)             # hold, then glide between slots, evenly through a unit
    im = S.text_card("50 个起批", "num", (1080, 1920), font_path)
    im = S.design_card(cover_png, (1080, 1920), bottom=1380, angle=-2.5)

What the defaults encode (each one fixed a real problem in a shipped video):
- a face crop has to include the chin; a tight square cut the mouth off.
- a cutout sticker needs the shoulders: a floating head reads wrong. The bottom edge fades instead of a hard cut.
- the matte is smoothed over time (EMA), or the outline shimmers.
- a glide faster than ~2.4 s across the frame trips the calm flicker check (a moving band).
- big text and design cards fade over 0.3-0.4 s; snap-ins flicker on bright frames.
- a design card stops above the caption box so the subtitle under it stays readable.
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

D = 290                       # face card size (px on a 1080-wide canvas)
GLIDE = 2.4                   # seconds for a glide between slots
STYLES = ("circle", "round", "polaroid", "sticker")


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def ease_out_back(u, k=1.6):
    u = min(max(u, 0.0), 1.0) - 1
    return 1 + (k + 1) * u ** 3 + k * u ** 2


def warm(rgb, sat=0.9, gain=(1.03, 1.0, 0.95)):
    """A touch less saturated and warmer: the face matches a warm film grade."""
    f = np.asarray(rgb, np.float32)
    g = f.mean(2, keepdims=True)
    return np.clip((g + (f - g) * sat) * np.array(gain, np.float32), 0, 255)


def _rrect(size, inset, rad):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    dx = np.maximum(np.maximum(inset + rad - xx, xx - (size - 1 - inset - rad)), 0)
    dy = np.maximum(np.maximum(inset + rad - yy, yy - (size - 1 - inset - rad)), 0)
    return np.clip(rad - np.sqrt(dx ** 2 + dy ** 2) + 0.5, 0, 1)


def face_card(rgb, style="circle", size=D, ring=6):
    """One face frame (RGB, square, ``size`` px) -> float32 RGBA card. circle and round get a white ring;
    polaroid gets a cream frame with a deeper bottom margin."""
    rgb = warm(rgb)
    if style == "polaroid":
        m, mb = 14, 46
        card = np.zeros((size + m + mb, size + 2 * m, 4), np.float32)
        card[..., :3] = (248, 246, 240)
        card[..., 3] = 255
        card[m:m + size, m:m + size, :3] = rgb
        return card
    if style == "round":
        face, outer = _rrect(size, ring, 48), _rrect(size, 0, 48)
    else:
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        r = np.sqrt((xx - size / 2 + 0.5) ** 2 + (yy - size / 2 + 0.5) ** 2)
        face, outer = np.clip(size / 2 - ring - r + 0.5, 0, 1), np.clip(size / 2 - r + 0.5, 0, 1)
    card = np.zeros((size, size, 4), np.float32)
    card[..., :3] = rgb * face[..., None] + 255 * (1 - face[..., None])
    card[..., 3] = outer * 255
    return card


class Sticker:
    """Head-and-shoulders cutout, frame after frame: MediaPipe selfie matte, smoothed over time, white outline,
    soft bottom fade. Call with a BGR frame already cropped/scaled to the sticker size."""

    def __init__(self, ema=0.45, outline=21, fade_from=0.82):
        self.prev, self.ema, self.outline, self.fade_from = None, ema, outline, fade_from

    def __call__(self, bgr):
        import cv2
        from . import matte as M
        h, w = bgr.shape[:2]
        a = M.mediapipe_alpha(bgr).astype(np.float32)
        a = a if self.prev is None else (1 - self.ema) * a + self.ema * self.prev
        self.prev = a
        fade = np.ones((h, 1), np.float32)
        n0 = int(h * self.fade_from)
        fade[n0:, 0] = np.linspace(1.0, 0.0, h - n0) ** 1.5
        a = np.clip((a - 0.12) / 0.88, 0, 1) * fade
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (self.outline, self.outline))
        ring = cv2.GaussianBlur(cv2.dilate((a > 0.5).astype(np.float32), k), (0, 0), 1.5) * fade
        card = np.zeros((h, w, 4), np.float32)
        card[..., :3] = warm(bgr[..., ::-1]) * a[..., None] + 252 * (1 - a[..., None])
        card[..., 3] = np.maximum(a, ring) * 255
        return card


def glide(points, t, dur, glide_s=GLIDE):
    """Position at local time ``t`` of a unit lasting ``dur``: hold each slot, glide to the next one at even
    points through the unit (n slots -> n-1 glides)."""
    x, y = points[0]
    legs = len(points) - 1
    for j in range(legs):
        u = ease((t - (dur * (j + 1) / (legs + 1) - glide_s / 2)) / glide_s)
        x, y = x + (points[j + 1][0] - x) * u, y + (points[j + 1][1] - y) * u
    return x, y


def pop(t, rem, grow=None, dur=None):
    """(scale, alpha) for a card that pops in, optionally grows slowly (``grow`` = (start, end)), and fades out."""
    s = ease_out_back(t / 0.45) if t < 0.45 else 1.0
    s *= 0.85 + 0.15 * min(1.0, rem / 0.35)
    if grow and dur:
        s *= grow[0] + (grow[1] - grow[0]) * ease(t / max(dur, 1e-3))
    return s, min(1.0, t / 0.25) * min(1.0, rem / 0.35)


def place(canvas, layer, cx, cy, scale, angle):
    """Composite float32 RGBA ``layer`` onto float32 RGBA ``canvas`` centred at (cx, cy), scaled and rotated."""
    import cv2
    h, w = layer.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    M[0, 2] += cx - w / 2
    M[1, 2] += cy - h / 2
    warped = cv2.warpAffine(layer, M, (canvas.shape[1], canvas.shape[0]), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    a = warped[..., 3:4] / 255.0
    canvas[..., :3] = warped[..., :3] * a + canvas[..., :3] * (1 - a)
    canvas[..., 3:4] = 255 * (a + canvas[..., 3:4] / 255.0 * (1 - a))
    return canvas


def shadow_of(card, blur=12, strength=0.45):
    import cv2
    sh = np.zeros_like(card)
    sh[..., 3] = cv2.GaussianBlur(card[..., 3], (0, 0), blur) * strength
    return sh


TEXT_STYLES = dict(title=dict(size=92, y=0.20), tag=dict(size=70, y=0.20), num=dict(size=150, y=0.42),
                   end=dict(size=96, y=0.44))


def text_card(text, style, size, font_path, accent=(255, 214, 120)):
    """Full-canvas RGBA PNG with one big line (or two, split on newline) on a soft dark pill.
    style: title | tag (upper third) | num (heavy, accent colour, middle) | end (middle)."""
    st = TEXT_STYLES[style]
    W, H = size
    f = ImageFont.truetype(font_path, st["size"])
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lines = str(text).split("\n")
    boxes = [d.textbbox((0, 0), ln, font=f) for ln in lines]
    lh = int(st["size"] * 1.25)
    tw, th = max(b[2] - b[0] for b in boxes), lh * len(lines)
    cx, cy = W // 2, int(H * st["y"])
    box = (cx - tw // 2 - 48, cy - th // 2 - 28, cx + tw // 2 + 48, cy + th // 2 + 28)
    pill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle(box, radius=36, fill=(12, 10, 8, 120 if style == "num" else 150))
    im.alpha_composite(pill.filter(ImageFilter.GaussianBlur(6)))
    d = ImageDraw.Draw(im)
    fill = accent + (255,) if style == "num" else (250, 246, 238, 255)
    y = cy - th // 2
    for ln, b in zip(lines, boxes):
        d.text((cx - (b[2] - b[0]) // 2 - b[0], y + (lh - (b[3] - b[1])) // 2 - b[1]), ln, font=f, fill=fill)
        y += lh
    return im


def design_card(image, size, bottom, angle=0.0, top=110, radius=28):
    """A full-frame design (a cover style) as an in-video card: scaled to fit between ``top`` and ``bottom``,
    rounded, tilted, soft shadow. Keep ``bottom`` above the caption box."""
    W, H = size
    im = (Image.open(image) if isinstance(image, str) else image).convert("RGBA")
    ch = bottom - top
    im = im.resize((int(im.width * ch / im.height), ch), Image.LANCZOS)
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius, fill=255)
    im.putalpha(m)
    im = im.rotate(angle, resample=Image.BICUBIC, expand=True)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x, y = (W - im.width) // 2, top + (ch - im.height) // 2
    sh = Image.new("L", (W, H), 0)
    sh.paste(im.getchannel("A"), (x + 14, y + 26))
    canvas.paste((0, 0, 0, 255), (0, 0), sh.filter(ImageFilter.GaussianBlur(26)).point(lambda v: int(v * 0.6)))
    canvas.alpha_composite(im, (x, y))
    return canvas


def slots(W, H, cap_top, box, top_safe=200):
    """Named positions (box top-left) for a ``box``-px overlay track: BR sits just above the caption box."""
    return {"BR": (W - box + 110, cap_top - box + 60), "TR": (W - box + 110, top_safe - 90),
            "TL": (-110, top_safe - 90), "ML": (-110, int(H * 0.30))}


def bob(t, amp=4.0, period=3.2):
    return amp * math.sin(2 * math.pi * t / period)
