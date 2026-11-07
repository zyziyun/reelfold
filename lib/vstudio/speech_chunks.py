"""Shared sentence/word-preserving input packing for local speech models."""
import re

VERSION = 1

_SENT_END = re.compile(r"(?<=[。！？!?；;])|(?<=\.)(?=\s)")
_CLAUSE_END = re.compile(r"(?<=[，、：,:—])")
_WORD_END = re.compile(r"(?<=\s)")


def _cut(text, n):
    """``text`` in ``n`` pieces of about equal length (a run-on with no mark or space left to split at)."""
    k = -(-len(text) // max(1, n))
    return [text[i:i + k] for i in range(0, len(text), k)]


def chunks(text, measure, limit):
    """Pack sentences, clauses, then words within a model's measured input budget.

    ``measure`` counts characters for Qwen and phonemes for Kokoro. Keep separators
    while joining adjacent parts; only trim at boundaries between separate takes.
    Run-ons with no punctuation or spaces fall back to smaller character groups.
    """
    if limit <= 0:
        raise ValueError("speech chunk limit must be positive")
    levels = (_CLAUSE_END.split, _WORD_END.split, lambda p: _cut(p, measure(p) // limit + 1), None)

    def pack(parts, level):
        out, cur = [], ""
        for p in parts:
            if not p.strip():
                continue
            if cur and measure(cur + p) > limit:
                out.append(cur)
                cur = ""
            split = levels[level]
            if not cur and split is not None and measure(p) > limit:
                pieces = split(p)
                if len(pieces) > 1:
                    out.extend(pack(pieces, level + 1))
                    continue
                if level + 1 < len(levels) and levels[level + 1] is not None:
                    out.extend(pack([p], level + 1))
                    continue
            cur += p
        if cur.strip():
            out.append(cur)
        return out
    return [c.strip() for c in pack(_SENT_END.split(text.strip()), 0) if c.strip()]
