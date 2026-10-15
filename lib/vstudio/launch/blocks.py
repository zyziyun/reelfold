"""Brand-moment blocks of a launch film (``film.blocks``), drawn into the HyperFrames page by compose.build:

  waterfall  hundreds of real video thumbnails pour down the frame, each landing as one tile of the wordmark (a mosaic
             of the films made with the product), which then resolves into the solid name in heavy type
  lift       the platforms' marks rise from below the frame and lift three heavy words into place
             ("Create · Edit · Publish" / "做 · 剪 · 发"), the promise line under them
  hook       one heavy line slammed in word by word (a short's first line)

    cells, word = mosaic("Reelfold", font, 880, (W, H), box, target=360)   # tile centres + the solid wordmark PNG

The mosaic is measured on the real font (PIL, the variable weight set like the browser sets it), so the tiles and
the solid wordmark that replaces them sit on the same pixels. Thumbnails come from ``film.waterfall.thumbs`` (a
folder / glob / list of images: covers and frames of the videos made with the product) or else frames of the film's
own recordings. Deterministic: every random draw is seeded.
"""
import glob
import os
import random

from . import brand as B
from . import config as C

# the product's own platform marks (a short glyph on its colour; not the platforms' trademarked logos), as in the
# desk's registry (apps/desk/src/shared/platforms.ts)
MARKS = {"youtube": ("▶", "#FF0033"), "youtube-shorts": ("S", "#FF0033"), "tiktok": ("T", "#111111"),
         "instagram": ("IG", "#D62976"), "x": ("X", "#000000"), "linkedin": ("in", "#0A66C2"),
         "facebook": ("f", "#1877F2"), "threads": ("@", "#000000"), "xiaohongshu": ("红", "#FF2442"),
         "douyin": ("抖", "#111111"), "wechat-channels": ("视", "#FA9D3B"), "bilibili": ("B", "#00A1D6"),
         "kuaishou": ("快", "#FF4906"), "weibo": ("微", "#E6162D")}
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
THUMBS_MAX = 160              # distinct thumbnails staged per film (the tiles reuse them)


def _r(x):
    return round(float(x), 3)


# ------------------------------------------------------------------------------------------------ thumbnails
def thumb_sources(cfg, shots):
    """Image files for the waterfall: ``film.waterfall.thumbs`` (dir / glob / list, relative to the config), else
    stills of the recordings -> [path] (sorted, deterministic)."""
    spec = ((cfg.get("film") or {}).get("waterfall") or {}).get("thumbs")
    root = cfg.get("_root") or "."
    out = []
    for item in ([spec] if isinstance(spec, str) else list(spec or [])):
        p = os.path.expanduser(str(item))
        p = p if os.path.isabs(p) else os.path.join(root, p)
        if os.path.isdir(p):
            out += [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.lower().endswith(IMG_EXT)]
        else:
            out += sorted(x for x in glob.glob(p) if x.lower().endswith(IMG_EXT))
    if not out:
        out = sorted({s["still"] for s in shots.values() if s.get("still") and os.path.exists(s["still"])})
    return out


def stage_thumbs(cfg, shots, proj, size, n=THUMBS_MAX):
    """Resize up to ``n`` thumbnails (spread over the sources) to ``size`` (w, h, cover crop) into the project ->
    [relative path]."""
    from PIL import Image, ImageOps
    src = thumb_sources(cfg, shots)
    if not src:
        return []
    if len(src) > n:
        src = [src[round(i * (len(src) - 1) / (n - 1))] for i in range(n)]
    d = os.path.join(proj, "assets", "thumbs")
    os.makedirs(d, exist_ok=True)
    out = []
    for k, p in enumerate(src):
        dst = os.path.join(d, f"t{k:03d}-{size[0]}x{size[1]}.jpg")
        if not os.path.exists(dst):
            try:
                with Image.open(p) as im:
                    ImageOps.fit(im.convert("RGB"), size, Image.LANCZOS).save(dst, quality=84)
            except OSError:
                continue
        out.append(os.path.relpath(dst, proj))
    return out


