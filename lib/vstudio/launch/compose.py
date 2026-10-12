"""Plan -> a HyperFrames project (index.html + assets) -> rendered, delivered MP4.

    from vstudio.launch import compose as CO
    proj = CO.build(cfg, plan, "kit/build/demo-en-16x9")       # writes the project, returns its dir
    CO.render(proj, "kit/demo/demo-en-16x9.mp4")             # npx hyperframes render + delivery (BT.709, faststart)

The look: a launch film. The product window is big, rounded, with a soft shadow on a gradient backdrop tinted with
the brand accent (brand.backdrop: studio | deep | paper; never black); a dark recording is lifted a little. Inside the
window the camera opens on an establishing frame and pushes 1.6-3x onto where the action is (story.push_camera).
Headlines are large, tightly tracked (Inter / Noto Sans SC) and rise word by word through a line mask; the 【term】
gets a marker sweep. Scenes hand over in 6-12 frames with push / zoom-through / rise / match cuts, centred on the
beats of the music bed. The end card animates the brand mark, name, call to action and site. No voice, no
music bed from the shared library (vstudio.music: built-in beds generated in code, free for any use; or your
own track with its license), no voice unless the config adds one (a TTS voice-over is labelled "AI voice").
HyperFrames CLI: ``npx hyperframes`` (set $VSTUDIO_HYPERFRAMES to pin a version, e.g. hyperframes@0.8.130).
"""
import html
import json
import os
import shutil
import subprocess

from vstudio import media

from . import brand as B
from . import config as C
from . import story as S
from ..oscompat import relpath as _relpath

GSAP = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"
DISPLAY_W = 560                 # display font weight used on screen (and when measuring)


def _e(s):
    return html.escape(s or "", quote=True)


def _r(x):
    return round(float(x), 3)


def hyperframes_cmd():
    spec = os.environ.get("VSTUDIO_HYPERFRAMES") or "hyperframes"
    return ["npx", spec]


# ------------------------------------------------------------------------------------------------ text
def caption_html(lines, cls="w"):
    """Fitted lines -> spans: one .w per word (CJK: per character run) and .mk around the 【term】."""
    out = []
    for ln in lines:
        parts, buf, i = [], "", 0
        while i < len(ln):
            if ln[i] == "【":
                j = ln.find("】", i)
                j = len(ln) if j < 0 else j
                if buf:
                    parts.append(("t", buf))
                    buf = ""
                parts.append(("m", ln[i + 1:j]))
                i = j + 1
            else:
                buf += ln[i]
                i += 1
        if buf:
            parts.append(("t", buf))
        spans = []
        for kind, txt in parts:
            if kind == "m":
                spans.append(f'<span class="{cls} mk">{_e(txt)}</span>')
                continue
            for w in _words(txt):
                spans.append(f'<span class="{cls}">{_e(w)}</span>' if w.strip() else _e(w))
        out.append('<span class="ln">' + "".join(spans) + "</span>")
    return "<br>".join(out)


def _words(txt):
    import re
    if any("㐀" <= c <= "鿿" for c in txt):
        return re.findall(r"[㐀-鿿][，。、！？；：]?|[^㐀-鿿]+", txt)
    return re.findall(r"\S+|\s+", txt)


# ------------------------------------------------------------------------------------------------ assets
def _asset(src, proj, sub, name=None):
    d = os.path.join(proj, "assets", sub)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, name or os.path.basename(src))
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        shutil.copy2(src, dst)
    return _relpath(dst, proj)


def _frame(src, t, proj, name):
    d = os.path.join(proj, "assets", "frames")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, name)
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        media.grab_frame(src, max(0.0, t), out, quality=2)
    return _relpath(out, proj)


def _music(cfg, proj, total):
    m = cfg.get("music")
    if not m:
        return None
    from vstudio import music as MU
    src = MU.resolve(m.get("file") or m["mood"], duration=total + 1.0, seed=int(m.get("seed", 0)))
    d = os.path.join(proj, "assets", "audio")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, "music.m4a")
    fo = max(0.0, total - 1.6)
    media.run(["ffmpeg", "-y", "-i", src, "-t", f"{total:.3f}", "-af",
               f"afade=t=in:d=0.4,afade=t=out:st={fo:.3f}:d=1.6", "-c:a", "aac", "-b:a", "192k", out])
    return _relpath(out, proj)


