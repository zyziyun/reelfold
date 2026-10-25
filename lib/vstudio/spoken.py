"""Source-grounded visual beats for spoken clips, on the composed/edited clock.

The planner selects cue indices, never invents timestamps. Its effects are drawn by
the shared export/output-edit renderer after reframing, so cards fit every canvas.
"""
import json
import math
import re


SCHEMA = {"type": "object", "required": ["beats"], "properties": {"beats": {
    "type": "array", "items": {"type": "object", "required": ["from", "to", "kind", "title", "items", "evidence"],
    "properties": {"from": {"type": "integer"}, "to": {"type": "integer"},
                   "evidence_from": {"type": "integer"},
                   "kind": {"enum": ["contrast", "chain", "takeaway"]}, "title": {"type": "string"},
                   "items": {"type": "array", "items": {"type": "string"}},
                   "evidence": {"type": "string"}}}}}}


def _plain(text):
    return re.sub(r"[\s【】]", "", str(text or "")).lower()


def validate(doc, cues, duration):
    """Validate every proposed beat; invalid plans fail visibly, never count as applied."""
    if not isinstance(doc, dict) or not isinstance(doc.get("beats"), list):
        raise ValueError("spoken finishing: the visual plan has no beats array")
    beats = doc["beats"]
    if len(beats) > max(1, math.ceil(duration / 8)):
        raise ValueError("spoken finishing: too many visual beats for this clip")
    effects, end = [], 0.0
    for i, b in enumerate(beats):
        if not isinstance(b, dict):
            raise ValueError("spoken finishing: each beat must be an object")
        a, z = b.get("from"), b.get("to")
        if type(a) is not int or type(z) is not int or not 0 <= a <= z < len(cues):
            raise ValueError("spoken finishing: a beat names an invalid caption index")
        start = float(cues[a]["start"])
        stop = float(cues[z]["end"])
        if (not all(math.isfinite(t) for t in (start, stop)) or start < 2.5 or stop > duration
                or not 2 <= stop - start <= 5):
            raise ValueError("spoken finishing: a beat must leave the spoken opening intact and last 2–5 seconds")
        if start < end + 1.5:
            raise ValueError("spoken finishing: visual beats overlap or leave no return to the speaker")
        kind, title, items = b.get("kind"), b.get("title"), b.get("items")
        if kind not in ("contrast", "chain", "takeaway") or not isinstance(title, str) or not 1 <= len(title) <= 44:
            raise ValueError("spoken finishing: invalid visual type or heading")
        if not isinstance(items, list) or not 1 <= len(items) <= 3 or any(
                not isinstance(t, str) or not 1 <= len(t) <= 54 for t in items):
            raise ValueError("spoken finishing: a card needs 1–3 short readable statements")
        if kind == "contrast" and len(items) != 2:
            raise ValueError("spoken finishing: a contrast needs exactly two sides")
        if kind == "chain" and len(items) < 2:
            raise ValueError("spoken finishing: a chain needs at least two steps")
        # The on-screen duration is not the length of the supporting argument.
        # Permit nearby prior context, but never borrow a later conclusion.
        ea = b.get("evidence_from", a)
        if type(ea) is not int or not 0 <= ea <= a or b.get("evidence_to", z) != z:
            raise ValueError("spoken finishing: evidence must begin at or before the display and end with it")
        evidence_start = float(cues[ea]["start"])
        if not math.isfinite(evidence_start) or not 0 <= start - evidence_start <= 12:
            raise ValueError("spoken finishing: supporting context must be within 12 seconds before the display")
        excerpt = "".join(c["text"] for c in cues[ea:z + 1])
        if not isinstance(b.get("evidence"), str) or len(_plain(b["evidence"])) < 4 or _plain(b["evidence"]) not in _plain(excerpt):
            raise ValueError("spoken finishing: the evidence must quote the selected speech")
        # Summary labels may paraphrase; they must not introduce a new number.
        number = r"\d+(?:[.,]\d+)*"
        source_numbers = set(re.findall(number, excerpt))
        if any(n not in source_numbers for n in re.findall(number, title + " ".join(items))):
            raise ValueError("spoken finishing: a card introduces a number absent from its source")
        effects.append(dict(id=f"spoken-{i + 1}", effect="explanation-card", start=start, end=stop,
                            params=dict(title=title, items=items, kind=kind)))
        end = stop
    if sum(e["end"] - e["start"] for e in effects) > duration * 0.4:
        raise ValueError("spoken finishing: graphics cover too much of the speaker's story")
    return effects


