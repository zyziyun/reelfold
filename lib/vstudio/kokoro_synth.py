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
import os
import sys
import wave


def synth(text, model, voice, lang=None, speed=1.0):
    """-> (samples float32 numpy array, sample_rate)."""
    import numpy as np
    from mlx_audio.tts.utils import load_model

    m = load_model(model, model_type="kokoro")      # named: a folder of any name (an HF snapshot hash) loads
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
    """English voices: a word in no dictionary is spelled (kokoro_g2p.SpellFallback) instead of skipped - the app's
    runtime has no espeak-ng fallback (GPL)."""
    from vstudio.kokoro_g2p import SpellFallback
    g2p = m._get_pipeline(lang).g2p
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