def _vo(cfg, scene, proj, lang):
    from vstudio import tts
    vo = cfg.get("voiceover") or {}
    d = os.path.join(proj, "assets", "audio")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, f"vo-{scene['id']}-{lang}.wav")
    tts.synth(C.plain(scene["vo"]), engine=vo.get("engine") or "auto", voice=vo.get("voice"), out=out)
    return _relpath(out, proj), media.probe(out)["duration"]


# ------------------------------------------------------------------------------------------------ build
CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: {W}px; height: {H}px; overflow: hidden; background: var(--bg-bot); }
#root { position: relative; width: {W}px; height: {H}px; overflow: hidden; color: var(--lk-ink);
  background: linear-gradient(172deg, var(--bg-top) 0%, var(--bg-bot) 100%); }
.full { position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; }
#bg { overflow: hidden; }
.glow { position: absolute; border-radius: 50%; will-change: transform; }
.scene { position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; opacity: 0; }
.kicker { position: absolute; font-family: {TEXT}; font-weight: 600; letter-spacing: .16em; text-transform: uppercase;
  color: var(--lk-accent-text); opacity: 0; display: flex; justify-content: center; align-items: center; gap: .7em;
  white-space: nowrap; }
.kicker i { display: inline-block; width: 1.8em; height: 2px; background: var(--lk-accent); }
.cap { position: absolute; font-family: {DISPLAY}; font-weight: {DW}; line-height: 1.1; letter-spacing: {TRACK};
  color: var(--lk-ink); text-align: center; }
.cap .w, .title .w, .oneliner .w, .cta .w { display: inline-block; opacity: 0; white-space: pre; }
.ln { display: inline-block; white-space: nowrap; overflow: hidden; vertical-align: top;
  padding: .02em .06em .16em; margin: 0 -.06em -.16em; }   /* the line is the mask the words rise through */
.cap .mk { padding: 0 .1em; margin: 0 -.02em; border-radius: .14em;
  background-image: linear-gradient(var(--lk-marker), var(--lk-marker)); background-repeat: no-repeat;
  background-position: 0 86%; background-size: 0% 42%; }
.win { position: absolute; overflow: hidden; border-radius: {RADIUS}px; background: #0c0d0e; opacity: 0;
  box-shadow: 0 0 0 1px rgba(var(--lk-shadow), .10), 0 2px 6px rgba(var(--lk-shadow), .10),
    0 24px 48px -12px rgba(var(--lk-shadow), .30), 0 60px 120px -30px rgba(var(--lk-shadow), .45); }
