"""One Qwen3-TTS (CustomVoice) take through mlx-audio's Python API (run as a child process by ``vstudio.tts``).

    python -m vstudio.qwen_synth --model <folder | HF repo> --voice serena [--instruct "..."] [--seed 7] --out take.wav < text

The free Chinese voice: Qwen3-TTS-12Hz-1.7B-CustomVoice (Apache-2.0) with its native Mandarin speakers (Serena,
Vivian, Uncle Fu, Dylan / Beijing, Eric / Sichuan). It reads tones, polyphones (行长, 重新, 划船) and the English terms
of a 中文讲解 (MCP, Tool Calling, Space Needle) by itself - no G2P, no dictionary.

Why a child process and not ``mlx_audio.tts.generate``: the app's runtime has no ``transformers`` (the model's text
tokenizer is ``vstudio.qwen_bpe``, the same BPE), no ``tokenizers`` and no scipy (App Review): ``light_codec_imports``
loads only the codec modules the model uses. Nothing is fetched for a local folder.

The model is autoregressive, so a take can run on (babble or a long silence after the line) or stop early. Each piece
is checked against the length its characters should take; an implausible take is said again with the next seed
(``MAX_TRIES``), and trailing silence is trimmed. Long lines go in sentence-sized pieces (``pieces``).
Writes 24 kHz mono 16-bit wav.
"""
import argparse
import os
import re
import sys
import wave

SPEAKERS = ("serena", "vivian", "uncle_fu", "dylan", "eric", "ryan", "aiden", "ono_anna", "sohee")
ZH_SPEAKERS = ("serena", "vivian", "uncle_fu", "dylan", "eric")
MAX_TRIES = 3
MAX_PIECE = 120                       # characters per generate call (a sentence or two)
GAP_S = 0.12                          # pause between the pieces of a long line
_SENT = re.compile(r"(?<=[。！？!?；;])|(?<=[.])\s+")
_CLAUSE = re.compile(r"(?<=[，、：,:])")
_CJK = re.compile(r"[㐀-鿿]")
_SYLLABIC = re.compile(r"[㐀-鿿\u3040-\u30ff\uac00-\ud7af\u1100-\u11ff]")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_LANGUAGES = dict(zh="chinese", en="english", ja="japanese", ko="korean", fr="french", de="german",
                  it="italian", pt="portuguese", es="spanish", ru="russian")


def language_for(text, language=None):
    """Honor an explicit locale; infer distinctive scripts only (Latin languages need a locale)."""
    if language:
        code = str(language).strip().lower().replace("_", "-").split("-")[0]
        name = _LANGUAGES.get(code, code)
        if name not in _LANGUAGES.values():
            raise ValueError(f"Qwen3-TTS does not support language {language!r}")
        return name
    for pattern, name in ((r"[\u3040-\u30ff]", "japanese"), (r"[\uac00-\ud7af\u1100-\u11ff]", "korean"),
                          (r"[㐀-鿿]", "chinese"), (r"[\u0400-\u04ff]", "russian")):
        if re.search(pattern, text):
            return name
    return "english"



def pieces(text, limit=MAX_PIECE):
    """``text`` in pieces of at most ``limit`` characters, cut at sentence ends, else at clause marks."""
    text = " ".join(str(text).split())
    out, cur = [], ""
    for s in (p for p in _SENT.split(text) if p and p.strip()):
        parts = [s] if len(s) <= limit else [c for c in _CLAUSE.split(s) if c]
        for p in parts:
            if cur and len(cur) + len(p) > limit:
                out.append(cur.strip())
                cur = ""
            cur += p
    if cur.strip():
        out.append(cur.strip())
    return out


def expected_seconds(text):
    """About how long ``text`` takes to say: CJK/Korean ~4.5 characters/s, other scripts ~2.6 words/s; a loose retry bound."""
    return len(_SYLLABIC.findall(text)) / 4.5 + len(_WORD.findall(_SYLLABIC.sub(" ", text))) / 2.6


def plausible(seconds, text):
    """A take of ``seconds`` for ``text`` is neither cut short nor running on."""
    e = expected_seconds(text)
    return 0.4 * e - 0.5 <= seconds <= 2.0 * e + 2.0


def trim_silence(a, sr, thresh=0.01, keep=0.12):
    """Cut leading / trailing silence (frames under ``thresh`` RMS), keeping ``keep`` s of air at each end."""
    import numpy as np
    fr = max(1, int(sr * 0.02))
    n = len(a) // fr
    if n == 0:
        return a
    rms = np.sqrt(np.mean(a[:n * fr].reshape(n, fr) ** 2, axis=1))
    loud = np.nonzero(rms > thresh)[0]
    if loud.size == 0:
        return a
    k = int(keep * sr)
    return a[max(0, loud[0] * fr - k):min(len(a), (loud[-1] + 1) * fr + k)]


