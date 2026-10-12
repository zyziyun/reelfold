#!/usr/bin/env python3
"""Cover image: dark title zone (kicker, title, EN subtitle, tagline with a red-pen-circled keyword),
a hero polaroid showing an A|B split (draft|final, before|after), and a row of taped polaroids
(optional caption + red circle) on paper. Everything comes from spec COVER; size = spec canvas.

    python3 cover.py spec.py [--out cover.png]

COVER = dict(kicker=, title=, subtitle=, tagline=(before, keyword, after),
             hero=dict(a=img, b=img, labels=(la, lb), c=(x,y), z=1.0)  or hero=dict(src=img),
             polaroids=[dict(src=, caption=, rot=, c=, z=, circle=(cx,cy,rx,ry)), ...],  out=)
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw

from vstudio import cover as vcover

from photostory.ctx import Ctx, _font_path, font_for, load_spec
from photostory.util import crop_aspect, has_cjk


def _zh(t):
    s = " ".join(map(str, t)) if isinstance(t, (list, tuple)) else str(t or "")
    return any("\u3400" <= ch <= "\u9fff" for ch in s)


def english_cover(spec, C):
    """The cover of an English-only platform (YouTube / Shorts): spec COVER_EN over COVER when the spec has one;
    every text still in Chinese is replaced (title -> TITLE_EN) or left out (kicker, subtitle, tagline, captions)."""
    cfg = dict(getattr(spec, "COVER", {}) or {})
    cfg.update(dict(getattr(spec, "COVER_EN", {}) or {}))
    if _zh(cfg.get("title", C.TITLE_ZH or C.TITLE_EN)):
        cfg["title"] = C.TITLE_EN or ""
    cfg.setdefault("title", C.TITLE_EN or "")
    sub = cfg.get("subtitle", "")
    cfg["subtitle"] = "" if _zh(sub) or str(sub).strip() == str(cfg["title"]).strip() else sub
    for k in ("kicker", "tagline"):
        if _zh(cfg.get(k)):
            cfg.pop(k)
    cfg["polaroids"] = [dict(p, caption=None) if _zh(p.get("caption")) else p for p in cfg.get("polaroids") or []]
    hero = dict(cfg.get("hero") or {})
    if hero.get("a") and (_zh(hero.get("labels")) or "labels" not in hero):
        hero["labels"] = ("Draft", "Final")          # the split hero's default labels are bilingual
        cfg["hero"] = hero
    return cfg


def polaroid(im, size, rot, k, cap=None, seed=0):
    """vstudio.cover.polaroid with the story's caption font (sans for latin, cjk for 中文)."""
    role = "cjk" if cap and has_cjk(cap) else "sans"
    return vcover.polaroid(im, size, rot=rot, cap=cap, scale=k, seed=seed, cap_role=_font_path(role))


