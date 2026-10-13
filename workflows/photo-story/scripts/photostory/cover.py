#!/usr/bin/env python3
"""The story's cover, per platform. Default (persona ``style.cover`` unset / "designed"): cover engine 2.0
(``vstudio.cover_engine``) on the best frame of the story - every still and clip window the spec uses, ranked by
``vstudio.cover.score_frames`` / ``score_images`` (sharp, exposed, clear subject, LAION aesthetic) - with one
language per platform (YouTube English; 小红书 / B站 Chinese), the most specific title of COVER / TITLE_* / POST
(``cover_engine.pick_text``), the small-size legibility check, and on YouTube the A/B trio (<out>.ab1-3.jpg +
<out>.ab.md). persona ``style.cover: cinema`` keeps the centred serif cover; ``style.cover: scrapbook`` (polaroid /
collage) keeps the old paper collage below.

    python3 cover.py spec.py [--out cover.png] [--platform youtube]

The scrapbook collage: dark title zone (kicker, title, EN subtitle, tagline with a red-pen-circled keyword),
a hero polaroid showing an A|B split (draft|final, before|after), and a row of taped polaroids
(optional caption + red circle) on paper. Everything comes from spec COVER; size = spec canvas.

COVER = dict(kicker=, title=, subtitle=, tagline=(before, keyword, after),
             hero=dict(a=img, b=img, labels=(la, lb), c=(x,y), z=1.0)  or hero=dict(src=img),
             polaroids=[dict(src=, caption=, rot=, c=, z=, circle=(cx,cy,rx,ry)), ...],  out=)
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
import hashlib
import json
import os
import shutil

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
    style = cover_style()
    if style == "designed":
        print("cover:", designed_cover(spec, C, cfg, W, H, out))
    elif style == "cinema":
        print("cover:", cinema_cover(C, cfg, W, H, out))
    else:
        print("cover:", scrapbook_cover(C, cfg, W, H, out))


def cover_style():
    """persona ``style.cover``: "scrapbook" / "polaroid" / "collage" -> the paper collage; "cinema" -> the centred
    serif cover; anything else (unset, "designed") -> cover engine 2.0."""
    try:
        from vstudio.config import persona
        st = (persona() or {}).get("style")
        v = str((st.get("cover") if isinstance(st, dict) else "") or "").lower()
    except Exception:  # noqa: BLE001
        v = ""
    if v in ("scrapbook", "polaroid", "polaroids", "collage"):
        return "scrapbook"
    return "cinema" if v in ("cinema", "centred", "centered") else "designed"


# ---------------------------------------------------------------- cover engine 2.0
HERO_PRIOR = 0.25      # the still the spec names as COVER hero: written for the cover, a small lead in the ranking
CLIP_SAMPLES = (0.5, 2.0, 3.5)   # seconds into each clip shot the story uses


def _cover_text(cfg):
    t = str((cfg or {}).get("title") or "").strip()
    sub = str((cfg or {}).get("subtitle") or "").strip()
    return t + (" | " + sub if sub and t else sub)


def cover_texts(spec, C):
    """{"zh", "en"}: per language the most specific of the cover text and the story's titles (a generic cover
    title like "航拍西雅图" loses to the title naming the subject)."""
    from vstudio import cover_engine as CE
    g = lambda k: dict(getattr(spec, k, {}) or {})
    zh = CE.pick_text([_cover_text(g("COVER")), C.TITLE_ZH, g("POST_ZH").get("title"), g("POST").get("title")], "zh")
    en = CE.pick_text([_cover_text(g("COVER_EN")), _cover_text(g("COVER")), C.TITLE_EN, g("POST_EN").get("title")],
                      "en")
    return {"zh": zh, "en": en}


def _shots(spec):
    for unit in getattr(spec, "SCRIPT", []) or []:
        try:
            shots = unit[2]
        except (TypeError, IndexError, KeyError):
            continue
        for sh in shots or []:
            if isinstance(sh, (list, tuple)) and sh and isinstance(sh[0], str):
                yield sh[0], (sh[3] if len(sh) > 3 and isinstance(sh[3], dict) else {})


def frame_candidates(spec, C):
    """-> (stills [(path, prior)], clips {video path: [seconds]}): the COVER stills (hero first), every still in the
    spec's image folders and every clip window the SCRIPT shows."""
    from photostory.shots import parse_src
    stills, seen = [], set()

    def add_still(name, prior=0.0):
        try:
            p = C._readable(C.find_image(name))
        except Exception:  # noqa: BLE001  (a missing still is not a cover candidate)
            return
        if p not in seen:
            seen.add(p)
            stills.append((p, prior))
    for key in ("COVER", "COVER_EN"):
        cfg = dict(getattr(spec, key, {}) or {})
        hero = cfg.get("hero") or {}
        for k in ("src", "b", "a"):
            if hero.get(k):
                add_still(hero[k], HERO_PRIOR)
        for pz in cfg.get("polaroids") or []:
            if pz.get("src"):
                add_still(pz["src"])
    clips = {}
    for src, opts in _shots(spec):
        try:
            kind, arg = parse_src(C, src)
        except Exception:  # noqa: BLE001
            continue
        if kind == "video":
            v = C.find_video(arg)
            off = float(opts.get("off", 0) or 0)
            if v:
                clips.setdefault(v, []).extend(off + d for d in CLIP_SAMPLES)
        elif kind == "img":
            add_still(arg)
    for d in C.img_dirs:
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if os.path.splitext(f)[1] in C.img_ext and not f.startswith("."):
                    add_still(os.path.join(d, f))
    return stills[:60], {v: sorted(set(round(t, 2) for t in ts)) for v, ts in clips.items()}


