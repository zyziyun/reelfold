"""vstudio.cinefx: cinematic multi-effect vertical vlog engine (1080x1920, numpy + ffmpeg), vlog style "cine".

A project file builds a list of Shot objects on a beat grid and a Project config (voiceover,
captions, chapter labels, hook text, sfx). `cinefx.cli(__file__)` then gives the commands:

  python3 project.py stills 3.0 10.5 ...   # single frames -> <work>/stills/
  python3 project.py video [scene idx...]  # parallel render -> <work>/out/video.mp4
  python3 project.py audio                 # voiceover + music bed + sfx -> <work>/out/audio.wav
  python3 project.py final                 # mux + loudnorm -14 + bt709 tags -> <raw>/<out name>

Shots: Clip Photo Opening Triptych Dual Super8 FilmStrip Slides Strip Print EndCard DoubleExp.
Looks: clean night super8 paper bw. Covers: cover_negative / cover_still / cover_strip.
Workflow, rules and effect choice: workflows/vlog/WORKFLOW.md "Cine style"; worked example
workflows/vlog/examples/cine.example.py.
"""
import math
import os
import subprocess
import sys
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

FPS = 30
W, H = 1080, 1920
BEAT = 0.5          # seconds per beat; set by configure() from the music analysis
MUSIC = None
MUSIC_START = 0.0   # music time that lands on timeline 0 (first beat)
ROOT = os.getcwd()  # the project work dir: sdr/, photos_full/, voice/, out/, scenes/, stills/
SDR = os.path.join(ROOT, "sdr")
PHOTOS = os.path.join(ROOT, "photos_full")
RAW = os.path.dirname(ROOT)


def configure(root, music, beat=None, music_start=None, raw=None):
    """Point the engine at a project's work dir (sdr/, photos_full/, voice/) and its music.

    beat / music_start default to the track's analysed grid (vstudio.beats): the period, and the first beat
    so timeline 0 lands on a beat and every B(n) cut sits on the music."""
    global ROOT, SDR, PHOTOS, RAW, MUSIC, BEAT, MUSIC_START
    ROOT = os.path.abspath(root)
    SDR = os.path.join(ROOT, "sdr")
    PHOTOS = os.path.join(ROOT, "photos_full")
    RAW = os.path.abspath(raw) if raw else os.path.dirname(ROOT)
    MUSIC = os.path.expanduser(music) if music else None
    if MUSIC and os.path.exists(MUSIC) and (beat is None or music_start is None):
        from . import beats
        g = beats.analyze(MUSIC)
        beat = g.period if beat is None else beat
        music_start = g.offset if music_start is None else music_start
    BEAT = beat or BEAT
    MUSIC_START = music_start or 0.0
from .config import font as _font


def _role(*roles):
    """First installed font among roles (install.sh fetches them); None keeps imports working without fonts."""
    for r in roles:
        try:
            return _font(r)
        except Exception:
            continue
    return None


F_SERIF = _role("cjk-serif", "cjk")
F_SERIF_B = _role("cjk-serif-bold", "cjk-bold", "cjk-serif", "cjk")
F_MONO = _role("mono", "cjk")
F_HAND = _role("zh-humanist", "cjk-serif", "cjk")


def B(n):
    return n * BEAT


def ease(p):
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def ease_out(p):
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def ease_in(p):
    p = min(max(p, 0.0), 1.0)
    return p ** 3


# ---------------------------------------------------------------- sources
def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip().split(",")
    a, b = out[2].split("/")
    return int(out[0]), int(out[1]), float(a) / float(b)


class Reader:
    """Sequential decoder of one source window, scaled to `size` (cover fit, focus point)."""

    def __init__(self, clip, start, length, size=(W, H), focus=(0.5, 0.5)):
        path = os.path.join(SDR, clip + ".mp4")
        sw, sh, self.fps = probe(path)
        tw, th = size
        s = max(tw / sw, th / sh)
        nw, nh = int(round(sw * s / 2) * 2), int(round(sh * s / 2) * 2)
        nw, nh = max(nw, tw), max(nh, th)
        x = int((nw - tw) * focus[0])
        y = int((nh - th) * focus[1])
        vf = f"scale={nw}:{nh}:flags=lanczos,crop={tw}:{th}:{x}:{y}"
        self.size = size
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", path, "-t",
                                   f"{length + 0.5:.3f}", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                  stdout=subprocess.PIPE)
        self.n = tw * th * 3
        self.idx = -1
        self.frame = np.zeros((th, tw, 3), np.uint8)

    def at(self, ts):
        k = max(0, int(round(ts * self.fps)))
        while self.idx < k:
            buf = self.p.stdout.read(self.n)
            if len(buf) < self.n:
                break
            self.frame = np.frombuffer(buf, np.uint8).reshape(self.size[1], self.size[0], 3)
            self.idx += 1
        return self.frame

    def close(self):
        try:
            self.p.kill()
        except Exception:
            pass


def ramp_time(keys, dur):
    """keys: [(u, rate)] over u in 0..1 -> function local t -> source offset (integrated, smooth between keys)."""
    n = 400
    ts = np.linspace(0, dur, n + 1)
    us = ts / dur
    ku = [k[0] for k in keys]
    kr = [k[1] for k in keys]
    rates = []
    for u in us:
        if u <= ku[0]:
            rates.append(kr[0]); continue
        if u >= ku[-1]:
            rates.append(kr[-1]); continue
        i = max(j for j in range(len(ku)) if ku[j] <= u)
        p = ease((u - ku[i]) / (ku[i + 1] - ku[i]))
        rates.append(kr[i] + (kr[i + 1] - kr[i]) * p)
    rates = np.array(rates)
    cum = np.concatenate([[0], np.cumsum((rates[1:] + rates[:-1]) / 2 * np.diff(ts))])
    return lambda t: float(np.interp(t, ts, cum)), float(cum[-1])


@lru_cache(maxsize=32)
def photo(name, w, h, focus=(0.5, 0.5), over=1.0):
    im = ImageOps.exif_transpose(Image.open(os.path.join(PHOTOS, name + ".jpg"))).convert("RGB")
    tw, th = int(w * over), int(h * over)
    s = max(tw / im.width, th / im.height)
    im = im.resize((max(tw, round(im.width * s)), max(th, round(im.height * s))), Image.LANCZOS)
    x = int((im.width - tw) * focus[0]); y = int((im.height - th) * focus[1])
    return np.asarray(im.crop((x, y, x + tw, y + th)), np.float32)


