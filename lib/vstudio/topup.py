"""Script top-up: an AI-drafted script / storyboard that comes out much shorter than its target (a 120 s history
explainer drafted as 80 s) is sent back to the same model to EXTEND it - more beats, verified facts only - up to
``ROUNDS`` times. A piece is never silently shipped much shorter: the draft record carries ``length`` (target, first,
final, rounds, short) and the review says it when it is still short.

    from vstudio import topup
    text, rec = topup.extend(text, target_s, measure=lambda t: seconds, redraft=lambda t, est, k: new_text_or_None)
    topup.note(rec, "en")   # "runs about 82 s of the 120 s target after 2 extensions" or None

``measure(text) -> seconds``; ``redraft(text, est_s, round) -> text | None`` (None: the model failed / returned
nothing usable - the loop stops and keeps the best draft). A longer draft replaces the current one only when it is
longer. The caller runs its fact guard on the final text (vstudio.factguard), so added facts are checked too.
"""
SHORT_BY = 0.15        # shorter than the target by more than this: extend
ROUNDS = 2


def is_short(est, target):
    return bool(target) and est is not None and float(est) < float(target) * (1.0 - SHORT_BY)


def ask(est, target, unit="s"):
    """The instruction for one extension round (English: the drafter reads English instructions)."""
    more = max(1.0, float(target) - float(est))
    return (f"Your draft runs about {float(est):.0f} {unit} but the target is about {float(target):.0f} {unit}: EXTEND "
            f"it by about {more:.0f} {unit}. Add new beats (units / lines / scenes) with more of what the footage "
            "shows and what is well known and verifiable about the subject - never invent a date, number, name or "
            "event, no superlatives you cannot check. Keep every existing beat and its shots; do not pad with "
            "repetition or filler words. Return the whole reply again in the same format.")


def extend(text, target, measure, redraft, rounds=ROUNDS):
    """-> (best text, record {target_s, first_s, final_s, rounds, short, extended})."""
    try:
        first = float(measure(text))
    except Exception:  # noqa: BLE001  (cannot measure: nothing to compare)
        return text, None
    if first <= 0:                       # nothing measurable (no cues / lines): not a length problem
        return text, None
    best, est, k = text, first, 0
    while is_short(est, target) and k < rounds:
        k += 1
        try:
            new = redraft(best, est, k)
        except Exception:  # noqa: BLE001  (a failed call keeps the draft we have)
            new = None
        if not new:
            break
        try:
            e2 = float(measure(new))
        except Exception:  # noqa: BLE001
            continue
        if e2 > est:
            best, est = new, e2
    rec = dict(target_s=round(float(target), 1), first_s=round(first, 1), final_s=round(est, 1), rounds=k,
               extended=est > first, short=is_short(est, target))
    return best, rec


def note(rec, lang="en"):
    """A review line for the draft: what the top-up did, or that the piece is still short (never silent)."""
    if not rec or not rec.get("rounds"):
        return None
    t, f0, f1, k = int(rec["target_s"]), int(rec["first_s"]), int(rec["final_s"]), rec["rounds"]
    if rec.get("short"):
        if lang == "zh":
            return f"脚本仍偏短：约 {f1} 秒，目标 {t} 秒（已让 AI 扩写 {k} 次）"
        if lang == "fr":
            return f"Script encore court : environ {f1} s pour {t} s visées ({k} extension(s) demandée(s))"
        return f"script still short: about {f1} s of the {t} s target after {k} extension(s)"
    if lang == "zh":
        return f"脚本从约 {f0} 秒扩写到约 {f1} 秒（目标 {t} 秒）"
    if lang == "fr":
        return f"Script allongé d'environ {f0} s à {f1} s (cible {t} s)"
    return f"script extended from about {f0} s to {f1} s (target {t} s)"
