"""Plan -> a HyperFrames project (index.html + assets) -> rendered, delivered MP4.

    from vstudio.launch import compose as CO
    proj = CO.build(cfg, plan, "kit/build/demo-en-16x9")       # writes the project, returns its dir
    CO.render(proj, "kit/demo/demo-en-16x9.mp4")             # npx hyperframes render + delivery (BT.709, faststart)

The look: a product film, not one template per feature. Each scene renders its layout (story.py): full-bleed UI
(no chrome, no text, the camera gliding onto the action), a detail shot 2.5-4x on one element, two moments split side
by side / stacked (small labels), the window floating on a flat light field with a small lower-third caption, a
kinetic type beat (one short line, large, Inter 560 / Noto Sans SC Medium, tight tracking, words fading up out of a
blur) on a soft gradient field, chapter cards and the end card. Gradient fields only behind type; the rest is the UI
on a flat light field. Hand-overs follow the layouts (story beats): a hard cut into a detail, push / rise / cut
between footage, a zoom-through out of a type beat, a blur dissolve into a card, centred on the beats of the music
bed. No voice unless the config adds one (a TTS voice-over is labelled "AI voice"); the music bed is built in
(vstudio.music: generated in code, free for any use) or your own track with its license.
HyperFrames CLI: ``npx hyperframes`` (set $VSTUDIO_HYPERFRAMES to pin a version, e.g. hyperframes@0.8.130).
"""
import html
import json
import os
import re
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
html, body { width: {W}px; height: {H}px; overflow: hidden; background: var(--lk-flat); }
#root { position: relative; width: {W}px; height: {H}px; overflow: hidden; color: var(--lk-ink);
  background: var(--lk-flat); }
