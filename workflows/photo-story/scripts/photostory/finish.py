"""Last pass of a story vlog: optional highlight hook, loudness + true peak, subtitle files.

    python3 finish.py spec.py film.mp4 out.mp4 --cues cues.json [--srt subtitles.srt]

Spec key HOOK (optional) = dict(segments=[(t0, t1), ...], speed=1.0667): lines cut from the finished film itself
(face card, captions and all), joined with 0.15 s dissolves, played a little faster, then dissolving into the film.
Pick 2-3 short lines; the narration body is already sped, so keep the hook <= ~1.6x of the raw speech.
A story that opens on its own conflict (a cold open) needs no hook: leave HOOK out.

Loudness: a limiter first, then two-pass loudnorm to -14 LUFS / -2 dBTP. The AAC encode adds inter-sample peaks,
so normalising straight to -1.5 dBTP still fails the -1.5 check after a speed-up and dissolves.
The cues file is rewritten: film cues shift by the hook, the hook lines go first; the srt follows the version's
language (zh: text, en: alt).
"""
import argparse
import json
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from vstudio import audio                                          # noqa: E402
from photostory.storyrun import ENC, dur, ff, lang_of, timeline     # noqa: E402

X, XM = 0.15, 0.35


def ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def hook(src, segs, speed, tmp):
    enc = ENC + ["-r", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    parts = []
    for i, (a, b) in enumerate(segs):
        p = os.path.join(tmp, f"hook_{i}.mp4")
        ff(["-ss", f"{a}", "-to", f"{b}", "-i", src, "-filter_complex",
            f"[0:v]setpts=PTS/{speed},fps=30[v];[0:a]atempo={speed}[a]", "-map", "[v]", "-map", "[a]"] + enc + [p])
        parts.append(p)
    L = [dur(p) for p in parts]
    ins, vf, af, acc = [], [], [], L[0]
    for p in parts:
        ins += ["-i", p]
    vlast, alast = "0:v", "0:a"
    for i in range(1, len(parts)):
        vf.append(f"[{vlast}][{i}:v]xfade=transition=fade:duration={X}:offset={acc - X:.3f}[x{i}]")
        af.append(f"[{alast}][{i}:a]acrossfade=d={X}[y{i}]")
        vlast, alast = f"x{i}", f"y{i}"
        acc += L[i] - X
    out = os.path.join(tmp, "hook.mp4")
    if len(parts) == 1:
        return parts[0], L, L[0]
    ff(ins + ["-filter_complex", ";".join(vf + af), "-map", f"[{vlast}]", "-map", f"[{alast}]"] + enc + [out])
    return out, L, dur(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("film")
    ap.add_argument("out")
    ap.add_argument("--cues", required=True, help="cues.json of the film (rewritten in place)")
    ap.add_argument("--srt", help="subtitle file to write (default: next to the cues)")
    a = ap.parse_args()
    spec, C, _, _ = timeline(a.spec)
    lang = lang_of(spec, C)
    tmp = os.path.join(os.path.dirname(os.path.abspath(a.out)), f"_finish_{lang}")
    os.makedirs(tmp, exist_ok=True)
    H = getattr(spec, "HOOK", None)
    joined, shift, hook_cues = a.film, 0.0, []
    d = json.load(open(a.cues))
    cs = d["cues"] if isinstance(d, dict) else d
    if H and H.get("segments"):
        segs, speed = H["segments"], float(H.get("speed", 1.0))
        hk, L, Hd = hook(a.film, segs, speed, tmp)
        joined = os.path.join(tmp, "joined.mp4")
        ff(["-i", hk, "-i", a.film, "-filter_complex",
            f"[0:v]settb=1/30[h];[1:v]fps=30,settb=1/30[m];[h][m]xfade=transition=fade:duration={XM}:offset={Hd - XM:.3f}[v];"
            f"[0:a][1:a]acrossfade=d={XM}[a]", "-map", "[v]", "-map", "[a]"] + ENC + ["-c:a", "aac", "-b:a", "192k", joined])
        shift = Hd - XM
        starts = [sum(L[:i]) - i * X for i in range(len(L))]
        ends = starts[1:] + [Hd]
        pick = [min(cs, key=lambda c: abs(c["start"] - (s0 + 0.1))) for s0, _ in segs]
        hook_cues = [dict(c, start=round(s + 0.05, 3), end=round(e - 0.05, 3)) for c, s, e in zip(pick, starts, ends)]
    wav, wavn = os.path.join(tmp, "a.wav"), os.path.join(tmp, "a_n.wav")
    ff(["-i", joined, "-vn", "-ac", "2", "-ar", "48000", "-af", "alimiter=limit=0.5:level=false:attack=2:release=60", wav])
    audio.loudnorm_2pass(wav, wavn, lufs=-14, tp=-2.0)
    ff(["-i", joined, "-i", wavn, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-ar", "48000", "-movflags", "+faststart", a.out])
    for c in cs:
        c["start"], c["end"] = round(c["start"] + shift, 3), round(c["end"] + shift, 3)
    new = hook_cues + cs
    if isinstance(d, dict):
        d["cues"] = new
    else:
        d = new
    json.dump(d, open(a.cues, "w"), ensure_ascii=False, indent=1)
    key = "text" if lang == "zh" else "alt"
    srt = a.srt or os.path.join(os.path.dirname(os.path.abspath(a.cues)), "subtitles.srt")
    with open(srt, "w") as f:
        for i, c in enumerate(new, 1):
            f.write(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c.get(key) or c['text']}\n\n")
    print(f"finish: {lang} hook {shift:.2f}s, total {dur(a.out):.2f}s -> {a.out}")


if __name__ == "__main__":
    main()
