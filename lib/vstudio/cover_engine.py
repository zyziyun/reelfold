"""Cover engine 2.0: one picked frame -> a designed, platform-exact, monolingual cover per platform, plus three
YouTube variants for A/B testing (YouTube Studio "Test & Compare").

    from vstudio import cover_engine as CE
    res = CE.make_covers("frame.jpg", {"en": "Golden Hour | Elliott Bay, Seattle", "zh": "黄金时刻 | 西雅图艾略特湾"},
                         ["youtube", "bilibili", "xiaohongshu"], out_dir="covers")
    res["youtube"]["file"], res["youtube"]["variants"]   # chosen cover + the A/B pack (best first)

What it does, per frame (once) and per platform:
  analyse    saliency map (``vstudio.saliency``), faces (``vstudio.face``) and the subject matte (``vstudio.matte``:
             BiRefNet, MIT - MediaPipe when it is not downloaded) -> an occupancy map: where text must not go
  crop       the cover aspect around the subject; a crop smaller than the canvas is upscaled with Real-ESRGAN
             (``vstudio.upscale``, BSD-3; Lanczos when it cannot run)
  text       one language per platform (``platform.lang_for``: YouTube English, 小红书 / B站 Chinese); the title sits
             in the emptiest part of the title-safe box, clear of faces / the subject and of the platform keep-outs
             (``cover.keepouts``: YouTube's duration badge, B站's play-count band, 小红书's video mark); restrained
             type (theme ``font_title`` / ``font_strong`` tokens, OFL fonts), no stroke, no box: a soft local
             scrim only as dark as the contrast needs (WCAG 4.5 against warm white)
  variants   scene (full-bleed frame), subject (tighter on the subject; the title may sit behind it - depth from
             the matte), text-led (graded-down frame, bigger type). YouTube keeps all three; the others keep the
             best of the first two
  legibility every variant is rendered at 168x94 and 320x180 (YouTube's small sizes; portrait covers at 94x168 /
             180x320): headline cap height >= 6 % of the thumbnail's short side and contrast >= 3 at both,
             else it is rejected (never the chosen one while a legible one exists)
"""
import json
import os
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

INK = (250, 247, 240)
CHAMPAGNE = (214, 192, 150)
SMALL_SIZES = ((168, 94), (320, 180))
MIN_HEIGHT = 0.06            # headline cap height / thumbnail height at the small sizes
MIN_CONTRAST = 3.0
VARIANTS = ("scene", "subject", "text")
ANALYSIS_W = 480

# Keep-outs on the cover canvas the platform paints over (fractions of the cover size, x0 y0 x1 y1). Profiles may set
# ``cover.keepouts`` in pixels; these defaults cover the common surfaces.
DEFAULT_KEEPOUTS = {
    "youtube": [(0.855, 0.86, 1.0, 1.0), (0.915, 0.0, 1.0, 0.16)],       # duration badge; watch-later / queue icons
    "bilibili": [(0.0, 0.885, 1.0, 1.0), (0.91, 0.0, 1.0, 0.14)],        # play / danmaku / duration band; 稍后再看
    "xiaohongshu": [(0.88, 0.0, 1.0, 0.1)],                               # the video mark, top right
    "youtube-shorts": [(0.0, 0.8, 1.0, 1.0)],                             # the title / channel overlay
}


# ---------------------------------------------------------------- text per language
_CJK = re.compile(r"[㐀-鿿豈-﫿]")


def has_cjk(s):
    return bool(_CJK.search(str(s or "")))


def mono_text(text, lang):
    """A bilingual cover text in one language: per line ("|" / newline), the parts ("·" / "/" / "—") in ``lang``
    (zh: with Chinese, en: without); a line with nothing left is dropped. Lines joined with " | "."""
    out = []
    for line in re.split(r"\s*[|｜\n]\s*", str(text or "")):
        parts = [x.strip() for x in re.split(r"\s*[·•/／—]\s*", line) if x.strip()]
        keep = [x for x in parts if has_cjk(x) == (lang == "zh")]
        if keep:
            out.append(" · ".join(keep))
    return " | ".join(out)


def title_parts(text, lang):
    """Cover text -> (title, kicker). "Title | place" splits at the bar; a long single English title splits at a
    colon / dash. YouTube-style brevity: a title over 5 words (en) / 12 characters (zh) moves its tail to the kicker
    when there is a natural break; otherwise it stays whole (the legibility check judges it)."""
    parts = [x.strip() for x in re.split(r"\s*[|｜\n]\s*", str(text or "")) if x.strip()]
    if not parts:
        return "", ""
    title, kicker = parts[0], " · ".join(parts[1:])
    if lang == "en" and len(title.split()) > 5:
        for sep in (": ", " — ", " – ", " - ", ", "):
            if sep in title:
                a, b = title.split(sep, 1)
                if 1 <= len(a.split()) <= 5:
                    title, kicker = a.strip(), (b.strip() + (" · " + kicker if kicker else ""))
                    break
    if lang == "zh" and len(title) > 12:
        for sep in ("：", "，", "——", "—", "·", " "):
            if sep in title:
                a, b = title.split(sep, 1)
                if 2 <= len(a) <= 12:
                    title, kicker = a.strip(), (b.strip() + (" · " + kicker if kicker else ""))
                    break
    return title, kicker


