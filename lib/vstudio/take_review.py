"""Shared AIGC review rubric and file-bound evidence validation."""
import hashlib
import json
import os

HARD = {
    "identity_drift": "face/glasses/hair/outfit differs from the look sheet, or changes within the take; A/B swapped",
    "premise_missing": "the action or spatial relation this shot must establish is not on screen",
    "hands_limbs": "extra/fused fingers, hand shape morphing, limbs through objects",
    "physics": "objects pass through bodies, appear/vanish/duplicate, gliding instead of walking",
    "generated_text": "readable or garbled text on screens, signs, paper (all text is added in post)",
    "lipsync_or_line": "mouth does not match, wrong words, or the wrong character speaks the line",
    "body_integrity": "a body part hidden then revealed is gone; person merged into an object; half a body",
    "scene_master": "set, positions, props or screen direction differ from the scene master",
}
SOFT = {
    "plastic_skin": "no pores / fine lines at full size; waxy or over-smoothed",
    "symmetry_teeth": "perfectly symmetric face, one-block white teeth",
    "dead_eyes": "fixed stare or mechanical blinking",
    "helmet_hair": "hair moves as one block, no flyaways",
    "glasses_warp": "glasses deform or melt into skin when the head turns",
    "lighting_mismatch": "face light does not match the set; ad-perfect lighting in a gritty scene",
    "oversaturated": "colour too clean / saturated for the scene",
    "sound_mismatch": "studio-dry voice outdoors, odd breaths, music when none was asked",
    "template_camera": "generic 'AI epic' camera; no handheld, no imperfection",
    "over_acting": "open-mouth screaming, grinning, gurning, mugging at camera",
    "looks_at_camera": "someone looks into the lens or laughs in danger",
}


def verdict(card):
    """card: {"hard": {key: bool flaw}, "soft": {key: bool flaw}, "scores": {"A": 1-5, "B": 1-5, "C": 1-5}}.
    -> (decision, reasons). decision in {"pass", "redo", "fix-in-post"}."""
    if not isinstance(card, dict):
        return "redo", ["review card must be an object"]
    reasons = []
    for section, keys in (("hard", HARD), ("soft", SOFT)):
        checks = card.get(section)
        if not isinstance(checks, dict):
            reasons.append(f"{section} checklist is missing")
            continue
        if set(checks) != set(keys):
            reasons.append(f"{section} checklist has missing or unknown checks")
        for key in keys:
            if type(checks.get(key)) is not bool:
                reasons.append(f"{section}.{key} has not been reviewed (true or false required)")
    sc = card.get("scores")
    if not isinstance(sc, dict):
        reasons.append("scores are missing")
        sc = {}
    for key in ("A", "B", "C"):
        value = sc.get(key)
        if type(value) not in (int, float) or not 1 <= value <= 5:
            reasons.append(f"score {key} must be a number from 1 to 5")
    if reasons:
        return "redo", reasons
    hard = [key for key in HARD if card["hard"][key]]
    soft = [key for key in SOFT if card["soft"][key]]
    if hard:
        return "redo", [f"hard: {key}" for key in hard]
    low = [key for key in ("A", "B", "C") if sc[key] < 4]
    if low:
        return "redo", [f"score {key}={sc[key]} < 4" for key in low]
    if len(soft) >= 3:
        return "fix-in-post", [f"{len(soft)} soft flaws: {', '.join(soft)} - grade/grain/trim or redo"]
    return "pass", [f"soft: {key}" for key in soft]


def blank_card(take):
    return {"take": take, "hard": {k: None for k in HARD}, "soft": {k: None for k in SOFT},
            "scores": {"A": None, "B": None, "C": None}, "notes": ""}


def media_digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def bound_card(path):
    card = blank_card(os.path.basename(path))
    card['media_sha256'] = media_digest(path)
    return card


def inspect(path, card_path):
    try:
        with open(card_path, encoding='utf-8') as f:
            card = json.load(f)
        if not isinstance(card, dict) or card.get('media_sha256') != media_digest(path):
            return 'redo', ['Review does not match the current video file']
        return verdict(card)
    except (OSError, ValueError, TypeError):
        return 'redo', ['Video or review card is missing or unreadable']


def require(path, card_path):
    decision, reasons = inspect(path, card_path)
    if decision != 'pass':
        raise ValueError('take review: ' + '; '.join(reasons))