def light_codec_imports():
    """Let ``mlx_audio.codec.models.mimi`` (the speech tokenizer's building blocks) import without running
    ``mlx_audio/codec/__init__.py``, which imports every codec mlx-audio has - among them chatterbox's (``tokenizers``)
    and MiMo's resampler (scipy), neither in the app's runtime nor needed here. The two package modules are registered
    bare (their ``__path__`` only); submodules load from disk as usual. A no-op once mlx_audio.codec is imported."""
    import importlib.util
    import types
    if "mlx_audio.codec" in sys.modules:
        return
    spec = importlib.util.find_spec("mlx_audio")
    if spec is None or not spec.submodule_search_locations:
        return
    root = os.path.join(list(spec.submodule_search_locations)[0], "codec")
    for name, path in (("mlx_audio.codec", root), ("mlx_audio.codec.models", os.path.join(root, "models"))):
        if not os.path.isdir(path):
            return
        mod = types.ModuleType(name)
        mod.__path__ = [path]
        mod.__package__ = name
        sys.modules[name] = mod


def load(model):
    """A Qwen3-TTS model with the BPE tokenizer of ``vstudio.qwen_bpe`` (no transformers)."""
    import io
    from contextlib import redirect_stdout
    light_codec_imports()
    from mlx_audio.tts.utils import load_model
    with redirect_stdout(io.StringIO()):            # "Could not load tokenizer" (no transformers): ours follows
        m = load_model(model)
    if getattr(m, "tokenizer", None) is None:
        from vstudio.qwen_bpe import QwenBPE
        m.tokenizer = QwenBPE.from_dir(_local_dir(m, model))
    return m


def _local_dir(m, model):
    if os.path.isdir(model):
        return model
    from huggingface_hub import snapshot_download
    return snapshot_download(model, allow_patterns=["vocab.json", "merges.txt", "tokenizer_config.json"])


def _take(m, text, voice, instruct, lang, seed):
    import mlx.core as mx
    import numpy as np
    mx.random.seed(int(seed))
    kw = dict(text=text, voice=voice, lang_code=lang)
    if instruct:
        kw["instruct"] = instruct
    res = [np.asarray(r.audio, dtype=np.float32).reshape(-1) for r in m.generate(**kw)]
    res = [r for r in res if r.size]
    return np.concatenate(res) if res else np.zeros(0, dtype=np.float32)


def synth(text, model, voice="serena", instruct=None, lang=None, seed=7, log=None):
    """-> (samples float32 numpy array, sample_rate). ``model``: a folder / HF repo, or a loaded model."""
    import numpy as np
    m = model if hasattr(model, "generate") else load(model)
    sr = int(m.sample_rate)
    voice = str(voice or "serena").lower()
    if voice not in SPEAKERS:
        raise SystemExit(f"Qwen3-TTS has no voice {voice!r} (voices: {', '.join(SPEAKERS)})")
    lang = language_for(text, lang)
    out = []
    for i, p in enumerate(pieces(text)):
        best = None
        for t in range(MAX_TRIES):
            a = trim_silence(_take(m, p, voice, instruct, lang, seed + 1000 * t + i), sr)
            ok = plausible(len(a) / sr, p)
            if best is None or ok:
                best = a
            if ok:
                break
            if log:
                log(f"qwen: piece {i + 1} took {len(a) / sr:.1f}s for {len(p)} chars (about "
                    f"{expected_seconds(p):.1f}s expected): new take")
        if best is None or not best.size:
            raise SystemExit("qwen produced no audio")
        out.append(best)
    gap = np.zeros(int(GAP_S * sr), dtype=np.float32)
    joined = out[0] if len(out) == 1 else np.concatenate([x for a in out for x in (a, gap)][:-1])
    return joined, sr


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
    ap.add_argument("--voice", default="serena")
    ap.add_argument("--instruct")
    ap.add_argument("--lang")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True)
    ap.add_argument("--text", help="default: stdin")
    a = ap.parse_args(argv)
    text = (a.text if a.text is not None else sys.stdin.read()).strip()
    if not text:
        raise SystemExit("qwen: empty text")
    samples, sr = synth(text, a.model, a.voice, a.instruct, a.lang, a.seed, log=lambda s: print(s, flush=True))
    write_wav(a.out, samples, sr)
    print(f"qwen: {len(samples) / sr:.2f} s -> {a.out}")


if __name__ == "__main__":
    main()