def kenburns(img, w, h, p, z0=1.0, z1=1.08, dx=0.0, dy=0.0):
    """img (oversized) -> w x h view; zoom z0->z1, pan dx,dy (fractions of spare room)."""
    z = z0 + (z1 - z0) * p
    ih, iw = img.shape[:2]
    cw, ch = iw / z * (w / iw) * (iw / w), ih / z
    cw = iw / z
    cx = iw / 2 + dx * (iw - cw) / 2 * (2 * p - 1)
    cy = ih / 2 + dy * (ih - ch) / 2 * (2 * p - 1)
    M = np.float32([[w / cw, 0, -(cx - cw / 2) * w / cw], [0, h / ch, -(cy - ch / 2) * h / ch]])
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


# ---------------------------------------------------------------- text
@lru_cache(maxsize=256)
def text_img(text, font, size, fill=(255, 255, 255), spacing=0, shadow=True):
    f = ImageFont.truetype(font, size)
    chars = list(text)
    widths = [f.getlength(c) for c in chars]
    tw = int(sum(widths) + spacing * max(0, len(chars) - 1)) + 40
    asc, desc = f.getmetrics()
    th = asc + desc + 40
    im = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 20
    for c, cw in zip(chars, widths):
        d.text((x, 20), c, font=f, fill=fill + (255,))
        x += cw + spacing
    a = np.asarray(im, np.float32)
    if shadow:
        al = a[..., 3]
        sh = cv2.GaussianBlur(al, (0, 0), size * 0.12)
        out = np.zeros_like(a)
        out[..., :3] = a[..., :3]
        sh2 = cv2.GaussianBlur(al, (0, 0), size * 0.45)
        out[..., 3] = np.maximum(al, np.maximum(sh * 0.8, sh2 * 0.45))
        # dark where only shadow
        k = (al / 255.0)[..., None]
        out[..., :3] = a[..., :3] * k
        return out, True
    return a, False


def put_text(frame, text, font, size, cx, cy, alpha=1.0, fill=(255, 255, 255), spacing=0, shadow=True,
             anchor="c"):
    img, premult = text_img(text, font, size, fill, spacing, shadow)
    th, tw = img.shape[:2]
    x0 = int(cx - tw / 2) if anchor == "c" else int(cx - 20)
    y0 = int(cy - th / 2)
    x1, y1 = max(0, x0), max(0, y0)
    x2, y2 = min(W, x0 + tw), min(H, y0 + th)
    if x2 <= x1 or y2 <= y1 or alpha <= 0:
        return frame
    sub = img[y1 - y0:y2 - y0, x1 - x0:x2 - x0]
    a = sub[..., 3:4] / 255.0 * alpha
    if premult:
        frame[y1:y2, x1:x2] = frame[y1:y2, x1:x2] * (1 - a) + sub[..., :3] * alpha
    else:
        frame[y1:y2, x1:x2] = frame[y1:y2, x1:x2] * (1 - a) + sub[..., :3] * a
    return frame


