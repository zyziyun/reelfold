#!/usr/bin/env python3
"""Cine vlog helpers (style "cine", engine `vstudio.cinefx`). Run from the project folder.

  python3 cine_tools.py ingest  FILES... [--work work]      # SDR clips, full-res photos, 1 s contact sheets
  python3 cine_tools.py voice   CLIP.MOV [--atten-lim 10]   # her voice -> work/voice/<clip>.clean.wav, checked
  python3 cine_tools.py covers  --photos a b c --title T [--sub S] [--en E] [--out dir]
  python3 cine_tools.py practice LINES.txt [--starts 0.2,3.5,...] [--out dir]   # English VO practice audio

ingest: phone HDR (HLG / Dolby Vision) clips are tone-mapped with `media.to_sdr` (avconvert on macOS, which keeps
highlight detail as well as zscale + hable; libplacebo needs Vulkan). Photos are written at FULL resolution
(EXIF-rotated): a 1600 px export looks soft once a photo is cropped to 9:16 or used in a cover.
voice: DeepFilterNet (when installed; `pip install deepfilternet torch==2.0.1 torchaudio==2.0.2 "numpy<2"` in its own
venv, found via $VSTUDIO_DEEPFILTER, `deepFilter` on PATH or ~/.venvs/dfn/bin/deepFilter) then studiosound "light"
(EQ, de-ess, compression). Indoor takes take full strength; a street take at ~7 dB SNR loses words above
--atten-lim 10. Every result is re-transcribed and its lag measured, so a cleaned take that dropped words or moved
the lips out of sync is reported before it reaches the mix.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))

from vstudio import media  # noqa: E402

VIDEO = (".mov", ".mp4", ".m4v")
PHOTO = (".heic", ".heif", ".jpg", ".jpeg", ".png")


# ------------------------------------------------------------------------------------------------ ingest
def photo_full(src, dst):
    """Any phone photo -> full-resolution, upright JPEG."""
    from PIL import Image, ImageOps
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    try:
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        im.save(dst, quality=92)
        return dst
    except Exception:
        if shutil.which("sips"):        # macOS: HEIC without pillow-heif
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "92", src, "--out", dst],
                           check=True, capture_output=True)
            im = ImageOps.exif_transpose(Image.open(dst)).convert("RGB")
            im.save(dst, quality=92)
            return dst
        raise


def sheet(src, out, every=1.0):
    """One tile per `every` seconds, 8 across, for choosing windows (read every sheet before editing)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf",
                    f"fps={1 / every},scale=-2:300,tile=8x4", "-frames:v", "1", out], check=True)
    return out


def ingest(files, work):
    for d in ("sdr", "photos_full", "sheets"):
        os.makedirs(os.path.join(work, d), exist_ok=True)
    for f in files:
        name, ext = os.path.splitext(os.path.basename(f))
        if ext.lower() in VIDEO:
            dst = os.path.join(work, "sdr", name + ".mp4")
            if not os.path.exists(dst):
                media.to_sdr(f, dst)
            sheet(dst, os.path.join(work, "sheets", name + ".jpg"))
            info = media.probe(dst)
            print(f"{name:14s} video {info.get('width')}x{info.get('height')} {info.get('duration', 0):.1f}s")
        elif ext.lower() in PHOTO:
            dst = os.path.join(work, "photos_full", name + ".jpg")
            photo_full(f, dst)
            print(f"{name:14s} photo -> {dst}")


# ------------------------------------------------------------------------------------------------ voice
def deepfilter_bin():
    for c in (os.environ.get("VSTUDIO_DEEPFILTER"), shutil.which("deepFilter"),
              os.path.expanduser("~/.venvs/dfn/bin/deepFilter")):
        if c and os.path.exists(c):
            return c
    return None


def lag_ms(a, b, sr=48000, hop=48, span=200):
    """Envelope cross-correlation lag of b against a, in ms: positive = b is later (0 = lips still in sync)."""
    n = min(len(a), len(b)) // hop * hop
    ea = np.abs(a[:n]).reshape(-1, hop).mean(1)
    eb = np.abs(b[:n]).reshape(-1, hop).mean(1)
    ea, eb = ea - ea.mean(), eb - eb.mean()
    best, best_v = 0, -np.inf
    for L in range(-span, span + 1):
        x = ea[max(0, L):len(ea) + min(0, L)]
        y = eb[max(0, -L):len(eb) - max(0, L)]
        v = float(np.dot(x, y))
        if v > best_v:
            best, best_v = L, v
    return -best * hop * 1000 // sr