# Words that say how a video was shot or what kind it is, not what it is about: a cover title made of them
# ("航拍西雅图", "Seattle Drone Footage") is weak next to one naming the subject ("埃利奥特湾作业岸线").
GENERIC_ZH = ("航拍", "无人机", "风景", "美景", "大片", "记录", "日常", "旅行", "旅拍", "随拍", "合集", "打卡",
              "一日游", "城市", "视频", "分享", "vlog", "Vlog", "VLOG", "4K", "4k", "空镜", "延时", "随笔", "短片",
              "混剪", "合辑")
GENERIC_EN = {"drone", "aerial", "aerials", "footage", "vlog", "travel", "views", "view", "scenery", "cinematic",
              "4k", "trip", "beautiful", "video", "film", "b-roll", "broll", "essay", "montage", "compilation",
              "from", "above", "the", "of", "a", "in"}


def specificity(title, lang):
    """How much a cover title names its subject (higher is better): the share of it that is generic wording
    (``GENERIC_ZH`` / ``GENERIC_EN``) counts against it, a number (a year, a height) for it, and a length a
    phone can read (zh 3-12 characters, en 2-5 words) is preferred."""
    t = str(title or "").strip()
    if not t:
        return -9.0
    if not re.search(r"[A-Za-z㐀-鿿]", t):            # "2026" alone says nothing
        return -1.0
    if lang == "zh":
        core = re.sub(r"\s+", "", t)
        gen = 0
        for g in sorted(GENERIC_ZH, key=len, reverse=True):
            if g in core:
                gen += len(g) * core.count(g)
                core_ = core.replace(g, "")
                core = core_ if core_ else core
        n = len(re.sub(r"\s+", "", t))
        share = min(1.0, gen / max(1, n))
        size = -0.4 if n < 3 else (-0.08 * (n - 12) if n > 12 else 0.0)
    else:
        words = re.findall(r"[A-Za-z0-9'’&-]+", t)
        n = len(words)
        stop = {"the", "of", "a", "in", "from", "above"}
        content = [w for w in words if w.lower() not in stop] or words
        share = sum(w.lower() in GENERIC_EN for w in content) / max(1, len(content))
        size = -0.3 if n < 2 else (-0.1 * (n - 5) if n > 5 else 0.0)
    num = 0.15 if re.search(r"\d", t) else 0.0
    return round(1.0 - 1.5 * share + size + num, 4)


def pick_text(candidates, lang):
    """The cover text in ``lang`` from a few candidates (the cover text she gave, the video's title, the post
    title, ...), "title | kicker": each made monolingual (``mono_text``), the most specific title wins
    (``specificity``; the earlier candidates keep a small lead - the first is the one written for the cover,
    then the video's title). Its own
    kicker stays; with none, the next candidate that adds words becomes the kicker."""
    rows = []
    for k, c in enumerate(candidates):
        m = mono_text(c, lang)
        if not m.strip():
            continue
        title, kicker = title_parts(m, lang)
        if title:
            rows.append((specificity(title, lang) + max(0.0, 0.1 - 0.05 * k), k, title, kicker))
    if not rows:
        return ""
    best = max(rows, key=lambda r: (r[0], -r[1]))
    _, _, title, kicker = best
    if kicker and specificity(kicker, lang) > specificity(title, lang) + 0.3 and len(kicker) <= max(len(title), 1) * 2.5:
        title, kicker = kicker, title                  # "秋日随笔 · 放手 | 当整条街一起变红": the subject leads
    if not kicker:
        norm = lambda x: re.sub(r"[\s·•:：,，|｜-]+", "", x.lower())
        units = (lambda x: set(norm(x))) if lang == "zh" else (lambda x: set(re.findall(r"[a-z0-9']+", x.lower())))
        for _, _, t, kk in sorted(rows, key=lambda r: r[1]):
            for alt in (t, kk):
                u = units(alt or "")
                if not u or specificity(alt, lang) < 0.6 or len(u & units(title)) >= 0.5 * len(u):
                    continue                           # generic, or mostly the title again
                kicker = alt
                break
            if kicker:
                break
        if kicker and specificity(kicker, lang) > specificity(title, lang) + 0.3 and \
                len(kicker) <= max(len(title), 1) * 2.5:
            title, kicker = kicker, title
    return title + (" | " + kicker if kicker else "")


# ---------------------------------------------------------------- platform geometry
def spec_for(platform):
    """{name, key, size, safe (x0,y0,x1,y1), keepouts [(x0,y0,x1,y1) px], lang, max_bytes}."""
    from . import platform as P
    prof = P.parse_targets([platform])[0]
    W, H = P.cover_size(prof)
    ko = prof.cover.get("keepouts")
    if ko:
        keep = [tuple(int(v) for v in k) for k in ko]
    else:
        keep = [(int(a * W), int(b * H), int(c * W), int(d * H)) for a, b, c, d in DEFAULT_KEEPOUTS.get(prof.name, [])]
    return dict(name=prof.name, key=prof.key, size=(W, H), safe=tuple(P.cover_title_safe(prof)), keepouts=keep,
                lang=P.lang_for(prof.name, "en"), max_bytes=prof.cover.get("max_bytes"))


