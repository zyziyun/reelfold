"""Source-bound edits of filmed performances, including silent physical comedy.

No ASR, speed-up, filler removal or generated insert is a prerequisite. Protected
story beats must survive the cut; this is editing, not merely repackaging a file.
"""
import json
import math
import os

from vstudio import media

ROLES = ("setup", "development", "payoff", "reaction")
SCHEMA = {"type": "object", "required": ["title", "summary", "segments", "beats"], "properties": {
    "title": {"type": "string"}, "summary": {"type": "string"},
    "segments": {"type": "array", "items": {"type": "object", "required": ["start", "end", "reason"],
        "properties": {"start": {"type": "number"}, "end": {"type": "number"}, "reason": {"type": "string"}}}},
    "beats": {"type": "array", "items": {"type": "object", "required": ["start", "end", "role", "evidence"],
        "properties": {"start": {"type": "number"}, "end": {"type": "number"},
                       "role": {"enum": list(ROLES)}, "evidence": {"type": "string"}}}}}}


def _range(row, duration):
    if not isinstance(row, dict):
        raise ValueError("performance edit: a range must be an object")
    a, b = row.get("start"), row.get("end")
    if (type(a) not in (int, float) or type(b) not in (int, float) or not math.isfinite(a + b)
            or not 0 <= a < b <= duration):
        raise ValueError("performance edit: invalid or out-of-source range")
    return float(a), float(b)


def validate(doc, duration):
    if not isinstance(doc, dict) or not isinstance(doc.get("segments"), list) or not doc["segments"]:
        raise ValueError("performance edit: no kept segments")
    if not isinstance(doc.get("title"), str) or not doc["title"].strip():
        raise ValueError("performance edit: no title")
    if not isinstance(doc.get("summary"), str) or not doc["summary"].strip():
        raise ValueError("performance edit: no summary")
    end = -1.0
    for segment in doc["segments"]:
        a, b = _range(segment, duration)
        if a < end or b - a < .1:
            raise ValueError("performance edit: segments overlap, reorder the performance or are too short")
        if not isinstance(segment.get("reason"), str) or not segment["reason"].strip():
            raise ValueError("performance edit: a cut needs a reason")
        end = b
    beats = doc.get("beats")
    if not isinstance(beats, list) or not beats:
        raise ValueError("performance edit: no source-grounded story beats")
    roles = set()
    for beat in beats:
        a, b = _range(beat, duration)
        if beat.get("role") not in ROLES or not isinstance(beat.get("evidence"), str) or not beat["evidence"].strip():
            raise ValueError("performance edit: each beat needs a role and visible/spoken source evidence")
        if not any(s["start"] <= a and s["end"] >= b for s in doc["segments"]):
            raise ValueError("performance edit: a protected action, punchline or reaction was cut")
        roles.add(beat["role"])
    if not {"setup", "payoff"}.issubset(roles):
        raise ValueError("performance edit: the source plan lacks a setup or payoff; review the source story")
    return doc


