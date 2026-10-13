"""Qwen2's byte-level BPE tokenizer (encode only) from a model folder's ``vocab.json`` + ``merges.txt`` +
``tokenizer_config.json`` - what Qwen3-TTS needs to turn a line into token ids, without ``transformers``.

mlx-audio's Qwen3-TTS loads ``transformers.AutoTokenizer`` for this one call (``tokenizer.encode(text)``); the app's
runtime does not ship transformers (and the engine never needs the rest of it). This is the same algorithm as
transformers' ``Qwen2Tokenizer``: NFC, the special tokens split off whole, Qwen2's pre-tokenizer pattern, GPT-2 byte
-> unicode mapping, then BPE by merge rank. tests/test_qwen_tts.py checks it against a recorded transformers output.

    from vstudio.qwen_bpe import QwenBPE
    tok = QwenBPE.from_dir(model_dir)
    tok.encode("<|im_start|>assistant\\n大家好，MCP<|im_end|>")
"""
import json
import os
import unicodedata

import regex

# transformers' Qwen2Tokenizer PRETOKENIZE_REGEX
PATTERN = (r"""(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}| ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|"""
           r"""\s+(?!\S)|\s+""")


def bytes_to_unicode():
    """GPT-2's reversible byte -> printable unicode character table."""
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, (chr(c) for c in cs)))


class QwenBPE:
    def __init__(self, vocab, merges, special):
        self.vocab = vocab
        self.ranks = {tuple(m): i for i, m in enumerate(merges)}
        self.special = dict(special)
        self.byte_map = bytes_to_unicode()
        self.pat = regex.compile(PATTERN)
        # longest first, so "<tts_text_bos_single>" wins over "<tts_text_bos>"
        alts = "|".join(regex.escape(s) for s in sorted(self.special, key=len, reverse=True))
        self.special_pat = regex.compile(f"({alts})") if alts else None
        self._cache = {}

    @classmethod
    def from_dir(cls, d):
        with open(os.path.join(d, "vocab.json"), encoding="utf-8") as f:
            vocab = json.load(f)
        merges = []
        with open(os.path.join(d, "merges.txt"), encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line or line.startswith("#version"):
                    continue
                a, _, b = line.partition(" ")
                merges.append((a, b))
        special = {}
        try:
            with open(os.path.join(d, "tokenizer_config.json"), encoding="utf-8") as f:
                cfg = json.load(f)
            for i, t in (cfg.get("added_tokens_decoder") or {}).items():
                special[t["content"]] = int(i)
        except (OSError, ValueError, KeyError):
            pass
        return cls(vocab, merges, special)

    def _bpe(self, word):
        if word in self._cache:
            return self._cache[word]
        parts = list(word)
        while len(parts) > 1:
            best, at = None, -1
            for i in range(len(parts) - 1):
                r = self.ranks.get((parts[i], parts[i + 1]))
                if r is not None and (best is None or r < best):
                    best, at = r, i
            if best is None:
                break
            a, b = parts[at], parts[at + 1]
            out, i = [], 0
            while i < len(parts):         # merge every occurrence of this pair, left to right
                if i < len(parts) - 1 and parts[i] == a and parts[i + 1] == b:
                    out.append(a + b)
                    i += 2
                else:
                    out.append(parts[i])
                    i += 1
            parts = out
        self._cache[word] = parts
        return parts

    def _encode_plain(self, text):
        ids = []
        for piece in self.pat.findall(unicodedata.normalize("NFC", text)):
            mapped = "".join(self.byte_map[b] for b in piece.encode("utf-8"))
            for tok in self._bpe(mapped):
                ids.append(self.vocab[tok])
        return ids

    def encode(self, text, **_):
        if not self.special_pat:
            return self._encode_plain(text)
        ids = []
        for i, part in enumerate(self.special_pat.split(text)):
            if not part:
                continue
            if i % 2:
                ids.append(self.special[part])
            else:
                ids.extend(self._encode_plain(part))
        return ids

    __call__ = encode