def circled(im, ell, red):
    a = np.asarray(im).copy()
    h, w = a.shape[:2]
    cx, cy, rx, ry = ell
    cv2.ellipse(a, (int(cx * w), int(cy * h)), (int(rx * w), int(ry * h)), -6, -100, 282, red, max(4, w // 60), cv2.LINE_AA)
    return Image.fromarray(a)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--out")
    ap.add_argument("--platform", help="override spec PLATFORM (cover size = vstudio.platform.cover_size)")
    a = ap.parse_args()
    spec = load_spec(a.spec)
    if a.platform:
        spec.PLATFORM = a.platform
    C = Ctx(spec)
    cfg = english_cover(spec, C) if C.SUBS == "en" else dict(getattr(spec, "COVER", {}) or {})
    if C.prof is not None:
        from vstudio import platform as vplat
        W, H = tuple(cfg.get("size", vplat.cover_size(C.prof)))
    else:
        W, H = tuple(cfg.get("size", (C.W, C.H)))
    out = a.out or C.path(cfg.get("out", "cover.png"))
    if C.cinema and cfg.get("style") != "scrapbook":
        print("cover:", cinema_cover(C, cfg, W, H, out))
        return
    k = min(W / 1620, H / 2160)
    q = lambda v: int(round(v * k))
    GOLD, RED = C.GOLD, C.pal["mark"]
    top = int(H * 600 / 2160)

    cv = Image.new("RGB", (W, H), C.pal["ground"])
    rng = np.random.default_rng(3)
    ph = H - top
    paper = np.full((ph, W, 3), C.pal["paper"], np.float32)
    paper += cv2.GaussianBlur(rng.normal(0, 1, (ph, W)).astype(np.float32), (0, 0), 1.2)[..., None] * 6
    paper += cv2.GaussianBlur(rng.normal(0, 1, (ph, W)).astype(np.float32), (0, 0), 9)[..., None] * 10
    yy, xx = np.mgrid[0:ph, 0:W]
    paper *= (1 - 0.35 * (((xx - W / 2) / W) ** 2 + ((yy - ph / 2) / ph) ** 2) * 2)[..., None]
    cv.paste(Image.fromarray(np.clip(paper, 0, 255).astype(np.uint8)), (0, top))
    d = ImageDraw.Draw(cv)

    def ct(y, t, f, fill):
        d.text((W / 2, y), t, font=f, fill=fill, anchor="mt")
        return d.textbbox((W / 2, y), t, font=f, anchor="mt")[3]

    y = q(52)
    if cfg.get("kicker"):
        y = ct(y, cfg["kicker"], font_for(cfg["kicker"], q(60), "serif-italic", "cjk-serif"), GOLD) + q(20)
    title = cfg.get("title", C.TITLE_ZH or C.TITLE_EN)
    if title:
        tf = font_for(title, q(150), "serif-italic", "cjk-serif")
        while d.textlength(title, font=tf) > W * 0.92 and tf.size > 20:
            tf = font_for(title, tf.size - 4, "serif-italic", "cjk-serif")
        y = ct(y, title, tf, (250, 245, 235)) + q(28)
    sub = cfg.get("subtitle", C.TITLE_EN if title != C.TITLE_EN else "")
    if sub:
        y = ct(y, sub, font_for(sub, q(44), "serif-italic", "cjk"), (205, 188, 155)) + q(30)
    tag = cfg.get("tagline")
    if tag:
        t1, t2, t3 = (tuple(tag) + ("", "", ""))[:3]
        f = font_for(t1 + t2 + t3, q(92), "serif-italic", "cjk-serif")
        x = (W - d.textlength(t1 + t2 + t3, font=f)) / 2
        d.text((x, y), t1, font=f, fill=(245, 238, 225)); x += d.textlength(t1, font=f)
        d.text((x, y), t2, font=f, fill=GOLD); x2 = x; x += d.textlength(t2, font=f)
        d.text((x, y), t3, font=f, fill=(245, 238, 225))
        if t2:   # red pen around the keyword
            bb = d.textbbox((x2, y), t2, font=f)
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            rx, ry = (bb[2] - bb[0]) / 2 + q(18), (bb[3] - bb[1]) / 2 + q(18)
            arr = np.asarray(cv).copy()
            cv2.ellipse(arr, (int(cx), int(cy)), (int(rx), int(ry)), -6, -100, 285, RED, max(2, q(8)), cv2.LINE_AA)
            cv2.ellipse(arr, (int(cx) + q(4), int(cy) - q(3)), (int(rx * 1.05), int(ry * 0.94)), -3, -96, 270, RED,
                        max(1, q(3)), cv2.LINE_AA)
            cv = Image.fromarray(arr)
            d = ImageDraw.Draw(cv)

    # hero: A|B split on a polaroid
    hero = cfg.get("hero")
    S0 = min(q(860), int(W * 0.6), int(H * 0.4))
    hero_bottom = top
    if hero:
        c, z = tuple(hero.get("c", (0.5, 0.5))), hero.get("z", 1.0)
        if "a" in hero:
            A = crop_aspect(C.open_img(hero["a"]), c, z, 1.0).resize((S0, S0), Image.LANCZOS)
            B = crop_aspect(C.open_img(hero["b"]), c, z, 1.0).resize((S0, S0), Image.LANCZOS)
            img = A.copy()
            img.paste(B.crop((S0 // 2, 0, S0, S0)), (S0 // 2, 0))
            hd = ImageDraw.Draw(img)
            hd.rectangle((S0 // 2 - q(3), 0, S0 // 2 + q(3), S0), fill=GOLD)
            hd.ellipse((S0 // 2 - q(24), S0 // 2 - q(24), S0 // 2 + q(24), S0 // 2 + q(24)), fill=GOLD)
            hd.ellipse((S0 // 2 - q(10), S0 // 2 - q(10), S0 // 2 + q(10), S0 // 2 + q(10)), fill=(30, 24, 18))
            la, lb = hero.get("labels", ("草稿 Draft", "成品 Final"))
            for x0, t in ((q(24), la), (S0 - q(24) - q(230), lb)):
                hd.rounded_rectangle((x0, q(24), x0 + q(230), q(86)), q(12), fill=(18, 14, 10))
                hd.text((x0 + q(115), q(55)), t, font=font_for(t, q(34), "sans", "cjk"), fill=(245, 238, 225), anchor="mm")
        else:
            img = crop_aspect(C.open_img(hero["src"]), c, z, 1.0).resize((S0, S0), Image.LANCZOS)
        card = polaroid(img, (S0, S0), hero.get("rot", -2.5), k, None, 1)
        hy = max(int(top + q(50)), int(y + q(40)))
        cv.paste(card, ((W - card.width) // 2, hy), card)
        hero_bottom = hy + card.height

    # row of small polaroids along the bottom
    pols = cfg.get("polaroids") or []
    if pols:
        n = len(pols)
        side = min(q(300), int(W / (n + 0.6) * 0.78))
        py = max(hero_bottom - q(40), H - side - q(260))
        for j, p in enumerate(pols):
            im = crop_aspect(C.open_img(p["src"]), tuple(p.get("c", C.focus_of(p["src"])[0])),
                             p.get("z", C.focus_of(p["src"])[1]), 1.0)
            if p.get("circle"):
                im = circled(im, p["circle"], RED)
            c = polaroid(im, (side, side), p.get("rot", 0), k, p.get("caption"), j * 7 + 1)
            px = int((j + 0.5) * W / n - c.width / 2)
            cv.paste(c, (px, int(py)), c)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    cv.save(out)
    print("cover:", out)


def cinema_cover(C, cfg, W, H, out):
    """LOOK cinema (references/AESTHETICS.md P8): the hero still full-bleed (cropped to the cover's aspect around its
    focus), the title in the serif over a soft gradient, a hairline and a small spaced line - no polaroids, no tape,
    no red circle. COVER style="scrapbook" keeps the collage."""
    import tempfile
    from vstudio.batch.edits import _text_cover
    hero = cfg.get("hero") or {}
    src = hero.get("src") or hero.get("b") or hero.get("a") or next(
        (p.get("src") for p in cfg.get("polaroids") or [] if p.get("src")), None)
    if not src:
        raise SystemExit("cover: COVER needs hero=dict(src=<still>) (or a polaroid) for the cinema cover")
    c = tuple(hero.get("c", C.focus_of(src)[0]))
    im = crop_aspect(C.open_img(src), c, hero.get("z", 1.0), W / H).resize((W, H), Image.LANCZOS)
    lead, other = (C.TITLE_EN, C.TITLE_ZH) if C.EN_LEAD else (cfg.get("title") or C.TITLE_ZH or C.TITLE_EN,
                                                            C.TITLE_EN)
    sub = cfg.get("subtitle") or (other if other and other != lead else "")
    if C.EN_LEAD and has_cjk(sub or "") and not has_cjk(lead or ""):
        sub = cfg.get("kicker") if cfg.get("kicker") and not has_cjk(cfg["kicker"]) else ""
    for sep in (": ", "：", " — ", " - "):          # a long title: its head on the cover, the rest the small line
        if lead and sep in lead and len(lead) > 22:
            lead, sub = (x.strip() for x in lead.split(sep, 1))
            break
    text = (lead or "") + (("|" + sub) if sub else "")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        fr = os.path.join(td, "hero.jpg")
        im.convert("RGB").save(fr, quality=95)
        _text_cover(fr, text, out, style="cinema")
    return out


if __name__ == "__main__":
    main()