def pick_frame(spec, C, log=print):
    """The best cover frame of the story -> (path, pick record). Cached in <cache>/cover/ by the candidates."""
    stills, clips = frame_candidates(spec, C)
    key = hashlib.sha1(json.dumps([[p, pr, os.path.getmtime(p)] for p, pr in stills]
                                  + [[v, ts, os.path.getmtime(v)] for v, ts in sorted(clips.items())]).encode()
                       ).hexdigest()[:12]
    d = os.path.join(C.cache_dir, "cover")
    rec_p, frame_p = os.path.join(d, f"pick.{key}.json"), os.path.join(d, f"frame.{key}.jpg")
    if os.path.exists(rec_p) and os.path.exists(frame_p):
        return frame_p, json.load(open(rec_p, encoding="utf-8"))
    os.makedirs(d, exist_ok=True)
    from vstudio import cover as VC
    rows = []
    if stills:
        prior = dict(stills)
        for r in VC.score_images([p for p, _ in stills], log=log):
            rows.append(dict(kind="still", src=r["path"], score=round(r["score"] + prior.get(r["path"], 0.0), 4),
                             parts=r["parts"]))
    images = {}
    for v, ts in clips.items():
        try:
            picks = VC.score_frames(v, top_n=len(ts), min_gap=0.4, times=ts, log=log)
        except Exception as e:  # noqa: BLE001  (an unreadable clip: the stills still rank)
            log(f"cover: {os.path.basename(v)} not scored ({str(e)[:80]})")
            continue
        for p in picks:
            rid = f"{v}@{p['t']:.2f}"
            images[rid] = p.get("image")
            rows.append(dict(kind="clip", src=v, t=p["t"], score=p["score"], parts=p["parts"]))
    if not rows:
        raise SystemExit("cover: no still or clip frame to make a cover from (COVER hero / SCRIPT shots)")
    rows.sort(key=lambda r: -r["score"])
    best = rows[0]
    if best["kind"] == "still":
        from PIL import ImageOps
        ImageOps.exif_transpose(Image.open(best["src"])).convert("RGB").save(frame_p, quality=95)
    else:
        img = images.get(f"{best['src']}@{best['t']:.2f}")
        if img is None:
            raise SystemExit(f"cover: could not read {best['src']} at {best['t']} s")
        cv2.imwrite(frame_p, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    rec = dict(best=best, ranked=rows[:12])
    with open(rec_p, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    log(f"cover: frame {os.path.basename(best['src'])}" + (f" @ {best['t']:.1f}s" if best.get("t") is not None else "")
        + f" (score {best['score']}, of {len(rows)})")
    return frame_p, rec


def designed_cover(spec, C, cfg, W, H, out, log=print):
    """Cover engine 2.0 for this platform -> out (+ on YouTube <stem>.ab1-3.jpg and <stem>.ab.md)."""
    from vstudio import cover_engine as CE
    frame, _ = pick_frame(spec, C, log=log)
    texts = cover_texts(spec, C)
    if C.prof is not None and not cfg.get("size"):
        sp = CE.spec_for(C.prof.key)
    else:
        m = int(min(W, H) * 0.06)
        lang = "en" if C.SUBS == "en" else ("zh" if texts["zh"] else "en")
        sp = dict(name="generic", key="generic", size=(W, H), safe=(m, m, W - m, H - m), keepouts=[], lang=lang,
                  max_bytes=None)
    if not texts.get(sp["lang"]):                # an English-only story on a Chinese platform: its own language
        texts[sp["lang"]] = texts["en"] or texts["zh"]
    out_dir = os.path.dirname(os.path.abspath(out))
    stem = os.path.splitext(os.path.basename(out))[0]
    work = os.path.join(C.cache_dir, "cover", "render")
    if os.path.isdir(work):
        shutil.rmtree(work)
    res = CE.make_covers(frame, texts, [sp], work, stem=stem, log=log)
    r = res[sp["key"]]
    os.makedirs(out_dir, exist_ok=True)
    img = Image.open(r["file"]).convert("RGB")
    if os.path.splitext(out)[1].lower() in (".jpg", ".jpeg"):
        img.save(out, quality=92)
    else:
        img.save(out)
    for old in [f for f in os.listdir(out_dir) if f.startswith(stem + ".ab")]:
        os.remove(os.path.join(out_dir, old))
    variants = []
    for k, v in enumerate(r.get("variants") or []):
        dst = os.path.join(out_dir, f"{stem}.ab{k + 1}.jpg")
        shutil.copyfile(v["file"], dst)
        variants.append(dict(v, file=dst))
    if len(variants) >= 2:
        with open(os.path.join(out_dir, f"{stem}.ab.md"), "w", encoding="utf-8") as f:
            f.write(CE.ab_note({"youtube": dict(variants=variants)}))
    leg = r.get("legibility") or {}
    sizes = ", ".join(f"{x['size']} h{x['height']:.3f} c{x['contrast']}" for x in leg.get("sizes") or [])
    log(f"cover: {sp['key']} {sp['lang']} \"{r.get('title', '')}\"" + (f" / {r['kicker']}" if r.get("kicker") else "")
        + f" - {r.get('variant')}, " + ("legible" if r.get("ok") else "FAILS the small-size check") + f" ({sizes})"
        + (f"; A/B {len(variants)}" if variants else ""))
    with open(os.path.join(out_dir, f"{stem}.covers.json"), "w", encoding="utf-8") as f:
        json.dump(dict({k: v for k, v in r.items() if k != "file"}, platform=sp["key"], frame=frame, texts=texts,
                       variants=[{k: v for k, v in x.items() if k != "legibility"} for x in variants]),
                  f, ensure_ascii=False, indent=1)
    return out


def scrapbook_cover(C, cfg, W, H, out):
    """The old paper collage (persona style.cover: scrapbook)."""
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
    return out


def cinema_cover(C, cfg, W, H, out):
    """LOOK cinema (references/AESTHETICS.md P8): the hero still full-bleed (cropped to the cover's aspect around its
    focus), the title in the serif over a soft gradient, a hairline and a small spaced line - no polaroids, no tape,
    no red circle. persona style.cover: cinema."""
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
