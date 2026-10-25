"""Multi-platform export: one clean master -> a file + cover + post stub per platform, plus a manifest.

    python -m vstudio.export master.mp4 --platforms xiaohongshu:vertical,douyin,youtube --out exports/ \\
        [--cues cues.json | --cues subs.srt | --cues en=cues.en.json --cues zh=cues.zh.json]
        [--captions both|burn|sidecar] [--no-captions] [--cover cover.png | --cover douyin=c916.png ...]
        [--title "..."] [--post post.json]

Per target (vstudio.platform profile):
  1. reframe the master to the profile canvas (vstudio.reframe): same aspect -> plain scale (no face
     tracking; reported as ``scale``); otherwise ``--mode`` (default face, keeping the face in the
     profile's safe box; no face -> pad-blur; ``subject`` / ``follow`` for travel and drone footage: the camera
     follows what stands out in each shot, kept in the safe box above the caption band, a shot that cannot be
     cropped shown whole on a blurred fill; ``--shots`` names the master's crossfades);
  2. burn captions (if cues are given and not --no-captions) in the profile's caption box at a fitted
     size (PIL, no libass), keyword markup 【】 / ``hl`` spans in brand.highlight. ``keepouts`` in
     cues.json ([{t0, t1, box: [x, y, w, h]}] in master px - or 0..1 fractions - and final seconds:
     panels, stamps, titles already burned into the master) are mapped through the reframe and the
     caption moves above/below them while they are on screen;
     ONE language per platform (references/AESTHETICS.md P9): ``--cues lang=path`` (repeatable) gives one track per
     language and each platform takes the track of its language (vstudio.platform.lang_for: English on YouTube /
     Shorts, Chinese on 小红书 / B站 / 抖音); a bare ``--cues path`` is one track for every platform, the line in the
     platform's language picked per cue (cues_for_platform). A platform whose language has no track gets another
     track through cues_for_platform and a warning. The keepouts and the post copy language follow the picked track;
     the creator's watermark (vstudio.watermark) goes on top when she set one up and it is on by default
     (``--watermark on|off`` / ``watermark=`` per call), placed in the profile's safe box above the captions;
  3. two-pass loudnorm to the profile's LUFS / true-peak target (audio.loudnorm_2pass);
  4. H.264 delivery encode (media.delivery_args with the profile's encode guidance);
  5. cover: a per-target ``--cover platform[:orientation]=path`` wins; else the --cover whose aspect is
     closest - cover-cropped when the aspect matches, otherwise FITTED on a blurred pad of itself (a
     centre crop would cut the headline off) with a warning to supply a per-target cover; else a frame
     of the export. Covers shown as a centre crop in the feed also get a ``.feed.jpg`` preview;
  6. post stub via publish.post_body when --title / --post is given;
  7. caption files: a platform whose upload page takes one (profile ``caption_upload``: YouTube / Shorts, X,
     Facebook, LinkedIn) gets ``<stem>.<lang>.srt`` next to its video for every caption language there is (timed
     like the burned cues: shifted by --start, cut at --dur), listed in the manifest (``sidecars`` + a note) and
     under the post.md text where the platform's text limit leaves room (X keeps post.md the exact 280 to paste).
     ``--captions``: ``both`` (default) burns everywhere and writes the files; ``sidecar``
     leaves the upload-capable videos clean (viewers switch the captions on; YouTube also indexes them) and still
     burns where there is no caption upload (小红书, 抖音 ...); ``burn`` burns only, no files. --no-captions: neither;
and ``manifest.json`` with files, durations, measured loudness, reframe stats and warnings.

Masters should be caption-free: keep a clean master + cues (JSON from subs.Cue.to_dict, or SRT) so each
platform gets captions sized and placed for its own UI. A master with burned-in captions will have them
cropped or covered on other canvases.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile

import numpy as np

from . import media
from . import platform as P
from . import reframe as R


# ----------------------------------------------------------------------------------- cues
def _hl_markup(text, hl):
    """Apply ``hl`` (keywords ["AWS", ...] or [[i, j], ...] char spans of the plain text) as highlight
    markup, unless the text already carries markup."""
    from . import draw
    a, z = draw.markup()
    if not hl or a in text:
        return text
    mark = [False] * len(text)
    for h in hl:
        if isinstance(h, str):
            k = text.find(h)
            while h and k >= 0:
                for j in range(k, k + len(h)):
                    mark[j] = True
                k = text.find(h, k + len(h))
        elif isinstance(h, (list, tuple)) and len(h) == 2:
            for j in range(max(0, int(h[0])), min(len(text), int(h[1]))):
                mark[j] = True
    out, on = [], False
    for ch, m in zip(text, mark):
        if m != on:
            out.append(a if m else z)
            on = m
        out.append(ch)
    if on:
        out.append(z)
    return "".join(out)


def _cue_from_dict(d):
    from .subs import Cue
    c = Cue.from_dict(d)
    hl = d.get("hl") or (d.get("style") or {}).get("hl") or (d.get("meta") or {}).get("hl")
    if hl:
        c.text = _hl_markup(c.text, hl)
    st = d.get("style")
    if isinstance(st, dict):
        c.meta = dict(c.meta or {}, style={k: v for k, v in st.items() if k != "hl"})
    return c


def load_cues(path):
    """Cues from a list, .srt, or cues.json (a list of Cue dicts, or {cues: [...], keepouts: [...]}).
    Per-cue ``hl`` (keywords or [i, j] spans) becomes 【】 markup; ``style`` ({fill, highlight}
    colours) is kept in ``meta["style"]``."""
    from .subs import Cue, srt_read
    if path is None:
        return []
    if isinstance(path, (list, tuple)):
        return [c if isinstance(c, Cue) else _cue_from_dict(c) for c in path]
    if str(path).lower().endswith(".srt"):
        return srt_read(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("cues") or data.get("segments") or []
    return [_cue_from_dict(d) for d in data]


def _is_zh(text):
    return any("\u3400" <= c <= "\u9fff" for c in str(text or ""))


def cues_for_platform(prof, cues, bilingual=None):
    """Captions in the platform's language, ONE language per platform (2026-10-12): English on YouTube / Shorts and
    the international platforms, Chinese on 小红书 / B站 / 抖音 ... (vstudio.platform.lang_for). A bilingual cue keeps
    the line in that language (中文 text + English alt -> the alt alone on YouTube); a cue with no line in it is kept
    and named in a warning. ``bilingual`` (default ``subs.bilingual_wanted()``: persona subtitles.bilingual) keeps
    both lines - never on YouTube, which is English only. -> (cues, warnings)"""
    if not cues:
        return [], []
    from .subs import Cue, bilingual_wanted, pick_lang
    lang = P.lang_for(prof.name, "en")
    if (bilingual if bilingual is not None else bilingual_wanted()) and not P.lang_fixed(prof.name):
        return list(cues), []
    out, bare = [], 0
    for c in cues:
        text, alt, found = pick_lang(c.text, c.alt, lang)
        bare += not found and bool(text)
        out.append(Cue(c.start, c.end, text, alt, c.meta))
    name = "English" if lang == "en" else "Chinese"
    warn = [f"{prof.name}: captions are {name} only, but {bare} cue(s) have no {name} line"] if bare else []
    return out, warn


# ----------------------------------------------------------------------------------- caption tracks
# a language key of ``--cues lang=path``: "en", "zh", "zh-Hans", "pt-BR". Anything else before a "=" is part of a
# path (a Windows "C:\\clips\\a=b.json" never reads as a track).
LANG_KEY = re.compile(r"^[a-z]{2}(-[A-Za-z]{2,4})?$")
CAPTION_MODES = ("both", "burn", "sidecar")
_LATIN = re.compile(r"[A-Za-z]{2,}")


def parse_cues_arg(values):
    """--cues values -> one track (a path: every platform) or {lang: path} (a track per language; a bare path next
    to them is the ``"*"`` track for the other languages). Only ``^[a-z]{2}(-[A-Za-z]{2,4})?=`` names a language, and
    an existing file wins over that reading, so ``C:\\x.json`` and ``a=b.json`` stay paths."""
    if values is None:
        return None
    if isinstance(values, (str, os.PathLike)):
        values = [values]
    tracks, bare = {}, []
    for v in values:
        v = os.fspath(v)
        k, sep, path = v.partition("=")
        if sep and LANG_KEY.match(k.strip()) and path.strip() and not os.path.exists(v):
            tracks[k.strip()] = path.strip()
        else:
            bare.append(v)
    if len(bare) > 1:
        raise ValueError(f"--cues: one bare path at most (the track for every platform), got {bare}; name the others "
                         "lang=path, e.g. --cues en=cues.en.json --cues zh=cues.zh.json")
    if not tracks:
        return bare[0] if bare else None
    if bare:
        tracks["*"] = bare[0]
    return tracks


def is_track_map(cues):
    """True for a {lang: path-or-list} caption map (not one track)."""
    return isinstance(cues, dict) and bool(cues) and all(k == "*" or LANG_KEY.match(str(k)) for k in cues)


def _lang_base(k):
    return str(k or "").split("-")[0].lower()


def _lang_name(lang):
    return {"en": "English", "zh": "Chinese"}.get(_lang_base(lang), str(lang))


def pick_track(prof, cues):
    """The caption source for one platform -> (source, track_lang, warnings). One track: (cues, None, []). A map: the
    track of the platform's language (``zh`` serves ``zh-Hans``), else the ``"*"`` track, else the first other track
    with a warning naming it (cues_for_platform then keeps the line in the platform's language where a cue has one)."""
    if not is_track_map(cues):
        return cues, None, []
    lang = P.lang_for(prof.name, "en")
    named = [(k, v) for k, v in cues.items() if k != "*"]
    for k, v in named:
        if k == lang:
            return v, k, []
    for k, v in named:
        if _lang_base(k) == lang:
            return v, k, []
    if "*" in cues:
        return cues["*"], None, []
    k, v = named[0]
    return v, k, [f"{prof.name}: no {_lang_name(lang)} caption track (--cues {lang}=...): used the {k} track, its "
                  f"{_lang_name(lang)} line where a cue has one"]


def _line_in(c, lang):
    """The line of cue ``c`` in ``lang`` (text or alt; markup kept) or None. en = Latin words and no CJK; zh = CJK."""
    from .subs import _ZH
    for x in (c.text or "", c.alt or ""):
        if not x.strip():
            continue
        if lang == "zh" and _ZH.search(x):
            return x
        if lang == "en" and not _ZH.search(x) and _LATIN.search(x):
            return x
    return None


def _neutral(c):
    """A cue with no words in any language (a year, a score): it belongs to every language's track."""
    from .subs import _ZH
    s = (c.text or "") + (c.alt or "")
    return bool(s.strip()) and not _ZH.search(s) and not _LATIN.search(s)


def caption_tracks(cues, prof):
    """Every caption language there is -> {lang: [Cue]} (one line each, the platform's language first, then English,
    then Chinese, then other named tracks). A map gives its tracks (each kept to its language's line); one track gives
    each language it has a line in (a bilingual cues.json -> en + zh)."""
    from .subs import Cue
    want = P.lang_for(prof.name, "en")
    srcs = list(cues.items()) if is_track_map(cues) else [("*", cues)]
    out = {}
    for k, src in srcs:
        cl = load_cues(src)
        langs = [k] if k != "*" else ["en", "zh"]
        for L in langs:
            base = _lang_base(L)
            if base in ("en", "zh"):
                if not any(_line_in(c, base) for c in cl):
                    continue
                cs = [Cue(c.start, c.end, _line_in(c, base) or c.text, "", c.meta) for c in cl
                      if _line_in(c, base) or _neutral(c)]
            else:
                cs = [Cue(c.start, c.end, c.text, "", c.meta) for c in cl if (c.text or "").strip()]
            if cs:
                out.setdefault(L, cs)
    order = sorted(out, key=lambda L: (_lang_base(L) != want, _lang_base(L) != "en", _lang_base(L) != "zh"))
    return {L: out[L] for L in order}


def write_sidecars(prof, cues, out_dir, stem, start=0.0, dur=None):
    """``<stem>.<lang>.srt`` for every caption language (caption_tracks), timed like the burned captions: shifted by
    ``start``, cut at ``dur``. -> [{lang, file, cues}]."""
    from .subs import Cue, srt_write
    out = []
    for L, cs in caption_tracks(cues, prof).items():
        cs = [Cue(c.start - start, c.end - start, c.text, c.alt, c.meta) for c in cs if c.end > start]
        if dur:
            cs = [Cue(c.start, min(c.end, dur), c.text, c.alt, c.meta) for c in cs if c.start < dur]
        path = os.path.join(out_dir, f"{stem}.{L}.srt")
        n = srt_write(cs, path, trailing_newline=True)
        if not n:
            os.remove(path)
            continue
        out.append(dict(lang=L, file=os.path.basename(path), cues=n))
    return out


def sidecar_note(prof, sidecars):
    """The post.md section that goes with the caption files: which file is which language, where to upload it."""
    where = prof.extra.get("caption_upload")
    where = where if isinstance(where, str) else "the upload page's captions field"
    rows = "\n".join(f"- {_lang_name(s['lang'])}: {s['file']}" for s in sidecars)
    return f"## Caption files\n\nUpload in {where}, one file per language:\n\n{rows}\n"


def captions_mode(captions):
    """``captions`` of export_one -> "off" | "both" | "burn" | "sidecar" (True / None = "both", False = "off")."""
    if captions is True or captions is None:
        return "both"
    if captions is False or captions == "off":
        return "off"
    if captions in CAPTION_MODES:
        return captions
    raise ValueError(f"captions={captions!r}: one of {', '.join(CAPTION_MODES)} (or off)")


def load_keepouts(path, master_size=None):
    """``keepouts`` of a cues.json -> [{t0, t1, box: (x, y, w, h) in master px}]. A box whose values are
    all <= 1 is a fraction of the frame; a top-level ``size`` [W, H] different from ``master_size``
    rescales. Missing / SRT / list cues -> []."""
    if path is None or isinstance(path, (list, tuple)) or str(path).lower().endswith(".srt"):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return []
    W, H = master_size or data.get("size") or (1, 1)
    sx = sy = 1.0
    if data.get("size") and master_size:
        sx, sy = master_size[0] / float(data["size"][0]), master_size[1] / float(data["size"][1])
    out = []
    for k in data.get("keepouts") or []:
        x, y, w, h = (float(v) for v in k["box"])
        if max(x, y, w, h) <= 1.0:
            x, y, w, h = x * W, y * H, w * W, h * H
        else:
            x, y, w, h = x * sx, y * sy, w * sx, h * sy
        out.append(dict(t0=float(k.get("t0", 0.0)), t1=float(k.get("t1", 1e9)), box=(x, y, w, h),
                        kind=k.get("kind", "")))
    return out


def map_box(pl, box, i=0):
    """Master-px box (x, y, w, h) -> target-px (x0, y0, x1, y1) through a reframe plan at frame ``i``."""
    x, y, w, h = box
    tw, th = pl["target"]
    sw, sh = pl["src_w"], pl["src_h"]
    r = R.rect_at(pl, i)
    if r is None:                                  # shown whole (pad-blur / letterbox / a subject plan's wide shot)
        s = min(tw / sw, th / sh)
        ox, oy = (tw - sw * s) / 2, (th - sh * s) / 2
        return (ox + x * s, oy + y * s, ox + (x + w) * s, oy + (y + h) * s)
    cx, cy, cw, ch = r
    s = tw / cw
    return ((x - cx) * s, (y - cy) * s, (x + w - cx) * s, (y + h - cy) * s)


def _rebalance(lines, mk):
    """Close/reopen highlight markup across wrapped lines so each line renders its own spans."""
    a, z = mk[0], mk[-1]
    out, open_ = [], False
    for ln in lines:
        s = (a if open_ else "") + ln
        depth = 0
        for ch in s:
            if ch == a:
                depth = 1
            elif ch == z:
                depth = 0
        open_ = depth == 1
        out.append(s + (z if open_ else ""))
    return out


def fit_cues(prof, cues):
    """Cues that do not fit the profile's caption box in ``max_lines`` lines (a whole spoken sentence in one cue) ->
    consecutive cues of at most ``max_lines`` lines each, the cue's time shared by length: captions stay inside the
    platform's safe area at every shape (3:4 cropped a single over-wide line on both sides)."""
    from .subs import Cue
    out = []
    n = int(prof.caption.get("max_lines", 2))
    for c in cues:
        fit = P.fit_text_size(prof, c.text.replace("\n", " "))
        lines = fit["lines"]
        if fit["fits"] or len(lines) <= n or c.alt or (c.meta or {}).get("kind") == "hook":
            out.append(c)
            continue
        parts = [" ".join(lines[k:k + n]) if not P._has_cjk(c.text) else "".join(lines[k:k + n])
                 for k in range(0, len(lines), n)]
        total = sum(max(1, len(x)) for x in parts)
        t = c.start
        for k, x in enumerate(parts):
            te = c.end if k == len(parts) - 1 else round(t + (c.end - c.start) * max(1, len(x)) / total, 3)
            out.append(Cue(t, te, x, "", dict(c.meta or {}, split_from=c.text[:40])))
            t = te
    return out


def caption_overlay(prof, cues, fps, role="cjk-bold", fill=(255, 255, 255, 255), keepouts=None, plan=None,
                    report=None):
    """overlay(i, t, img_bgr) for reframe.render: draws the active cue centred in caption_box.
    keepouts ([{t0, t1, box}] master px, see load_keepouts) + plan: while a keep-out is on screen and
    overlaps the caption, the caption moves to the nearest free spot above/below it inside the
    profile's safe box. ``report`` (dict) collects {"moved": n, "blocked": n} frame counts."""
    from . import draw
    x0, y0, x1, y1 = P.caption_box(prof)
    sx0, sy0, sx1, sy1 = P.safe_box(prof)
    cache = {}
    kos = list(keepouts or []) if plan is not None else []
    rep_ = report if report is not None else {}
    rep_.setdefault("moved", 0); rep_.setdefault("blocked", 0)
    mk = draw.markup()

    def layer(k, c):
        if k not in cache:
            fit = P.fit_text_size(prof, c.text.replace("\n", " "), role)
            f = draw.load_font(role, fit["size"])
            stroke = max(2, int(fit["size"] * float(prof.caption.get("stroke", 0.08))))
            st = (c.meta or {}).get("style") or {}
            fl = draw.rgba(st["fill"]) if st.get("fill") else fill
            hl = draw.rgba(st["highlight"]) if st.get("highlight") else None
            prim = _lines_layer(_rebalance(fit["lines"], mk), f, fl, stroke, hl)
            if c.alt and c.alt.strip():
                fa = draw.load_font("cjk", max(16, int(fit["size"] * 0.66)))
                alt_lines = draw.wrap(c.alt.strip(), fa, x1 - x0, balance=True, max_lines=2)
                sec = _lines_layer(alt_lines, fa, _alt_fill(st), max(2, stroke * 2 // 3))
                w = max(prim.width, sec.width)
                from PIL import Image
                im = Image.new("RGBA", (w, prim.height + sec.height - 8), (0, 0, 0, 0))
                im.alpha_composite(prim, ((w - prim.width) // 2, 0))
                im.alpha_composite(sec, ((w - sec.width) // 2, prim.height - 8))
                prim = im
            cache[k] = np.asarray(prim)
        return cache[k]

    spans = sorted(((c.start, c.end, k, c) for k, c in enumerate(cues) if c.text.strip()), key=lambda s: s[0])

    def _place(i, t, w, h, cx, y):
        boxes = [map_box(plan, k["box"], i) for k in kos if k["t0"] <= t < k["t1"]]
        if not boxes:
            return y
        def hits(yy):
            return any(not (cx + w / 2 <= b[0] or cx - w / 2 >= b[2] or yy + h <= b[1] or yy >= b[3]) for b in boxes)
        if not hits(y):
            return y
        m = 12
        cands = [b[1] - h - m for b in boxes] + [b[3] + m for b in boxes]
        cands = [c for c in cands if sy0 <= c <= sy1 - h and not hits(c)]
        if not cands:
            rep_["blocked"] += 1
            return y
        rep_["moved"] += 1
        return min(cands, key=lambda c: abs(c - y))

    from .subs import cue_opacity

    def overlay(i, t, img):
        for a, b, k, c in spans:                       # keep text within its spoken cue
            if a <= t < b:
                op = cue_opacity(a, b, t)
                if op <= 0:
                    continue
                L = layer(k, c)
                h, w = L.shape[:2]
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                y = min(cy - h / 2, y1 - h) if h <= y1 - y0 else cy - h / 2   # over-tall: centred on the band
                if kos:
                    y = _place(i, t, w, h, cx, y)
                draw.alpha_paste(img, L, (cx - w / 2, y), opacity=op, bgr=True)
        return img
    return overlay


def _alt_fill(style=None):
    """Colour of the second (translated) caption line: the cue's ``style.alt_fill``, else the theme's secondary ink
    over video (``over_ink2``), so a bilingual pair reads as one main line + a quieter translation."""
    from . import draw
    if (style or {}).get("alt_fill"):
        return draw.rgba(style["alt_fill"])
    try:
        from . import theme as TH
        return TH.rgba(TH.current(), "over_ink2")
    except Exception:                                   # noqa: BLE001 - themes optional
        return (226, 226, 222, 255)


def _lines_layer(lines, f, fill, stroke, hl_fill=None):
    """Centred stroked lines (markup 【】 highlighted in brand.highlight / ``hl_fill``) as one RGBA strip."""
    from PIL import Image
    from . import draw
    rows = [draw.text_layer(ln, f, fill=fill, hl_fill=hl_fill, stroke=stroke, stroke_fill=(0, 0, 0, 235),
                            shadow_alpha=110, pad=6)
            for ln in lines]
    if not rows:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    gap = -int(f.size * 0.12)
    w = max(r.width for r in rows)
    h = sum(r.height for r in rows) + gap * (len(rows) - 1)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    y = 0
    for r in rows:
        im.alpha_composite(r, ((w - r.width) // 2, y))
        y += r.height + gap
    return im


# ----------------------------------------------------------------------------------- covers
def _aspect(wh):
    return wh[0] / wh[1]


def fit_cover(src_img, size, focus=None):
    """Cover-crop a PIL image to ``size`` (w, h) around ``focus`` (fx, fy in 0..1, default centre)."""
    from PIL import Image
    W, H = size
    im = src_img.convert("RGB")
    s = max(W / im.width, H / im.height)
    rw, rh = max(W, int(round(im.width * s))), max(H, int(round(im.height * s)))
    im = im.resize((rw, rh), Image.LANCZOS)
    fx, fy = focus or (0.5, 0.5)
    x = int(min(max(fx * rw - W / 2, 0), rw - W))
    y = int(min(max(fy * rh - H / 2, 0), rh - H))
    return im.crop((x, y, x + W, y + H))


def fit_cover_pad(src_img, size, dim=0.55):
    """Fit a PIL image INSIDE ``size`` (nothing cropped) over a blurred, dimmed cover-crop of itself -
    for a cover whose aspect differs from the target (keeps a headline that a crop would cut)."""
    from PIL import Image, ImageEnhance, ImageFilter
    W, H = size
    im = src_img.convert("RGB")
    bg = fit_cover(im, size).filter(ImageFilter.GaussianBlur(max(8, W // 30)))
    bg = ImageEnhance.Brightness(bg).enhance(dim)
    s = min(W / im.width, H / im.height)
    fg = im.resize((max(1, int(round(im.width * s))), max(1, int(round(im.height * s)))), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    return bg


def parse_covers(covers):
    """--cover values -> (generic [paths], {target: path}); "douyin=c.png" / "xiaohongshu:full=c.png"
    are per-target, anything else (an existing path) is generic."""
    generic, per = [], {}
    for c in covers or []:
        c = os.fspath(c)
        if "=" in c and not os.path.exists(c):
            k, _, v = c.partition("=")
            per[k.strip()] = v.strip()
        else:
            generic.append(c)
    return generic, per


def _cover_for(prof, per):
    for k, v in (per or {}).items():
        n, _, o = k.partition(":")
        try:
            if P.canonical(n) != prof.name:
                continue
            if o and P.profile(n, o).key != prof.key:
                continue
        except (KeyError, ValueError):
            continue
        return v
    return None


def _face_focus(im):
    try:
        import cv2
        from . import face
        lm = face.landmarker(1)
        try:
            bgr = cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2BGR)
            f = face.main_face(face.detect(lm, bgr))
        finally:
            lm.close()
        if f is None:
            return None
        p = f["pts"]
        return float(p[:, 0].mean() / im.width), float(p[:, 1].mean() / im.height)
    except Exception:
        return None


def make_cover(prof, covers, video, out_path, at=None, per_target=None, warnings=None):
    """Write the profile's cover to out_path: the per-target cover (``per_target`` {"douyin": path,
    "xiaohongshu:full": path}) if one matches, else the closest-aspect image in ``covers`` (paths), else a
    frame of ``video`` (at ``at`` s, default 1/3 in). A cover of the right aspect (<= 5 % off) is
    cover-cropped (face-aware); a different aspect is FITTED over a blurred pad (never centre-cropped:
    that cuts the headline) and a warning asks for a per-target cover. Returns (path, notes)."""
    from PIL import Image
    size = P.cover_size(prof)
    notes = []
    pad = False
    own = _cover_for(prof, per_target)
    if own or covers:
        imgs = [(own, Image.open(own))] if own else [(c, Image.open(c)) for c in covers]
        c, im = min(imgs, key=lambda ci: abs(np.log(_aspect(ci[1].size) / _aspect(size))))
        if abs(np.log(_aspect(im.size) / _aspect(size))) > 0.05:
            pad = True
            msg = (f"cover {os.path.basename(c)} {im.width}x{im.height} is not {prof.cover.get('aspect')}: fitted on a "
                   f"blurred pad to {size[0]}x{size[1]}; pass --cover {prof.name}=<{size[0]}x{size[1]} cover> for a real one")
            notes.append(msg)
            if warnings is not None:
                warnings.append(msg)
    else:
        tmp = out_path + ".frame.png"
        media.grab_frame(video, at if at is not None else media.duration(video) / 3, tmp)
        im = Image.open(tmp); im.load(); os.remove(tmp)
        notes.append("no --cover given: used a frame of the export")
    if pad:
        fit_cover_pad(im, size).save(out_path, quality=92)
    elif abs(np.log(_aspect(im.size) / _aspect(size))) < 0.01:
        fit_cover(im, size).save(out_path, quality=92)          # same aspect: a plain resize, no face pass
    else:
        fit_cover(im, size, _face_focus(im)).save(out_path, quality=92)
    mb = prof.cover.get("max_bytes")
    if mb and os.path.getsize(out_path) > mb:
        Image.open(out_path).save(out_path, quality=80)
    fc = prof.cover.get("feed_crop")
    if fc:
        aw, ah = (float(v) for v in fc.split(":"))
        W, H = size
        cw, ch = (H * aw / ah, H) if W / H > aw / ah else (W, W * ah / aw)
        x0, y0 = (W - cw) / 2, (H - ch) / 2
        prev = os.path.splitext(out_path)[0] + ".feed.jpg"
        Image.open(out_path).crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).save(prev, quality=90)
        notes.append(f"feed shows a centre {fc} crop: preview {os.path.basename(prev)}")
    extra = [a for a in P.cover_crops(prof) if a != fc]
    if extra:
        chk = cover_crop_check(out_path, prof, write_previews=True)
        notes.append("cover is also shown as centre " + ", ".join(extra) + " crops: previews "
                     + ", ".join(os.path.basename(c["preview"]) for c in chk["crops"] if c.get("preview"))
                     + f" and {os.path.basename(chk['sheet'])}")
        for c in chk["crops"]:
            if c["cut_detail"]:
                msg = (f"cover: detail (text/edges) in the strips the {c['aspect']} crop cuts off "
                       f"({c['cut_density']:.0%} busy tiles) - keep the headline inside {list(P.cover_title_safe(prof))}")
                notes.append(msg)
                if warnings is not None:
                    warnings.append(msg)
    return out_path, notes


def _busy_tiles(edges, tile=48, busy=0.04):
    """Share of tile x tile blocks with > ``busy`` edge pixels (text / faces / detail, not flat or gradient fill)."""
    h, w = edges.shape
    if h < 8 or w < 8:
        return 0.0
    n = hit = 0
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            b = edges[y:y + tile, x:x + tile]
            if b.size < tile * tile // 4:
                continue
            n += 1
            hit += b.mean() > busy
    return hit / n if n else 0.0


def cover_crop_check(path, prof, write_previews=False, threshold=0.15):
    """Check a cover against every centre crop a surface shows (``platform.cover_crops``: Instagram 4:5 feed /
    3:4 grid / 1:1, 视频号 6:7 share card, B站 4:3 / 16:9, ...). For each crop: the box, and (cut_density) the
    share of busy 48 px tiles (text, faces, detail - not flat fill) in the busiest strip the crop removes; over
    ``threshold`` = ``cut_detail`` (something worth seeing is cut). write_previews: ``<stem>.crop-4x5.jpg`` per crop + ``<stem>.crops.jpg``,
    the cover with every crop outlined. Returns {crops: [{aspect, box, cut_density, cut_detail, preview}], sheet}."""
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.open(path).convert("RGB")
    W, H = im.size
    edges = np.asarray(im.convert("L").filter(ImageFilter.FIND_EDGES)) > 48
    stem = os.path.splitext(path)[0]
    out = []
    sheet = im.copy()
    dr = ImageDraw.Draw(sheet)
    colours = [(255, 214, 10), (45, 212, 191), (244, 114, 182), (96, 165, 250)]
    for k, a in enumerate(P.cover_crops(prof)):
        box = P.crop_box(W, H, a)
        x0, y0, x1, y1 = box
        strips = [edges[:y0], edges[y1:], edges[:, :x0], edges[:, x1:]]       # what the crop removes, per side
        dens = max([_busy_tiles(st) for st in strips if st.size] or [0.0])
        cut = any(st.size for st in strips)
        e = dict(aspect=a, box=list(box), cut_density=round(dens, 4), cut_detail=bool(cut and dens > threshold))
        if write_previews:
            pv = f"{stem}.crop-{a.replace(':', 'x')}.jpg"
            im.crop(box).save(pv, quality=90)
            e["preview"] = pv
        c = colours[k % len(colours)]
        dr.rectangle(box, outline=c, width=max(3, W // 200))
        dr.text((x0 + 12, y0 + 12 + 28 * k), a, fill=c)
        out.append(e)
    res = dict(crops=out, sheet=None)
    if write_previews and out:
        ts = P.cover_title_safe(prof)
        dr.rectangle(ts, outline=(255, 255, 255), width=2)
        res["sheet"] = f"{stem}.crops.jpg"
        sheet.save(res["sheet"], quality=88)
    return res


# ----------------------------------------------------------------------------------- export
MODE_ALIASES = {"follow": "subject", "blur": "pad-blur"}     # the creator's words (recipe param ``reframe``)


def shot_summary(pl):
    """{kind: number of shots} of a subject plan (follow / hold / face / pad-blur)."""
    out = {}
    for x in pl.get("shots") or []:
        out[x["kind"]] = out.get(x["kind"], 0) + 1
    return out


def load_shots(path):
    """``<master>.shots.json`` (vlog build: {transitions: [[t0, t1], ...]}) -> the transitions list (seconds)."""
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    tr = d.get("transitions") if isinstance(d, dict) else d
    return [[float(a), float(b)] for a, b in tr or []]


def _publish_platform(prof):
    return "youtube" if prof.name == "youtube-shorts" else prof.name


def _scale_only(master, dst, prof, info, start, dur, vargs, fps_out, wm_png=None):
    """Same-aspect fast path: one ffmpeg scale + encode (no Python frame pipe, no face tracking). ``wm_png``:
    (path, x, y) of the scaled watermark, laid over in the same pass."""
    win = (["-ss", f"{start:.3f}"] if start else []) + (["-t", f"{dur:.3f}"] if dur else [])
    # Convert the pixels to the delivery matrix, as well as tagging them. Older
    # FFmpeg releases otherwise preserve an untagged SD input's 601 coefficients
    # while delivery_args labels the HD output 709 (a visible saturated-colour shift).
    vf = f"scale={prof.w}:{prof.h}:flags=lanczos:out_color_matrix=bt709:out_range=tv,setsar=1"
    if wm_png:
        from . import watermark as WM
        cmd = [media.ffmpeg_bin(), "-y", "-v", "error", *win, "-i", master, "-i", wm_png[0], "-filter_complex",
               f"[0:v:0]{vf}[b];" + WM.ffmpeg_overlay("[b]", 1, wm_png[1], wm_png[2]), "-map", "[v]"]
    else:
        cmd = [media.ffmpeg_bin(), "-y", "-v", "error", *win, "-i", master, "-map", "0:v:0", "-vf", vf]
    if info["has_audio"]:
        cmd += ["-map", "0:a:0"]
    cmd += list(vargs) + (["-r", str(fps_out)] if fps_out else [])
    cmd += (["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"] if info["has_audio"] else ["-an", "-movflags", "+faststart"])
    media.run(cmd + [dst])
    return dst


def export_one(master, prof, out_dir, cues=None, covers=None, post=None, mode="face", fallback="pad-blur",
               start=0.0, dur=None, workdir=None, encoder=None, preset="medium", captions=True,
               cover_targets=None, post_lang=None, watermark=None, cover_ab=None, effects=None, cover_canvas="platform", **reframe_opts):
    """Export ``master`` for one Profile. Returns the manifest entry (dict).
    cues: one track (cues.json / .srt path or a list) or {lang: track} (pick_track takes the platform's language).
    captions: "both" (True, default) | "burn" | "sidecar" | "off" (False: never burn ``cues``, the master already has
    them) - see the module doc, step 7. cover_targets: {target: path}
    per-target covers (see make_cover). watermark: True / False / None (= the creator's default, vstudio.watermark;
    never drawn when none is set up). cover_canvas="video" keeps the cover on the video canvas,
    with a preview of the platform feed crop."""
    from . import audio
    mode = MODE_ALIASES.get(mode, mode)
    info = media.probe(master)
    stem = f"{prof.name}-{prof.orientation}"
    out_mp4 = os.path.join(out_dir, stem + ".mp4")
    warnings = []
    same_aspect = abs(np.log(_aspect((info["display_w"], info["display_h"])) / _aspect(prof.size))) < 0.01
    crop_b = float(reframe_opts.pop("crop_bottom", 0) or 0)
    crop_t = float(reframe_opts.pop("crop_top", 0) or 0)
    band = None
    if mode == "band":                              # old burned captions cropped off, the rest fitted in a band
        sw, sh = int(info["display_w"]), int(info["display_h"])
        y0 = int(round(sh * max(0.0, crop_t)))
        hh = max(2, int(round(sh * max(0.1, 1 - crop_t - crop_b))) // 2 * 2)
        band = dict(crop_top=crop_t, crop_bottom=crop_b, region=[0, y0, sw, min(hh, sh - y0)])
        m = "pad-blur"
        reframe_opts["region"] = band["region"]
    else:
        m = "letterbox" if same_aspect else mode   # same aspect: a fit == a plain scale, no face tracking
    pl = R.plan(master, prof.w, prof.h, mode=m, safe=P.safe_box(prof), start=start, dur=dur,
                fallback=fallback, caption=P.caption_box(prof), **reframe_opts)
    if band:
        same_aspect = False
    if pl["mode_used"] != m:
        warnings.append(f"reframe fell back to {pl['mode_used']}: {pl.get('fallback_reason')}")
    wide = [x for x in pl.get("shots") or [] if x["kind"] == "pad-blur"]
    if wide and pl["mode_used"] == "subject":
        warnings.append(f"{len(wide)} of {len(pl['shots'])} shots shown whole on a blurred fill: "
                        + "; ".join(dict.fromkeys(x["reason"] for x in wide)))
    cmode = captions_mode(captions)
    upload = bool(prof.extra.get("caption_upload"))
    src, track_lang, track_warn = pick_track(prof, cues)
    burn = cmode in ("both", "burn") or (cmode == "sidecar" and not upload)
    all_cues = load_cues(src) if (src is not None and cmode != "off") else []
    shown, lang_warn = cues_for_platform(prof, all_cues)
    cue_list = shown if burn else []
    if all_cues:
        warnings += track_warn + (lang_warn if burn else [])
    kos = load_keepouts(src, (info["display_w"], info["display_h"])) if cue_list else []
    if start:
        from .subs import Cue
        cue_list = [Cue(c.start - start, c.end - start, c.text, c.alt, c.meta) for c in cue_list if c.end > start]
        kos = [dict(k, t0=k["t0"] - start, t1=k["t1"] - start) for k in kos if k["t1"] > start]
    cue_list = fit_cues(prof, cue_list)                # a cue too long for the caption box: shown in turns, inside it
    cap_report = {}
    pl_geo = pl
    overlay = caption_overlay(prof, cue_list, pl["fps"], keepouts=kos, plan=pl_geo, report=cap_report) if cue_list else None
    if effects:
        from . import spoken
        fx = [dict(e, start=e["start"] - start, end=e["end"] - start) for e in effects
              if e["end"] > start and (dur is None or e["start"] < start + dur)]
        draw_effects = spoken.overlay(fx, prof.w, prof.h, P.safe_box(prof))
        draw_captions = overlay

        def overlay(i, t, img, _f=draw_effects, _c=draw_captions):
            picture = _f(i, t, img)
            return _c(i, t, picture) if _c else picture
    for c in cue_list:
        fit = P.fit_text_size(prof, c.text.replace("\n", " "))
        if not fit["fits"]:
            warnings.append(f"caption too long for {prof.caption['max_lines']} lines at min size: {c.text[:24]}…")
    from . import watermark as WM
    wm_cfg = WM.resolve(prof.name, override=watermark)
    if wm_cfg and WM.already_marked(master):
        wm_cfg = None
        warnings.append("watermark: the master is an export that already carries it (not drawn twice)")
    if wm_cfg:
        wm_draw = WM.overlay(wm_cfg, prof.w, prof.h, prof)
        cap_ov = overlay

        def overlay(i, t, img, _c=cap_ov, _w=wm_draw):
            return _w(_c(i, t, img) if _c else img)
    fps_out = None
    if info["fps"] and info["fps"] > prof.fps.get("max", 60) + 0.5:
        fps_out = prof.fps.get("default", 30)
    enc = dict(prof.encode)
    vargs = media.delivery_args(crf=enc.get("crf"), preset=preset, audio=None, faststart=False, encoder=encoder,
                                maxrate=enc.get("maxrate"), bufsize=enc.get("bufsize"), vbitrate=enc.get("vbitrate"),
                                hw_bitrate=P.delivery_bitrate(prof, prof.w, prof.h, fps_out or info["fps"] or 30))
    has_a = info["has_audio"]
    tmpd = workdir or tempfile.mkdtemp(prefix="vexport-")
    try:
        fast = same_aspect and not effects and (overlay is None or (wm_cfg and not cue_list)) and not info.get("hdr")
        wm_png = WM.write_png(wm_cfg, prof.w, prof.h, prof, os.path.join(tmpd, stem + ".wm.png")) \
            if (fast and wm_cfg) else None
        if has_a:
            mid = os.path.join(tmpd, stem + ".mov")
            if fast:
                _scale_only(master, mid, prof, info, start, dur, vargs, fps_out, wm_png)
            else:
                R.render(master, mid, pl_geo, overlay=overlay,
                         encode_args=vargs + ["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"], fps=fps_out)
            audio.loudnorm_2pass(mid, out_mp4, lufs=prof.loudness["lufs"], tp=prof.loudness["tp"])
        else:
            if fast:
                _scale_only(master, out_mp4, prof, info, start, dur, vargs, fps_out, wm_png)
            else:
                R.render(master, out_mp4, pl_geo, overlay=overlay, encode_args=vargs + ["-an", "-movflags", "+faststart"],
                         fps=fps_out)
            warnings.append("master has no audio")
        if cap_report.get("blocked"):
            warnings.append(f"captions overlap a burned overlay (keepout) on {cap_report['blocked']} frames: "
                            f"no free spot in the safe box")
    finally:
        if workdir is None:
            shutil.rmtree(tmpd, ignore_errors=True)
    crop_json = os.path.join(out_dir, stem + ".crop.json")
    with open(crop_json, "w") as f:
        json.dump(pl, f)
    oinfo = media.probe(out_mp4)
    loud = None
    if has_a:
        mm = audio.measure_loudness(out_mp4, prof.loudness["lufs"], prof.loudness["tp"])
        loud = dict(i=round(mm["input_i"], 2), tp=round(mm["input_tp"], 2), lra=round(mm["input_lra"], 2))
        if abs(mm["input_i"] - prof.loudness["lufs"]) > 1.0:
            warnings.append(f"loudness {mm['input_i']:.1f} LUFS vs target {prof.loudness['lufs']}")
        if mm["input_tp"] > prof.loudness["tp"] + 0.5:
            warnings.append(f"true peak {mm['input_tp']:.1f} dBTP over {prof.loudness['tp']}")
    warnings += P.check_length(prof, oinfo["duration"])
    warnings += P.check_format(prof, info["display_w"] / info["display_h"], oinfo["duration"])
    lim = prof.extra.get("limits") or {}
    if lim.get("max_bytes") and os.path.getsize(out_mp4) > lim["max_bytes"]:
        warnings.append(f"file {os.path.getsize(out_mp4) / 1e6:.0f} MB over the {prof.name} upload cap "
                        f"{lim['max_bytes'] / 1e6:.0f} MB ({prof.extra.get('account') or 'standard'} account)")
    sidecars = write_sidecars(prof, cues, out_dir, stem, start, dur) \
        if (upload and cues is not None and cmode in ("both", "sidecar")) else []
    capr = prof.extra.get("captions") or {}
    if capr.get("burn") == "recommended" and not cue_list and cmode != "off":
        warnings.append(f"{prof.name}: {capr.get('reason', 'burned captions recommended')} "
                        + ("(--captions sidecar: only the caption file, which viewers must switch on)" if sidecars
                           else "(pass --cues)"))
    cprof = P.video_canvas_cover(prof) if cover_canvas == "video" else prof
    cover_path, notes = make_cover(cprof, covers, out_mp4, os.path.join(out_dir, stem + ".cover.jpg"),
                                   per_target=cover_targets, warnings=warnings)
    entry = dict(platform=prof.name, orientation=prof.orientation, label=prof.label, file=os.path.basename(out_mp4),
                 w=oinfo["w"], h=oinfo["h"], fps=round(oinfo["fps"], 3), duration=round(oinfo["duration"], 3),
                 loudness=loud, target_loudness=prof.loudness, reframe=dict(
                     mode="scale" if same_aspect else pl["mode"], mode_used="scale" if same_aspect else pl["mode_used"],
                     hit_rate=pl.get("hit_rate"), cuts=len(pl.get("cuts") or []),
                     switches=pl.get("switches"), stats=pl.get("stats"), plan=os.path.basename(crop_json),
                     **({"band": band} if band else {}), **({"shots": shot_summary(pl)} if pl.get("shots") else {})),
                 captions=len(cue_list), captions_mode=cmode, keepouts=len(kos), captions_moved_frames=cap_report.get("moved", 0),
                 cover=os.path.basename(cover_path), cover_size=list(P.cover_size(cprof)),
                 notes=notes, safe_box=list(P.safe_box(prof)), caption_box=list(P.caption_box(prof)),
                 watermark=dict(WM.summary(wm_cfg), box=list(WM.box(wm_cfg, prof.w, prof.h, prof))) if wm_cfg else None)
    if track_lang:
        entry["caption_track"] = track_lang
    if sidecars:
        entry["sidecars"] = [dict(lang=s["lang"], file=s["file"]) for s in sidecars]
        entry["notes"].append(f"caption files to upload on {prof.label} (one per language): "
                              + ", ".join(s["file"] for s in sidecars))
    if prof.feed_crop:
        entry["notes"].append(f"{prof.label} feed shows a centre {prof.feed_crop} crop of the video "
                              f"{list(P.feed_crop_box(prof))}: keep faces and captions inside it")
    ab = _cover_for(prof, cover_ab) if cover_ab else None
    if ab:
        entry["cover_ab"] = write_cover_ab(cprof, [x for x in str(ab).split(",") if x.strip()], out_dir, stem)
    if post:
        src_cues = cue_list or shown or (load_cues(src) if src is not None else [])
        own = _lang_base(track_lang) if (track_lang and not track_warn) else None   # the copy follows the track
        warnings += write_post(prof, out_dir, post, entry, cues=src_cues, post_lang=post_lang or own)
        if entry.get("cover_ab") and entry.get("post"):
            with open(os.path.join(out_dir, entry["post"]), "a", encoding="utf-8") as f:
                f.write("\n" + cover_ab_note(entry["cover_ab"]))
    entry["warnings"] = list(dict.fromkeys(warnings))
    return entry


def write_cover_ab(prof, files, out_dir, stem):
    """A thumbnail A/B pack (YouTube Studio "Test & Compare" takes up to 3): each file fitted to the cover size as
    ``<stem>.cover.ab<k>.jpg`` (under the profile's byte cap) -> [basenames]."""
    from PIL import Image
    out = []
    for k, src in enumerate(files[:3]):
        if not os.path.exists(src):
            continue
        dst = os.path.join(out_dir, f"{stem}.cover.ab{k + 1}.jpg")
        q = 92
        im = fit_cover(Image.open(src), P.cover_size(prof))
        im.save(dst, quality=q)
        while prof.cover.get("max_bytes") and os.path.getsize(dst) > prof.cover["max_bytes"] and q > 60:
            q -= 8
            im.save(dst, quality=q)
        out.append(os.path.basename(dst))
    return out


def cover_ab_note(names):
    """The post.md section that goes with an A/B pack."""
    rows = "\n".join(f"{k + 1}. {n}" for k, n in enumerate(names))
    return ("## Thumbnail A/B test\n\nIn YouTube Studio open the video > Thumbnail > Test & Compare and upload "
            f"these {len(names)}; YouTube keeps the one with the most watch time. Number 1 is the cover set now.\n\n"
            + rows + "\n")


def write_post(prof, out_dir, post, entry, cues=None, post_lang=None):
    """``<platform>-<orientation>.post.md`` of one export from post.json (``post``): the platform's text in its
    language (publish.platform_post), checked against its limits. Updates ``entry`` (post, post_lang, post_len,
    post_warnings, notes) -> the warnings about the text."""
    from . import publish
    msgs = []
    content_lang = post_lang or publish.detect_lang(cues or [])
    body, copy = publish.platform_post(post, _publish_platform(prof), content_lang=content_lang,
                                       lang=post.get("_lang"), bilingual=post.get("_bilingual"), warn=msgs.append)
    ttl = publish.fit_title(copy["title"], _publish_platform(prof))[0] if copy.get("title") else None
    msgs += P.check_text(prof, title=ttl, body=body, tags=copy.get("tags"))   # the title as post_body fit it
    if copy.get("chapters") and not prof.chapters.get("supported") and prof.name not in publish.NO_TITLE:
        note = f"{prof.label} has no native chapters; timeline kept as plain text"
        if note not in entry.setdefault("notes", []):
            entry["notes"].append(note)
    pp = os.path.join(out_dir, f"{prof.name}-{prof.orientation}.post.md")
    text = body
    if entry.get("sidecars"):                        # the upload notes, outside the measured post text; a short-post
        note = sidecar_note(prof, entry["sidecars"])    # platform (X: 280) keeps post.md the exact text to paste
        fuller = body.rstrip("\n") + "\n\n" + note
        if not prof.desc_max or P.text_len(prof, fuller) <= prof.desc_max:
            text = fuller
    with open(pp, "w", encoding="utf-8") as f:
        f.write(text)
    entry.update(post=os.path.basename(pp), post_lang=copy.get("lang"), post_len=P.text_len(prof, body),
                 post_warnings=list(dict.fromkeys(msgs)))
    return msgs


def _profile_of(e, master_aspect=None):
    """A manifest entry -> its platform Profile."""
    return P.parse_targets([f"{e['platform']}:{e['orientation']}"], master_aspect=master_aspect)[0]


# text warnings an export wrote before ``post_warnings`` was kept apart (old manifests): dropped when the post is
# written again, so they are not reported twice
_OLD_TEXT_WARNING = ("needs a title", "em-dash", "title ", "description ", "hashtag", "links in the text",
                     "put the link", "tags")


def rewrite_posts(out_dir, post, cues=None, post_lang=None):
    """Write every export's post.md again from ``post`` (no video work) and update ``manifest.json`` -> the manifest.
    The new per-platform post copy of a finished video."""
    path = os.path.join(out_dir, "manifest.json")
    with open(path, encoding="utf-8") as f:
        man = json.load(f)
    for e in man.get("exports") or []:
        prof = _profile_of(e)
        old = e.get("post_warnings")
        if old is not None:
            keep = [w for w in e.get("warnings") or [] if w not in old]
        else:
            keep = [w for w in e.get("warnings") or [] if not any(k in w for k in _OLD_TEXT_WARNING)]
        e["warnings"] = list(dict.fromkeys(keep + write_post(prof, out_dir, post, e, cues=cues, post_lang=post_lang)))
    man["warnings"] = [f"{e['platform']}:{e['orientation']}: {w}" for e in man.get("exports") or []
                       for w in e["warnings"]]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    return man


def export(master, targets, out_dir="exports", cues=None, covers=None, post=None, account=None, merge=False, **kw):
    """Export to every target ("name[:orientation]" strings or Profiles). Writes out_dir/manifest.json and
    returns the manifest dict. A bare platform name that takes several shapes (X) gets the orientation closest
    to the master's aspect (no letterbox); ``account`` ("premium") applies that account tier's limits.
    ``merge``: the targets are made again, the other exports already in out_dir/manifest.json are kept."""
    os.makedirs(out_dir, exist_ok=True)
    mi = media.probe(master)
    aspect = mi["display_w"] / mi["display_h"]
    ov = {"account": account} if account else None
    profs = P.parse_targets(targets if isinstance(targets, (str, list, tuple)) else [targets], master_aspect=aspect,
                            overrides=ov)
    covers = [covers] if isinstance(covers, str) else list(covers or [])
    covers, per = parse_covers(covers)
    if per:
        kw = dict(kw, cover_targets=dict(per, **(kw.get("cover_targets") or {})))
    if kw.get("cover_ab") is not None:
        kw["cover_ab"] = parse_covers(kw["cover_ab"])[1] or None
    from .batch.livestatus import heartbeat
    done = []

    def one(prof):
        print(f"[export] {prof.key} {prof.w}x{prof.h}", file=sys.stderr)
        e = export_one(master, prof, out_dir, cues=cues, covers=covers, post=post, **kw)
        done.append(prof.key)
        heartbeat("export", progress=len(done) / max(1, len(profs)), message=prof.key, force=True)
        return e
    # platforms render side by side (each is a decode -> draw -> encode pipe that leaves cores idle on its own):
    # ~1.6x faster for the usual two or three targets. $VSTUDIO_EXPORT_PARALLEL=1 renders one at a time.
    workers = max(1, min(len(profs), int(os.environ.get("VSTUDIO_EXPORT_PARALLEL") or 2)))
    heartbeat("export", progress=0.0, message=", ".join(p.key for p in profs), force=True)
    if workers == 1:
        entries = [one(p) for p in profs]
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(workers) as ex:
            entries = list(ex.map(one, profs))
    if merge:
        try:
            with open(os.path.join(out_dir, "manifest.json"), encoding="utf-8") as f:
                old = json.load(f).get("exports") or []
        except (OSError, ValueError):
            old = []
        key = lambda e: (e["platform"], e["orientation"])  # noqa: E731
        new = {key(e): e for e in entries}
        had = {key(e) for e in old}
        entries = [new.get(key(e), e) for e in old] + [e for e in entries if key(e) not in had]
    man = dict(master=os.path.abspath(master), master_info={k: media.probe(master)[k] for k in
                                                            ("w", "h", "fps", "duration", "has_audio")},
               exports=entries, warnings=[f"{e['platform']}:{e['orientation']}: {w}" for e in entries for w in e["warnings"]])
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    return man


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m vstudio.export", description=__doc__.split("\n\n")[0])
    ap.add_argument("master", help="clean (caption-free) master video")
    ap.add_argument("--platforms", default=None,
                    help="comma list of name[:orientation], e.g. xiaohongshu:vertical,douyin,youtube "
                         "(default persona platforms.default). Known: " + ", ".join(P.list_profiles()))
    ap.add_argument("--out", default="exports")
    ap.add_argument("--cues", action="append", default=None,
                    help="cues.json (subs.Cue dicts) or .srt to burn per platform; repeatable as lang=path, one track "
                         "per language (--cues en=cues.en.json --cues zh=cues.zh.json): each platform takes the "
                         "track in its language (YouTube English, 小红书 / B站 / 抖音 Chinese)")
    ap.add_argument("--captions", choices=list(CAPTION_MODES), default="both",
                    help="both (default): burn + a <target>.<lang>.srt where the platform takes a caption upload "
                         "(YouTube, X, Facebook, LinkedIn); sidecar: no burn there (clean video + SRT), still "
                         "burned elsewhere; burn: burn only, no SRT")
    ap.add_argument("--cover", action="append", default=[],
                    help="cover image(s): a path (closest aspect wins; another aspect is fitted on a blurred pad) "
                         "or platform[:orientation]=path for one target, e.g. --cover xiaohongshu=c34.png")
    ap.add_argument("--cover-canvas", default="platform", choices=["platform", "video"],
                    help="cover on the platform canvas or on the exported video canvas")
    ap.add_argument("--cover-ab", action="append", default=[],
                    help="thumbnail A/B pack for one target: platform=a.jpg,b.jpg,c.jpg (YouTube Test & Compare) "
                         "-> <target>.cover.ab1..3.jpg + a note in its post")
    ap.add_argument("--no-captions", action="store_true",
                    help="do not burn --cues (the master already carries its captions)")
    ap.add_argument("--title", help="post title (checked against each platform's limit)")
    ap.add_argument("--post", help="post.json {title, hook, body, chapters, links, tags} -> <target>.post.md")
    ap.add_argument("--lang", default=None, help="post copy language (en | zh); default: the content language "
                    "detected from the cues (English content -> English copy on X / Instagram / TikTok / YouTube)")
    ap.add_argument("--bilingual", action="store_true", help="post copy in English + Chinese (post.json en + zh blocks)")
    ap.add_argument("--account", default=None, help="account tier for limits, e.g. premium (X: longer videos/posts)")
    ap.add_argument("--mode", default="face", choices=list(R.MODES) + list(MODE_ALIASES),
                    help="reframe mode when the aspect changes: face (talking head), subject / follow (travel, "
                    "drone: follow what stands out per shot), pad-blur / blur, center, letterbox")
    ap.add_argument("--shots", help="shots.json {transitions: [[t0, t1], ...]} of the master (crossfades) for "
                    "--mode subject")
    ap.add_argument("--fallback", default="pad-blur", choices=R.MODES[1:])
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=None)
    ap.add_argument("--encoder", default=None, help="H.264 encoder (default $VSTUDIO_H264_ENCODER / persona "
                    "export.h264_encoder / libx264): libx264 | videotoolbox | h264_videotoolbox | h264_mf")
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--watermark", choices=["auto", "on", "off"], default="auto",
                    help="the creator's watermark (python -m vstudio.watermark): auto = her default, on, off")
    a = ap.parse_args(argv)
    targets = a.platforms
    if not targets:
        try:
            from .config import persona
            targets = (persona().get("platforms") or {}).get("default") or "xiaohongshu"
        except Exception:
            targets = "xiaohongshu"
    post = None
    if a.post:
        with open(a.post, encoding="utf-8") as f:
            post = json.load(f)
    if a.title:
        post = dict(post or {}, title=a.title)
    if post is not None and (a.lang or a.bilingual):
        post = dict(post, _lang=a.lang, _bilingual=a.bilingual or None)
    man = export(a.master, targets, a.out, cues=parse_cues_arg(a.cues), covers=a.cover, post=post, account=a.account,
                 mode=MODE_ALIASES.get(a.mode, a.mode), fallback=a.fallback, transitions=load_shots(a.shots),
                 start=a.start, dur=a.dur, encoder=a.encoder, preset=a.preset, captions="off" if a.no_captions else a.captions,
                 watermark=None if a.watermark == "auto" else a.watermark == "on", cover_ab=a.cover_ab or None, cover_canvas=a.cover_canvas)
    for e in man["exports"]:
        print(f"{e['file']:32s} {e['w']}x{e['h']} {e['duration']:.1f}s "
              f"{(e['loudness'] or {}).get('i', '-')} LUFS  reframe={e['reframe']['mode_used']}")
    for w in man["warnings"]:
        print("WARN", w)
    print(os.path.join(a.out, "manifest.json"))


if __name__ == "__main__":
    sys.exit(main())
