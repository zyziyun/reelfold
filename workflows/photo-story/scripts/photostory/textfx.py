"""Big on-screen text, number stamps, design cards and sound effects, anchored to the spoken lines.

    python3 textfx.py spec.py film.mp4 out.mp4

Spec keys
  TEXTFX = [(unit, cue or None, (中文, English), style, sfx), ...]
      cue    a piece of the unit's caption text (spec VO / RAW); the item shows while that line is spoken.
             None = the whole unit.
      style  title | tag (upper third) | num (heavy accent number, middle) | end (end card) |
             card (the text is an image path relative to the spec: a cover design shown as a ~2 s tilted card)
      sfx    a vstudio.audio.sfx_bank name (pop, stamp, ding, soft, whoosh, shutter ...) or None
  SHUTTER = (unit, ...)   every shot change inside these units gets a camera click (a photo montage)

Timing rules baked in: num / tag land 0.35 s after the line starts (never on top of a face card popping in);
text fades 0.4 s, cards 0.3 s; a card holds at most 2 s and ends above the caption box.
"""
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np                                                # noqa: E402

from vstudio import audio as A                                    # noqa: E402
from vstudio import storyfx as S                                  # noqa: E402
from vstudio.config import font                                   # noqa: E402
from photostory.storyrun import ENC, cue_rows, ff, lang_of, timeline   # noqa: E402

SR = 48000
ROLES = {"zh": dict(title="cjk-serif-bold", num="cjk-bold"), "en": dict(title="display-latin", num="cjk-bold")}


def events(spec_path):
    spec, C, T, units = timeline(spec_path)
    lang = lang_of(spec, C)
    ev = []
    for unit, key, (zh, en), style, sfx in getattr(spec, "TEXTFX", []) or []:
        u = units[unit]
        if key is None:
            a, b = u["start"] + 0.15, u["start"] + u["dur"]
        else:
            r = next((r for r in cue_rows(spec, unit) if key in r[2]), None)
            if r is None:
                raise SystemExit(f"TEXTFX: no caption line in {unit} contains {key!r}")
            a, b = u["start"] + r[0], u["start"] + r[1]
        if style in ("num", "tag"):
            a += 0.35
        if style == "card":
            b = min(b + 0.3, a + 2.0)
        ev.append(dict(t0=a, t1=max(b, a + 1.4), text=zh if lang == "zh" else en, style=style, sfx=sfx))
    shots = []
    for unit in getattr(spec, "SHUTTER", ()) or ():
        u = units[unit]
        shots += [sh["start"] for sh in T.shots if u["start"] - 0.05 <= sh["start"] < u["start"] + u["dur"]]
    return spec, C, T.total, lang, ev, shots


def main(spec_path, video, out):
    spec, C, total, lang, ev, shots = events(spec_path)
    tmp = os.path.join(os.path.dirname(os.path.abspath(out)), f"_textfx_{lang}")
    os.makedirs(tmp, exist_ok=True)
    args, chain, last = ["-i", video], [], "0:v"
    for k, e in enumerate(ev):
        p = os.path.join(tmp, f"g{k:02d}.png")
        if e["style"] == "card":
            S.design_card(C.path(e["text"]), (C.W, C.H), bottom=C.SUB_Y0 - 40, angle=(-2.5, 2.0)[k % 2]).save(p)
        else:
            role = ROLES.get(lang, ROLES["zh"])["num" if e["style"] == "num" else "title"]
            S.text_card(e["text"], e["style"], (C.W, C.H), font(role)).save(p)
        a, b = e["t0"], e["t1"]
        fd = 0.3 if e["style"] == "card" else 0.4
        args += ["-loop", "1", "-t", f"{total:.2f}", "-i", p]
        chain.append(f"[{k + 1}:v]format=rgba,fade=t=in:st={a:.2f}:d={fd}:alpha=1,"
                     f"fade=t=out:st={b - fd:.2f}:d={fd}:alpha=1[g{k}]")
        chain.append(f"[{last}][g{k}]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[o{k}]")
        last = f"o{k}"
    bank = A.sfx_bank(SR)
    n = int((total + 1) * SR)
    fx = np.zeros(n, np.float32)

    def put(name, t, gain):
        x = bank[name] * gain
        i = int(t * SR)
        fx[i:i + len(x)] += x[: max(0, n - i)]
    for e in ev:
        if e["sfx"]:
            put(e["sfx"], e["t0"], A.SFX_GAINS.get(e["sfx"], 0.35))
    for i, t in enumerate(shots):
        put("shutter" if i % 2 == 0 else "shutter_b", t, 0.32)
    fxw = os.path.join(tmp, "sfx.wav")
    A.write_wav(fxw, np.stack([fx, fx], 1), SR)
    args += ["-i", fxw]
    chain.append(f"[0:a][{len(ev) + 1}:a]amix=inputs=2:duration=first:normalize=0[a]")
    ff(args + ["-filter_complex", ";".join(chain), "-map", f"[{last}]", "-map", "[a]"] + ENC +
       ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out])
    print(f"textfx: {len(ev)} items, {len(shots)} shutter clicks -> {out}")
    for e in ev:
        print(f"  {e['t0']:7.2f}-{e['t1']:7.2f}  {e['style']:5s} {e['sfx'] or '-':7s} {e['text']}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:4])