def plan(source, request, work, speech=False, complete=None):
    from vstudio import footage, llm
    os.makedirs(work, exist_ok=True)
    text, images, facts = footage.sequence_context(source, os.path.join(work, "sheets"))
    if not images:
        raise ValueError("performance edit: source frames are unavailable; cannot verify the performance")
    info = media.probe(source)
    transcript = ""
    dialogue = []
    if speech and info["has_audio"]:
        from vstudio import asr
        heard = asr.transcribe(source, cache=False, language="auto")
        dialogue = [{k: s[k] for k in ("start", "end", "text")} for s in heard.get("segments", [])]
        transcript = "\n".join(f"{s['start']:.3f}–{s['end']:.3f} {s['text']}" for s in dialogue)
    system = ("Edit a filmed comedy performance from its real source. Inspect all supplied contact sheets and "
        "the transcript when provided. Preserve the causal setup, development, payoff, surprise and reaction "
        "pauses; pauses are not automatically dead air. Identify protected source ranges for the actual story "
        "beats, with visible or spoken evidence. Choose chronological kept source ranges with reasons. "
        "Keep full actions and natural dialogue boundaries. Do not cut just to hit a duration, reorder events, "
        "accelerate, loop, fabricate dialogue or replace acting with explanatory cards. A contiguous range is "
        "valid when interruption would damage the gag. Request context is not evidence of what happens. "
        "Source times are in seconds, within the listed source duration. No file paths, code or generated assets. "
        "Return JSON with title, summary, segments:[{start,end,reason}], "
        "beats:[{start,end,role:setup|development|payoff|reaction,evidence}]. "
        "Every protected beat must be completely inside one kept range. Use the creator's request language.")
    prompt = f"REQUEST:\n{request}\nSOURCE:\n{text}\nTRANSCRIPT (empty means unavailable, not invented speech):\n{transcript}"
    call = complete or llm.complete
    repairs = []
    for attempt in range(2):
        result = call("segment_plan", system, prompt, schema=SCHEMA, images=images, max_tokens=5000)
        doc = result.get("json")
        try:
            validate(doc, info["duration"])
        except ValueError as e:
            if attempt:
                raise ValueError(f"performance edit: still invalid after one repair: {e}") from e
            repairs.append(str(e))
            prompt += "\nPREVIOUS PLAN:\n" + json.dumps(doc, ensure_ascii=False) + "\nVALIDATION ERROR: " + str(e)
            continue
        doc.update(provider=result.get("provider"), model=result.get("model"), repairs=repairs,
                   source_duration=info["duration"], source_has_audio=info["has_audio"], speed=1.0,
                   source_dialogue=dialogue)
        return review_boundaries(source, doc, work, call)


def render(source, doc, destination, preset="medium"):
    info = media.probe(source)
    validate(doc, info["duration"])
    has_audio = info["has_audio"]
    graph, labels = [], []
    colour = media.hdr_to_sdr_args(source, info.get("transfer"))
    colour = (colour + "," if colour else "") + "scale=out_color_matrix=bt709:out_range=tv"
    for i, s in enumerate(doc["segments"]):
        a, b = s["start"], s["end"]
        graph.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,{colour}[v{i}]")
        labels.append(f"[v{i}]")
        if has_audio:
            graph.append(f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]")
            labels.append(f"[a{i}]")
    graph.append("".join(labels) + f"concat=n={len(doc['segments'])}:v=1:a={int(has_audio)}[v]" + ("[a]" if has_audio else ""))
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", source, *media.filter_complex_args(";".join(graph)), "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "[a]"]
    cmd += media.delivery_args(preset=preset, audio=has_audio, encoder="libx264") + [destination]
    media.run(cmd)
    output = media.probe(destination)
    expected = sum(s["end"] - s["start"] for s in doc["segments"])
    if abs(output["duration"] - expected) > max(.15, 2 / (info["fps"] or 24)):
        raise ValueError("performance edit: output timing does not match the protected edit list")
    if (output["display_w"], output["display_h"]) != (info["display_w"], info["display_h"]):
        raise ValueError("performance edit: original frame geometry was changed")
    if has_audio and not output["has_audio"]:
        raise ValueError("performance edit: the original performance audio is missing")
    return dict(master=destination, duration=output["duration"], files=[destination],
                source_has_audio=has_audio, source_geometry=[info["display_w"], info["display_h"]])