def plan(cues, duration, title="", complete=None):
    from vstudio import llm
    system = (
        "You edit spoken videos: lessons, interviews, demos and personal or expert stories. "
        "Infer the purpose from the speech. Create visual explanations of its actual argument, "
        "not decoration. Preserve the speaker's meaning, qualifications and first-person perspective. "
        "Choose only moments that benefit from a contrast, causal chain or takeaway. Return beats with from/to "
        "CAPTION INDICES, kind (contrast/chain/takeaway), a short title, 1–3 short items and evidence quoted "
        "EXACTLY from those captions. If a complete idea begins before the brief display range, "
        "set optional evidence_from to its first caption (at most 12 seconds before from). "
        "Evidence ends at to: never borrow later speech to announce a conclusion early. "
        "Prior context must belong to the SAME argument, not an unrelated earlier topic. "
        "Use it to retain the subject, condition or qualification that makes the displayed idea accurate. "
        "The display still spans 2–5 seconds; supporting context does not extend the graphic. "
        "Contrast has 2 items; chain has 2–3. "
        "The renderer draws arrows between chain items: use chain ONLY for an explicitly stated cause "
        "and consequence or ordered procedural steps. A conditional, concession or hypothetical "
        "(if, even if, unless, despite) is not a causal chain. Keep that condition together with its "
        "qualified conclusion in a takeaway; do not separate it into arrow-linked items. "
        "Contrast requires two actual alternatives or differences, not two successive phrases. "
        "For example, 'Even if the network fails, the saved draft remains' is one conditional takeaway; "
        "'First save the draft, then export it' may be ordered steps. Retain the condition or limitation "
        "in the visible label, not only the evidence. No invented facts, claims, statistics, "
        "testimonials, receipts, or added call to action. Use the speech's language. Each beat starts after "
        "2.5 seconds, spans 2–5 seconds (choose suitable caption boundaries), and leaves at least 1.5 seconds "
        "of speaker between beats. Graphics occupy at most 40% of the clip; fewer well-placed beats are better "
        "than a quota. Caption boundaries may split words or sentences: read the WHOLE argument, including "
        "later qualifications or corrections, before summarizing a selected span. A personal experience is "
        "not a universal promise. These rules apply across subjects; do not impose a personal-story narrative "
        "on a lesson, interview, demo or company presentation. Preserve the opening and natural ending. "
        "Max 44 characters for titles and 54 per item; "
        "prefer much shorter phrases. [] is valid only if no visual explanation helps. JSON only."
    )
    prompt = f"TITLE (context only): {title}\nDURATION: {duration:.3f}s\nCAPTIONS:\n" + "\n".join(
        f"[{i}] {c['start']:.3f}–{c['end']:.3f} {c['text']}" for i, c in enumerate(cues))
    call = complete or llm.complete
    repairs = []
    for attempt in range(2):
        result = call("edit", system, prompt, schema=SCHEMA, max_tokens=3500)
        doc = (result or {}).get("json")
        try:
            effects = validate(doc, cues, duration)
            # Use the real typography layout before accepting a plan. A high-resolution
            # export must not hide overflow by shrinking below readable phone scale.
            from vstudio.project import outfx
            for effect in effects:
                for w, h in ((640, 360), (360, 640), (450, 600)):
                    layer = outfx.make_layer(effect, w, h, (w * .07, h * .07, w * .92, h * .9))
                    try:
                        layer.setup()
                    except ValueError as error:
                        raise ValueError(f"spoken finishing: {w}x{h} layout: {error}") from error
        except ValueError as error:
            if attempt:
                raise ValueError(f"spoken finishing: visual plan still invalid after one repair: {error}") from error
            repairs.append(str(error))
            prompt += ("\nPREVIOUS PLAN FAILED VALIDATION:\n" + json.dumps(doc, ensure_ascii=False)
                       + "\nVALIDATION ERROR: " + str(error)
                       + "\nReturn a corrected full plan using the SAME source captions. "
                         "Do not remove source evidence or invent timing to pass validation.")
            continue
        return dict(version=1, effects=effects, beats=doc["beats"], provider=(result or {}).get("provider"),
                    model=(result or {}).get("model"), duration=duration, repairs=repairs,
                    note="Conceptual summaries of the speaker's words; no generated evidence or replacement speech.")


def overlay(effects, width, height, safe):
    """Export's callback: actual timed layers, after reframe and before captions/watermark."""
    from vstudio.project import outfx
    layers = [(e["start"], e["end"], outfx.make_layer(e, width, height, safe)) for e in effects]

    def draw(_i, t, img):
        for a, b, layer in layers:
            if layer is not None and a <= t < b:
                layer.draw(img, t - a, b - a)
        return img
    return draw