# ------------------------------------------------------------------------------------------------ mosaic
def _heavy_font(path, px, weight):
    return B._font(path, int(px), weight)


def wordmark_px(text, path, weight, width, height):
    """Largest size (px) at which ``text`` fits ``width`` x ``height`` (cap height ~0.73 em)."""
    lo, hi = 24, 900
    while hi - lo > 2:
        mid = (lo + hi) // 2
        if B.measure(text, path, mid, weight) <= width and mid * 0.78 <= height:
            lo = mid
        else:
            hi = mid
    return lo


def mosaic(text, path, weight, canvas, box, target=360, scale=2, ink="#151412"):
    """The wordmark as a mosaic -> (cells [(cx, cy)], cell (w, h), word PNG bytes-free dict {img, x, y, w, h}).
    ``box`` = (x, y, w, h) the wordmark is centred in; cells are 16:9 tiles on the letters (>= half covered), sized so
    about ``target`` of them cover the word."""
    from PIL import Image, ImageDraw
    W, H = canvas
    bx, by, bw, bh = box
    px = wordmark_px(text, path, weight, bw, bh)
    f = _heavy_font(path, px * scale, weight)
    l, t, r, b = f.getbbox(text)
    tw, th = r - l, b - t
    ox = int((bx + bw / 2) * scale - tw / 2 - l)
    oy = int((by + bh / 2) * scale - th / 2 - t)
    mask = Image.new("L", (W * scale, H * scale), 0)
    ImageDraw.Draw(mask).text((ox, oy), text, font=f, fill=255)
    area = sum(1 for v in mask.resize((W // 4, H // 4)).getdata() if v > 127) * 16       # canvas px²
    cw = max(10.0, (area / max(1, target) * 16 / 9) ** 0.5)
    ch = cw * 9 / 16
    cells = []
    small = mask.resize((W, H), Image.BILINEAR)
    pix = small.load()
    x0, y0 = (ox + l) / scale, (oy + t) / scale
    nx, ny = int(tw / scale / cw) + 2, int(th / scale / ch) + 2
    for j in range(ny):
        for i in range(nx):
            cx, cy = x0 + (i + 0.5) * cw - cw * 0.5, y0 + (j + 0.5) * ch - ch * 0.5
            n = hit = 0
            for u in range(4):
                for v in range(4):
                    sx, sy = int(cx - cw / 2 + (u + 0.5) * cw / 4), int(cy - ch / 2 + (v + 0.5) * ch / 4)
                    if 0 <= sx < W and 0 <= sy < H:
                        n += 1
                        hit += pix[sx, sy] > 127
            if n and hit / n >= 0.5:
                cells.append((round(cx, 1), round(cy, 1)))
    # the solid wordmark, drawn with the same font on the same pixels (2x, shown at 1x)
    word = Image.new("RGBA", (tw + 8 * scale, th + 8 * scale), (0, 0, 0, 0))
    ImageDraw.Draw(word).text((4 * scale - l, 4 * scale - t), text, font=f, fill=ink)
    return cells, (round(cw, 2), round(ch, 2)), dict(img=word, x=round(x0 - 4, 1), y=round(y0 - 4, 1),
                                                     w=round(word.width / scale, 1), h=round(word.height / scale, 1),
                                                     px=px)


# ------------------------------------------------------------------------------------------------ html
def waterfall_html(ctx, sid, s, land, st, du, js, sfx):
    """Thumbnails pour down and land as the wordmark's tiles; the tiles give way to the solid wordmark, the tagline
    under it (and 千剪 above it on a Chinese film)."""
    from . import compose as CO
    W, H, L, cfg, proj = ctx["W"], ctx["H"], ctx["L"], ctx["cfg"], ctx["proj"]
    x0, y0, x1, y1 = L["text"]
    wide = W > H
    bw = (x1 - x0) * (0.86 if wide else 0.94)
    bh = H * (0.3 if wide else 0.16)
    box = ((W - bw) / 2, H * (0.44 if wide else 0.42) - bh / 2, bw, bh)
    path, weight = ctx["heavy_file_en"], ctx["heavy"]
    target = int(((cfg.get("film") or {}).get("waterfall") or {}).get("tiles") or (380 if wide else 300))
    cells, (cw, ch), word = mosaic(s.get("title") or cfg["product"]["name"], path, weight, (W, H), box, target,
                                   ink=ctx["ink"])
    wdir = os.path.join(proj, "assets", "brand")
    os.makedirs(wdir, exist_ok=True)
    wpath = os.path.join(wdir, f"wordmark-{W}x{H}.png")
    word["img"].save(wpath)
    thumbs = stage_thumbs(cfg, ctx["shots"], proj, (int(cw * 3), int(ch * 3)))
    rnd = random.Random(7)
    html = [f'<div class="full" id="{sid}c">']
    tiles = []
    for k, (cx, cy) in enumerate(cells):
        img = thumbs[k % len(thumbs)] if thumbs else ""
        tiles.append(f'<div class="tile" id="{sid}t{k}" style="left:{_r(cx - cw / 2)}px; top:{_r(cy - ch / 2)}px; '
                     f'width:{_r(cw - 1.5)}px; height:{_r(ch - 1.5)}px">'
                     + (f'<img src="{img}" alt="">' if img else "") + "</div>")
    html.append(f'<div class="full" id="{sid}m">' + "".join(tiles) + "</div>")
    html.append(f'<img class="mark" id="{sid}w" src="{os.path.relpath(wpath, proj)}" alt="" style="left:{word["x"]}px; '
                f'top:{word["y"]}px; width:{word["w"]}px; height:{word["h"]}px">')
    # the pour: a sweep from left to right with some chaos; tiles fall big (they read as videos) and land small. They
    # start as the scene starts (under the transition) from just above the frame and enter at once, so the stage is
    # never an empty backdrop waiting for them
    xs = [c[0] for c in cells] or [0]
    lo, span = min(xs), max(1.0, max(xs) - min(xs))
    lands = []
    for k, (cx, cy) in enumerate(cells):
        r1, r2, r3 = rnd.random(), rnd.random(), rnd.random()
        t0 = st + (cx - lo) / span * 0.45 + r1 * 0.55
        d = 0.6 + r2 * 0.26
        fall = cy + ch * 2.2 + H * (0.02 + r3 * 0.3)
        js.append(f'tl.fromTo("#{sid}t{k}", {{y: {-int(fall)}, x: {int((r1 - 0.5) * 90)}, scale: {_r(2.4 + r2 * 1.4)}, '
                  f'rotation: {_r((r3 - 0.5) * 24)}, opacity: 1}}, {{y: 0, x: 0, scale: 1, rotation: 0, opacity: 1, '
                  f'duration: {_r(d)}, ease: "power1.in"}}, {_r(t0)});')
        lands.append(t0 + d)
    for k, t in enumerate(sorted(lands)[::max(1, len(lands) // 26)]):
        sfx.append(dict(t=t, sfx=("tick", "tick_b")[k % 2], gain_db=-17))
    sfx.append(dict(t=land + 0.1, sfx="whoosh_b", gain_db=-16))
    resolve = st + S_WATERFALL_TEXT()
    # the tiles give way to the solid wordmark, from the middle out
    mid = (lo + span / 2)
    order = sorted(range(len(cells)), key=lambda k: abs(cells[k][0] - mid))
    for q, k in enumerate(order[::1]):
        if q % 6:
            continue
        group = ",".join(f"#{sid}t{x}" for x in order[q:q + 6])
        js.append(f'tl.to("{group}", {{opacity: 0, scale: .55, duration: .38, ease: "power2.in"}}, '
                  f'{_r(resolve - 0.2 + 0.28 * q / max(1, len(order)))});')
    js.append(f'tl.fromTo("#{sid}w", {{opacity: 0, scale: 1.04, filter: "blur(10px)"}}, {{opacity: 1, scale: 1, '
              f'filter: "blur(0px)", duration: .5, ease: "expo.out"}}, {_r(resolve - 0.1)});')
    sfx.append(dict(t=resolve, sfx="impact_b", gain_db=-14))
    ty = word["y"] + word["h"] + word["px"] * 0.16
    if s.get("kicker"):
        kpx, kl = CO._fit(s["kicker"], ctx["files"], (int(L["kicker_px"] * 1.3), int(L["kicker_px"] * 0.8)), x1 - x0, 2,
                          ctx["lang"], 600)
        html.append(f'<div class="center kicker" id="{sid}k" style="top:{int(ty)}px; font-size:{kpx}px">'
                    f'{"<br>".join(map(CO._e, kl))}</div>')
        js.append(f'tl.fromTo("#{sid}k", {{opacity: 0, y: 16, filter: "blur(6px)"}}, {{opacity: 1, y: 0, '
                  f'filter: "blur(0px)", duration: .55, ease: "quint.out"}}, {_r(resolve + 0.3)});')
    if s.get("eyebrow"):
        epx = int(L["eyebrow_px"] * 1.6)
        html.append(f'<div class="center heavy" id="{sid}e" style="top:{int(word["y"] - epx * 1.7)}px; '
                    f'font-size:{epx}px; opacity:0">{CO._e(s["eyebrow"])}</div>')
        js.append(f'tl.fromTo("#{sid}e", {{opacity: 0, y: -10}}, {{opacity: 1, y: 0, duration: .5, ease: "quint.out"}}, '
                  f'{_r(resolve + 0.15)});')
    js.append(f'tl.fromTo("#{sid}c", {{scale: 1.0}}, {{scale: 1.035, duration: {_r(du)}, ease: "sine.inOut"}}, {_r(st)});')
    html.append("</div>")
    return "".join(html)


def S_WATERFALL_TEXT():
    from . import story as S
    return S.WATERFALL_TEXT


def _mark(pid, px):
    g, bg = MARKS.get(pid, ((pid[:1] or "?").upper(), "#666666"))
    fs = int(px * (0.5 if len(g) > 1 else 0.6))
    return (f'<span class="pmark" style="width:{px}px; height:{px}px; border-radius:{int(px * 0.24)}px; '
            f'background:{bg}; font-size:{fs}px">{g}</span>')


def lift_html(ctx, sid, s, land, st, du, js, sfx):
    """The platforms' marks rise from below and lift the three heavy words into place; the promise line under."""
    from . import compose as CO
    W, H, L, lang = ctx["W"], ctx["H"], ctx["L"], ctx["lang"]
    x0, y0, x1, y1 = L["text"]
    words = list(s.get("words") or [])
    path, weight = ctx["heavy_file"], ctx["heavy"]
    sep = " · "
    wide = W > H
    zh = lang == "zh"
    width = (x1 - x0) * 0.98
    stacked = not wide and not zh
    if stacked:                                         # a word per line on a tall canvas
        px = min(int(H * 0.115), *[wordmark_px(w, path, weight, width, H) for w in words])
        lines = [[w] for w in words]
    else:
        px = wordmark_px(sep.join(words), path, weight, width, H * (0.3 if zh else 0.22))
        lines = [words]
    lh = px * (1.12 if zh else 1.0)
    pls = [p for p in s.get("platforms") or [] if p]
    ipx = int(min(px * (0.42 if stacked else 0.5), (width - 14 * len(pls)) / max(1, len(pls)), 112))
    gap = int(ipx * 0.22)
    block_h = lh * len(lines) + ipx * 1.6 + (L["oneliner_px"] * 1.6 if s.get("sub") else 0)
    top = (y0 + y1) / 2 - block_h / 2
    html = [f'<div class="full" id="{sid}c">']
    k = 0
    for j, ln in enumerate(lines):
        y = top + j * lh
        parts = []
        for i, w in enumerate(ln):
            if i:
                parts.append(f'<span class="sep">{CO._e(sep.strip())}</span>')
            parts.append(f'<span class="lw" id="{sid}w{k}">{CO._e(w)}</span>')
            k += 1
        html.append(f'<div class="center heavy liftline" style="top:{int(y)}px; font-size:{px}px; '
                    f'height:{int(lh * 1.05)}px">' + "".join(parts) + "</div>")
    iy = top + lh * len(lines) + ipx * 0.45
    tot = len(pls) * ipx + (len(pls) - 1) * gap
    ix = (W - tot) / 2
    for i, pid in enumerate(pls):
        html.append(f'<div class="pm" id="{sid}p{i}" style="left:{int(ix + i * (ipx + gap))}px; top:{int(iy)}px">'
                    f'{_mark(pid, ipx)}</div>')
    rnd = random.Random(11)
    # the marks rise from below the frame, the middle first, as the scene starts (under the transition): the stage is
    # never empty between the previous scene and the words
    for i in range(len(pls)):
        t = st + 0.055 * abs(i - (len(pls) - 1) / 2) + rnd.random() * 0.05
        js.append(f'tl.fromTo("#{sid}p{i}", {{y: {int(H - iy + ipx)}, rotation: {int((rnd.random() - .5) * 40)}, '
                  f'opacity: 1}}, {{y: 0, rotation: 0, opacity: 1, duration: .7, ease: "back.out(1.5)"}}, {_r(t)});')
        sfx.append(dict(t=t + 0.42, sfx=("pop", "pop_b")[i % 2], gain_db=-15))
    for i in range(k):                                    # each word is lifted out from under its line
        t = st + 0.3 + 0.16 * i
        js.append(f'tl.fromTo("#{sid}w{i}", {{yPercent: 115, opacity: 1}}, {{yPercent: 0, opacity: 1, duration: .62, '
                  f'ease: "expo.out"}}, {_r(t)});')
        sfx.append(dict(t=t + 0.05, sfx="swoosh_b", gain_db=-18))
    js.append(f'tl.fromTo("#{sid}c .sep", {{opacity: 0}}, {{opacity: 1, duration: .3}}, {_r(st + 0.45)});')
    if s.get("sub"):
        spx, sl = CO._fit(s["sub"], ctx["files"], (L["oneliner_px"], int(L["oneliner_px"] * 0.7)), x1 - x0, 2, lang,
                          ctx["lw"])
        sy = iy + ipx * 1.55
        html.append(f'<div class="center cta" id="{sid}o" style="top:{int(sy)}px; font-size:{spx}px">'
                    f'{CO.caption_html(sl)}</div>')
        CO._blur_in(js, f"#{sid}o .w", land + 0.95, stagger=0.03 if zh else 0.05, dur=0.6)
    js.append(f'tl.fromTo("#{sid}c", {{scale: 1}}, {{scale: 1.03, duration: {_r(du)}, ease: "sine.out"}}, {_r(st)});')
    html.append("</div>")
    return "".join(html)


def hook_html(ctx, sid, s, land, st, du, js, sfx):
    """One heavy line, slammed in word by word (a short's opening line), a small kicker above it."""
    from . import compose as CO
    W, H, L, lang = ctx["W"], ctx["H"], ctx["L"], ctx["lang"]
    x0, y0, x1, y1 = L["text"]
    zh = lang == "zh"
    hi = int(L["type_px"][0] * 1.3)
    if "\n" in s["text"]:                              # her own line breaks: each line fitted on its own
        ls = [x.strip() for x in s["text"].split("\n") if x.strip()]
        px = min(B.fit(x, ctx["heavy_file"], (hi, int(L["type_px"][1] * 0.6)), int(L["type_w"]), 1, lang,
                       ctx["heavy"])[0] for x in ls)
    else:
        px, ls = B.fit(s["text"], ctx["heavy_file"], (hi, int(L["type_px"][1])), int(L["type_w"]),
                       L["type_lines"] + 1, lang, ctx["heavy"])
    lh = 1.16 if zh else 1.02
    h = px * lh * len(ls)
    top = int((y0 + y1) / 2 - h / 2)
    left = int((x0 + x1) / 2 - L["type_w"] / 2)
    html = []
    if s.get("kicker"):
        kpx = L["kicker_px"]
        html.append(f'<div class="center kicker" id="{sid}k" style="top:{int(top - kpx * 2.0)}px; font-size:{kpx}px">'
                    f'{CO._e(s["kicker"])}</div>')
        js.append(f'tl.fromTo("#{sid}k", {{opacity: 0, y: 14}}, {{opacity: 1, y: 0, duration: .45, ease: "quint.out"}}, '
                  f'{_r(land)});')
    html.append(f'<div class="type heavy" id="{sid}t" style="left:{left}px; top:{top}px; width:{L["type_w"]}px; '
                f'font-size:{px}px; line-height:{lh}">{CO.caption_html(ls)}</div>')
    CO._slam(js, f"#{sid}t .w", land + 0.08, stagger=0.035 if zh else 0.09, dur=0.5, scale=1.5)
    sfx.append(dict(t=land + 0.12, sfx="impact_b", gain_db=-15))
    js.append(f'tl.fromTo("#{sid}t", {{scale: 1}}, {{scale: 1.04, duration: {_r(du)}, ease: "sine.out"}}, {_r(st)});')
    return "".join(html)


CSS = """
.tile { position: absolute; overflow: hidden; border-radius: 2px; background: var(--lk-ink); opacity: 0;
  box-shadow: 0 1px 2px rgba(var(--lk-shadow), .25); }
.tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
.heavy { font-family: {HEAVY}; font-weight: {HW}; letter-spacing: {HTRACK}; color: var(--lk-ink); {HSTROKE} }
.type.heavy { font-family: {HEAVY}; font-weight: {HW}; }
.liftline { overflow: hidden; white-space: nowrap; line-height: 1.04; }
.liftline .lw { display: inline-block; }
.liftline .sep { display: inline-block; color: var(--lk-accent); margin: 0 .16em; opacity: 0; }
.pm { position: absolute; }
.pmark { display: inline-grid; place-items: center; color: #fff; font-family: {HEAVY}; font-weight: 800; line-height: 1;
  box-shadow: 0 14px 30px -14px rgba(var(--lk-shadow), .55), inset 0 0 0 1px rgba(255,255,255,.14); }
"""


def css(ctx):
    zh = ctx["lang"] == "zh"
    stroke = "-webkit-text-stroke: .022em currentColor;" if zh and B.zh_faux_heavy(ctx["heavy_file"]) else ""
    return (CSS.replace("{HEAVY}", ctx["heavy_family"]).replace("{HW}", str(ctx["heavy"]))
            .replace("{HTRACK}", ".02em" if zh else "-.045em").replace("{HSTROKE}", stroke))


def used(plan):
    return any(s["layout"] in ("waterfall", "lift", "hook") for s in plan["scenes"])


def words(plan):
    """Every string a block puts on screen (for the font subset)."""
    out = []
    for s in plan["scenes"]:
        out += list(s.get("words") or []) + [s.get("sub") or "", s.get("kicker") or "", s.get("eyebrow") or ""]
        if s["layout"] in ("hook", "waterfall"):
            out += [s.get("text") or "", s.get("title") or ""]
        if s["layout"] == "lift":
            out += [MARKS.get(p, ((p[:1] or "?").upper(), ""))[0] for p in s.get("platforms") or [] if p]
    return C.plain("".join(out))