def review_boundaries(source, doc, work, complete, precise=False):
    """Refine sampled cuts using measured IDs, without rewriting the performance."""
    from . import boundaries
    text, images, records = boundaries.context(source, doc['segments'], os.path.join(work, 'boundaries'),
        radius=.15 if precise else 1.0, precise=precise)
    pick = {'type': 'object', 'required': ['id', 'near_black', 'reason'], 'properties': {
        'id': {'type': 'string'}, 'near_black': {'type': 'boolean'}, 'reason': {'type': 'string'}}}
    schema = {'type': 'object', 'required': ['choices', 'beats'], 'properties': {
        'choices': {'type': 'array', 'items': {'type': 'object', 'required': ['start', 'end'],
                    'properties': {'start': pick, 'end': pick}}}, 'beats': SCHEMA['properties']['beats']}}
    system = ('Review only the proposed source cut boundaries using measured frame IDs. '
        'Return one start/end choice per segment, in order, with id, measured near_black and reason. '
        'Use the supplied IDs, not estimated timestamps. Exclude unwanted credit fragments while preserving '
        'complete actions, reactions and intentional pauses. Near-black is not automatically unwanted. '
        'A start is inclusive; an end excludes the selected frame and everything after it. '
        'Do not claim visible action in a measured near-black sample. Keep all protected beats and roles in '
        'their original order. You may correct a beat endpoint only within 1 second of a proposed cut, '
        'with evidence; keep every other endpoint unchanged. Return choices and the complete beats list. '
        'Nearby dialogue is source ASR evidence, with approximate phrase times. Preserve complete spoken '
        'phrases and intentional interruptions; do not move a cut into a phrase based only on a still. '
        'ASR can be wrong: it is not word-accurate timing or proof of listening. '
        'This is visual sampling, not verification of audio continuity or continuous playback.')
    # Keep the same source speech through both review passes, but only show nearby phrases.
    edges = [s[e] for s in doc['segments'] for e in ('start', 'end')]
    nearby = [s for s in doc.get('source_dialogue', [])
              if any(s['start'] <= t + 1 and s['end'] >= t - 1 for t in edges)]
    review_doc = {k: v for k, v in doc.items() if k != 'source_dialogue'}
    prompt = (json.dumps(review_doc, ensure_ascii=False) + '\n' + text
              + '\nNEARBY SOURCE DIALOGUE (empty means unavailable):\n'
              + json.dumps(nearby, ensure_ascii=False))
    errors = []
    for attempt in range(2):
        result = complete('segment_plan', system, prompt, schema=schema, images=images, max_tokens=6000)
        answer = result.get('json')
        try:
            if not isinstance(answer, dict):
                raise ValueError('Missing boundary review')
            segments = boundaries.resolve(answer.get('choices'), records, doc['segments'])
            beats = answer.get('beats')
            if not isinstance(beats, list) or len(beats) != len(doc['beats']):
                raise ValueError('Boundary review cannot remove protected story beats')
            edges = [s[e] for s in doc['segments'] for e in ('start', 'end')]
            for old, new in zip(doc['beats'], beats):
                if not isinstance(new, dict) or new.get('role') != old['role']:
                    raise ValueError('Boundary review changed a protected beat role')
                for edge in ('start', 'end'):
                    value = new.get(edge)
                    if type(value) not in (int, float) or not math.isfinite(value):
                        raise ValueError('Invalid protected beat time')
                    if value != old[edge] and (abs(value - old[edge]) > 1 or
                            not any(abs(old[edge] - t) <= 1 and abs(value - t) <= 1 for t in edges)):
                        raise ValueError('Boundary review changed an internal story beat')
            refined = dict(doc, segments=segments, beats=beats)
            validate(refined, doc['source_duration'])
            refined['boundary_review'] = dict(choices=answer['choices'], repairs=errors,
                provider=result.get('provider'), model=result.get('model'), evidence=records)
            break
        except ValueError as error:
            if attempt:
                raise ValueError(f'performance boundary review still invalid: {error}') from error
            errors.append(str(error))
            prompt += '\nPREVIOUS REVIEW:\n' + json.dumps(answer) + '\nVALIDATION ERROR: ' + str(error)
    if not precise:
        return review_boundaries(source, refined, os.path.join(work, 'exact'), complete, precise=True)
    refined['boundary_review']['frame_pts'] = True
    return refined
