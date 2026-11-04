"""Narrate a photo story with the creator's own recording instead of TTS.

    python3 own_voice.py timing spec.py                     # -> <TTS dir>/timing.json from spec VO / RAW / UNITS
    python3 own_voice.py sweep in.mp4 out.mp4 --words 然后   # remove every 然后 the cleanup's own ASR missed

Spec keys
  UNITS = ["c1", "u00", ...]            one name per SCRIPT item
  VO = {unit: [(start, end, 中文, English), ...]}   voice units: cue times on the cleaned voice clip
       (the clip lives at <spec dir>/<VO_DIR>/<unit>c.wav, its face video <unit>c.mp4)
  VO_DIR = "vo"
  RAW = {unit: (seconds, [(start, end, 中文, English), ...])}   no-voice units: clip sound or music only

Preparing the voice (per unit, from one long recording):
  1. cut each unit's span at word boundaries (ASR words, ~0.15 s pad);
  2. vstudio.cleanup analyze (profile tight) -> apply: approve the plain fillers, but READ every restart /
     cut-off edit first - the detectors cut deliberate parallel phrasing ("论可爱不是很可爱，论智能不是很智能",
     "压得重一点偏黑，轻一点偏蓝") and complete sentence endings; --keep those ids;
  3. ``sweep`` for connectors the cleanup's ASR merged into neighbouring words (然后 often survives step 2);
  4. speed with atempo + setpts on the same file so the face video stays in sync (e.g. 1.5x when she asks);
  5. re-transcribe for the cue times and proofread every line before it goes into VO.
"""
import argparse
import json
import os
import subprocess
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from photostory.ctx import Ctx, load_spec        # noqa: E402
from photostory.timeline import tts_dir          # noqa: E402
from photostory.storyrun import dur              # noqa: E402


def write_timing(spec_path):
    spec = load_spec(spec_path)
    C = Ctx(spec)
    vo, raw = getattr(spec, "VO", {}) or {}, getattr(spec, "RAW", {}) or {}
    vdir = getattr(spec, "VO_DIR", "vo")
    rows = []
    for i, unit in enumerate(spec.UNITS):
        if unit in vo:
            rel = f"{vdir}/{unit}c.wav"
            d, cues = dur(C.path(rel)), vo[unit]
        elif unit in raw:
            rel, (d, cues) = None, raw[unit]
        else:
            raise SystemExit(f"unit {unit!r} is in neither VO nor RAW")
        rows.append(dict(i=i, path=rel, dur=round(d, 3),
                         chunks=[dict(start=round(a, 3), end=round(min(b, d), 3)) for a, b, *_ in cues]))
    out = os.path.join(tts_dir(C), "timing.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(rows, open(out, "w"), indent=1)
    print(f"timing: {len(rows)} units, {sum(1 for r in rows if r['path'])} with her voice, "
          f"{sum(r['dur'] for r in rows):.1f}s -> {out}")


def char_spans(words, needle):
    """Every occurrence of ``needle`` in the joined word text -> [(t0, t1)], split proportionally inside tokens
    (ASR often glues a connector onto the next word: "然后如果")."""
    chars = []
    for w in words:
        t = str(w["w"]).strip()
        n = max(len(t), 1)
        for i, ch in enumerate(t):
            chars.append((ch, w["t"] + (w["te"] - w["t"]) * i / n, w["t"] + (w["te"] - w["t"]) * (i + 1) / n))
    s = "".join(c[0] for c in chars)
    out, i = [], s.find(needle)
    while i >= 0:
        out.append((max(0.0, chars[i][1] - 0.03), chars[i + len(needle) - 1][2] + 0.03))
        i = s.find(needle, i + len(needle))
    return out


def sweep(src, out, needles, language="zh"):
    from vstudio import asr
    tr = asr.transcribe(src, language=language, prompt=" ".join(needles))
    words = tr["words"]
    spans = sorted(s for n in needles for s in char_spans(words, n))
    if not spans:
        subprocess.run(["cp", src, out], check=True)
        print(f"sweep: nothing to cut in {src}")
        return
    edl = os.path.splitext(out)[0] + ".sweep.json"
    tjson = os.path.splitext(out)[0] + ".words.json"
    json.dump(dict(words=words), open(tjson, "w"), ensure_ascii=False)
    py = sys.executable
    subprocess.run([py, "-m", "vstudio.cleanup", "analyze", src, "--transcript", tjson, "--profile", "gentle",
                    "--lang", language, "--out", edl, "--review", edl + ".md", "--force"], check=True)
    autos = [str(e["id"]) for e in json.load(open(edl))["edits"] if e["action"] == "auto"]
    cmd = [py, "-m", "vstudio.cleanup", "apply", edl, "--out", out, "--force",
           "--cut=" + ",".join(f"{a:.2f}-{b:.2f}" for a, b in spans)]
    if autos:
        cmd.append("--keep=" + ",".join(autos))      # only the swept words in this pass
    subprocess.run(cmd, check=True)
    print(f"sweep: cut {len(spans)} x {'/'.join(needles)} -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("timing")
    t.add_argument("spec")
    s = sub.add_parser("sweep")
    s.add_argument("src")
    s.add_argument("out")
    s.add_argument("--words", nargs="+", default=["然后"])
    s.add_argument("--lang", default="zh")
    a = ap.parse_args()
    if a.cmd == "timing":
        write_timing(a.spec)
    else:
        sweep(a.src, a.out, a.words, a.lang)


if __name__ == "__main__":
    main()
