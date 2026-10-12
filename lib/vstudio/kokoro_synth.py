"""One Kokoro-82M take through mlx-audio's Python API (run as a child process by ``vstudio.tts``).

    python kokoro_synth.py --model <folder | HF repo> --voice <voice id | voices/x.safetensors> --lang z \
        --speed 1.0 --out take.wav  < text

Why not ``python -m mlx_audio.tts.generate``: that CLI imports its audio player (sounddevice / PortAudio) for every
take, and with a local model folder it still resolves voices through the Hugging Face hub. Here the model type is
named (a folder of any name loads), a voice file is used as is, and nothing but mlx-audio + misaki is imported - the
same set the app's runtime bundles (Mac App Store: no audio device, no network). Writes 24 kHz mono 16-bit wav.
Mandarin voices read English terms as English and long lines in pieces that fit the model (vstudio.kokoro_g2p).
"""
import argparse
import math
import os
import sys
import wave


def synth(text, model, voice, lang=None, speed=1.0):
    """-> (samples float32 numpy array, sample_rate). ``model``: a folder / HF repo, or a loaded Kokoro model."""
    import numpy as np
    from mlx_audio.tts.utils import load_model

    exact_interpolate()
    m = model if hasattr(model, "generate") else load_model(model, model_type="kokoro")   # named: any folder loads
    lang = lang or "a"
    if lang == "z":
        text = "\n".join(mandarin(m, text))
    elif lang in "ab":
        english(m, lang)
    chunks = [np.asarray(r.audio, dtype=np.float32).reshape(-1)
              for r in m.generate(text=text, voice=voice, speed=float(speed), lang_code=lang, split_pattern=r"\n+")]
    chunks = [c for c in chunks if c.size]
    if not chunks:
        raise SystemExit("kokoro produced no audio (empty text, or every word was out of the dictionary)")
    return np.concatenate(chunks), int(m.sample_rate)


def scaled_size(n, scale):
    """Output length of resampling ``n`` steps by ``scale``: the exact integer when n * scale is one up to float error
    (n = 300 * k, scale = 1 / 300 -> k), else rounded up as mlx-audio does."""
    x = float(n) * float(scale)
    r = round(x)
    return max(1, int(r if abs(x - r) < 1e-6 else math.ceil(x)))


def exact_interpolate():
    """Kokoro's vocoder (mlx-audio istftnet.SineGen) resamples its F0 track by 1/300 and back by 300, sizing each
    step as ``ceil(n * scale)`` in floating point. For about one frame count in five (n = 1782 * 300: 534600 / 300
    -> 1782.0000000000002 -> 1783) the sine source comes back 300 samples longer than the voiced/unvoiced mask and
    the take dies with "[broadcast_shapes] Shapes (1,534600,1) and (1,534900,9)" - a fixed function of the line's
    phoneme durations, so the same line failed on every retry and only rewording it got through. mlx-audio 0.5.x
    trims the sine to length afterwards; 0.4.x (a pip install outside the app) does not. Sizing the two resamples
    exactly fixes both."""
    try:
        from mlx_audio.tts.models.kokoro import istftnet
    except ImportError:
        return
    orig = getattr(istftnet, "interpolate", None)
    if orig is None or getattr(orig, "_vstudio_exact", False):
        return

    def interpolate(input, size=None, scale_factor=None, mode="nearest", align_corners=None):
        if size is None and scale_factor is not None:
            dims = input.shape[2:]
            scales = scale_factor if isinstance(scale_factor, (list, tuple)) else [scale_factor] * len(dims)
            size = [scaled_size(n, s) for n, s in zip(dims, scales)]
            size = size[0] if len(size) == 1 else size
        return orig(input, size=size, mode=mode, align_corners=align_corners)

    interpolate._vstudio_exact = True
    istftnet.interpolate = interpolate


def mandarin(m, text):
    """Mandarin: English terms read as English (kokoro_g2p.MixedZhG2P on the model's "z" pipeline) and the text cut
    into pieces that fit Kokoro's 510-phoneme window -> the pieces (one per generate segment)."""
    from vstudio.kokoro_g2p import MixedZhG2P, chunks
    if not hasattr(m, "_get_pipeline"):
        raise SystemExit("mlx-audio's Kokoro model changed (no _get_pipeline): update vstudio/kokoro_synth.py")
    pipe = m._get_pipeline("z")
    if not isinstance(pipe.g2p, MixedZhG2P):
        pipe.g2p = MixedZhG2P(pipe.g2p)
    return chunks(" ".join(text.split("\n")), lambda s: len(pipe.g2p(s)[0]))


def english(m, lang):
    """English voices: the curated names first (vstudio.kokoro_lexicon: Elliott, Elvis, Puget ... as phonemes), and a
    word in no dictionary is spelled (kokoro_g2p.SpellFallback) instead of skipped - the app's runtime has no
    espeak-ng fallback (GPL)."""
    from vstudio import kokoro_lexicon
    from vstudio.kokoro_g2p import SpellFallback
    g2p = m._get_pipeline(lang).g2p
    if hasattr(g2p, "lexicon"):
        kokoro_lexicon.install(g2p.lexicon)
    if getattr(g2p, "fallback", None) is None and hasattr(g2p, "lexicon"):
        g2p.fallback = SpellFallback(g2p.lexicon)


def write_wav(path, samples, sr):
    import numpy as np
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--lang")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--text", help="default: stdin")
    a = ap.parse_args(argv)
    text = a.text if a.text is not None else sys.stdin.read()
    samples, sr = synth(text.strip(), a.model, a.voice, a.lang, a.speed)
    write_wav(a.out, samples, sr)
    print(f"kokoro: {len(samples) / sr:.2f} s -> {a.out}")


if __name__ == "__main__":
    main()