# ---------------------------------------------------------------- frame analysis
def analyse(img, matte_engine="auto", log=None):
    """PIL frame -> {img, sal (HxW 0..1 at ANALYSIS_W), faces [(x0,y0,x1,y1) fractions], alpha (full size 0..1 or
    None), matte (engine name or None), subject_box (fractions or None)}."""
    import cv2
    say = log or (lambda m: None)
    im = img.convert("RGB")
    bgr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    h = int(round(ANALYSIS_W * im.height / im.width))
    small = cv2.resize(bgr, (ANALYSIS_W, h), interpolation=cv2.INTER_AREA)
    from . import saliency as S
    try:
        sal = S.Analyzer(person=False)(small)["map"]
        sal = cv2.resize(sal.astype(np.float32), (ANALYSIS_W, h))
    except Exception as e:  # noqa: BLE001
        say(f"cover: saliency skipped ({str(e)[:80]})")
        sal = np.zeros((h, ANALYSIS_W), np.float32)
    faces = []
    try:
        from . import face as F
        lm = F.landmarker(4)
        try:
            for f in F.detect(lm, small) or []:
                p = f["pts"]
                x0, y0, x1, y1 = p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()
                faces.append((x0 / ANALYSIS_W, y0 / h, x1 / ANALYSIS_W, y1 / h))
        finally:
            lm.close()
    except Exception as e:  # noqa: BLE001
        say(f"cover: face detection skipped ({str(e)[:80]})")
    alpha, engine, box, top = None, None, None, None
    try:
        from . import matte as M
        _, alpha, engine = M.matte(bgr, matte_engine, log=say)
        m = alpha > 0.5
        area = float(m.mean())
        if 0.002 < area < 0.7:
            ys, xs = np.nonzero(m)
            box = (xs.min() / im.width, ys.min() / im.height, (xs.max() + 1) / im.width, (ys.max() + 1) / im.height)
            top = subject_top(m)
        else:
            alpha = None if area <= 0.002 else alpha
    except Exception as e:  # noqa: BLE001  (no matte engine: saliency + faces still place the text)
        say(f"cover: subject matte skipped ({str(e)[:100]})")
    return dict(img=im, sal=sal, faces=faces, alpha=alpha, matte=engine, subject_box=box, subject_top=top)


