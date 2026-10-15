"""Learning commentary: source register, source-grounded montage draft, export and review."""
import json
import os

from vstudio import learning as L
from vstudio.batch.util import read_json, write_json


def prepare(env):
    sources = L.catalog(env.params.get('_inputs') or {})
    path = env.item_path('work', 'sources.json')
    write_json(path, sources)
    return dict(sources=sources, files=[path])


def script(env):
    path = env.item_path('SCRIPT.md')
    if not os.path.isfile(path):
        raise ValueError('Prepare your learning outline before recording')
    return dict(script=path, files=[path])


def draft_outline(ctx, cp, path, template=None, instruction=None, complete=None):
    from .. import drafts as DR
    sources = L.catalog(ctx.inputs)
    transcript = []
    if sources:
        from vstudio import asr
        for sid, row in sources.items():
            if row['role'] == 'reference' and row['has_audio']:
                got = asr.transcribe(row['path'], cache=False, language='auto')
                transcript.append(dict(source=sid, segments=got.get('segments', [])))
    brief = ctx.inputs.get('brief') or ''
    guidance = ('This is video CREATION before editing. Develop a focused learning question, source evidence, '
        "the creator's interpretation, optional real experience and an application. Use only supplied personal "
        'facts for first-person experiences. Missing experience becomes an OPEN QUESTION, never a fabricated '
        'anecdote. A URL alone is not watched source evidence: do not invent its contents or timestamps. '
        'Do not reproduce a whole source. Suggest what to look for when local evidence is absent. '
        'Write Markdown sections: ## QUESTION, ## SOURCE, ## MY PERSPECTIVE, ## OPEN QUESTIONS, ## RECORD. '
        'RECORD contains ONLY camera-ready spoken commentary grounded in supplied thoughts, without source '
        'quotes, stage directions, placeholders, invented personal facts or claims of having tried something. '
        'Keep source playback instructions and excerpt citations in SOURCE, outside RECORD. '
        'If there is insufficient perspective to write authentic commentary, leave RECORD empty and ask focused '
        'questions in OPEN QUESTIONS. User notes: ' + str(brief) + '\nActual source evidence: ' +
        json.dumps(transcript, ensure_ascii=False))
    return DR.generic(ctx, cp, path, instruction=guidance + ('\n' + instruction if instruction else ''), complete=complete)


def draft_montage(ctx, cp, path, template=None, instruction=None, complete=None):
    """No substitute personal testimony: without the creator's takes, prepare a recording brief and wait."""
    from .. import drafts as DR
    sources = L.catalog(ctx.inputs)
    if not any(s['role'] == 'commentary' and s['has_audio'] for s in sources.values()):
        brief = ctx.item_path('RECORDING.md')
        with open(brief, 'w', encoding='utf-8') as f:
            f.write('# ' + {'en': 'Your learning commentary', 'zh': '你的学习分享', 'fr': 'Votre commentaire'}.get(ctx.lang(), 'Your learning commentary') + '\n\n')
            f.write(ctx.request() + '\n\n')
            f.write({'en': 'Choose a source passage. What did you learn? What do you agree or disagree with? '
                'Add one real experience and an action to try. Record these thoughts and attach the take; '
                'the original clip is not your personal testimony.',
                'zh': '选一段原片或书页：你学到了什么？认同或不认同哪里？补充一个真实经历，以及准备尝试的行动。'
                '录下这些想法后，把口播添加到项目；原片不会被当成你的经历。',
                'fr': 'Choisissez un passage. Que retenez-vous ? Ajoutez une expérience réelle et une action à essayer. '
                'Enregistrez votre commentaire et ajoutez la prise au projet.'}.get(ctx.lang(), 'Record your commentary.'))
        raise ValueError({'zh': '请先录制并添加自己的口播；讲解提示已写入 RECORDING.md',
                          'fr': 'Ajoutez votre prise de commentaire ; les pistes sont dans RECORDING.md.'}.get(
                              ctx.lang(), 'Add your commentary recording first; prompts are in RECORDING.md.'))
    # Transcripts ground both excerpt selection and the creator's actual opinions. No guessed speech from thumbnails.
    from vstudio import asr, llm
    evidence = []
    for ident, s in sources.items():
        if not s['image'] and s['has_audio']:
            heard = asr.transcribe(s['path'], cache=False, language='auto')
            evidence.append(dict(source=ident, role=s['role'], segments=heard.get('segments', [])))
    notes = []
    given_notes = ctx.inputs.get('notes') or []
    for p in given_notes if isinstance(given_notes, list) else [given_notes]:
        with open(p, encoding='utf-8') as f:
            notes.append(f.read(40000))
    public_sources = {k: {a: b for a, b in v.items() if a != 'path'} for k, v in sources.items()}
    prompt = json.dumps(dict(request=ctx.request(), instruction=instruction,
        sources=public_sources, transcripts=evidence, notes=notes, brief=ctx.inputs.get('brief')), ensure_ascii=False)
    system = ('Plan a learn-and-share video: source excerpt, then the creator\'s own explanation/experience, '
        'repeat as needed and finish with their application. Use only the source IDs and actual transcript times. '
        'Never invent personal experiences, quotes, page numbers, URLs or credentials. Reference sources must '
        'have citation {title,creator,locator} grounded in supplied notes/request; missing provenance means ask '
        'for it, not guessing. Book pages need voice: a commentary audio/video ID and voice_start; start=0 and '
        'end=hold duration. A commentary video uses its own sound. Keep quotations contextual and original speed, '
        'one audible speaker at a time. Do not rewrite speech or add TTS. Return JSON {title,segments: '
        '[{source,start,end,point,citation? ,voice?,voice_start?}]}. point explains why it is kept, in the request language.')
    call = complete or llm.complete
    for attempt in range(2):
        r = call('segment_plan', system, prompt, schema=True, max_tokens=6500)
        doc = r.get('json')
        try:
            L.validate(doc, sources)
        except ValueError as e:
            if attempt:
                raise ValueError(f'Learning commentary needs source/take details: {e}') from e
            prompt += '\nPrevious plan: ' + json.dumps(doc, ensure_ascii=False) + '\nRepair: ' + str(e)
            continue
        write_json(path, doc)
        return dict(by='ai', provider=r.get('provider'), model=r.get('model'), review=_review(doc))


def _review(doc):
    return dict(kind='outline', summary=dict(code='draft.generic', params=dict(text=doc['title'])),
        lines=[dict(code='draft.line', params=dict(label=f"{s['point']} · {s['start']:.1f}–{s['end']:.1f}s"))
               for s in doc['segments']])


def review_montage(ctx, cp, path, side=None):
    return _review(read_json(path, {}))


def format_ok(path):
    try:
        sources = read_json(os.path.join(os.path.dirname(path), 'sources.json'), {})
        L.validate(read_json(path, {}), sources)
        return True
    except (ValueError, TypeError, KeyError):
        return False


def compose(env):
    sources = L.catalog(env.params.get('_inputs') or {})
    doc = read_json(env.item_path('work', 'montage.json'), {})
    out = L.render(doc, sources, env.item_path('work', 'master.mp4'),
                   width=env.params.get('width', 1280), height=env.params.get('height', 720),
                   preset=env.params.get('preset', 'medium'))
    out.update(title=doc['title'], body=L.citations(doc))
    write_json(env.item_path('work', 'timeline.json'), out['timeline'])
    return out


# Shared native-canvas export and quality gates; source attribution becomes each platform's post copy.
from .performance import export, qc  # noqa: E402,F401