def voice(clip, work, atten_lim=None, language="zh"):
    from vstudio import asr, studiosound as SS, audio as A
    os.makedirs(os.path.join(work, "voice"), exist_ok=True)
    name = os.path.splitext(os.path.basename(clip))[0]
    raw = A.decode_audio(clip, sr=48000, channels=1)
    raw = raw if raw.ndim == 1 else raw[:, 0]
    x = raw
    dfn = deepfilter_bin()
    if dfn:
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, name + ".wav")
            A.write_wav(src, raw, 48000)
            cmd = [dfn, src, "-o", td] + (["--atten-lim", str(atten_lim)] if atten_lim else [])
            subprocess.run(cmd, check=True, capture_output=True)
            out = [p for p in os.listdir(td) if p != name + ".wav" and p.endswith(".wav")][0]
            x = A.decode_audio(os.path.join(td, out), sr=48000, channels=1)
            x = x if x.ndim == 1 else x[:, 0]
    else:
        print("note: DeepFilterNet not found; studiosound only (weaker on street noise)")
    y, _ = SS.enhance_array(x, 48000, strength="light" if dfn else "standard")
    y = (y if y.ndim == 1 else y[:, 0])[:len(raw)]
    dst = os.path.join(work, "voice", name + ".clean.wav")
    A.write_wav(dst, y, 48000)
    before, after = SS.analyze(raw), SS.analyze(y)
    heard = asr.transcribe(dst, language=language, cache=False)["text"]
    print(f"{name}: SNR {before['snr_db']} -> {after['snr_db']} dB, lag {lag_ms(raw, y)} ms")
    print(f"  heard: {heard[:120]}")
    print("  compare the words with the original transcript; if they drifted, lower --atten-lim")
    return dst


# ------------------------------------------------------------------------------------------------ covers
def covers(work, photos, title, sub="", en="", out=None):
    from vstudio import cinefx as C
    C.configure(work, None, beat=0.5, music_start=0.0)
    out = out or os.path.join(C.RAW, "covers")
    os.makedirs(out, exist_ok=True)
    made = [C.save_cover(C.cover_negative(photos[0], title, sub, en), os.path.join(out, "cover_negative.png")),
            C.save_cover(C.cover_still(photos[0], title, sub, en), os.path.join(out, "cover_still.png"))]
    if len(photos) >= 3:
        made.append(C.save_cover(C.cover_strip(photos[:3], title, sub, en), os.path.join(out, "cover_strip.png")))
    for p in made:
        print(p)
    return made


# ------------------------------------------------------------------------------------------------ practice
def practice(lines, starts=None, out="practice", voice="af_heart", respell=None):
    """English VO practice audio: shadowing track (normal, gap, slow, gap, normal) and, given each line's
    timeline start, a timed track to rehearse against the cut. respell maps hard names to TTS spellings."""
    from vstudio import tts, audio as A
    os.makedirs(os.path.join(out, "lines"), exist_ok=True)
    sr = 48000

    def trim(x):
        e = np.abs(x) > 0.01
        i, j = np.argmax(e), len(x) - np.argmax(e[::-1])
        return x[max(0, i - 480):j + 2400]

    def say(t, speed):
        for k, v in (respell or {}).items():
            t = t.replace(k, v)
        x = A.decode_audio(tts.synth(t, engine="kokoro", voice=voice, speed=speed), sr=sr, channels=1)
        return trim(x if x.ndim == 1 else x[:, 0])
    norm = [say(t, 1.0) for t in lines]
    slow = [say(t, 0.8) for t in lines]
    sil = lambda s: np.zeros(int(s * sr), np.float32)  # noqa: E731
    parts = [sil(0.5)]
    for i, (x, y) in enumerate(zip(norm, slow)):
        A.write_wav(os.path.join(out, "lines", f"{i + 1:02d}.wav"), x, sr)
        d = len(x) / sr
        parts += [x, sil(d * 1.4 + 0.8), y, sil(len(y) / sr * 1.3 + 0.8), x, sil(d * 1.4 + 1.5)]
    A.write_wav(os.path.join(out, "01_shadowing.wav"), np.concatenate(parts), sr)
    if starts:
        tr = np.zeros(int((max(starts) + 6) * sr), np.float32)
        for x, t0 in zip(norm, starts):
            i = int(t0 * sr)
            tr[i:i + len(x)] += x[:len(tr) - i]
        A.write_wav(os.path.join(out, "02_timed.wav"), tr, sr)
    for i, x in enumerate(norm):
        print(f"{i + 1:02d} {len(x) / sr:.2f}s")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ingest")
    a.add_argument("files", nargs="+")
    a.add_argument("--work", default="work")
    v = sub.add_parser("voice")
    v.add_argument("clip")
    v.add_argument("--work", default="work")
    v.add_argument("--atten-lim", type=float)
    v.add_argument("--language", default="zh")
    c = sub.add_parser("covers")
    c.add_argument("--work", default="work")
    c.add_argument("--photos", nargs="+", required=True)
    c.add_argument("--title", required=True)
    c.add_argument("--sub", default="")
    c.add_argument("--en", default="")
    c.add_argument("--out")
    p = sub.add_parser("practice")
    p.add_argument("lines")
    p.add_argument("--starts")
    p.add_argument("--out", default="practice")
    p.add_argument("--voice", default="af_heart")
    args = ap.parse_args(argv)
    if args.cmd == "ingest":
        ingest(args.files, args.work)
    elif args.cmd == "voice":
        voice(args.clip, args.work, args.atten_lim, args.language)
    elif args.cmd == "covers":
        covers(args.work, args.photos, args.title, args.sub, args.en, args.out)
    elif args.cmd == "practice":
        lines = [ln.strip() for ln in open(args.lines, encoding="utf-8") if ln.strip()]
        starts = [float(s) for s in args.starts.split(",")] if args.starts else None
        practice(lines, starts, args.out, args.voice)


if __name__ == "__main__":
    main()