.win::after { content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.08); }
.cam { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
.cam > img, .cam > video { position: absolute; left: 0; top: 0; width: 100%; height: 100%; object-fit: fill; }
.center { position: absolute; left: 0; width: {W}px; text-align: center; }
.mark { position: absolute; opacity: 0; }
.title { font-family: {DISPLAY}; font-weight: {TW}; letter-spacing: {TTRACK}; color: var(--lk-ink); line-height: 1.04; }
.oneliner { font-family: {DISPLAY}; font-weight: {OW}; color: var(--lk-ink2); line-height: 1.25; letter-spacing: -.01em; }
.chip, .site { display: inline-block; font-family: {TEXT}; font-weight: 600; letter-spacing: .02em;
  color: var(--lk-accent-text); border: 2px solid var(--lk-accent); border-radius: 999px; padding: .34em 1.05em;
  opacity: 0; background: rgba(255,255,255,.04); }
.cta { font-family: {DISPLAY}; font-weight: {OW}; color: var(--lk-ink2); line-height: 1.2; letter-spacing: -.012em; }
.sub { font-family: {TEXT}; font-weight: 400; color: var(--lk-ink2); opacity: 0; }
.ailabel { position: absolute; font-family: {TEXT}; font-size: 20px; color: var(--lk-ink2); opacity: .85; }
"""


def _fit_caption(text, lang, layout, files, weight=DISPLAY_W):
    x0, y0, x1, y1 = layout["text"]
    px, lines = B.fit(text, files["display"], layout["caption_px"], int((x1 - x0) * 0.97), layout["caption_lines"], lang,
                      weight)
    return px, lines


def _ease_in_words(tl_lines, sel, at, stagger=0.05, dur=0.7, rise=None):
    """Words rise through their line (the .ln mask) with a stagger: the headline reveal."""
    tl_lines.append(f'tl.fromTo("{sel}", {{opacity: 0, yPercent: 112}}, {{opacity: 1, yPercent: 0, duration: {dur}, '
                    f'ease: "expo.out", stagger: {stagger}}}, {_r(at)});')


def _cap_top(layout, px, nlines, kicker):
    """Caption block top: its bottom sits ``gap`` above the window, never above the text box (+ the kicker)."""
    x0, y0, x1, y1 = layout["text"]
    kpx = layout["kicker_px"]
    h = int(px * 1.1 * nlines)
    return max(y0 + (int(kpx * 1.9) if kicker else 0), layout["win"][1] - layout.get("gap", 30) - h)


_LUMA = {}


def _lift(still):
    """CSS filter for the product footage: a dark UI is lifted a little (no murky frames), a light one gets a touch
    of contrast (crisp). Decided from the shot's poster frame."""
    if not still or not os.path.exists(still):
        return ""
    if still not in _LUMA:
        try:
            from PIL import Image, ImageStat
            with Image.open(still) as im:
                _LUMA[still] = ImageStat.Stat(im.convert("L").resize((160, 100))).mean[0] / 255
        except Exception:                                     # noqa: BLE001 - an unreadable poster: no filter
            _LUMA[still] = None
    y = _LUMA[still]
    if y is None:
        return ""
    if y < 0.22:
        return "filter: brightness(1.16) contrast(1.06) saturate(1.06);"
    return "filter: contrast(1.04) saturate(1.04);"


# ------------------------------------------------------------------------------------------------ transitions
MIX = ("push", "zoom", "push", "rise")


def transition_of(plan, i):
    """The hand-over INTO scene i: the plan's transition. "mix" cycles push / zoom-through / push / rise; a feature's
    second shot is a match cut (the window holds, the UI changes in place, the caption stays); the end card zooms
    through. A plain crossfade stays a crossfade everywhere."""
    tr = plan.get("transition") or "crossfade"
    sc = plan["scenes"]
    if i >= len(sc) or tr == "crossfade":
        return "crossfade"
    if sc[i].get("part"):
        return "match"
    if sc[i]["kind"] == "end":
        return "zoom" if tr == "mix" else "crossfade"
    if tr == "mix":
        k = sum(1 for z in sc[1:i] if not z.get("part"))
        return MIX[k % len(MIX)]
    return tr


def scene_in(sid, tr, at, d, W, H=None):
    """GSAP for a scene arriving (``d`` s, the scene overlap; 6-12 frames). push: slides in over the outgoing one
    with a little motion blur | zoom: through from 86 % | rise: up from below | match / crossfade: a dissolve."""
    H = H or W
    if tr == "push":
        return (f'tl.fromTo("#{sid}", {{opacity: 1, x: {W}, filter: "blur(10px)"}}, {{opacity: 1, x: 0, '
                f'filter: "blur(0px)", duration: {_r(d)}, ease: "expo.inOut"}}, {_r(at)});')
    if tr == "zoom":
        return (f'tl.fromTo("#{sid}", {{opacity: 0, scale: 0.86, filter: "blur(12px)"}}, {{opacity: 1, scale: 1, '
                f'filter: "blur(0px)", duration: {_r(d)}, ease: "expo.out"}}, {_r(at)});')
    if tr == "rise":
        return (f'tl.fromTo("#{sid}", {{opacity: 0, y: {int(H * 0.3)}, filter: "blur(8px)"}}, {{opacity: 1, y: 0, '
                f'filter: "blur(0px)", duration: {_r(d)}, ease: "expo.out"}}, {_r(at)});')
    if tr == "match":
        return f'tl.fromTo("#{sid}", {{opacity: 0}}, {{opacity: 1, duration: {_r(min(d, 0.2))}, ease: "none"}}, {_r(at)});'
    return f'tl.fromTo("#{sid}", {{opacity: 0}}, {{opacity: 1, duration: {_r(d)}, ease: "none"}}, {_r(at)});'


def scene_out(sid, tr, at, d, W, H=None):
    """The scene leaving as the next one arrives with ``tr``."""
    H = H or W
    if tr == "push":
        return (f'tl.to("#{sid}", {{x: -{int(W * 0.32)}, opacity: 0, duration: {_r(d)}, ease: "expo.inOut"}}, '
                f'{_r(at)});')
    if tr == "zoom":
        return (f'tl.to("#{sid}", {{opacity: 0, scale: 1.18, filter: "blur(12px)", duration: {_r(d)}, '
                f'ease: "power2.in"}}, {_r(at)});')
    if tr == "rise":
        return (f'tl.to("#{sid}", {{opacity: 0, y: -{int(H * 0.12)}, duration: {_r(d)}, ease: "power2.in"}}, '
                f'{_r(at)});')
    if tr == "match":
        return f'tl.to("#{sid}", {{opacity: 0, duration: {_r(min(d, 0.2))}, ease: "none"}}, {_r(at + d - min(d, 0.2))});'
    return f'tl.to("#{sid}", {{opacity: 0, duration: {_r(d)}, ease: "none"}}, {_r(at)});'


def _chars_html(text, cls="w"):
    """A wordmark split per character (each rises through the line mask)."""
    return '<span class="ln">' + "".join(f'<span class="{cls}">{_e(c)}</span>' if c.strip() else _e(c)
                                         for c in text) + "</span>"


def _backdrop(body, js, W, H, total, Bk):
    """Soft gradient + two accent glows drifting slowly over the whole film (never black, never static)."""
    g1, g2 = int(max(W, H) * 0.9), int(max(W, H) * 0.75)
    body.append(f'<div id="bg" class="full clip" data-start="0" data-duration="{_r(total)}" data-track-index="0">'
                f'<div class="glow" id="g1" style="left:{int(-g1 * 0.35)}px; top:{int(-g1 * 0.45)}px; width:{g1}px; '
                f'height:{g1}px; background: radial-gradient(closest-side, {Bk["glow"]}, transparent)"></div>'
                f'<div class="glow" id="g2" style="left:{int(W - g2 * 0.6)}px; top:{int(H - g2 * 0.5)}px; '
                f'width:{g2}px; height:{g2}px; background: radial-gradient(closest-side, {Bk["glow2"]}, transparent)">'
                f'</div></div>')
    js.append(f'tl.fromTo("#g1", {{x: 0, y: 0}}, {{x: {int(W * 0.12)}, y: {int(H * 0.08)}, duration: {_r(total)}, '
              f'ease: "sine.inOut"}}, 0);')
    js.append(f'tl.fromTo("#g2", {{x: 0, y: 0}}, {{x: -{int(W * 0.1)}, y: -{int(H * 0.06)}, duration: {_r(total)}, '
              f'ease: "sine.inOut"}}, 0);')


def build(cfg, plan, proj, quiet=False):
    """Write ``proj``/index.html (+ assets, plan.json, cues.json) for a story plan. Returns proj."""
    os.makedirs(proj, exist_ok=True)
    lang, W, H, L = plan["lang"], plan["W"], plan["H"], plan["layout"]
    T = B.theme(cfg)
    Bk = B.backdrop(cfg)
    p = cfg["product"]
    files = B.font_files(cfg, lang)
    dw = B.display_weight(cfg, lang)
    k = W / 1920 if W >= H else W / 1080
    # every string on screen, for CJK subsetting
    end = cfg.get("end_card") or {}
    strings = [p["name"], C.text(p.get("name_zh"), lang), C.text(p.get("one_liner"), lang), C.text(end.get("cta"), lang),
               C.text(end.get("sub"), lang), p.get("site", ""), p.get("version", ""), "AI voice AI 配音"]
    for s in plan["scenes"]:
        strings += [s.get("kicker", ""), s.get("caption", "")]
    faces = B.stage_fonts(cfg, os.path.join(proj, "assets", "fonts"), "".join(strings), [lang])
    from vstudio import theme as TH
    lk = (f":root{{--bg-top:{Bk['top']};--bg-bot:{Bk['bottom']};--lk-ink:{Bk['ink']};--lk-ink2:{Bk['ink2']};"
          f"--lk-accent:{Bk['accent']};--lk-accent-text:{Bk['accent_text']};--lk-shadow:{Bk['shadow']};"
          f"--lk-marker:{B.rgba(Bk['accent'], 0.34)};}}")
    css = TH.css_vars(T) + "\n" + lk + "\n" + B.font_css(faces) + CSS
    zh = lang == "zh"
    css = (css.replace("{W}", str(W)).replace("{H}", str(H)).replace("{RADIUS}", str(L.get("radius", 18)))
           .replace("{DW}", str(dw)).replace("{TW}", str(min(760, dw + 80) if not zh else 700))
           .replace("{OW}", str(500 if not zh else 400)).replace("{TRACK}", "-.012em" if zh else "-.032em")
           .replace("{TTRACK}", "0" if zh else "-.045em")
           .replace("{DISPLAY}", B.families(faces, lang, "display")).replace("{TEXT}", B.families(faces, lang, "text")))
    body, js, tracks = [], [], [1, 2]
    total = plan["duration"]
    _backdrop(body, js, W, H, total, Bk)
    b = cfg.get("brand") or {}
    mark = _asset(b["mark"], proj, "brand") if b.get("mark") else None
    logo = _asset(b["logo"], proj, "brand") if b.get("logo") else None
    vo_on = (cfg.get("voiceover") or {}).get("enabled")
    n = len(plan["scenes"])
    cues = S.caption_cues(plan)
    xf = plan["xf"]
    for i, s in enumerate(plan["scenes"]):
        sid, st, du = f"s{i}", s["start"], s["dur"]
        track = tracks[i % 2]
        inner = []
        last_scene = i == n - 1
        # scene in / out (the first scene is already there at frame 0; a loop's last scene fades to the tail)
        tr = transition_of(plan, i)
        if i == 0:
            js.append(f'tl.set("#{sid}", {{opacity: 1}}, 0);')
        else:
            js.append(scene_in(sid, tr, st, xf, W, H))
        if not last_scene or plan["loop"]:
            js.append(scene_out(sid, transition_of(plan, i + 1), st + du - xf, xf, W, H))
        land = st + (0.0 if i == 0 else xf * 0.55)            # the moment the new scene has arrived
        if s["kind"] == "feature":
            x0, y0, x1, y1 = L["text"]
            kpx = L["kicker_px"]
            px, lines = _fit_caption(s["caption"], lang, L, files, dw)
            num = "" if plan["cut"] != "demo" else \
                f"{sum(1 for z in plan['scenes'][:i + 1] if z['kind'] == 'feature' and not z.get('part')):02d}"
            held = bool(s.get("part"))                    # the feature's second shot: its caption is already up
            ktxt = f"{num} · {s['kicker']}" if num and s["kicker"] else s["kicker"]
            ctop = _cap_top(L, px, len(lines), bool(ktxt))
            ktop = ctop - int(kpx * 1.9)
            # no kicker (her brief gives one line per shot): the empty rule stays out of the frame
            inner.append(f'<div class="kicker" id="{sid}k" style="left:{x0}px; width:{x1 - x0}px; top:{ktop}px; '
                         f'font-size:{kpx}px{"" if ktxt else "; display:none"}"><i></i>{_e(ktxt)}<i></i></div>')
            inner.append(f'<div class="cap" id="{sid}c" style="left:{x0}px; top:{ctop}px; width:{x1 - x0}px; '
                         f'font-size:{px}px">{caption_html(lines)}</div>')
            wx, wy, ww, wh = L["win"]
            m = s["media"]
            sw, sh = m.get("w") or ww, m.get("h") or wh
            k0 = s["cam"][0]
            cam = f'<div class="cam" id="{sid}m" style="width:{sw}px; height:{sh}px; {_lift(m.get("still"))}">'
            js.append(f'tl.set("#{sid}m", {{x: {k0["x"]}, y: {k0["y"]}, scale: {k0["scale"]}}}, 0);')
            tag = f"{sid}-{s['shot']}"
            if m["kind"] == "video":
                src = _asset(m["file"], proj, "shots")
                segs = m.get("segs") or [(m["at"], m["until"], m["rate"])]
                last = _frame(m["file"], segs[-1][1] - 0.05, proj, f"{tag}-last.jpg")
                cam += f'<img src="{last}" alt="">'
                off = 0.0
                for kk, (m0, m1, rate) in enumerate(segs):      # speed ramp: one clip per segment, back to back
                    d = (m1 - m0) / rate
                    if off >= s["play"] - 1e-3:
                        break
                    d = min(d, s["play"] - off)
                    cam += (f'<video id="{sid}v{kk}" src="{src}" muted playsinline data-start="{_r(st + off)}" '
                            f'data-duration="{_r(d)}" data-media-start="{_r(m0)}" data-playback-rate="{round(rate, 4)}" '
                            f'data-track-index="{3 + i % 2}" data-volume="0"></video>')
                    off += d
            else:
                cam += f'<img src="{_asset(m["file"], proj, "shots")}" alt="">'
            cam += "</div>"
            inner.append(f'<div class="win" id="{sid}w" style="left:{wx}px; top:{wy}px; width:{ww}px; height:{wh}px">'
                         f'{cam}</div>')
            loop_first = plan["loop"] and i == 0
            if loop_first:                                   # the loop's frame 0 = its last frame: no entrance
                js.append(f'tl.set(["#{sid}k", "#{sid}w"], {{opacity: 1}}, 0);')
            elif i == 0:
                # the film opens: the window rises into place, the headline follows
                js.append(f'tl.set("#{sid}k", {{opacity: 1}}, 0);')
                js.append(f'tl.fromTo("#{sid}w", {{opacity: 0, y: {int(60 * k)}, scale: 0.94}}, {{opacity: 1, y: 0, '
                          f'scale: 1, duration: 0.8, ease: "expo.out"}}, 0);')
            else:
                # the transition carries the whole scene in: the window and kicker are simply there
                js.append(f'tl.set(["#{sid}k", "#{sid}w"], {{opacity: 1}}, {_r(st)});')
            if plan["loop"]:
                js.append(f'tl.set("#{sid}k", {{opacity: 1}}, {_r(st)});')
            if held:
                js.append(f'tl.set("#{sid}c .w", {{opacity: 1, yPercent: 0}}, {_r(st)});')
                js.append(f'tl.set("#{sid}c .mk", {{backgroundSize: "100% 42%"}}, {_r(st)});')
            else:
                stg = 0.03 if zh else 0.055
                _ease_in_words(js, f"#{sid}c .w", land + (0.15 if i == 0 else 0.0), stagger=stg)
                nw = sum(len(_words(C.plain(ln))) for ln in lines)
                js.append(f'tl.to("#{sid}c .mk", {{backgroundSize: "100% 42%", duration: 0.5, ease: "power3.out"}}, '
                          f'{_r(land + 0.3 + stg * nw)});')
            for kf in s["cam"][1:]:
                js.append(f'tl.to("#{sid}m", {{x: {kf["x"]}, y: {kf["y"]}, scale: {kf["scale"]}, duration: {kf["d"]}, '
                          f'ease: "{kf["ease"]}"}}, {_r(st + kf["t"])});')
            if vo_on and s.get("vo"):
                vsrc, vdur = _vo(cfg, s, proj, lang)
                body.append(f'<audio src="{vsrc}" id="{sid}vo" data-start="{_r(st + 0.35)}" data-duration="{_r(vdur)}" '
                            f'data-track-index="8" data-volume="1"></audio>')
        elif s["kind"] == "title":
            ty = H * (0.42 if H > W else 0.4)
            mpx = int(L["title_px"] * 0.95)
            if mark:
                inner.append(f'<img class="mark" id="{sid}i" src="{mark}" alt="" style="left:{(W - mpx * 1.75) // 2}px; '
                             f'top:{int(ty - mpx * 1.35)}px; width:{int(mpx * 1.75)}px">')
                js.append(f'tl.fromTo("#{sid}i", {{opacity: 0, scale: .7, rotation: -6}}, {{opacity: 1, scale: 1, '
                          f'rotation: 0, duration: .7, ease: "back.out(1.6)"}}, 0.05);')
            name = p["name"] + (f" {C.text(p.get('name_zh'), lang)}" if zh and p.get("name_zh") else "")
            inner.append(f'<div class="center title" id="{sid}t" style="top:{int(ty)}px; font-size:{L["title_px"]}px">'
                         f'{_chars_html(name)}</div>')
            _ease_in_words(js, f"#{sid}t .w", 0.2, stagger=0.035, dur=0.75)
            ol = C.text(p.get("one_liner"), lang)
            olw = W - 2 * L["text"][0]
            opx, olines = B.fit(ol, files["display"], (L["oneliner_px"], int(L["oneliner_px"] * 0.7)), olw, 2, lang, 500)
            oy = int(ty + L["title_px"] * 1.3)
            inner.append(f'<div class="center oneliner" id="{sid}o" style="top:{oy}px; font-size:{opx}px">'
                         f'{caption_html(olines)}</div>')
            _ease_in_words(js, f"#{sid}o .w", 0.6, stagger=0.04)
            if p.get("version"):
                cy = oy + int(opx * 1.3 * len(olines) + opx * 0.9)
                inner.append(f'<div class="center" style="top:{cy}px"><span class="chip" id="{sid}v" '
                             f'style="font-size:{int(L["kicker_px"] * 1.05)}px">{_e(p["version"])}</span></div>')
                js.append(f'tl.fromTo("#{sid}v", {{opacity: 0, y: 14}}, {{opacity: 1, y: 0, duration: .5, '
                          f'ease: "expo.out"}}, 1.1);')
        elif s["kind"] == "end":
            t0 = st + xf * 0.4
            ty = H * (0.42 if H > W else 0.4)
            grp = []
            if logo:
                lw = int(min(W * 0.46, 760))
                grp.append(f'<img class="mark" id="{sid}l" src="{logo}" alt="" style="left:{(W - lw) // 2}px; '
                           f'top:{int(ty)}px; width:{lw}px">')
                js.append(f'tl.fromTo("#{sid}l", {{opacity: 0, y: 24, scale: .96}}, {{opacity: 1, y: 0, scale: 1, '
                          f'duration: .7, ease: "expo.out"}}, {_r(t0)});')
                cy = ty + lw * 0.34
            else:
                tpx = L["title_px"]
                if mark:
                    mw = int(tpx * 1.6)
                    grp.append(f'<img class="mark" id="{sid}i" src="{mark}" alt="" style="left:{(W - mw) // 2}px; '
                               f'top:{int(ty - mw * 0.75)}px; width:{mw}px">')
                    js.append(f'tl.fromTo("#{sid}i", {{opacity: 0, scale: .6, rotation: -8, y: 20}}, {{opacity: 1, '
                              f'scale: 1, rotation: 0, y: 0, duration: .75, ease: "back.out(1.7)"}}, {_r(t0)});')
                    t0 += 0.18
                nm = (f"{C.text(p.get('name_zh'), lang)} {p['name']}" if zh and p.get("name_zh") else p["name"])
                grp.append(f'<div class="center title" id="{sid}n" style="top:{int(ty)}px; '
                           f'font-size:{tpx}px">{_chars_html(nm)}</div>')
                _ease_in_words(js, f"#{sid}n .w", t0, stagger=0.035, dur=0.75)
                cy = ty + tpx * 1.32
            cta = C.text(end.get("cta"), lang) or C.text(p.get("one_liner"), lang)
            cpx, clines = B.fit(cta, files["display"], (int(L["oneliner_px"] * 1.12), int(L["oneliner_px"] * 0.7)),
                                W - 2 * L["text"][0], 2, lang, 500)
            grp.append(f'<div class="center cta" id="{sid}c" style="top:{int(cy)}px; font-size:{cpx}px">'
                       f'{caption_html(clines)}</div>')
            _ease_in_words(js, f"#{sid}c .w", t0 + 0.35, stagger=0.03 if zh else 0.05)
            sy = cy + cpx * 1.25 * len(clines) + cpx * 0.75
            if p.get("site"):
                site = p["site"].replace("https://", "").replace("http://", "").rstrip("/")
                grp.append(f'<div class="center" style="top:{int(sy)}px"><span class="site" id="{sid}s" '
                           f'style="font-size:{int(cpx * 0.66)}px">{_e(site)}</span></div>')
                js.append(f'tl.fromTo("#{sid}s", {{opacity: 0, y: 16, scale: .94}}, {{opacity: 1, y: 0, scale: 1, '
                          f'duration: .6, ease: "expo.out"}}, {_r(t0 + 0.75)});')
                sy += cpx * 1.6
            sub = C.text(end.get("sub"), lang)
            if sub:
                grp.append(f'<div class="center sub" id="{sid}u" style="top:{int(sy)}px; '
                           f'font-size:{int(L["kicker_px"] * 0.95)}px">{_e(sub)}</div>')
                js.append(f'tl.fromTo("#{sid}u", {{opacity: 0}}, {{opacity: 1, duration: .4}}, {_r(t0 + 1.0)});')
            # the card keeps a slow push while it holds
            inner.append(f'<div class="full" id="{sid}g">' + "".join(grp) + "</div>")
            js.append(f'tl.fromTo("#{sid}g", {{scale: 1}}, {{scale: 1.04, duration: {_r(du)}, ease: "sine.out"}}, '
                      f'{_r(st)});')
        body.append(f'<div class="scene clip" id="{sid}" data-start="{_r(st)}" data-duration="{_r(du)}" '
                    f'data-track-index="{track}">' + "".join(inner) + "</div>")
    if plan["loop"]:
        # tail: a still of the first scene's opening frame fades in over the last crossfade -> seamless loop
        s0 = plan["scenes"][0]
        m = s0["media"]
        first = (_frame(m["file"], m["at"], proj, "tail-first.jpg") if m["kind"] == "video"
                 else _asset(m["file"], proj, "shots"))
        wx, wy, ww, wh = L["win"]
        x0, _, x1, _ = L["text"]
        k0 = s0["cam"][0]
        sw, sh = m.get("w") or ww, m.get("h") or wh
        kick = plan["scenes"][0]["kicker"]
        px0, lines0 = _fit_caption(s0["caption"], lang, L, files, dw)
        ky = _cap_top(L, px0, len(lines0), bool(kick)) - int(L["kicker_px"] * 1.9)
        tail_at = total - xf
        body.append(f'<div class="scene clip" id="tail" data-start="{_r(tail_at)}" data-duration="{_r(xf)}" '
                    f'data-track-index="5"><div class="kicker" style="left:{x0}px; width:{x1 - x0}px; top:{ky}px; '
                    f'font-size:{L["kicker_px"]}px; opacity:1"><i></i>{_e(kick)}<i></i></div>'
                    f'<div class="win" style="left:{wx}px; top:{wy}px; width:{ww}px; height:{wh}px; opacity:1">'
                    f'<div class="cam" id="tailm" style="width:{sw}px; height:{sh}px; {_lift(m.get("still"))}">'
                    f'<img src="{first}" alt=""></div></div></div>')
        js.append(f'tl.set("#tailm", {{x: {k0["x"]}, y: {k0["y"]}, scale: {k0["scale"]}}}, 0);')
        js.append(f'tl.fromTo("#tail", {{opacity: 0}}, {{opacity: 1, duration: {xf}, ease: "none"}}, {_r(tail_at)});')
    if vo_on:
        label = "AI 配音" if zh else "AI voice"
        body.append(f'<div class="ailabel clip" data-start="0" data-duration="{_r(total)}" data-track-index="9" '
                    f'style="left:{L["text"][0]}px; bottom:{max(24, int(H * 0.03))}px">{label}</div>')
    music = None if plan["loop"] else _music(cfg, proj, total)       # a loop stays silent: no seam in the bed
    if music:
        vol = 0.22 if vo_on else 0.5
        body.append(f'<audio src="{music}" id="music" data-start="0" data-duration="{_r(total)}" data-track-index="7" '
                    f'data-volume="{vol}"></audio>')
    doc = f"""<!doctype html>
<html lang="{'zh-CN' if zh else 'en'}"><head><meta charset="utf-8">
<script src="{GSAP}"></script>
<style>
{css}
</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-width="{W}" data-height="{H}" data-duration="{_r(total)}">
{chr(10).join(body)}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{chr(10).join(js)}
window.__timelines = window.__timelines || {{}};
window.__timelines["main"] = tl;
</script>
</body></html>
"""
    with open(os.path.join(proj, "index.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    with open(os.path.join(proj, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    with open(os.path.join(proj, "cues.json"), "w", encoding="utf-8") as f:
        json.dump({"cues": cues}, f, ensure_ascii=False, indent=1)
    if not quiet:
        print(f"built {proj} ({plan['cut']} {lang} {plan['aspect']}, {total:.1f}s, {len(plan['scenes'])} scenes)")
    return proj


# ------------------------------------------------------------------------------------------------ render
def render(proj, out, quality="delivery", fps=30, lufs=-14.0):
    """HyperFrames render -> deliver: loudness (only when there is audio), BT.709 tags, +faststart."""
    from vstudio import node, proctail
    env = node.child_env(extra_dirs=[d for d in [media.ffmpeg_dir()] if d])    # raises NodeError (+ the fix)
    raw = os.path.join(proj, "renders", "_raw.mp4")
    os.makedirs(os.path.dirname(raw), exist_ok=True)
    cmd = node.npx(*hyperframes_cmd()[1:], env=env) + ["render", "--quality", quality, "--fps", str(fps),
                                                       "--video-frame-format", "png", "--output", "renders/_raw.mp4"]
    r = subprocess.run(cmd, cwd=proj, capture_output=True, text=True, env=env)
    if r.returncode != 0 or not os.path.exists(raw):
        tail = proctail.tail(r.stderr + "\n" + r.stdout, n=25)
        raise RuntimeError(f"hyperframes render failed in {proj}:\n{tail}")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    info = media.probe(raw)
    if info.get("has_audio"):
        from vstudio import audio
        tmp = out[:-4] + ".loud.mp4"
        audio.loudnorm_2pass(raw, tmp, lufs=lufs)
        media.retag_bt709(tmp, out)
        os.remove(tmp)
    else:
        media.retag_bt709(raw, out)
    return out


def cover(video, t, out):
    """A cover = one frame of the video (same canvas), JPEG."""
    return media.grab_frame(video, t, out, quality=2)


def gif(video, out, width=960, fps=15):
    """Looping GIF for a README (palette per file, no dither banding on flat paper)."""
    pal = out + ".palette.png"
    vf = f"fps={fps},scale={width}:-1:flags=lanczos"
    media.run(["ffmpeg", "-y", "-i", video, "-vf", vf + ",palettegen=max_colors=128:stats_mode=diff", pal])
    media.run(["ffmpeg", "-y", "-i", video, "-i", pal, "-lavfi",
               vf + " [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle", "-loop", "0", out])
    os.remove(pal)
    return out