# ---------------------------------------------------------------- look
rng = np.random.default_rng(5)
GRAIN = []
for _ in range(10):
    g = rng.normal(0, 1, (H // 2, W // 2)).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), 0.6)
    GRAIN.append(cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR))
YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = (1 - 0.32 * (((XX - W / 2) / (W * 0.62)) ** 2 + ((YY - H / 2) / (H * 0.62)) ** 2)).clip(0.55, 1)[..., None]
CURVE_X = np.array([0, 0.12, 0.3, 0.5, 0.72, 0.9, 1.0])
CURVE_Y = np.array([0.03, 0.115, 0.29, 0.5, 0.735, 0.885, 0.955])
LUT = np.interp(np.linspace(0, 1, 1024), CURVE_X, CURVE_Y).astype(np.float32)

LOOKS = {
    "clean": dict(sat=0.94, warm=1.0, hal=0.32, grain=2.0, vig=1.0, fade=0.0, streak=0.0),
    "night": dict(sat=0.97, warm=1.0, hal=0.55, grain=2.2, vig=1.0, fade=0.0, streak=0.10),
    "super8": dict(sat=0.78, warm=1.6, hal=0.45, grain=6.0, vig=1.4, fade=0.07, streak=0.0),
    "paper": dict(sat=0.9, warm=1.0, hal=0.2, grain=1.8, vig=0.8, fade=0.0, streak=0.0),
    "bw": dict(sat=0.0, warm=0.0, hal=0.12, grain=3.5, vig=1.25, fade=0.0, streak=0.0),
}


def finish(img, fi, look="clean"):
    L = LOOKS[look]
    x = np.clip(img / 255.0, 0, 1)
    x = LUT[(x * 1023).astype(np.int32)]
    lum = x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    l3 = lum[..., None]
    # split tone: teal shadows, warm highlights
    x = x + (1 - l3) ** 2 * np.array([-0.014, 0.004, 0.020], np.float32) \
        + l3 ** 2 * np.array([0.022, 0.006, -0.022], np.float32) * L["warm"]
    x = l3 + (x - l3) * L["sat"]
    if L["fade"]:
        x = x * (1 - L["fade"]) + L["fade"] * np.array([0.55, 0.47, 0.38], np.float32)
    # halation: red-orange glow around bright points
    small = cv2.resize(lum, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    hi = np.clip((small - 0.68) / 0.3, 0, 1)
    glow = cv2.GaussianBlur(hi, (0, 0), 5) * 0.7 + cv2.GaussianBlur(hi, (0, 0), 14) * 0.5
    glow = cv2.resize(glow, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]
    x = x + glow * np.array([1.0, 0.36, 0.14], np.float32) * L["hal"] * (1 - l3 * 0.6)
    if L["streak"]:
        st = cv2.GaussianBlur(np.clip((small - 0.85) / 0.15, 0, 1), (0, 0), sigmaX=60, sigmaY=0.8)
        st = cv2.resize(st, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]
        x = x + st * np.array([0.35, 0.6, 1.0], np.float32) * L["streak"]
    x = x * (1 - (1 - VIG) * L["vig"])
    blur = cv2.GaussianBlur(x, (0, 0), 1.3)
    x = x + (x - blur) * 0.45                      # mild sharpen before grain
    out = x * 255 + GRAIN[fi % len(GRAIN)][..., None] * L["grain"] * (0.35 + 2.2 * l3 * (1 - l3))
    return out


# ---------------------------------------------------------------- shot helpers
class Shot:
    """A timeline piece [t0, t1) with a draw(frame, t_local, gt) method returning the picture."""
    look = "clean"

    def __init__(self, t0, t1):
        self.t0, self.t1 = t0, t1

    def open(self):
        pass

    def close(self):
        pass


class Clip(Shot):
    def __init__(self, t0, t1, clip, start, speed=1.0, ramp=None, focus=(0.5, 0.5), look="clean",
                 hold=None, freeze_at=None, zoom=(1.0, 1.0), fps_step=None):
        super().__init__(t0, t1)
        self.clip, self.start, self.speed, self.focus, self.look = clip, start, speed, focus, look
        self.zoom, self.fps_step = zoom, fps_step
        dur = t1 - t0
        if ramp:
            self.fn, span = ramp_time(ramp, dur)
        else:
            self.fn, span = (lambda t, s=speed: t * s), dur * speed
        self.freeze_at = freeze_at  # local time after which the picture holds
        self.span = span

    def open(self):
        self.r = Reader(self.clip, self.start, self.span + 0.2, (W, H), self.focus)

    def close(self):
        self.r.close()

    def picture(self, t):
        if self.freeze_at is not None:
            t = min(t, self.freeze_at)
        if self.fps_step:
            t = math.floor(t * self.fps_step) / self.fps_step
        f = self.r.at(self.fn(t)).astype(np.float32)
        z = self.zoom[0] + (self.zoom[1] - self.zoom[0]) * (t / max(1e-6, self.t1 - self.t0))
        if abs(z - 1) > 1e-3:
            M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, z)
            f = cv2.warpAffine(f, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        return f

    def draw(self, t, gt):
        return self.picture(t)


BLACK = np.full((H, W, 3), 6, np.float32)


class Photo(Shot):
    def __init__(self, t0, t1, name, focus=(0.5, 0.5), z=(1.0, 1.09), dx=0.0, dy=0.0, look="clean"):
        super().__init__(t0, t1)
        self.name, self.focus, self.z, self.dx, self.dy, self.look = name, focus, z, dx, dy, look

    def draw(self, t, gt):
        img = photo(self.name, W, H, self.focus, 1.12)
        return kenburns(img, W, H, t / (self.t1 - self.t0), self.z[0], self.z[1], self.dx, self.dy)


class Opening(Shot):
    """Title card: a 2.39:1 band opens on a landscape clip, title + English line + date around it,
    then the band expands to full frame while crossfading into a vertical clip (the next shot
    should continue that clip at into_start + B(2.5))."""
    look = "night"

    def __init__(self, t0, t1, strip, into, title, en="", date=""):
        super().__init__(t0, t1)
        self.strip, self.into, self.title, self.en, self.date = strip, into, title, en, date

    def open(self):
        self.a = Reader(self.strip[0], self.strip[1], 6, (1080, 608))
        self.b = Reader(self.into[0], self.into[1], 4, (W, H), (0.5, 0.5))

    def close(self):
        self.a.close(); self.b.close()

    def draw(self, t, gt):
        d = self.t1 - self.t0
        out = BLACK.copy()
        hfull = 452
        te = d - B(2.5)                                  # expand starts
        if t < te:
            h = int(hfull * ease_out(t / 1.3))
            src = self.a.at(t * 0.8).astype(np.float32)
            if h > 1:
                y0 = (H - h) // 2
                out[y0:y0 + h] = src[(608 - h) // 2:(608 - h) // 2 + h]
            ta = min(1, max(0, (t - 0.9) / 0.6)) * (1 - min(1, max(0, (t - (te - 0.45)) / 0.4)))
            put_text(out, self.title, F_SERIF, 66, W / 2, H / 2 + hfull / 2 + 110, ta, spacing=8)
            if self.en:
                put_text(out, self.en, F_MONO, 22, W / 2, H / 2 + hfull / 2 + 190, ta * 0.8,
                         fill=(225, 214, 196), spacing=9)
            if self.date:
                put_text(out, self.date, F_MONO, 22, W / 2, H / 2 - hfull / 2 - 80, ta * 0.7,
                         fill=(225, 214, 196), spacing=6)
        else:
            p = ease((t - te) / (d - te))
            h = int(hfull + (H - hfull) * p)
            y0 = (H - h) // 2
            nxt = self.b.at(t - te).astype(np.float32)
            bund = np.zeros((H, W, 3), np.float32)
            bund[(H - 608) // 2:(H - 608) // 2 + 608] = self.a.at(t * 0.8)
            mix = min(1, (t - te) / 0.35)
            pic = bund * (1 - mix) + nxt * mix
            out[y0:y0 + h] = pic[y0:y0 + h]
        return out


class Triptych(Shot):
    """Three landscape clips stacked as wide bands, each sliding in from alternating sides."""

    def __init__(self, t0, t1, items, stagger):
        super().__init__(t0, t1)
        self.items, self.stagger = items, stagger
        self.bh, self.gap = 456, 22
        self.top = (H - 3 * self.bh - 2 * self.gap) // 2

    def open(self):
        self.rs = [Reader(c, s, self.t1 - self.t0 + 0.5, (W, self.bh), (0.5, fy)) for c, s, fy in self.items]

    def close(self):
        for r in self.rs:
            r.close()

    def draw(self, t, gt):
        out = BLACK.copy()
        for i, r in enumerate(self.rs):
            ti = t - i * self.stagger
            if ti < 0:
                continue
            p = ease_out(ti / 0.55)
            side = -1 if i % 2 == 0 else 1
            x = int(side * W * (1 - p))
            y = self.top + i * (self.bh + self.gap)
            band = r.at(ti).astype(np.float32)
            xs, xe = max(0, x), min(W, W + x)
            out[y:y + self.bh, xs:xe] = band[:, xs - x:xe - x]
        return out


class Super8(Shot):
    """Super 8 gate: rounded aperture, weave, 18 fps step, flicker, date stamp."""
    look = "super8"
    GX0, GY0, GX1, GY1 = 40, 250, 1040, 1650

    def __init__(self, t0, t1, clip, start, speed=1.0, focus=(0.5, 0.5), date=""):
        super().__init__(t0, t1)
        self.clip, self.start, self.speed, self.focus, self.date = clip, start, speed, focus, date
        gw, gh = self.GX1 - self.GX0, self.GY1 - self.GY0
        m = np.zeros((gh, gw), np.float32)
        cv2.rectangle(m, (30, 30), (gw - 31, gh - 31), 1.0, -1)
        m = cv2.GaussianBlur(m, (0, 0), 14)
        m = np.clip((m - 0.5) * 2.4 + 0.5, 0, 1)
        self.mask = m[..., None]

    def open(self):
        gw, gh = self.GX1 - self.GX0 + 24, self.GY1 - self.GY0 + 24
        self.r = Reader(self.clip, self.start, (self.t1 - self.t0) * self.speed + 0.3, (gw, gh), self.focus)

    def close(self):
        self.r.close()

    def draw(self, t, gt):
        ts = math.floor(t * 18) / 18
        pic = self.r.at(ts * self.speed).astype(np.float32)
        k = int(gt * 18)
        rr = np.random.default_rng(k)
        dx, dy = int(round(rr.normal(0, 1.4))), int(round(rr.normal(0, 1.8) + 2 * math.sin(gt * 2.1)))
        gw, gh = self.GX1 - self.GX0, self.GY1 - self.GY0
        crop = pic[12 + dy:12 + dy + gh, 12 + dx:12 + dx + gw]
        crop = crop * (1 + rr.uniform(-0.035, 0.035))
        out = np.full((H, W, 3), 10, np.float32)
        out[self.GY0:self.GY1, self.GX0:self.GX1] = crop * self.mask + 10 * (1 - self.mask)
        if self.date:
            put_text(out, self.date, F_MONO, 30, self.GX1 - 120, self.GY1 - 70, 0.85, fill=(255, 150, 60),
                     shadow=False, spacing=2)
        return out


class FilmStrip(Shot):
    """A vertical 35mm strip of photos scrolling upward."""
    look = "paper"

    def __init__(self, t0, t1, names, edge="400T", first_no=14):
        super().__init__(t0, t1)
        self.names, self.edge, self.first_no = names, edge, first_no
        self.sw, self.fw, self.fh, self.gap = 780, 620, 826, 70

    def build(self):
        sw, fw, fh, gap = self.sw, self.fw, self.fh, self.gap
        n = len(self.names)
        L = n * (fh + gap) + 2 * H
        strip = np.zeros((L, sw, 3), np.float32)
        strip[:] = (34, 25, 18)
        r = np.random.default_rng(3)
        strip += r.normal(0, 2.0, (L, sw, 1)).astype(np.float32)
        for y in range(0, L, 64):           # sprocket holes
            for x in (26, sw - 26 - 30):
                cv2.rectangle(strip, (x, y + 14), (x + 30, y + 14 + 40), (222, 214, 198), -1, cv2.LINE_AA)
        y = H
        self.centers = []
        for i, nm in enumerate(self.names):
            img = photo(nm, fw, fh, (0.5, 0.5), 1.0)
            x = (sw - fw) // 2
            strip[y:y + fh, x:x + fw] = img
            self.centers.append(y + fh / 2)
            y += fh + gap
        im = Image.fromarray(np.clip(strip, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(im)
        f = ImageFont.truetype(F_MONO, 20)
        for i, c in enumerate(self.centers):
            d.text((92, int(c - self.fh / 2 - 46)), f"{self.first_no + i}A", font=f, fill=(255, 160, 70))
            d.text((self.sw - 250, int(c - self.fh / 2 - 46)), self.edge, font=f, fill=(255, 160, 70))
        self.strip = np.asarray(im, np.float32)

    def open(self):
        self.build()

    def draw(self, t, gt):
        d = self.t1 - self.t0
        c0 = self.centers[0] - H / 2 - 260
        c1 = self.centers[-1] - H / 2 + 120
        off = c0 + (c1 - c0) * (t / d)
        out = np.zeros((H, W, 3), np.float32)
        out[:] = (14, 13, 12)
        y0 = int(off)
        view = self.strip[y0:y0 + H]
        ang = -2.5
        canvas = np.zeros((H, W, 3), np.float32)
        x = (W - self.sw) // 2
        canvas[:, x:x + self.sw] = view
        msk = np.zeros((H, W), np.float32)
        msk[:, x:x + self.sw] = 1
        M = cv2.getRotationMatrix2D((W / 2, H / 2), ang, 1.0)
        canvas = cv2.warpAffine(canvas, M, (W, H), flags=cv2.INTER_LINEAR)
        msk = cv2.warpAffine(msk, M, (W, H), flags=cv2.INTER_LINEAR)[..., None]
        shadow = cv2.GaussianBlur(msk, (0, 0), 30)[..., None] if msk.ndim == 2 else cv2.GaussianBlur(msk[..., 0], (0, 0), 30)[..., None]
        out = out * (1 - shadow * 0.6)
        out = out * (1 - msk) + canvas * msk
        return out


class Slides(Shot):
    """Slide projector: photos in card mounts, mechanical advance."""
    look = "paper"

    def __init__(self, t0, t1, items):
        super().__init__(t0, t1)
        self.items = items  # (photo, label)
        self.per = (t1 - t0) / len(items)
        bg = np.zeros((H, W, 3), np.float32)
        d = np.sqrt(((XX - W / 2) / (W * 0.75)) ** 2 + ((YY - H / 2) / (H * 0.42)) ** 2)
        bg[:] = np.array([44, 38, 32], np.float32)
        self.bg = bg * np.clip(1.25 - d * 0.9, 0.25, 1.25)[..., None]

    def mount(self, name, label):
        key = (name, label)
        if not hasattr(self, "_m"):
            self._m = {}
        if key in self._m:
            return self._m[key]
        mw, mh = 920, 1120
        card = Image.new("RGBA", (mw, mh), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle((0, 0, mw - 1, mh - 1), 46, fill=(236, 230, 216, 255))
        iw, ih = 700, 900
        img = photo(name, iw, ih, (0.5, 0.5), 1.0)
        card.paste(Image.fromarray(img.astype(np.uint8)), ((mw - iw) // 2, 70))
        f = ImageFont.truetype(F_HAND, 40)
        d.text((110, mh - 128), label, font=f, fill=(70, 62, 54, 255))
        f2 = ImageFont.truetype(F_MONO, 22)
        d.text((mw - 260, mh - 116), "KODACHROME", font=f2, fill=(150, 120, 90, 255))
        a = np.asarray(card, np.float32)
        self._m[key] = a
        return a

    def draw(self, t, gt):
        out = self.bg.copy()
        i = min(int(t / self.per), len(self.items) - 1)
        tl = t - i * self.per
        slides = []
        cur = self.mount(*self.items[i])
        if i == 0 and tl < 0.25:
            slides.append((cur, (1 - ease_out(tl / 0.25)) * W * 0.9))
        elif tl < 0.25 and i > 0:
            prev = self.mount(*self.items[i - 1])
            p = ease_out(tl / 0.25)
            slides.append((prev, -W * p))
            slides.append((cur, W * (1 - p)))
        else:
            slides.append((cur, 0))
        for card, dx in slides:
            mh, mw = card.shape[:2]
            x0 = int((W - mw) / 2 + dx)
            y0 = (H - mh) // 2 - 30
            sh = cv2.GaussianBlur(card[..., 3], (0, 0), 22) / 255.0 * 0.55
            for (img, ox, oy, sha) in [(None, 18, 26, sh)]:
                xs, xe = max(0, x0 + ox), min(W, x0 + ox + mw)
                if xe > xs:
                    out[y0 + oy:y0 + oy + mh, xs:xe] *= (1 - sha[:, xs - x0 - ox:xe - x0 - ox, None])
            xs, xe = max(0, x0), min(W, x0 + mw)
            if xe > xs:
                sub = card[:, xs - x0:xe - x0]
                a = sub[..., 3:4] / 255.0
                out[y0:y0 + mh, xs:xe] = out[y0:y0 + mh, xs:xe] * (1 - a) + sub[..., :3] * a
        return out


class Strip(Shot):
    """Landscape picture in a 2.39:1 (or 16:9) band; optional reveal."""
    look = "night"

    def __init__(self, t0, t1, clip=None, start=0, speed=1.0, h=452, reveal=0.0, photo_name=None,
                 kb=(1.0, 1.06), fy=0.5, close=0.0):
        super().__init__(t0, t1)
        self.close_t = close
        self.clip, self.start, self.speed, self.h, self.reveal = clip, start, speed, h, reveal
        self.photo_name, self.kb, self.fy = photo_name, kb, fy

    def open(self):
        if self.clip:
            self.r = Reader(self.clip, self.start, (self.t1 - self.t0) * self.speed + 0.3, (W, 608))

    def close(self):
        if self.clip:
            self.r.close()

    def band(self, t):
        if self.clip:
            return self.r.at(t * self.speed).astype(np.float32)
        img = photo(self.photo_name, W, 608, (0.5, self.fy), 1.1)
        return kenburns(img, W, 608, t / (self.t1 - self.t0), self.kb[0], self.kb[1])

    def draw(self, t, gt):
        out = BLACK.copy()
        h = self.h if not self.reveal else int(self.h * ease_out(t / self.reveal))
        if self.close_t:
            h = int(h * (1 - ease_in((t - (self.t1 - self.t0 - self.close_t)) / self.close_t)))
        if h > 1:
            src = self.band(t)
            y0 = (H - h) // 2
            out[y0:y0 + h] = src[(608 - h) // 2:(608 - h) // 2 + h]
        return out


class Dual(Shot):
    look = "night"

    def __init__(self, t0, t1, a, b, delay):
        super().__init__(t0, t1)
        self.a, self.b, self.delay = a, b, delay
        self.bh, self.gap = 560, 24
        self.top = (H - 2 * self.bh - self.gap) // 2

    def open(self):
        d = self.t1 - self.t0 + 0.4
        self.ra = Reader(self.a[0], self.a[1], d, (W, self.bh))
        self.rb = Reader(self.b[0], self.b[1], d, (W, self.bh))

    def close(self):
        self.ra.close(); self.rb.close()

    def draw(self, t, gt):
        out = BLACK.copy()
        out[self.top:self.top + self.bh] = self.ra.at(t)
        tb = t - self.delay
        if tb >= 0:
            p = ease_out(tb / 0.6)
            y = self.top + self.bh + self.gap
            band = self.rb.at(tb).astype(np.float32)
            out[y:y + self.bh] = BLACK[:self.bh] * (1 - p) + band * p
        return out


class Print(Shot):
    """The last Bund photo settles into a printed photograph on a dark table, then everything fades."""
    look = "paper"

    def __init__(self, t0, t1, name, settle, fade_from, label=""):
        super().__init__(t0, t1)
        self.name, self.settle, self.fade_from, self.label = name, settle, fade_from, label
        r = np.random.default_rng(9)
        tex = cv2.GaussianBlur(r.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 2.5)
        self.table = (np.array([24, 21, 19], np.float32) + tex[..., None] * 3) * \
            np.clip(1.2 - 0.6 * np.sqrt(((XX - W / 2) / W) ** 2 + ((YY - H / 2) / H) ** 2) * 2, 0.4, 1.2)[..., None]

    def draw(self, t, gt):
        pw, ph = 900, 506
        img = photo(self.name, pw, ph, (0.5, 0.5), 1.0)
        p = ease(t / self.settle)
        # print: white border + handwritten note
        bw = 30
        card = np.full((ph + bw * 2 + 70, pw + bw * 2, 3), (240, 236, 228), np.float32)
        card[bw:bw + ph, bw:bw + pw] = img
        cim = Image.fromarray(card.astype(np.uint8))
        ImageDraw.Draw(cim).text((bw + 6, bw + ph + 14), self.label, font=ImageFont.truetype(F_HAND, 34),
                                 fill=(80, 72, 64))
        card = np.asarray(cim, np.float32)
        ch, cw = card.shape[:2]
        # start: band-only picture filling the 452 strip at full width; end: card scaled .9, rotated -3
        s = (W / pw) * (1 - p) + 0.92 * p
        ang = -3.0 * p
        alpha_border = p
        canvas = np.zeros((H, W, 3), np.float32)
        msk = np.zeros((H, W), np.float32)
        M = cv2.getRotationMatrix2D((cw / 2, ch / 2), ang, s)
        M[0, 2] += W / 2 - cw / 2
        M[1, 2] += H / 2 - ch / 2 - 20 * p
        src = card.copy()
        src_m = np.ones((ch, cw), np.float32)
        if alpha_border < 1:
            # fade the border in: before settling only the photo shows
            bm = np.zeros((ch, cw), np.float32)
            bm[bw:bw + ph, bw:bw + pw] = 1
            src_m = bm + (1 - bm) * alpha_border
        canvas = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_LINEAR)
        msk = cv2.warpAffine(src_m, M, (W, H), flags=cv2.INTER_LINEAR)[..., None]
        bg = BLACK * (1 - p) + self.table * p
        sh = cv2.GaussianBlur(msk[..., 0], (0, 0), 26)[..., None]
        sh = np.roll(np.roll(sh, 22, 0), 14, 1)
        out = bg * (1 - sh * 0.7 * p)
        out = out * (1 - msk) + canvas * msk
        if t > self.fade_from:
            out *= 1 - ease((t - self.fade_from) / (self.t1 - self.t0 - self.fade_from))
        return out


class EndCard(Shot):
    """Quiet end card on near-black: title + small mono line, fades in and out."""
    look = "paper"

    def __init__(self, t0, t1, title, sub=""):
        super().__init__(t0, t1)
        self.title, self.sub = title, sub

    def draw(self, t, gt):
        out = np.full((H, W, 3), 6, np.float32)
        d = self.t1 - self.t0
        a = min(1, t / 0.8) * (1 - max(0, (t - (d - 1.0)) / 1.0))
        put_text(out, self.title, F_SERIF, 54, W / 2, H / 2 - 30, a, spacing=10)
        if self.sub:
            put_text(out, self.sub, F_MONO, 22, W / 2, H / 2 + 50, a * 0.75, fill=(220, 210, 192), spacing=8)
        return out


class DoubleExp(Shot):
    """Two clips screen-blended: a tower over the river."""
    look = "night"

    def __init__(self, t0, t1, a, b):
        super().__init__(t0, t1)
        self.a, self.b = a, b

    def open(self):
        d = self.t1 - self.t0 + 0.3
        self.ra = Reader(self.a[0], self.a[1], d, (W, H))
        self.rb = Reader(self.b[0], self.b[1], d, (W, H), (0.5, 0.5))

    def close(self):
        self.ra.close(); self.rb.close()

    def draw(self, t, gt):
        a = self.ra.at(t).astype(np.float32)
        b = self.rb.at(t).astype(np.float32)
        return 255 - (255 - a) * (255 - b * 0.85) / 255


def shift(s, d):
    s.t0 += d
    s.t1 += d
    return s


def sequence(t0, plan):
    """plan: [(beats, make(a, b) -> Shot)] laid end to end from t0; returns the shots."""
    S, b = [], 0.0
    for n, mk in plan:
        S.append(mk(t0 + B(b), t0 + B(b + n)))
        b += n
    return S


# ---------------------------------------------------------------- project config + overlays
class Project:
    """Everything that is not a picture: words on screen, sound, output name.

    vo:      [(clip, src_a, src_b, timeline_at, [(src_t0, src_t1, caption)])]  her own voice pieces
    labels:  [(t, zh, en)]       chapter labels top-left, 2.6 s each
    hook:    (t0, t1, text) | None   big bold line over the opening highlights
    typewriter: (t0, text) | None    one mono line typed on screen
    leak:    t | None            the single warm light leak (keep it to one)
    dips:    [t]                 2-frame dips to black at chapter breaks (instead of flashes)
    sfx:     [(name, t, gain)]   from vstudio.audio.sfx_bank (shutter, shutter_b, camera, ...)
    total:   seconds; out: final file name in RAW
    """

    def __init__(self, timeline, vo=(), labels=(), hook=None, typewriter=None, leak=None, dips=(), sfx=(),
                 total=None, out="vlog.mp4", raw_ext=".MOV", duck_db=-11.0, caption_y=1560):
        self.timeline, self.vo, self.labels, self.hook = timeline, list(vo), list(labels), hook
        self.typewriter, self.leak, self.dips, self.sfx = typewriter, leak, list(dips), list(sfx)
        self.total, self.out, self.raw_ext, self.duck_db, self.caption_y = total, out, raw_ext, duck_db, caption_y
        self.caps = [(at + s0 - a, at + s1 - a + 0.15, text) for clip, a, b, at, cues in self.vo
                     for s0, s1, text in cues]


HOOK_BAND = 1 - 0.4 * np.exp(-((np.arange(H, dtype=np.float32)[:, None, None] - 620) / 150) ** 2)


def overlays(out, gt, P):
    if P.hook:
        t0, t1, hook = P.hook
        if t0 <= gt < t1:
            a = min(1, (gt - t0) / 0.2, (t1 - gt) / 0.25)
            out *= 1 - (1 - HOOK_BAND) * a
            rise = int(16 * (1 - ease_out((gt - t0) / 0.35)))
            put_text(out, hook, F_SERIF_B, 96, W / 2, 620 + rise, a, spacing=8)
    for t0, t1, text in P.caps:
        if t0 <= gt < t1:
            a = min(1, (gt - t0) / 0.12, (t1 - gt) / 0.12)
            put_text(out, text, F_SERIF, 48, W / 2, P.caption_y, a, spacing=3)
    for t, zh, en in P.labels:
        if t <= gt < t + 2.6:
            a = min(1, (gt - t) / 0.4, (t + 2.6 - gt) / 0.5)
            put_text(out, zh, F_SERIF, 44, 90, 330, a, spacing=8, anchor="l")
            put_text(out, en, F_MONO, 22, 92, 390, a * 0.8, fill=(232, 222, 205), spacing=5, anchor="l")
            cv2.line(out, (92, 362), (92 + int(150 * ease_out((gt - t) / 0.6)), 362),
                     (232, 222, 205), 1, cv2.LINE_AA)
    if P.typewriter:
        t0, text = P.typewriter
        if t0 <= gt < t0 + 3.4:
            n = min(len(text), int((gt - t0) / 0.06))
            a = min(1, (t0 + 3.4 - gt) / 0.4)
            s = text[:n] + ("_" if int(gt * 3) % 2 == 0 else " ")
            put_text(out, s, F_MONO, 34, 90, 1420, a, fill=(250, 244, 230), anchor="l", spacing=1)
    if P.leak is not None and abs(gt - P.leak) < 0.45:
        p = (gt - P.leak + 0.45) / 0.9
        cx = W * (-0.2 + 1.4 * p)
        d = np.sqrt(((XX - cx) / (W * 0.55)) ** 2 + ((YY - H * 0.4) / (H * 0.5)) ** 2)
        leak = np.clip(1 - d, 0, 1)[..., None] ** 1.6 * np.array([255, 150, 70], np.float32)
        out[:] = 255 - (255 - out) * (1 - leak / 255 * 0.85 * math.sin(math.pi * p))
    return out


def dips(gt, frame, P):
    for t in P.dips:
        if abs(gt - t) < 0.12:
            frame *= 0.15 + 0.85 * abs(gt - t) / 0.12
    return frame


def frame_at(shot, gt, P):
    pic = shot.draw(gt - shot.t0, gt)
    pic = finish(pic, round(gt * FPS), shot.look)
    return overlays(dips(gt, pic, P), gt, P)


# ---------------------------------------------------------------- runner
_LOADED = {}


def load(project_file):
    """Import a project file once per process (workers re-import it; it calls configure())."""
    import importlib.util
    if project_file not in _LOADED:
        spec = importlib.util.spec_from_file_location("cinefx_project", project_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LOADED[project_file] = mod
    return _LOADED[project_file].P


ENC = ["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-maxrate", "16M", "-bufsize", "32M",
       "-profile:v", "high", "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
       "-color_trc", "bt709"]


def render_range(args):
    project_file, idx, f0, f1, path = args
    P = load(project_file)
    shot = P.timeline()[idx]
    shot.open()
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", *ENC, path], stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        enc.stdin.write(np.clip(frame_at(shot, fi / FPS, P), 0, 255).astype(np.uint8).tobytes())
    enc.stdin.close(); enc.wait()
    shot.close()
    return path


def jobs(project_file, P):
    return [(project_file, i, round(s.t0 * FPS), round(s.t1 * FPS), os.path.join(ROOT, "scenes", f"s{i:03d}.mp4"))
            for i, s in enumerate(P.timeline())]


def cli(project_file, argv=None):
    argv = sys.argv[1:] if argv is None else argv
    project_file = os.path.abspath(project_file)
    P = load(project_file)
    cmd = argv[0] if argv else "help"
    if cmd == "stills":
        os.makedirs(os.path.join(ROOT, "stills"), exist_ok=True)
        S = P.timeline()
        for a in argv[1:]:
            gt = float(a)
            s = next(x for x in S if x.t0 <= gt < x.t1)
            s.open()
            pic = frame_at(s, gt, P)
            s.close()
            p = os.path.join(ROOT, "stills", f"t{gt:06.2f}.jpg")
            Image.fromarray(np.clip(pic, 0, 255).astype(np.uint8)).resize((540, 960)).save(p, quality=88)
            print(p, type(s).__name__)
    elif cmd == "video":
        from multiprocessing import Pool
        os.makedirs(os.path.join(ROOT, "scenes"), exist_ok=True)
        js = jobs(project_file, P)
        only = {int(x) for x in argv[1:]}
        todo = [j for j in js if not only or j[1] in only]
        with Pool(max(1, (os.cpu_count() or 8) - 1)) as pool:
            for p in pool.imap_unordered(render_range, todo):
                print("done", os.path.basename(p), flush=True)
        lst = os.path.join(ROOT, "scenes", "list.txt")
        with open(lst, "w") as f:
            for j in js:
                f.write(f"file '{j[4]}'\n")
        os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                        os.path.join(ROOT, "out", "video.mp4")], check=True)
        print("video ->", os.path.join(ROOT, "out", "video.mp4"))
    elif cmd == "audio":
        make_audio(P)
    elif cmd == "final":
        final(P)
    else:
        print(__doc__)


def make_audio(P):
    from . import audio
    sr = 48000
    total = P.total or P.timeline()[-1].t1
    n = int(total * sr)
    voice = np.zeros((n, 2), np.float32)
    for clip, a, b, at, _ in P.vo:
        clean = os.path.join(ROOT, "voice", clip + ".clean.wav")   # scripts/voice_clean.py output
        if os.path.exists(clean):
            x = audio.decode_audio(clean, sr=sr, channels=2, start=a - 0.03, dur=b - a + 0.18)
        else:
            x = audio.decode_audio(os.path.join(RAW, clip + P.raw_ext), sr=sr, channels=2, start=a - 0.03,
                                   dur=b - a + 0.18, af="highpass=f=90,afftdn=nf=-30")
        fade = int(0.04 * sr)
        x[:fade] *= np.linspace(0, 1, fade)[:, None]
        x[-fade * 2:] *= np.linspace(1, 0, fade * 2)[:, None]
        i = int((at - 0.03) * sr)
        r = np.sqrt((x ** 2).mean()) + 1e-9
        voice[i:i + len(x)] += (x * (0.1 / r))[:n - i]       # every piece at the same level
    bank = audio.sfx_bank(sr)
    fx = np.zeros(n, np.float32)

    def place(name, t, g):
        s = bank[name]
        i = int(t * sr)
        if 0 <= i < n:
            fx[i:i + len(s)] += s[:n - i] * g
    for name, t, g in P.sfx:
        place(name, t, g)
    if P.typewriter:
        t0, text = P.typewriter
        for j in range(len(text)):
            place("typewriter" if j % 2 else "typewriter_b", t0 + j * 0.06, 0.12)
    voice += fx[:, None]
    os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
    vpath, mpath = os.path.join(ROOT, "out", "voice.wav"), os.path.join(ROOT, "out", "music.wav")
    audio.write_wav(vpath, voice, sr)
    m = audio.decode_audio(MUSIC, sr=sr, channels=2, start=MUSIC_START, dur=total)
    fo = int(3.5 * sr)
    m[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
    audio.write_wav(mpath, m, sr)
    audio.mix_bed(vpath, mpath, os.path.join(ROOT, "out", "audio.wav"), duck_db=P.duck_db, fade_in=0.4,
                  fade_out=3.5)
    print("audio ->", os.path.join(ROOT, "out", "audio.wav"))


def tag_bt709(path):
    tmp = path + ".tag.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-c", "copy", "-bsf:v",
                    "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1",
                    "-movflags", "+faststart", tmp], check=True)
    os.replace(tmp, path)


def burn_cover(video, cover, frames=3):
    """Put the cover on the first `frames` frames (replace, not insert: duration and sync unchanged)."""
    tmp = video + ".cover.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-loop", "1", "-i", cover, "-filter_complex",
                    f"[1:v]scale={W}:{H},format=yuv420p[c];[0:v][c]overlay=0:0:enable='lt(n,{frames})':shortest=1,"
                    "format=yuv420p", *ENC, "-c:a", "copy", "-movflags", "+faststart", tmp], check=True)
    os.replace(tmp, video)


def final(P, cover=None):
    from . import audio
    tmp = os.path.join(ROOT, "out", "mux.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(ROOT, "out", "video.mp4"), "-i",
                    os.path.join(ROOT, "out", "audio.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a",
                    "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", tmp], check=True)
    dst = os.path.join(RAW, P.out)
    audio.loudnorm_2pass(tmp, dst, lufs=-14)
    tag_bt709(dst)
    cover = cover or os.path.join(RAW, "cover.png")
    if os.path.exists(cover):
        burn_cover(dst, cover)
    print("final ->", dst)


# ---------------------------------------------------------------- film covers (same canvas as the video)
def _film(img, grain=7.0, hal=0.7, warm=1.0, seed=21):
    """Static film finish for a still: the motion look plus stronger grain and halation."""
    rng = np.random.default_rng(seed)
    x = finish(img, 3, "clean")
    lum = (x / 255.0) @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    hi = np.clip((lum - 0.62) / 0.3, 0, 1)
    g = cv2.GaussianBlur(hi, (0, 0), 14) * 0.7 + cv2.GaussianBlur(hi, (0, 0), 40) * 0.5
    x = x + g[..., None] * np.array([255, 92, 36], np.float32) * hal * 0.35
    x = x + x * np.array([0.03, 0.0, -0.035], np.float32) * warm
    n = cv2.GaussianBlur(rng.normal(0, 1, x.shape[:2]).astype(np.float32), (0, 0), 0.7)
    l3 = np.clip(x.mean(2, keepdims=True) / 255, 0, 1)
    return x + n[..., None] * grain * (0.4 + 2.4 * l3 * (1 - l3))


def lift(img, gamma=0.8, contrast=1.12):
    """Open up a dim indoor / night photo before the film finish (grain on mud looks dirty)."""
    x = np.clip(img / 255.0, 0, 1) ** gamma
    return np.clip((x - 0.5) * contrast + 0.5, 0, 1) * 255


def _shade(img, start=0.55, amt=0.62):
    yy = np.linspace(0, 1, img.shape[0], dtype=np.float32)[:, None, None]
    return img * (1 - np.clip((yy - start) / (1 - start), 0, 1) ** 1.3 * amt)


def cover_titles(img, title, sub="", en="", y=1390, big=104):
    """Title block inside the 3:4 feed crop (y 240..1680): bold serif, serif sub, spaced mono line."""
    put_text(img, title, F_SERIF_B, big, W / 2, y, 1.0, spacing=8)
    if sub:
        put_text(img, sub, F_SERIF, 62, W / 2, y + 122, 1.0, spacing=10)
    if en:
        put_text(img, en, F_MONO, 24, W / 2, y + 205, 0.85, fill=(235, 226, 210), spacing=6)
    return img


def _edge(d, xy, text, size=24, fill=(255, 150, 62)):
    d.text(xy, text, font=ImageFont.truetype(F_MONO, size), fill=fill)


def cover_negative(name, title, sub="", en="", focus=(0.5, 0.6), edge=("14A", "400T", "15"), foot=("", "")):
    """A 35mm negative scan: black rebate, sprockets on both sides, orange edge print, photo in the gate."""
    out = np.full((H, W, 3), 13, np.float32)
    x0, x1, y0, y1 = 92, W - 92, 130, H - 130
    pic = _shade(lift(photo(name, x1 - x0, y1 - y0, focus, 1.0)), 0.5, 0.6)
    m = np.zeros((y1 - y0, x1 - x0), np.float32)
    cv2.rectangle(m, (6, 6), (x1 - x0 - 7, y1 - y0 - 7), 1, -1)
    m = cv2.GaussianBlur(m, (0, 0), 3)[..., None]
    out[y0:y1, x0:x1] = pic * m + out[y0:y1, x0:x1] * (1 - m)
    im = Image.fromarray(np.clip(_film(out), 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for y in range(20, H, 92):
        for x in (24, W - 24 - 40):
            d.rounded_rectangle((x, y, x + 40, y + 56), 7, fill=(226, 220, 208))
    _edge(d, (110, 72), "> " + edge[0], 26)
    _edge(d, (W / 2 - 80, 72), edge[1], 26)
    _edge(d, (W - 200, 72), edge[2] + " >", 26)
    _edge(d, (110, H - 104), foot[0], 26)
    _edge(d, (W - 250, H - 104), foot[1], 26)
    return cover_titles(np.asarray(im, np.float32), title, sub, en, 1380)


def cover_still(name, title, sub="", en="", focus=(0.5, 0.55), top="", bottom=""):
    """A film still: full bleed, 2.39 bars outside the feed crop, subtitle-style title."""
    pic = _film(_shade(lift(photo(name, W, H, focus, 1.0)), 0.52, 0.66), grain=6.0, hal=0.8)
    bar = 210
    pic[:bar] = 6
    pic[H - bar:] = 6
    if top:
        put_text(pic, top, F_SERIF, 28, W / 2, bar / 2, 0.8, fill=(220, 210, 192), spacing=8)
    if bottom:
        put_text(pic, bottom, F_MONO, 22, W / 2, H - bar / 2, 0.7, fill=(255, 150, 62), spacing=4, shadow=False)
    return cover_titles(pic, title, sub, en, 1370)


def cover_strip(names, title, sub="", en="", edge="400T", angle=-6):
    """A tilted film strip of three frames (pick three different subjects: activity, place, landmark)."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    out = np.array([30, 24, 20], np.float32) * np.clip(
        1.3 - 0.9 * np.hypot((xx - W / 2) / W, (yy - H / 2) / H) * 2, 0.4, 1.3)[..., None]
    sw, fw, fh, gap = 820, 660, 560, 36
    L = 3 * fh + 4 * gap + 300
    strip = np.full((L, sw, 3), (28, 21, 16), np.float32)
    y = 150
    for nm in names[:3]:
        nm, f = (nm, (0.5, 0.5)) if isinstance(nm, str) else nm
        strip[y:y + fh, (sw - fw) // 2:(sw - fw) // 2 + fw] = lift(photo(nm, fw, fh, f, 1.0))
        y += fh + gap
    sim = Image.fromarray(np.clip(strip, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(sim)
    for yh in range(10, L, 64):
        for x in (22, sw - 22 - 32):
            d.rounded_rectangle((x, yh, x + 32, yh + 42), 6, fill=(226, 220, 208))
    for i, yy0 in enumerate(range(150, 150 + 3 * (fh + gap), fh + gap)):
        _edge(d, (90, yy0 - 32), f"{14 + i}A", 20)
        _edge(d, (sw - 200, yy0 - 32), edge, 20)
    strip = np.asarray(sim, np.float32)
    big = np.zeros((H, W, 3), np.float32)
    msk = np.zeros((H, W), np.float32)
    x, ys = (W - sw) // 2, (H - L) // 2
    big[max(0, ys):ys + L, x:x + sw] = strip[max(0, -ys):H - ys]
    msk[max(0, ys):ys + L, x:x + sw] = 1
    M = cv2.getRotationMatrix2D((W / 2, H / 2), angle, 1.0)
    big = cv2.warpAffine(big, M, (W, H))
    msk = cv2.warpAffine(msk, M, (W, H))[..., None]
    sh = np.roll(cv2.GaussianBlur(msk[..., 0], (0, 0), 30), 26, 0)[..., None]
    out = out * (1 - sh * 0.7)
    out = _film(_shade(out * (1 - msk) + big * msk, 0.6, 0.5), grain=6.0, hal=0.6)
    return cover_titles(out, title, sub, en, 1420)


def save_cover(img, path):
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(path)
    return path