def subject_top(mask):
    """The subject's tip (a spire, a mast, a head): (x0, x1, y_top, height) as fractions of the frame - the columns
    the matte fills in its top 6 %. A matte loses thin tips (the Space Needle's antenna), so ``occupancy`` keeps
    the space above this band clear as well."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return None
    H, W = mask.shape
    y0, y1 = int(ys.min()), int(ys.max())
    band = xs[ys <= y0 + max(2, int((y1 - y0) * 0.06))]
    return (float(band.min()) / W, float(band.max() + 1) / W, y0 / H, (y1 - y0 + 1) / H)


def occupancy(an, crop, size):
    """Where text must not go, on the cover canvas (W x H float 0..1): saliency + subject matte + faces (padded)."""
    import cv2
    W, H = size
    x0, y0, x1, y1 = crop
    iw, ih = an["img"].size
    sal = an["sal"]
    sh, sw = sal.shape
    sx0, sy0, sx1, sy1 = (int(x0 / iw * sw), int(y0 / ih * sh), max(int(x0 / iw * sw) + 1, int(x1 / iw * sw)),
                          max(int(y0 / ih * sh) + 1, int(y1 / ih * sh)))
    occ = cv2.resize(sal[sy0:sy1, sx0:sx1], (W, H), interpolation=cv2.INTER_LINEAR) * 0.7
    if an["alpha"] is not None:
        a = an["alpha"][int(y0):int(y1), int(x0):int(x1)]
        a = cv2.resize(a.astype(np.float32), (W, H), interpolation=cv2.INTER_AREA)
        occ = np.maximum(occ, cv2.dilate(a, np.ones((max(3, W // 60),) * 2, np.uint8)))
    tip = an.get("subject_top")
    if tip:                                            # the subject's tip and the air just above it
        tx0, tx1, ty, sh_ = tip
        cx0, cx1 = (tx0 * iw - x0) / (x1 - x0) * W, (tx1 * iw - x0) / (x1 - x0) * W
        cy = (ty * ih - y0) / (y1 - y0) * H
        sub_h = sh_ * ih / (y1 - y0) * H
        px = max(W * 0.03, (cx1 - cx0) * 0.6)
        up = max(H * 0.07, sub_h * 0.18)
        r0, r1 = max(0, int(cy - up)), max(0, int(cy + max(H * 0.02, sub_h * 0.06)))
        c0, c1 = max(0, int(cx0 - px)), max(0, int(cx1 + px))
        if r1 > r0 and c1 > c0:
            occ[r0:r1, c0:c1] = 1.0
    for fx0, fy0, fx1, fy1 in an["faces"]:
        bx0, by0 = (fx0 * iw - x0) / (x1 - x0) * W, (fy0 * ih - y0) / (y1 - y0) * H
        bx1, by1 = (fx1 * iw - x0) / (x1 - x0) * W, (fy1 * ih - y0) / (y1 - y0) * H
        px, py = (bx1 - bx0) * 0.35, (by1 - by0) * 0.35
        occ[max(0, int(by0 - py)):max(0, int(by1 + py)), max(0, int(bx0 - px)):max(0, int(bx1 + px))] = 1.0
    return np.clip(occ, 0, 1)


def crop_box(an, aspect, zoom=1.0):
    """(x0, y0, x1, y1) source pixels of the ``aspect`` (w/h) crop that holds the most subject / saliency;
    ``zoom`` > 1 crops tighter around the subject box (capped so the subject still fits)."""
    iw, ih = an["img"].size
    if iw / ih > aspect:
        cw, ch = ih * aspect, float(ih)
    else:
        cw, ch = float(iw), iw / aspect
    cw, ch = cw / zoom, ch / zoom
    sb = an["subject_box"]
    if zoom > 1 and sb:                                       # never cut the subject: shrink the zoom
        sw_, sh_ = (sb[2] - sb[0]) * iw * 1.25, (sb[3] - sb[1]) * ih * 1.25
        k = max(1.0, sw_ / cw, sh_ / ch)
        cw, ch = min(cw * k, iw if iw / ih <= aspect else ih * aspect), min(ch * k, ih)
    sal = an["sal"].astype(np.float64)
    w = sal.copy()
    if an["alpha"] is not None:
        import cv2
        w += cv2.resize(an["alpha"].astype(np.float32), (sal.shape[1], sal.shape[0])) * 1.5
    sh, sw = w.shape
    if sb:
        cx, cy = (sb[0] + sb[2]) / 2 * iw, (sb[1] + sb[3]) / 2 * ih
    else:
        ys, xs = np.mgrid[0:sh, 0:sw]
        tot = w.sum() + 1e-6
        cx, cy = (xs * w).sum() / tot / sw * iw, (ys * w).sum() / tot / sh * ih
    x0 = min(max(0.0, cx - cw / 2), iw - cw)
    y0 = min(max(0.0, cy - ch / 2), ih - ch)
    return (int(x0), int(y0), int(x0 + cw), int(y0 + ch))


def third_boxes(an, box):
    """A narrow subject (a tower, a mast, one person) in a crop with room to slide: the same crop with the subject
    on the left / right third, so the title gets the other two thirds instead of squeezing beside a centred one."""
    sb = an["subject_box"]
    if not sb:
        return []
    iw, _ = an["img"].size
    x0, y0, x1, y1 = box
    cw = x1 - x0
    sw = (sb[2] - sb[0]) * iw
    if cw >= iw * 0.98 or sw > cw * 0.3:
        return []
    cx = (sb[0] + sb[2]) / 2 * iw
    out = []
    for f in (2 / 3, 1 / 3):
        nx = int(min(max(0.0, cx - cw * f), iw - cw))
        if abs(nx - x0) > cw * 0.08 and sb[0] * iw >= nx and sb[2] * iw <= nx + cw:
            out.append((nx, y0, nx + cw, y1))
    return out


# ---------------------------------------------------------------- type
def _font_roles(lang, variant):
    """(title role, kicker role): the theme's tokens (font_title / font_strong, the typography kit's display roles
    when installed), falling back to the bundled OFL faces."""
    from . import config
    roles = {}
    try:
        from . import theme
        T = theme.resolve(recipe="vlog")
        roles = {k: T.get(k) for k in ("font_title", "font_strong", "font_body", "font_label", "font_display")
                 if T.get(k)}
    except Exception:  # noqa: BLE001
        pass

    def have(role):
        try:
            return bool(role) and bool(config.font(role))
        except Exception:  # noqa: BLE001
            return False
    if variant == "text":
        cands = [roles.get("font_display"), "display-latin" if lang == "en" else "display-zh-modern",
                 roles.get("font_strong"), "cjk-bold"]
    else:
        cands = [roles.get("font_title"), "cjk-serif-bold", "cjk-bold"]
    title = next((r for r in cands if have(r)), "cjk-bold")
    kick = next((r for r in [roles.get("font_body"), "cjk"] if have(r)), "cjk")
    return title, kick


def _font(role, size):
    from .draw import load_font
    return load_font(role, size)


_NO_START = set("，。、；：？！）》」』”’,.;:?!)")
_AFTER_NUMBER = set("年月日号届岁米度位个座条次周%")


def _zh_words(text):
    """Chinese text -> words (jieba, in the runtime for the free voice) so a line never breaks inside a word
    (华盛顿东部 / 公路旅行, not 华盛顿东 / 部公路旅行); characters when jieba is missing."""
    try:
        import logging

        import jieba
        jieba.setLogLevel(logging.WARNING)
        return [w for w in jieba.cut(text) if w]
    except Exception:  # noqa: BLE001
        return list(text)


def _wrap(text, f, maxw, lang, max_lines=2):
    """Balanced lines (the widest line as short as possible) no wider than ``maxw``: English at spaces, Chinese at
    any character but never a line starting with closing punctuation (避头尾) or a one-character line."""
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    cjk = lang == "zh" and " " not in text.strip()
    toks = _zh_words(text) if cjk else text.split()
    join = (lambda xs: "".join(xs)) if cjk else (lambda xs: " ".join(xs))
    n = len(toks)
    best = None

    def ok_break(i):
        prev = toks[i - 1].strip()
        if prev and prev[-1].isdigit() and toks[i].strip()[:1] in _AFTER_NUMBER:   # 1962 年 stays one unit
            return False
        if not cjk:
            return True
        a, b = len("".join(toks[:i])), len("".join(toks[i:]))
        return toks[i][0] not in _NO_START and a >= 2 and b >= 2
    if max_lines >= 2:
        for i in range(1, n):
            if not ok_break(i):
                continue
            lines = [join(toks[:i]), join(toks[i:])]
            w = max(d.textlength(x, font=f) for x in lines)
            if w <= maxw and (best is None or w < best[0]):
                best = (w, lines)
    if best:
        return best[1]
    if max_lines >= 3:
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                if not (ok_break(i) and ok_break(j)):
                    continue
                lines = [join(toks[:i]), join(toks[i:j]), join(toks[j:])]
                w = max(d.textlength(x, font=f) for x in lines)
                if w <= maxw and (best is None or w < best[0]):
                    best = (w, lines)
    return best[1] if best else None


def layout_text(title, kicker, lang, size, variant, box_w):
    """-> dict(lines, title_font, title_size, kicker_text, kicker_font, kicker_size, track, w, h, line_h) fitted in
    ``box_w``: the title as large as the variant allows, shrinking before it wraps (max 2 lines)."""
    W, H = size
    trole, krole = _font_roles(lang, variant)
    base = {"scene": 0.135, "subject": 0.16, "text": 0.185}[variant] * H
    if W < H:                                    # portrait canvases: the width limits
        base = min(base, W * (0.16 if lang == "en" else 0.17))
    if lang == "zh":
        base *= 0.9
    d = ImageDraw.Draw(Image.new("L", (1, 1)))

    def biggest(nlines):
        """Largest size <= base at which the title fits in ``nlines`` balanced lines -> (size, lines) or None."""
        s = int(base)
        while s >= int(base * 0.4):
            f = _font(trole, s)
            ls = [title] if nlines == 1 and d.textlength(title, font=f) <= box_w else \
                (_wrap(title, f, box_w, lang, max_lines=nlines) if nlines > 1 else None)
            if ls and len(ls) <= nlines:
                return s, ls
            s = int(s * 0.95)
        return None
    one, two = biggest(1), biggest(2)
    # two lines when they buy real size (a one-liner that had to shrink a lot reads small on a phone)
    pick = two if two and (not one or two[0] > one[0] * 1.22) else one
    if not pick:
        pick = biggest(3) or (int(base * 0.4), [title])
    s, lines = pick
    tf = _font(trole, s)
    ks = max(12, int(s * (0.27 if lang == "en" else 0.32)), int(min(W, H) * 0.026))
    kt = kicker.upper() if lang == "en" else kicker
    kf = _font(krole, ks)
    track = ks * (0.22 if lang == "en" else 0.12)

    def kw(t):
        return sum(d.textlength(c, font=kf) for c in t) + track * max(0, len(t) - 1)
    while kt and kw(kt) > box_w and ks > 11:
        ks -= 1
        kf = _font(krole, ks)
        track = ks * (0.22 if lang == "en" else 0.12)
    lh = int(s * (1.08 if lang == "en" else 1.2))
    tw = max(d.textlength(ln, font=tf) for ln in lines)
    kh = int(ks * 2.2) if kt else 0
    return dict(lines=lines, tf=tf, ts=s, kt=kt, kf=kf, ks=ks, track=track, lh=lh, w=int(max(tw, kw(kt) if kt else 0)),
                h=lh * len(lines) + kh, kw=kw(kt) if kt else 0, kh=kh)


def place(occ, L, safe, keepouts, align_pref=("left", "center", "right")):
    """Best (x, y, align) for a text block of L["w"] x L["h"] inside ``safe``, clear of ``keepouts``: lowest mean
    occupancy under the block (+ a margin), a small preference for the lower-left / left third."""
    H, W = occ.shape
    sx0, sy0, sx1, sy1 = safe
    bw, bh = L["w"], L["h"]
    best = None
    ys = np.linspace(sy0, max(sy0, sy1 - bh), 9)
    for align in align_pref:
        if align == "left":
            xs = [sx0]
        elif align == "right":
            xs = [sx1 - bw]
        else:
            xs = [(sx0 + sx1 - bw) / 2]
        for x in xs:
            if x < sx0 - 1 or x + bw > sx1 + 1:
                continue
            for y in ys:
                x0, y0, x1, y1 = int(x), int(y), int(x + bw), int(y + bh)
                pad = int(bh * 0.25)
                reg = occ[max(0, y0 - pad):min(H, y1 + pad), max(0, x0 - pad):min(W, x1 + pad)]
                cost = float(reg.mean()) + 0.5 * float(np.percentile(reg, 90)) if reg.size else 1.0
                core = occ[max(0, y0):min(H, y1), max(0, x0):min(W, x1)]
                if core.size:                              # never type over the subject / a face itself
                    hit = float((core >= 0.9).mean())
                    cost += 6.0 * hit + (1.5 if hit > 0.002 else 0.0)   # even a thin tower / mast
                if any(x0 < kx1 and x1 > kx0 and y0 < ky1 and y1 > ky0 for kx0, ky0, kx1, ky1 in keepouts):
                    cost += 5.0
                cy = (y0 + y1) / 2 / H
                cost += 0.04 * (0.0 if align == "left" else 1.0) + 0.05 * abs(cy - 0.72)
                if best is None or cost < best[0]:
                    best = (cost, int(x), int(y), align)
    return best


def _lum(rgb):
    a = np.asarray(rgb, np.float32) / 255.0
    a = np.where(a <= 0.03928, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def _texture(reg):
    """Fine texture (0..~0.2): mean |luminance - its blur| - high for foliage / ripples, ~0 for a sky gradient."""
    import cv2
    if not reg.size:
        return 0.0
    lum = _lum(reg).astype(np.float32)
    return float(np.abs(lum - cv2.GaussianBlur(lum, (0, 0), 3)).mean())


def _contrast(l1, l2):
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def draw_block(base, L, x, y, align, occ_alpha=None, scrim=True, depth=None):
    """Draw the text block onto ``base`` (PIL RGB) -> (image, glyph mask L). ``scrim``: a feathered local darkening
    just strong enough for contrast 4.5 against the ink (no box, no band edge). ``depth``: the subject alpha on the
    canvas - drawn back over the title (the subject in front of the type)."""
    W, H = base.size
    bw, bh = L["w"], L["h"]
    x0 = x
    lay = Image.new("L", (W, H), 0)
    kl = Image.new("L", (W, H), 0)
    d, dk = ImageDraw.Draw(lay), ImageDraw.Draw(kl)
    yy = y
    if L["kt"]:
        kx = x0 if align == "left" else (x0 + bw - L["kw"] if align == "right" else x0 + (bw - L["kw"]) / 2)
        for c in L["kt"]:
            dk.text((kx, yy), c, font=L["kf"], fill=255)
            kx += dk.textlength(c, font=L["kf"]) + L["track"]
        yy += L["kh"]
    for ln in L["lines"]:
        lw = d.textlength(ln, font=L["tf"])
        lx = x0 if align == "left" else (x0 + bw - lw if align == "right" else x0 + (bw - lw) / 2)
        d.text((lx, yy), ln, font=L["tf"], fill=255)
        yy += L["lh"]
    glyphs = Image.fromarray(np.maximum(np.asarray(lay), np.asarray(kl)))
    out = base.convert("RGB")
    if scrim:
        ys, xs = np.nonzero(np.asarray(glyphs) > 0)
        if len(xs):
            reg = np.asarray(out)[max(0, ys.min() - 8):ys.max() + 8, max(0, xs.min() - 8):xs.max() + 8]
            lbg = float(np.percentile(_lum(reg), 85)) if reg.size else 0.0
            need = (_lum(np.array(INK)) + 0.05) / 4.5 - 0.05           # max bg luminance for contrast 4.5
            a = float(np.clip(1.0 - need / max(lbg, 1e-3), 0.0, 0.72))
            a = max(a, float(np.clip((_texture(reg) - 0.035) * 6.0, 0.0, 0.45)))   # foliage / ripples fight type
            if a > 0.02:
                m = Image.new("L", (W, H), 0)
                pad = int(L["ts"] * 0.9)
                ImageDraw.Draw(m).rectangle([xs.min() - pad, ys.min() - pad, xs.max() + pad, ys.max() + pad],
                                            fill=int(255 * a))
                m = m.filter(ImageFilter.GaussianBlur(max(8, int(L["ts"] * 0.9))))
                out = Image.composite(Image.new("RGB", (W, H), (6, 6, 8)), out, m)
    sh = glyphs.filter(ImageFilter.GaussianBlur(max(2, L["ts"] // 14))).point(lambda v: int(v * 0.55))
    out = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), out, sh)
    ink = Image.new("RGB", (W, H), INK)
    out = Image.composite(ink, out, lay)
    out = Image.composite(Image.new("RGB", (W, H), CHAMPAGNE), out, kl)
    if depth is not None:                                         # the subject back in front of the title
        out = Image.composite(depth[0], out, depth[1])
        glyphs = Image.fromarray((np.asarray(glyphs) * (1 - np.asarray(depth[1]) / 255.0)).astype(np.uint8))
    return out, glyphs


def legibility(img, glyphs, title_size, sizes=SMALL_SIZES):
    """Render the cover at each small size: headline height (cap height of the title font, as a share of the
    thumbnail height) and contrast (median luminance of glyph pixels vs the ring around them). ok when every size
    passes ``MIN_HEIGHT`` and ``MIN_CONTRAST``."""
    import cv2
    W, H = img.size
    rows = []
    for sw, sh in sizes:
        if H > W:                                   # a portrait cover is shown as a portrait thumbnail
            sw, sh = sh, sw
        k = min(sw / W, sh / H)
        tw, th = max(1, int(W * k)), max(1, int(H * k))
        small = np.asarray(img.resize((tw, th), Image.LANCZOS))
        m = np.asarray(glyphs.resize((tw, th), Image.BOX)) > 110
        height = title_size * 0.7 * k / min(tw, th)  # cap height / the thumbnail's short side
        if not m.any():
            rows.append(dict(size=f"{sw}x{sh}", height=round(height, 4), contrast=0.0, ok=False))
            continue
        ring = cv2.dilate(m.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & ~m
        lt = float(np.median(_lum(small[m])))
        lb = float(np.median(_lum(small[ring]))) if ring.any() else 0.0
        c = _contrast(lt, lb)
        rows.append(dict(size=f"{sw}x{sh}", height=round(height, 4), contrast=round(c, 2),
                         ok=bool(height >= MIN_HEIGHT and c >= MIN_CONTRAST)))
    return dict(ok=all(r["ok"] for r in rows), sizes=rows)


# ---------------------------------------------------------------- variants
def _grade_down(im, k=0.62, sat=0.8):
    from PIL import ImageEnhance
    return ImageEnhance.Brightness(ImageEnhance.Color(im).enhance(sat)).enhance(k)


def render_variant(an, sp, title, kicker, variant, log=None):
    """One cover for one platform spec -> dict(image, glyphs, legibility, cost, variant, crop, upscale)."""
    from .upscale import upscale_to
    W, H = sp["size"]
    zoom = {"scene": 1.0, "subject": 1.45, "text": 1.0}[variant]
    if variant == "subject" and not (an["subject_box"] or an["faces"]):
        zoom = 1.25
    sx0, sy0, sx1, sy1 = sp["safe"]
    margin = int(min(W, H) * 0.06)
    safe = (max(sx0, margin), max(sy0, margin), min(sx1, W - margin), min(sy1, H - margin))
    box_w = int((safe[2] - safe[0]) * ((0.8 if variant == "text" else 0.62) if W > H else 0.92))
    base = crop_box(an, W / H, zoom)
    best = None
    for bi, box in enumerate([base] + third_boxes(an, base)):
        occ = occupancy(an, box, (W, H))
        if variant == "text":
            occ = np.where(occ >= 0.9, occ, occ * 0.35)    # a graded backdrop: type may take the space, not the subject
        for k in (1.0, 0.8, 0.64, 0.5, 0.4):           # every spot hits the subject: smaller type before overlap
            Lk = layout_text(title, kicker, sp["lang"], (W, H), variant, int(box_w * k))
            Lk = dict(Lk, w=min(Lk["w"], int(box_w * k)))
            pk = place(occ, Lk, safe, sp["keepouts"])
            if not pk:
                continue
            total = pk[0] + 0.8 * (1 - k) + (0.08 if bi else 0.0)   # smaller type / an off-centre crop only
            if best is None or total < best[2]:                       # for a much cleaner spot
                best = (pk, Lk, total, box)
            if best[2] < 0.35:
                break
        if best and best[2] < 0.35:
            break
    if best is None:
        return None
    (cost, x, y, align), L, _, box = best
    src = an["img"].crop(box)
    src, how = upscale_to(src, (W, H), log=log)
    canvas = src.resize((W, H), Image.LANCZOS)
    if variant == "text":
        canvas = _grade_down(canvas)
    depth = None
    if variant == "subject" and an["alpha"] is not None:
        import cv2
        a = an["alpha"][box[1]:box[3], box[0]:box[2]]
        a = cv2.resize(a.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
        ta = np.zeros((H, W), bool)
        ta[y:y + L["h"], x:x + L["w"]] = True
        ov = float((a[ta] > 0.5).mean()) if ta.any() else 0.0
        if 0.05 < ov < 0.3:                                # the subject overlaps the title a little: depth
            depth = (canvas.copy(), Image.fromarray((a * 255).astype(np.uint8)))
    img, glyphs = draw_block(canvas, L, x, y, align, depth=depth)
    leg = legibility(img, glyphs, L["ts"])
    return dict(image=img, glyphs=glyphs, legibility=leg, cost=round(cost, 4), variant=variant, crop=list(box),
                upscale=how, depth=depth is not None, title=title, kicker=kicker, font_size=L["ts"],
                lines=L["lines"])


def _rank(v):
    leg = v["legibility"]
    worst_h = min(r["height"] for r in leg["sizes"])
    worst_c = min(r["contrast"] for r in leg["sizes"])
    return (0 if leg["ok"] else 1, round(v["cost"] - 0.6 * min(worst_h, 0.12) - 0.02 * min(worst_c, 8), 4))


def _save(img, path, max_bytes=None):
    q = 92
    img.save(path, quality=q)
    while max_bytes and os.path.getsize(path) > max_bytes and q > 60:
        q -= 8
        img.save(path, quality=q)
    return path


def make_covers(frame, texts, platforms, out_dir, stem="cover", matte_engine="auto", log=print, ab=3):
    """Covers for ``platforms`` from one frame (path / PIL). ``texts``: {"en": ..., "zh": ...} or one (bilingual)
    string split by ``mono_text``. -> {platform: {file, lang, title, kicker, variant, legibility, variants:
    [{file, variant, ok, ...}] (YouTube: the ``ab`` A/B pack, best first)}} + "_analysis"; also <stem>.covers.json."""
    os.makedirs(out_dir, exist_ok=True)
    im = Image.open(frame).convert("RGB") if isinstance(frame, (str, os.PathLike)) else frame.convert("RGB")
    an = analyse(im, matte_engine, log=log)
    if isinstance(texts, str):
        texts = {"en": mono_text(texts, "en"), "zh": mono_text(texts, "zh")}
    res = {"_analysis": dict(matte=an["matte"], faces=len(an["faces"]), subject_box=an["subject_box"])}
    for plat in platforms:
        sp = plat if isinstance(plat, dict) else spec_for(plat)
        plat = sp["key"] if isinstance(plat, dict) else plat
        text = texts.get(sp["lang"]) or ""
        tag = re.sub(r"[^a-z0-9-]+", "-", sp["key"].replace(":", "-"))
        if not text.strip():
            log(f"cover: no {sp['lang']} text for {plat}; the frame alone")
            path = _save(render_plain(an, sp), os.path.join(out_dir, f"{stem}.{tag}.jpg"), sp["max_bytes"])
            res[plat] = dict(file=path, lang=sp["lang"], title="", variant="plain", variants=[])
            continue
        title, kicker = title_parts(text, sp["lang"])
        names = VARIANTS if sp["name"] == "youtube" and ab else VARIANTS[:2]
        vs = [v for v in (render_variant(an, sp, title, kicker, n, log=log) for n in names) if v]
        vs.sort(key=_rank)
        if sp["name"] == "youtube" and ab:
            files = []
            for k, v in enumerate(vs[:ab]):
                p = _save(v["image"], os.path.join(out_dir, f"{stem}.{tag}.ab{k + 1}.jpg"), sp["max_bytes"])
                files.append(dict(file=p, **_meta(v)))
        else:
            files = []
        best = vs[0]
        path = _save(best["image"], os.path.join(out_dir, f"{stem}.{tag}.jpg"), sp["max_bytes"])
        if not best["legibility"]["ok"]:
            log(f"cover: {plat}: no variant passed the small-size legibility check; kept the most legible")
        res[plat] = dict(file=path, lang=sp["lang"], **_meta(best), variants=files)
    with open(os.path.join(out_dir, f"{stem}.covers.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    return res


def single_cover(frame, text, out_path, platform=None, variant=None, log=None):
    """One designed cover at the frame's own size (or ``platform``'s cover size) -> out_path. The text is made
    monolingual: the platform's language, else Chinese when it has any, else English. ``variant``: scene |
    subject | text (default: the most legible of scene / subject)."""
    im = Image.open(frame).convert("RGB") if isinstance(frame, (str, os.PathLike)) else frame.convert("RGB")
    if platform:
        sp = spec_for(platform)
    else:
        W, H = im.size
        m = int(min(W, H) * 0.06)
        sp = dict(name="generic", key="generic", size=(W, H), safe=(m, m, W - m, H - m), keepouts=[],
                  lang="zh" if has_cjk(text) else "en", max_bytes=None)
    txt = mono_text(text, sp["lang"]) or str(text or "")
    an = analyse(im, log=log)
    if not txt.strip():
        return _save(render_plain(an, sp), out_path, sp["max_bytes"])
    title, kicker = title_parts(txt, sp["lang"])
    vs = [v for v in (render_variant(an, sp, title, kicker, n, log=log) for n in ([variant] if variant else
                                                                                VARIANTS[:2])) if v]
    if not vs:
        raise RuntimeError("cover: no text placement fits this canvas")
    vs.sort(key=_rank)
    return _save(vs[0]["image"], out_path, sp["max_bytes"])


def _meta(v):
    return dict(variant=v["variant"], title=v["title"], kicker=v["kicker"], ok=v["legibility"]["ok"],
                legibility=v["legibility"], crop=v["crop"], upscale=v["upscale"], depth=v["depth"],
                font_size=v["font_size"], lines=v["lines"])


def render_plain(an, sp):
    from .upscale import upscale_to
    W, H = sp["size"]
    box = crop_box(an, W / H)
    src, _ = upscale_to(an["img"].crop(box), (W, H))
    return src.resize((W, H), Image.LANCZOS)


def ab_note(res, lang="en"):
    """Markdown for the publish package: the YouTube A/B pack and how to test it."""
    yt = res.get("youtube") or {}
    vs = yt.get("variants") or []
    if len(vs) < 2:
        return ""
    names = {"scene": "full-bleed scene", "subject": "subject close-up", "text": "text-led"}
    rows = [f"{k + 1}. `{os.path.basename(v['file'])}` - {names.get(v['variant'], v['variant'])}"
            + ("" if v["ok"] else " (fails the small-size legibility check)") for k, v in enumerate(vs)]
    return ("## YouTube thumbnail A/B test\n\nUpload all three in YouTube Studio > the video > Thumbnail > "
            "Test & Compare; YouTube picks the winner by watch-time share. Variant 1 is the default cover.\n\n"
            + "\n".join(rows) + "\n")