.full { position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; }
.scene { position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; opacity: 0; overflow: hidden; }
.flat { background: var(--lk-flat); }
.field { overflow: hidden; background: linear-gradient(172deg, var(--bg-top) 0%, var(--bg-bot) 100%); }
.glow { position: absolute; border-radius: 50%; }
.win { position: absolute; overflow: hidden; background: #0c0d0e; }
.win.framed { border-radius: {RADIUS}px;
  box-shadow: 0 0 0 1px rgba(var(--lk-shadow), .08), 0 2px 6px rgba(var(--lk-shadow), .08),
    0 30px 60px -20px rgba(var(--lk-shadow), .26), 0 70px 140px -40px rgba(var(--lk-shadow), .28); }
.win.framed::after { content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.08); }
.cam { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
.cam > img, .cam > video { position: absolute; left: 0; top: 0; width: 100%; height: 100%; object-fit: fill; }
.type { position: absolute; font-family: {DISPLAY}; font-weight: {TW}; line-height: {TLH}; letter-spacing: {TTRACK};
  color: var(--lk-ink); text-align: center; {STROKE} }
.type .w, .chap .w, .lt .w, .cta .w { display: inline-block; opacity: 0; white-space: pre; }
.ln { display: inline-block; white-space: nowrap; }
.mk { color: var(--lk-accent-text); }
.lt { position: absolute; font-family: {DISPLAY}; font-weight: {LW}; line-height: 1.3; letter-spacing: {LTRACK};
  color: var(--lk-ink); {STROKE} }
.lt.c { text-align: center; }
.center { position: absolute; left: 0; width: {W}px; text-align: center; }
.mark { position: absolute; opacity: 0; }
.chap { font-family: {LATIN}; font-weight: {CW}; letter-spacing: {CTRACK}; color: var(--lk-ink); line-height: 1.02; }
.eyebrow { font-family: {DISPLAY}; font-weight: 600; letter-spacing: .16em; text-transform: uppercase;
  color: var(--lk-accent-text); opacity: 0; }
.ver { font-family: {LATIN}; font-weight: 500; color: var(--lk-ink2); letter-spacing: -.01em; opacity: 0; }
.cta { font-family: {DISPLAY}; font-weight: {LW}; color: var(--lk-ink2); line-height: 1.25; letter-spacing: {LTRACK}; }
.site { font-family: {LATIN}; font-weight: 600; letter-spacing: .01em; color: var(--lk-accent-text); opacity: 0; }
.sub { font-family: {TEXT}; font-weight: 400; color: var(--lk-ink2); opacity: 0; }
.ailabel { position: absolute; font-family: {TEXT}; font-size: 20px; color: var(--lk-ink2); opacity: .85; }
.kicker { font-family: {DISPLAY}; font-weight: 600; color: var(--lk-accent-text); opacity: 0; letter-spacing: {KTRACK}; }
.badges { position: absolute; left: 0; width: {W}px; text-align: center; white-space: nowrap; }
.badge, .chip { display: inline-block; opacity: 0; border-radius: 999px; font-family: {DISPLAY}; font-weight: 560;
  color: var(--lk-ink); background: var(--lk-pill); box-shadow: inset 0 0 0 1px var(--lk-pill-rule),
  0 10px 24px -14px rgba(var(--lk-shadow), .35); white-space: nowrap; line-height: 1; }
.badge { padding: .5em .95em; margin: 0 .28em; }
.chip { position: absolute; padding: .52em 1em; }
.chip i, .badge i { display: inline-block; width: .5em; height: .5em; border-radius: 50%; margin-right: .5em;
  background: var(--lk-accent); vertical-align: .08em; }
.strip { position: absolute; left: 0; top: 0; white-space: nowrap; }
.thumb { position: absolute; top: 0; overflow: hidden; border-radius: 8px; opacity: .42; background: #0c0d0e; }
.thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.playhead { position: absolute; width: 3px; border-radius: 2px; background: var(--lk-accent); }
.playhead::before { content: ""; position: absolute; left: -7px; top: -12px; border: 8px solid transparent;
  border-top: 10px solid var(--lk-accent); }
.reeltitle { position: absolute; left: 0; width: {W}px; text-align: center; font-family: {DISPLAY};
  font-weight: {LW}; color: var(--lk-ink); letter-spacing: {LTRACK}; }
"""

# The camera between two poses: the zoom is eased in log space and the point it frames moves in a straight line, so
# a push reads even and the target never swims (after OpenFilm's virtual camera, MIT); each pose stays clamped so the
# shot always covers its window. Deterministic: a pure function of the timeline's time.
CAM_JS = """
const lkCam = (sel, W, H, sw, sh, a, b, d, ease, at) => {
  const el = document.querySelector(sel), o = {e: 0};
  const la = Math.log(a[2]), lb = Math.log(b[2]);
  const ax = (W / 2 - a[0]) / a[2], ay = (H / 2 - a[1]) / a[2], bx = (W / 2 - b[0]) / b[2], by = (H / 2 - b[1]) / b[2];
  tl.fromTo(o, {e: 0}, {e: 1, duration: d, ease: ease, immediateRender: false, onUpdate: () => {
    const s = Math.exp(la + (lb - la) * o.e), cx = ax + (bx - ax) * o.e, cy = ay + (by - ay) * o.e;
    const x = Math.min(0, Math.max(W - sw * s, W / 2 - cx * s)), y = Math.min(0, Math.max(H - sh * s, H / 2 - cy * s));
    gsap.set(el, {x: x, y: y, scale: s});
  }}, at);
};
"""


def _blur_in(js, sel, at, stagger=0.06, dur=0.75, rise=24):
    """Words arrive: a fade with a little rise and a blur that clears (refined, no bounce)."""
    js.append(f'tl.fromTo("{sel}", {{opacity: 0, yPercent: {rise}, filter: "blur(10px)"}}, {{opacity: 1, yPercent: 0, '
              f'filter: "blur(0px)", duration: {dur}, ease: "power3.out", stagger: {stagger}}}, {_r(at)});')


def _slam(js, sel, at, stagger=0.03, dur=0.5, scale=1.35):
    """A headline lands: each letter drops from ``scale`` onto the page with a spring overshoot while its blur clears
    in the first quarter (after OpenFilm's title slam, MIT)."""
    js.append(f'tl.fromTo("{sel}", {{opacity: 0, filter: "blur(10px)"}}, {{opacity: 1, filter: "blur(0px)", '
              f'duration: {_r(dur * 0.25)}, ease: "power1.out", stagger: {stagger}}}, {_r(at)});')
    js.append(f'tl.fromTo("{sel}", {{scale: {scale}}}, {{scale: 1, duration: {dur}, ease: "back.out(2.2)", '
              f'stagger: {stagger}}}, {_r(at)});')


def _pop_in(js, sel, at, stagger=0.09, rise=18):
    """Badges / chips snap in: a rise and a little overshoot."""
    js.append(f'tl.fromTo("{sel}", {{opacity: 0, y: {rise}, scale: .86}}, {{opacity: 1, y: 0, scale: 1, duration: .44, '
              f'ease: "back.out(1.2)", stagger: {stagger}}}, {_r(at)});')


def _pill_w(text, files, px, weight, pad=1.9, dot=True):
    return int(B.measure(text, files["display"], px, weight) + px * pad + (px * 1.0 if dot else 0))


def _fit(text, files, rng, width, lines, lang, weight):
    return B.fit(text, files["display"], rng, int(width), lines, lang, weight)


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
CUTS = ("cut", "push", "cut", "rise")


def transition_of(plan, i):
    """The hand-over INTO scene i, from the layouts on both sides: a card arrives with a soft blur dissolve, footage
    after a card zooms through, a detail shot is a hard cut on the beat, footage to footage alternates cut / push /
    cut / rise ("mix"; a fixed motion.transition is used as is). A plain crossfade stays a crossfade everywhere."""
    tr = plan.get("transition") or "crossfade"
    sc = plan["scenes"]
    if i <= 0 or i >= len(sc) or tr == "crossfade":
        return "crossfade"
    cur, prev = sc[i], sc[i - 1]
    if cur["layout"] in S.CARDS:
        return "through" if plan.get("arc") == "launch" and prev["layout"] in S.FOOTAGE + (S.REEL,) else "fade"
    if prev["layout"] in S.TITLES:
        return "zoom"
    if (cur.get("panes") or [{}])[0].get("cont"):
        return "cut"
    if tr == "mix":
        if cur["layout"] == "macro" or prev["layout"] == "macro":
            return "crossfade"             # a new context/scale, not a continuation punch-in
        k = sum(1 for j in range(1, i) if sc[j]["layout"] in S.FOOTAGE and sc[j - 1]["layout"] in S.FOOTAGE
                and not sc[j]["panes"][0].get("cont"))
        return CUTS[k % len(CUTS)]
    return tr


def scene_in(sid, tr, at, d, W, H=None):
    """GSAP for a scene arriving (``d`` s, the scene overlap; 6-12 frames). cut: on the beat (the overlap's middle) |
    push: slides in over the outgoing one with a little motion blur | zoom: settles from 106 % out of a blur | rise: up
    from below | fade: a blur dissolve | through: a card behind footage the camera flies through (the footage scales
    toward the viewer, 1 -> 2.9x, and fades) | crossfade: a dissolve."""
    H = H or W
    if tr == "cut":
        return f'tl.set("#{sid}", {{opacity: 1}}, {_r(at + d / 2)});'
    if tr == "push":
        return (f'tl.fromTo("#{sid}", {{opacity: 1, x: {W}, filter: "blur(10px)"}}, {{opacity: 1, x: 0, '
                f'filter: "blur(0px)", duration: {_r(d)}, ease: "expo.inOut"}}, {_r(at)});')
    if tr == "zoom":
        return (f'tl.fromTo("#{sid}", {{opacity: 0, scale: 1.06, filter: "blur(12px)"}}, {{opacity: 1, scale: 1, '
                f'filter: "blur(0px)", duration: {_r(d)}, ease: "expo.out"}}, {_r(at)});')
    if tr == "rise":
        return (f'tl.fromTo("#{sid}", {{opacity: 0, y: {int(H * 0.3)}, filter: "blur(8px)"}}, {{opacity: 1, y: 0, '
                f'filter: "blur(0px)", duration: {_r(d)}, ease: "expo.out"}}, {_r(at)});')
    if tr in ("fade", "through"):
        return (f'tl.fromTo("#{sid}", {{opacity: 0, filter: "blur(8px)"}}, {{opacity: 1, filter: "blur(0px)", '
                f'duration: {_r(d)}, ease: "power2.out"}}, {_r(at)});')
    return f'tl.fromTo("#{sid}", {{opacity: 0}}, {{opacity: 1, duration: {_r(d)}, ease: "none"}}, {_r(at)});'


def scene_out(sid, tr, at, d, W, H=None):
    """The scene leaving as the next one arrives with ``tr``."""
    H = H or W
    if tr == "cut":
        return f'tl.set("#{sid}", {{opacity: 0}}, {_r(at + d / 2)});'
    if tr == "push":
        return (f'tl.to("#{sid}", {{x: -{int(W * 0.32)}, opacity: 0, duration: {_r(d)}, ease: "expo.inOut"}}, '
                f'{_r(at)});')
    if tr == "zoom":
        return (f'tl.to("#{sid}", {{opacity: 0, scale: 1.12, filter: "blur(12px)", duration: {_r(d)}, '
                f'ease: "power2.in"}}, {_r(at)});')
    if tr == "rise":
        return (f'tl.to("#{sid}", {{opacity: 0, y: -{int(H * 0.12)}, duration: {_r(d)}, ease: "power2.in"}}, '
                f'{_r(at)});')
    if tr == "fade":
        return f'tl.to("#{sid}", {{opacity: 0, filter: "blur(6px)", duration: {_r(d)}, ease: "power1.in"}}, {_r(at)});'
    if tr == "through":                                  # the camera flies through the footage into the card
        return (f'tl.to("#{sid}", {{scale: 2.9, opacity: 0, filter: "blur(6px)", duration: {_r(d)}, '
                f'ease: "power3.in"}}, {_r(at)});')
    return f'tl.to("#{sid}", {{opacity: 0, duration: {_r(d)}, ease: "none"}}, {_r(at)});'


def _chars_html(text, cls="w"):
    """A wordmark split per character (each arrives on its own)."""
    return '<span class="ln">' + "".join(f'<span class="{cls}">{_e(c)}</span>' if c.strip() else _e(c)
                                         for c in text) + "</span>"


def _field(sid, i, W, H, st, du, Bk, js):
    """The soft gradient field of a card (type beat / chapter / end): two accent glows drifting slowly; where they sit
    changes card to card."""
    g1, g2 = int(max(W, H) * 0.85), int(max(W, H) * 0.7)
    spots = [((0.08, 0.02), (0.95, 0.98)), ((0.92, 0.05), (0.1, 0.95)), ((0.15, 0.95), (0.9, 0.1))]
    (c1x, c1y), (c2x, c2y) = spots[i % len(spots)]
    p1 = (int(c1x * W - g1 / 2), int(c1y * H - g1 / 2))
    p2 = (int(c2x * W - g2 / 2), int(c2y * H - g2 / 2))
    js.append(f'tl.fromTo("#{sid}g1", {{x: 0, y: 0}}, {{x: {int(W * 0.08)}, y: {int(H * 0.05)}, duration: {_r(du)}, '
              f'ease: "sine.inOut"}}, {_r(st)});')
    js.append(f'tl.fromTo("#{sid}g2", {{x: 0, y: 0}}, {{x: -{int(W * 0.06)}, y: -{int(H * 0.04)}, '
              f'duration: {_r(du)}, ease: "sine.inOut"}}, {_r(st)});')
    return (f'<div class="full field">'
            f'<div class="glow" id="{sid}g1" style="left:{p1[0]}px; top:{p1[1]}px; width:{g1}px; height:{g1}px; '
            f'background: radial-gradient(closest-side, {Bk["glow"]}, transparent)"></div>'
            f'<div class="glow" id="{sid}g2" style="left:{p2[0]}px; top:{p2[1]}px; width:{g2}px; height:{g2}px; '
            f'background: radial-gradient(closest-side, {Bk["glow2"]}, transparent)"></div></div>')


def _cam_html(proj, mid, i, k, p, st, js, track=None, vid=None):
    """One take inside a camera GSAP moves: the speed-ramped clips back to back (from scene time ``st``), then its
    last frame held; the camera eases from pose to pose in log space (lkCam)."""
    m = p["media"]
    w, h = p["box"][2], p["box"][3]
    sw, sh = m.get("w") or w, m.get("h") or h
    k0 = p["cam"][0]
    cam = f'<div class="cam" id="{mid}" style="width:{sw}px; height:{sh}px; {_lift(m.get("still"))}">'
    js.append(f'tl.set("#{mid}", {{x: {k0["x"]}, y: {k0["y"]}, scale: {k0["scale"]}}}, 0);')
    tag = f"{mid}-{p['shot']}"
    if m["kind"] == "video":
        src = _asset(m["file"], proj, "shots")
        segs = m.get("segs") or []
        last_t = (segs[-1][1] if segs else m.get("end") or m["until"]) - 0.05
        cam += f'<img src="{_frame(m["file"], last_t, proj, f"{tag}-last.jpg")}" alt="">'
        off = 0.0
        for kk, (m0, m1, rate) in enumerate(segs):      # speed ramp: one clip per segment, back to back
            d = (m1 - m0) / rate
            if off >= p["play"] - 1e-3:
                break
            d = min(d, p["play"] - off)
            cam += (f'<video id="{vid or mid + "v"}{kk}" src="{src}" muted playsinline data-start="{_r(st + off)}" '
                    f'data-duration="{_r(d)}" data-media-start="{_r(m0)}" data-playback-rate="{round(rate, 4)}" '
                    f'data-track-index="{track if track is not None else 3 + i % 2 + 7 * k}" data-volume="0"></video>')
            off += d
    else:
        cam += f'<img src="{_asset(m["file"], proj, "shots")}" alt="">'
    cam += "</div>"
    prev = k0
    for kf in p["cam"][1:]:
        js.append(f'lkCam("#{mid}", {w}, {h}, {sw}, {sh}, [{prev["x"]}, {prev["y"]}, {prev["scale"]}], '
                  f'[{kf["x"]}, {kf["y"]}, {kf["scale"]}], {kf["d"]}, "{kf["ease"]}", {_r(st + kf["t"])});')
        prev = kf
    return cam


def _pane_html(proj, sid, i, k, p, st, framed, js):
    """One window of footage: the take inside a camera that GSAP moves."""
    x, y, w, h = p["box"]
    cam = _cam_html(proj, f"{sid}m{k}", i, k, p, st, js, vid=f"{sid}v{k}")
    return (f'<div class="win{" framed" if framed else ""}" id="{sid}w{k}" style="left:{x}px; top:{y}px; '
            f'width:{w}px; height:{h}px">{cam}</div>')


def _tilt(js, sid, s, st, du, W, H):
    """Real UI in perspective: a floating window swings in from a 3D angle and settles flat; split panes stay angled
    a little toward each other, like an open book. Settled angles are small (<= 2.5 deg), so UI text still reads."""
    if s["layout"] == "float":
        js.append(f'tl.fromTo("#{sid}w0", {{rotationX: 11, rotationY: -15, z: -90, transformPerspective: 2000}}, '
                  f'{{rotationX: 2, rotationY: -3, z: 0, duration: 1.1, ease: "expo.out"}}, {_r(st)});')
        js.append(f'tl.to("#{sid}w0", {{rotationX: 0, rotationY: 0, duration: {_r(max(0.4, du - 1.1))}, '
                  f'ease: "sine.inOut"}}, {_r(st + 1.1)});')
    elif s["layout"] == "split":
        side = W > H
        for k in range(len(s["panes"])):
            sg = 1 if k == 0 else -1
            a, b = ("rotationY", 8 * sg), ("rotationY", 2.5 * sg)
            if not side:
                a, b = ("rotationX", -7 * sg), ("rotationX", -2 * sg)
            js.append(f'tl.fromTo("#{sid}w{k}", {{{a[0]}: {a[1]}, transformPerspective: 2200}}, {{{b[0]}: {b[1]}, '
                      f'duration: 1.0, ease: "expo.out"}}, {_r(st + 0.08 * k)});')


def _lower_third(L, box, text, lang, files, weight, W, H):
    """The in-shot caption under the floating window: small, left-aligned with it, inside the text box ->
    (x, y, width, px, lines) or None (it cannot fit: the scene goes without)."""
    x0, y0, x1, y1 = L["text"]
    bx, by, bw, bh = box
    x = max(bx, x0)
    y = by + bh + int(0.028 * max(W, H) if H > W else 30 * W / 1920)
    width = x1 - x
    for lines in range(L["lt_lines"], L["lt_lines"] + 1):
        try:
            px, ls = _fit(text, files, (L["lt_px"], int(L["lt_px"] * 0.78)), width * 0.97, lines, lang, weight)
        except ValueError:
            continue
        if y + px * 1.3 * len(ls) <= y1 + 2:
            return x, y, width, px, ls
    return None


def _labels(L, s, files, lang, weight):
    """Split-scene labels -> [(x, y, width, px, lines, centred)]: under each pane (16:9) or above it (stacked); one
    label for a feature shown in two shots."""
    x0, y0, x1, y1 = L["text"]
    out = []
    labels = s.get("labels") or []
    boxes = [p["box"] for p in s["panes"]]
    one = len(labels) == 1 and len(boxes) > 1
    for k, text in enumerate(labels):
        if not text or k >= len(boxes):
            continue
        bx, by, bw, bh = boxes[k]
        px0 = L["label_px"]
        if L.get("labels") == "below":
            x, width = (x0, x1 - x0) if one else (max(bx, x0), min(bx + bw, x1) - max(bx, x0))
            y = by + bh + 24
        else:
            x, width = max(bx, x0), x1 - max(bx, x0)
            y = by - int(px0 * 1.3) - 14
        try:
            px, ls = _fit(text, files, (px0, int(px0 * 0.72)), width * 0.97, 1, lang, weight)
        except ValueError:
            print(f"  label too long for its pane, left out: {text!r}")
            continue
        out.append((x, y, width, px, ls, one and L.get("labels") == "below"))
    return out


SWISH = {"push": "swoosh", "zoom": "whoosh_b", "rise": "swoosh_b", "through": "whoosh"}


def _sfx_track(cfg, proj, events, total):
    """Quiet foley under the music (a launch-arc film): a swish on each moving transition, a tick per badge / chip and
    per reel cut, a soft hit when a headline lands. Synthesised in code (vstudio.audio.sfx_bank, licence-free);
    ``motion.sfx: false`` turns it off."""
    if (cfg.get("motion") or {}).get("sfx") is False or not events:
        return None
    import numpy as np
    from vstudio import audio as AU
    x = np.zeros(int((total + 0.5) * AU.SR), np.float32)
    AU.place_sfx(x, [dict(e, t=max(0.0, e["t"])) for e in events if e["t"] < total - 0.05])
    d = os.path.join(proj, "assets", "audio")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, "sfx.wav")
    AU.write_wav(out, x)
    return _relpath(out, proj)


def _brand_html(sid, s, land, du, st, L, W, H, files, lang, tw, scale, display, mark, js, sfx):
    """The brand card (arc: launch): the positioning line as a kicker, the wordmark slammed in letter by letter, the
    version, then the badges snapping in on the beat after it."""
    ty = H * (0.42 if H > W else 0.38)
    cpx = int(L["chapter_px"] * 1.12 * scale)
    t0 = land + 0.05
    grp = []
    if s.get("kicker"):
        x0, _, x1, _ = L["text"]
        kpx, kl = _fit(s["kicker"], files, (L["kicker_px"], int(L["kicker_px"] * 0.75)), x1 - x0, 1, lang, 600)
        grp.append(f'<div class="center kicker" id="{sid}k" style="top:{int(ty - kpx * 2.1)}px; font-size:{kpx}px">'
                   f'{_e(kl[0])}</div>')
        js.append(f'tl.fromTo("#{sid}k", {{opacity: 0, y: 18}}, {{opacity: 1, y: 0, duration: .45, ease: "quint.out"}}, '
                  f'{_r(t0)});')
    elif mark:
        mw = int(cpx * 1.0)
        grp.append(f'<img class="mark" id="{sid}i" src="{mark}" alt="" style="left:{(W - mw) // 2}px; '
                   f'top:{int(ty - mw * 1.15)}px; width:{mw}px">')
        js.append(f'tl.fromTo("#{sid}i", {{opacity: 0, scale: .9}}, {{opacity: 1, scale: 1, duration: .6, '
                  f'ease: "expo.out"}}, {_r(t0)});')
    if s.get("eyebrow"):
        epx = int(L["eyebrow_px"] * 1.3)
        grp.append(f'<div class="center eyebrow" id="{sid}e" style="top:{int(ty + cpx * 1.12)}px; font-size:{epx}px">'
                   f'{_e(s["eyebrow"])}</div>')
        js.append(f'tl.fromTo("#{sid}e", {{opacity: 0}}, {{opacity: 1, duration: .5}}, {_r(t0 + 0.6)});')
    title = s.get("title") or ""
    grp.append(f'<div class="center chap" id="{sid}n" style="top:{int(ty)}px; font-size:{cpx}px; '
               f'font-weight:{min(700, tw + 120)}">{_chars_html(title)}</div>')
    _slam(js, f"#{sid}n .w", t0 + 0.15)
    sfx.append(dict(t=t0 + 0.18, sfx="impact_b", gain_db=-16))
    y = ty + cpx * 1.2 + (L["eyebrow_px"] * 2.2 if s.get("eyebrow") else 0)
    if s.get("version") and not s.get("badges"):
        vpx = int(L["oneliner_px"] * 0.95)
        grp.append(f'<div class="center ver" id="{sid}v" style="top:{int(y)}px; font-size:{vpx}px">{_e(s["version"])}</div>')
        js.append(f'tl.fromTo("#{sid}v", {{opacity: 0, y: 10}}, {{opacity: 1, y: 0, duration: .5, ease: "power3.out"}}, '
                  f'{_r(t0 + 0.6)});')
    badges = list(s.get("badges") or [])
    if s.get("version") and badges:
        badges.append("v" + s["version"])
    if badges:
        bpx = L["badge_px"]
        x0, _, x1, _ = L["text"]
        while bpx > 16 and sum(_pill_w(b, files, bpx, 560, dot=False) + bpx * 0.56 for b in badges) > (x1 - x0):
            bpx -= 2
        grp.append(f'<div class="badges" id="{sid}b" style="top:{int(y + bpx * 0.4)}px; font-size:{bpx}px">'
                   + "".join(f'<span class="badge">{_e(b)}</span>' for b in badges) + "</div>")
        _pop_in(js, f"#{sid}b .badge", t0 + 0.7)
        sfx += [dict(t=t0 + 0.8 + 0.09 * k, sfx=("tick", "tick_b")[k % 2], gain_db=-8) for k in range(len(badges))]
    js.append(f'tl.fromTo("#{sid}c", {{scale: 1}}, {{scale: 1.03, duration: {_r(du)}, ease: "sine.out"}}, {_r(st)});')
    return f'<div class="full" id="{sid}c">' + "".join(grp) + "</div>"


def _chips_html(sid, chips, cx, cy, top, L, files, lang, weight, at, js, sfx):
    """A chapter's chips fan out from its title into rows under it on a soft arc (the middle ones lower), the middle
    first, 45 ms apart (after OpenFilm's export fan, MIT)."""
    x0, _, x1, y1 = L["text"]
    px = L["chip_px"]
    width = (x1 - x0) * 0.92
    gap = int(px * 0.6)
    def wrap(ws, limit):
        rows, cur, cw = [], [], 0
        for k, w in enumerate(ws):
            if cur and cw + gap + w > limit:
                rows.append(cur)
                cur, cw = [], 0
            cur.append(k)
            cw += (gap if cw else 0) + w
        return rows + [cur]

    while True:
        ws = [_pill_w(c, files, px, 560) for c in chips]
        rows = wrap(ws, width)
        limit = (sum(ws) + gap * len(ws)) / len(rows)            # the same rows, evened out (no lonely last chip)
        while limit < width and len(wrap(ws, limit)) > len(rows):
            limit += px
        rows = wrap(ws, min(width, limit))
        rh = int(px * 2.1)
        if (top + rh * len(rows) <= y1 and len(rows) <= 3) or px <= 18:
            break
        px -= 2
    html_, order = [], []
    for r, row in enumerate(rows):
        tot = sum(ws[k] for k in row) + gap * (len(row) - 1)
        x = cx - tot / 2
        for j, k in enumerate(row):
            n = (j - (len(row) - 1) / 2) / max(1, (len(row) - 1) / 2)
            y = top + r * rh + int(px * (0.9 if len(rows) == 1 else 0.3) * (1 - n * n))
            html_.append(f'<span class="chip" id="{sid}h{k}" style="left:{int(x)}px; top:{int(y)}px; '
                         f'font-size:{px}px"><i></i>{_e(chips[k])}</span>')
            order.append((abs(n) + r * 0.5, k, x + ws[k] / 2, y))
            x += ws[k] + gap
    for q, (_, k, x, y) in enumerate(sorted(order)):
        js.append(f'tl.fromTo("#{sid}h{k}", {{opacity: 0, x: {int(cx - x)}, y: {int(cy - y)}, scale: .4}}, '
                  f'{{opacity: 1, x: 0, y: 0, scale: 1, duration: .6, ease: "quint.out"}}, {_r(at + 0.045 * q)});')
        sfx.append(dict(t=at + 0.045 * q + 0.12, sfx=("tick", "tick_b")[q % 2], gain_db=-10))
    return "".join(html_)


def _reel_html(proj, sid, i, s, st, du, plan, files, lang, weight, js, sfx):
    """The reel (arc: launch): one window, a hard cut through a moment of each feature, the filmstrip of those
    moments running under a fixed playhead at one thumbnail per cut (after OpenFilm's timeline montage, MIT), the
    promise line above."""
    L, W, H = plan["layout"], plan["W"], plan["H"]
    R = L["reel"]
    vx, vy, vw, vh = R["view"]
    xf = plan["xf"]
    out = []
    cams = []
    for k, p in enumerate(s["panes"]):
        mid = f"{sid}m{k}"
        cams.append(_cam_html(proj, mid, i, k, p, st + p["at"], js, track=10 + k))
        if k:
            js.append(f'tl.set("#{mid}", {{opacity: 1}}, {_r(st + p["at"])});')
            sfx.append(dict(t=st + p["at"], sfx=("tick", "tick_b")[k % 2], gain_db=-12))
    out.append(f'<div class="win framed" id="{sid}w0" style="left:{vx}px; top:{vy}px; width:{vw}px; height:{vh}px">'
               + "".join(cams) + "</div>")
    for k in range(1, len(cams)):
        js.append(f'tl.set("#{sid}m{k}", {{opacity: 0}}, 0);')
    # the filmstrip: thumbnails of the moments (and the next ones again, dimmed, so the strip never ends)
    sy, th = R["strip"]
    tw = int(th * vw / vh)
    pitch = tw + 14
    n = len(s["panes"])
    thumbs = []
    for k in list(range(n)) + list(range(min(n, 6))):
        p = s["panes"][k]
        m = p["media"]
        img = (_frame(m["file"], p["thumb"], proj, f"{sid}t{k}-{p['shot']}.jpg") if m["kind"] == "video"
               else _asset(m["file"], proj, "shots"))
        thumbs.append(f'<div class="thumb" id="{sid}u{len(thumbs)}" style="left:{len(thumbs) * pitch}px; width:{tw}px; '
                      f'height:{th}px"><img src="{img}" alt=""></div>')
    cx = vx + vw / 2
    x_at = lambda t: round(cx - tw / 2 - (t / s["slot"]) * pitch, 1)       # noqa: E731 - thumb k centred at cut k
    t_land = xf / 2
    out.append(f'<div class="strip" id="{sid}s" style="top:{sy}px">' + "".join(thumbs) + "</div>")
    js.append(f'tl.fromTo("#{sid}s", {{x: {x_at(-t_land)}}}, {{x: {x_at(du - t_land)}, duration: {_r(du)}, '
              f'ease: "none"}}, {_r(st)});')
    for k in range(n):
        a = st + (s["panes"][k]["at"] if k else 0.0)
        js.append(f'tl.to("#{sid}u{k}", {{opacity: 1, boxShadow: "0 0 0 3px {B.rgba(plan["accent"], 0.9)}", '
                  f'duration: .12}}, {_r(a)});')
        if k + 1 < n:
            js.append(f'tl.to("#{sid}u{k}", {{opacity: .42, boxShadow: "0 0 0 0px {B.rgba(plan["accent"], 0)}", '
                      f'duration: .2}}, {_r(st + s["panes"][k + 1]["at"])});')
    out.append(f'<div class="playhead" style="left:{int(cx - 1)}px; top:{sy - 10}px; height:{th + 20}px"></div>')
    if s.get("text"):
        x0, _, x1, _ = L["text"]
        tpx, tl_ = _fit(s["text"], files, (R["title_px"], int(R["title_px"] * 0.72)), x1 - x0, 1, lang, weight)
        out.append(f'<div class="reeltitle" id="{sid}r" style="top:{R["title_y"]}px; font-size:{tpx}px">'
                   f'{caption_html(tl_)}</div>')
        _blur_in(js, f"#{sid}r .w", st + xf * 0.55 + 0.1, stagger=0.025 if lang == "zh" else 0.05, dur=0.6, rise=30)
    return "".join(out)


def build(cfg, plan, proj, quiet=False):
    """Write ``proj``/index.html (+ assets, plan.json, cues.json) for a story plan. Returns proj."""
    os.makedirs(proj, exist_ok=True)
    lang, W, H, L = plan["lang"], plan["W"], plan["H"], plan["layout"]
    T = B.theme(cfg)
    Bk = B.backdrop(cfg)
    p = cfg["product"]
    files = B.font_files(cfg, lang)
    tw = B.display_weight(cfg, lang)
    lw = max(400, tw - 40)
    scale = float((cfg.get("type") or {}).get("scale") or 1.0)
    end = cfg.get("end_card") or {}
    zh = lang == "zh"
    strings = [p["name"], C.text(p.get("name_zh"), lang), C.text(p.get("one_liner"), lang), C.text(end.get("cta"), lang),
               C.text(end.get("sub"), lang), p.get("site", ""), p.get("version", ""), "AI voice AI 配音"]
    badges = C.texts(p.get("badges"), lang)
    strings += badges + [C.text(p.get("tagline"), lang)]
    for s in plan["scenes"]:
        strings += [s.get("text", ""), s.get("title", ""), s.get("eyebrow", ""), s.get("version", ""), s.get("sub", ""),
                    s.get("kicker", "")]
        strings += list(s.get("labels") or []) + list(s.get("chips") or []) + list(s.get("badges") or [])
    from . import blocks as BL
    if BL.used(plan):
        strings.append(BL.words(plan))
    langs = [lang] + (["en"] if zh else [])
    if BL.used(plan) and re.search(r"[\u3400-\u9fff]", BL.words(plan)) and "zh" not in langs:
        langs.append("zh")                 # Chinese platform glyphs also appear in English launch films
    # Optional YAML text (e.g. site/version) may be explicitly null. Use the
    # same text semantics as the visible fields, never render the word None.
    faces = B.stage_fonts(cfg, os.path.join(proj, "assets", "fonts"),
                          "".join(C.text(value, lang) for value in strings), langs)
    from vstudio import theme as TH
    lk = (f":root{{--bg-top:{Bk['top']};--bg-bot:{Bk['bottom']};--lk-flat:{Bk['flat']};--lk-ink:{Bk['ink']};"
          f"--lk-ink2:{Bk['ink2']};--lk-accent:{Bk['accent']};--lk-accent-text:{Bk['accent_text']};"
          f"--lk-shadow:{Bk['shadow']};--lk-pill:{B.rgba(Bk['flat'], 0.86)};--lk-pill-rule:{B.rgba(Bk['ink'], 0.12)};}}")
    css = TH.css_vars(T) + "\n" + lk + "\n" + B.font_css(faces) + CSS
    latin = B.families(faces, "en", "display") if ("en", "display") in faces else B.families(faces, lang, "display")
    # Chinese: Latin words in the Latin face, the rest in Noto Sans SC (Medium; Regular gets a hairline stroke)
    display = (latin.rsplit(",", 1)[0] + ", " + B.families(faces, lang, "display")) if zh else \
        B.families(faces, lang, "display")
    stroke = "-webkit-text-stroke: .014em currentColor;" if zh and B.zh_faux_medium(files["display"]) else ""
    css = (css.replace("{W}", str(W)).replace("{H}", str(H)).replace("{RADIUS}", str(L.get("radius", 18)))
           .replace("{TW}", str(tw)).replace("{LW}", str(lw)).replace("{CW}", str(min(700, tw + 50)))
           .replace("{TLH}", "1.3" if zh else "1.08").replace("{TTRACK}", ".02em" if zh else "-.022em")
           .replace("{LTRACK}", ".02em" if zh else "-.008em").replace("{CTRACK}", "-.04em")
           .replace("{KTRACK}", ".08em" if zh else ".01em")
           .replace("{STROKE}", stroke).replace("{LATIN}", latin)
           .replace("{DISPLAY}", display).replace("{TEXT}", B.families(faces, lang, "text")))
    heavy_titles = (cfg.get("type") or {}).get("titles") == "heavy"
    bctx = dict(W=W, H=H, L=L, cfg=cfg, proj=proj, lang=lang, files=files, lw=lw, ink=Bk["ink"],
                heavy=B.heavy_weight(cfg), heavy_file=files.get("heavy") or files["display"],
                heavy_file_en=B.font_files(cfg, "en").get("heavy") or B.INTER,
                heavy_family=B.families(faces, lang, "heavy"),
                shots={p0["shot"]: dict(still=p0["media"].get("still")) for s0 in plan["scenes"]
                       for p0 in s0.get("panes") or [] if p0.get("media")})
    css += BL.css(bctx)
    hv = " heavy" if heavy_titles else ""
    body, js = [], []
    total = plan["duration"]
    b = cfg.get("brand") or {}
    mark = _asset(b["mark"], proj, "brand") if b.get("mark") else None
    logo = _asset(b["logo"], proj, "brand") if b.get("logo") else None
    vo_on = (cfg.get("voiceover") or {}).get("enabled")
    n = len(plan["scenes"])
    cues = S.caption_cues(plan)
    xf = plan["xf"]
    tx0, ty0, tx1, ty1 = L["text"]
    ncard = 0
    sfx = []
    for i, s in enumerate(plan["scenes"]):
        sid, st, du = f"s{i}", s["start"], s["dur"]
        inner = []
        last_scene = i == n - 1
        tr = transition_of(plan, i)
        if i == 0:
            js.append(f'tl.set("#{sid}", {{opacity: 1}}, 0);')
        else:
            js.append(scene_in(sid, tr, st, xf, W, H))
            if tr in SWISH:
                sfx.append(dict(t=st + xf * 0.5, sfx=SWISH[tr], gain_db=-11))
        if not last_scene or plan["loop"]:
            js.append(scene_out(sid, transition_of(plan, i + 1), st + du - xf, xf, W, H))
        land = st + (0.0 if i == 0 else xf * 0.55)            # the moment the new scene has arrived
        lay = s["layout"]
        if lay in S.FOOTAGE:
            framed = lay in ("float", "split")
            if framed:
                inner.append('<div class="full flat"></div>')
            for k, pane in enumerate(s["panes"]):
                inner.append(_pane_html(proj, sid, i, k, pane, st, framed, js))
            if plan.get("arc") == "launch":
                _tilt(js, sid, s, st, du, W, H)
            if i == 0 and not plan["loop"]:                  # the film opens: the frame settles out of a soft blur
                js.append(f'tl.fromTo("#{sid}", {{scale: 1.04, filter: "blur(10px)"}}, {{scale: 1, '
                          f'filter: "blur(0px)", duration: 0.9, ease: "expo.out"}}, 0);')
            if lay == "float" and s.get("text"):
                lt = _lower_third(L, s["panes"][0]["box"], s["text"], lang, files, lw, W, H)
                if lt:
                    x, y, width, px, ls = lt
                    inner.append(f'<div class="lt" id="{sid}l" style="left:{x}px; top:{y}px; width:{width}px; '
                                 f'font-size:{px}px">{caption_html(ls)}</div>')
                    t0 = land + S.LT_IN
                    _blur_in(js, f"#{sid}l .w", t0, stagger=0.025 if zh else 0.04, dur=0.6, rise=30)
                    t1 = t0 + S.LT_HOLD - 0.35
                    if t1 < st + du - xf - 0.1:
                        js.append(f'tl.to("#{sid}l", {{opacity: 0, filter: "blur(4px)", duration: 0.35, '
                                  f'ease: "power1.in"}}, {_r(t1)});')
            if lay == "split":
                for k, (x, y, width, px, ls, centred) in enumerate(_labels(L, s, files, lang, lw)):
                    inner.append(f'<div class="lt{" c" if centred else ""}" id="{sid}b{k}" style="left:{x}px; '
                                 f'top:{y}px; width:{width}px; font-size:{px}px">{caption_html(ls)}</div>')
                    t0 = land + S.LT_IN + 0.15 * k
                    _blur_in(js, f"#{sid}b{k} .w", t0, stagger=0.025 if zh else 0.04, dur=0.6, rise=30)
                    t1 = land + S.LT_IN + S.LT_HOLD - 0.35
                    if t1 < st + du - xf - 0.1:
                        js.append(f'tl.to("#{sid}b{k}", {{opacity: 0, filter: "blur(4px)", duration: 0.35, '
                                  f'ease: "power1.in"}}, {_r(t1)});')
            if vo_on and s.get("vo") and not (s["panes"][0].get("cont")):
                vsrc, vdur = _vo(cfg, dict(s, id=s["id"]), proj, lang)
                body.append(f'<audio src="{vsrc}" id="{sid}vo" data-start="{_r(st + 0.35)}" data-duration="{_r(vdur)}" '
                            f'data-track-index="8" data-volume="1"></audio>')
        elif lay == S.REEL:
            inner.append('<div class="full flat"></div>')
            inner.append(_reel_html(proj, sid, i, s, st, du, dict(plan, accent=Bk["accent"]), files, lang, lw, js, sfx))
        else:
            inner.append(_field(sid, ncard, W, H, st, du, Bk, js))
            ncard += 1
        if lay == "waterfall":
            inner.append(BL.waterfall_html(bctx, sid, s, land, st, du, js, sfx))
        elif lay == "lift":
            inner.append(BL.lift_html(bctx, sid, s, land, st, du, js, sfx))
        elif lay == "hook":
            inner.append(BL.hook_html(bctx, sid, s, land, st, du, js, sfx))
        elif lay == "type":
            lo = max(40, int(L["type_px"][1] * scale))
            px, ls = _fit(s["text"], files, (int(L["type_px"][0] * scale), lo), L["type_w"], L["type_lines"], lang, tw)
            lh = 1.3 if zh else 1.08
            h = px * lh * len(ls)
            top = int((ty0 + ty1) / 2 - h / 2 - px * 0.06)
            left = int((tx0 + tx1) / 2 - L["type_w"] / 2)
            inner.append(f'<div class="type" id="{sid}t" style="left:{left}px; top:{top}px; width:{L["type_w"]}px; '
                         f'font-size:{px}px">{caption_html(ls)}</div>')
            _blur_in(js, f"#{sid}t .w", land + 0.05, stagger=0.035 if zh else 0.07, dur=0.8)
            js.append(f'tl.fromTo("#{sid}t", {{scale: 1}}, {{scale: 1.03, duration: {_r(du)}, ease: "sine.out"}}, '
                      f'{_r(st)});')
        elif lay == "brand":
            inner.append(_brand_html(sid, s, land, du, st, L, W, H, files, lang, tw, scale, display, mark, js, sfx))
        elif lay == "chapter":
            chips = s.get("chips") or []
            ty = H * (0.44 if H > W else 0.41) - (H * (0.09 if H > W else 0.1) if chips else 0)
            cpx = int(L["chapter_px"] * scale)
            grp = []
            t0 = land + 0.05
            if s.get("eyebrow"):
                epx = L["eyebrow_px"] if s["eyebrow"].isascii() else int(L["eyebrow_px"] * 1.45)
                grp.append(f'<div class="center eyebrow" id="{sid}e" style="top:{int(ty - epx * 2.2)}px; '
                           f'font-size:{epx}px">{_e(s["eyebrow"])}</div>')
                js.append(f'tl.fromTo("#{sid}e", {{opacity: 0, filter: "blur(6px)"}}, {{opacity: 1, '
                          f'filter: "blur(0px)", duration: .6, ease: "power2.out"}}, {_r(t0)});')
            elif mark and s.get("id") == "opening":
                mw = int(cpx * 1.1)
                grp.append(f'<img class="mark" id="{sid}i" src="{mark}" alt="" style="left:{(W - mw) // 2}px; '
                           f'top:{int(ty - mw * 1.15)}px; width:{mw}px">')
                js.append(f'tl.fromTo("#{sid}i", {{opacity: 0, scale: .9, filter: "blur(8px)"}}, {{opacity: 1, '
                          f'scale: 1, filter: "blur(0px)", duration: .7, ease: "expo.out"}}, {_r(t0)});')
            title = s.get("title") or p["name"]
            ascii_title = all(ord(c) < 0x2E80 for c in title)
            tpx = cpx if ascii_title else int(cpx * 0.72)
            fam = "" if ascii_title or heavy_titles else f' font-family:{display};'
            mf = bctx["heavy_file"] if heavy_titles else files["display"]
            while tpx > 40 and B.measure(title, mf, tpx, bctx["heavy"] if heavy_titles else min(700, tw + 50)) > \
                    (tx1 - tx0) * 0.96:
                tpx -= 4
            grp.append(f'<div class="center chap{hv}" id="{sid}n" style="top:{int(ty)}px; font-size:{tpx}px;{fam}">'
                       f'{_chars_html(title)}</div>')
            if plan.get("arc") == "launch":
                _slam(js, f"#{sid}n .w", t0 + 0.1)
                sfx.append(dict(t=t0 + 0.12, sfx="stamp", gain_db=-13))
            else:
                _blur_in(js, f"#{sid}n .w", t0 + 0.1, stagger=0.03, dur=0.8, rise=18)
            y = ty + tpx * 1.18
            if chips:
                grp.append(_chips_html(sid, chips, W / 2, ty + tpx * 0.55, y + tpx * 0.35, L, files, lang, lw, t0 + 0.45,
                                       js, sfx))
            if s.get("version"):
                vpx = int(L["oneliner_px"] * 0.95)
                grp.append(f'<div class="center ver" id="{sid}v" style="top:{int(y)}px; font-size:{vpx}px">'
                           f'{_e(s["version"])}</div>')
                js.append(f'tl.fromTo("#{sid}v", {{opacity: 0, y: 10, filter: "blur(6px)"}}, {{opacity: 1, y: 0, '
                          f'filter: "blur(0px)", duration: .6, ease: "power3.out"}}, {_r(t0 + 0.55)});')
                y += vpx * 1.6
            if s.get("sub"):
                spx, sl = _fit(s["sub"], files, (L["oneliner_px"], int(L["oneliner_px"] * 0.7)), tx1 - tx0, 2, lang, lw)
                grp.append(f'<div class="center cta" id="{sid}o" style="top:{int(y)}px; font-size:{spx}px">'
                           f'{caption_html(sl)}</div>')
                _blur_in(js, f"#{sid}o .w", t0 + 0.6, stagger=0.03 if zh else 0.05, dur=0.6)
            inner.append(f'<div class="full" id="{sid}c">' + "".join(grp) + "</div>")
            js.append(f'tl.fromTo("#{sid}c", {{scale: 1}}, {{scale: 1.035, duration: {_r(du)}, ease: "sine.out"}}, '
                      f'{_r(st)});')
        elif lay == "end":
            t0 = st + xf * 0.4
            ty = H * (0.42 if H > W else 0.4)
            grp = []
            if logo:
                lwid = int(min(W * 0.4, 680))
                grp.append(f'<img class="mark" id="{sid}l" src="{logo}" alt="" style="left:{(W - lwid) // 2}px; '
                           f'top:{int(ty)}px; width:{lwid}px">')
                js.append(f'tl.fromTo("#{sid}l", {{opacity: 0, scale: .97, filter: "blur(8px)"}}, {{opacity: 1, '
                          f'scale: 1, filter: "blur(0px)", duration: .8, ease: "expo.out"}}, {_r(t0)});')
                cy = ty + lwid * 0.34
            else:
                tpx = int(L["chapter_px"] * 0.86 * scale)
                if mark:
                    mw = int(tpx * 1.2)
                    grp.append(f'<img class="mark" id="{sid}i" src="{mark}" alt="" style="left:{(W - mw) // 2}px; '
                               f'top:{int(ty - mw * 1.1)}px; width:{mw}px">')
                    js.append(f'tl.fromTo("#{sid}i", {{opacity: 0, scale: .9, filter: "blur(8px)"}}, {{opacity: 1, '
                              f'scale: 1, filter: "blur(0px)", duration: .7, ease: "expo.out"}}, {_r(t0)});')
                    t0 += 0.15
                grp.append(f'<div class="center chap{hv}" id="{sid}n" style="top:{int(ty)}px; font-size:{tpx}px">'
                           f'{_chars_html(p["name"])}</div>')
                _blur_in(js, f"#{sid}n .w", t0, stagger=0.03, dur=0.8, rise=18)
                cy = ty + tpx * 1.25
                if zh and p.get("name_zh"):
                    zpx = int(L["eyebrow_px"] * 1.1)
                    grp.append(f'<div class="center eyebrow" id="{sid}z" style="top:{int(ty - zpx * 2.2)}px; '
                               f'font-size:{zpx}px">{_e(C.text(p.get("name_zh"), lang))}</div>')
                    js.append(f'tl.fromTo("#{sid}z", {{opacity: 0}}, {{opacity: 1, duration: .5}}, {_r(t0 + 0.2)});')
            cta = C.text(end.get("cta"), lang) or C.text(p.get("one_liner"), lang)
            cpx, clines = _fit(cta, files, (int(L["oneliner_px"]), int(L["oneliner_px"] * 0.7)), tx1 - tx0, 2, lang, lw)
            grp.append(f'<div class="center cta" id="{sid}c" style="top:{int(cy)}px; font-size:{cpx}px">'
                       f'{caption_html(clines)}</div>')
            _blur_in(js, f"#{sid}c .w", t0 + 0.4, stagger=0.03 if zh else 0.05, dur=0.7)
            sy = cy + cpx * 1.25 * len(clines) + cpx * 0.9
            if p.get("site"):
                site = p["site"].replace("https://", "").replace("http://", "").rstrip("/")
                grp.append(f'<div class="center site" id="{sid}s" style="top:{int(sy)}px; '
                           f'font-size:{int(cpx * 0.7)}px">{_e(site)}</div>')
                js.append(f'tl.fromTo("#{sid}s", {{opacity: 0, y: 8}}, {{opacity: 1, y: 0, duration: .6, '
                          f'ease: "power3.out"}}, {_r(t0 + 0.8)});')
                sy += cpx * 1.4
            if badges and plan.get("arc") == "launch":
                bpx = L["badge_px"]
                grp.append(f'<div class="badges" id="{sid}b" style="top:{int(sy + bpx * 0.2)}px; font-size:{bpx}px">'
                           + "".join(f'<span class="badge">{_e(b)}</span>' for b in badges) + "</div>")
                _pop_in(js, f"#{sid}b .badge", t0 + 1.0, stagger=0.07)
                sfx += [dict(t=t0 + 1.0 + 0.07 * k + 0.1, sfx=("tick", "tick_b")[k % 2], gain_db=-8)
                        for k in range(len(badges))]
                sy += bpx * 2.6
            sub = C.text(end.get("sub"), lang)
            if sub:
                grp.append(f'<div class="center sub" id="{sid}u" style="top:{int(sy)}px; '
                           f'font-size:{int(L["eyebrow_px"] * 0.95)}px">{_e(sub)}</div>')
                js.append(f'tl.fromTo("#{sid}u", {{opacity: 0}}, {{opacity: 1, duration: .4}}, {_r(t0 + 1.0)});')
            inner.append(f'<div class="full" id="{sid}g">' + "".join(grp) + "</div>")
            js.append(f'tl.fromTo("#{sid}g", {{scale: 1}}, {{scale: 1.03, duration: {_r(du)}, ease: "sine.out"}}, '
                      f'{_r(st)});')
        # Videos own their absolute media windows; the GSAP scene container must
        # not introduce a second timing clock around those videos.
        timed = '' if any('<video ' in part for part in inner) else (
            f' data-start="{_r(st)}" data-duration="{_r(du)}"')
        cls = 'scene' if not timed else 'scene clip'
        body.append(f'<div class="{cls}" id="{sid}"{timed} '
                    f'data-track-index="{1 + i % 2}" data-layout="{lay}">' + "".join(inner) + "</div>")
    if plan["loop"]:
        # tail: a still of the first scene's opening frame fades in over the last crossfade -> seamless loop
        s0 = plan["scenes"][0]
        p0 = s0["panes"][0]
        m = p0["media"]
        first = (_frame(m["file"], (m["segs"][0][0] if m.get("segs") else m["at"]), proj, "tail-first.jpg")
                 if m["kind"] == "video" else _asset(m["file"], proj, "shots"))
        x, y, w, h = p0["box"]
        k0 = p0["cam"][0]
        sw, sh = m.get("w") or w, m.get("h") or h
        framed = s0["layout"] in ("float", "split")
        tail_at = total - xf
        body.append(f'<div class="scene clip" id="tail" data-start="{_r(tail_at)}" data-duration="{_r(xf)}" '
                    f'data-track-index="5"><div class="full flat"></div>'
                    f'<div class="win{" framed" if framed else ""}" style="left:{x}px; top:{y}px; width:{w}px; '
                    f'height:{h}px"><div class="cam" id="tailm" style="width:{sw}px; height:{sh}px; '
                    f'{_lift(m.get("still"))}"><img src="{first}" alt=""></div></div></div>')
        js.append(f'tl.set("#tailm", {{x: {k0["x"]}, y: {k0["y"]}, scale: {k0["scale"]}}}, 0);')
        js.append(f'tl.fromTo("#tail", {{opacity: 0}}, {{opacity: 1, duration: {xf}, ease: "none"}}, {_r(tail_at)});')
    if vo_on:
        label = "AI 配音" if zh else "AI voice"
        body.append(f'<div class="ailabel clip" data-start="0" data-duration="{_r(total)}" data-track-index="9" '
                    f'style="left:{tx0}px; bottom:{max(24, int(H * 0.03))}px">{label}</div>')
    music = None if plan["loop"] else _music(cfg, proj, total)       # a loop stays silent: no seam in the bed
    fx = _sfx_track(cfg, proj, sfx, total) if music and plan.get("arc") == "launch" else None
    if fx:
        body.append(f'<audio src="{fx}" id="sfx" data-start="0" data-duration="{_r(total)}" data-track-index="6" '
                    f'data-volume="1"></audio>')
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
{CAM_JS}
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
        print(f"built {proj} ({plan['cut']} {lang} {plan['aspect']}, {total:.1f}s, {len(plan['scenes'])} scenes, "
              f"text {plan.get('text_share', 0):.0%})")
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
