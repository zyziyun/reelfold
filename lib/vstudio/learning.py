"""Source excerpts interleaved with the creator's recorded commentary, with durable citations."""
import hashlib
import math
import os
import tempfile

from vstudio import media

IMAGES = {'.png', '.jpg', '.jpeg', '.webp'}


def catalog(inputs):
    """Input roles are explicit: reference footage/pages never become the creator's testimony."""
    rows = {}
    for key, role in [('references', 'reference'), ('pages', 'page'), ('takes', 'commentary')]:
        paths = inputs.get(key) or []
        for path in paths if isinstance(paths, list) else [paths]:
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                raise ValueError(f'Missing learning material: {os.path.basename(path)}')
            ident = role + '-' + hashlib.sha256(os.fsencode(path)).hexdigest()[:12]
            image = os.path.splitext(path)[1].lower() in IMAGES
            info = {} if image else media.probe(path)
            rows[ident] = dict(id=ident, path=path, role=role, image=image,
                duration=info.get('duration'), has_audio=bool(info.get('has_audio')),
                width=info.get('display_w'), height=info.get('display_h'))
    return rows


def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate(doc, sources):
    if not isinstance(doc, dict) or not isinstance(doc.get('title'), str) or not doc['title'].strip():
        raise ValueError('Give this learning video a title')
    segments = doc.get('segments')
    if not isinstance(segments, list) or not (1 if doc.get('purpose') == 'creator-workspace' else 2) <= len(segments) <= 100:
        raise ValueError('Add source excerpts and your recorded commentary')
    roles = set()
    for s in segments:
        if not isinstance(s, dict) or s.get('source') not in sources:
            raise ValueError('An excerpt uses material that was not attached to this project')
        src = sources[s['source']]
        role = src['role']; roles.add(role)
        if not isinstance(s.get('point'), str) or not s['point'].strip():
            raise ValueError('Explain the point of each excerpt or commentary take')
        a, b = s.get('start'), s.get('end')
        if not _number(a) or not _number(b) or a < 0 or b <= a:
            raise ValueError('Excerpt times must be finite seconds with end after start')
        if src['image']:
            if a != 0:
                raise ValueError('A book page hold starts at zero and follows your recorded commentary')
            voice = sources.get(s.get('voice')) or {}
            va = s.get('voice_start', 0)
            if voice.get('role') != 'commentary' or not voice.get('has_audio'):
                raise ValueError('Record your own commentary for this book page')
            if not _number(va) or va < 0 or va + b > voice['duration'] + .04:
                raise ValueError('The book page exceeds the recorded commentary')
            roles.add('commentary')
        elif b > src['duration'] + .04:
            raise ValueError('An excerpt runs past the end of its attached source')
        elif role == 'commentary' and not src['has_audio']:
            raise ValueError('Your commentary recording has no audio')
        if role in ('reference', 'page'):
            cite = s.get('citation') or {}
            if not isinstance(cite, dict) or any(not isinstance(cite.get(k), str) or not cite[k].strip()
                                               for k in ('title', 'creator', 'locator')):
                raise ValueError('Add the source title, author/speaker and URL or book edition/page')
        if role == 'commentary' and not src['width']:
            raise ValueError('An audio-only take must accompany a book page or supplied visual')
    if 'commentary' not in roles or (doc.get('purpose') != 'creator-workspace' and not roles.intersection({'reference', 'page'})):
        raise ValueError('Include both a source excerpt and your own recorded contribution')
    return doc


def citations(doc):
    rows = []
    for s in doc['segments']:
        if s.get('citation'):
            c = s['citation']
            line = f"{c['title']} — {c['creator']} · {c['locator']} · {s['start']:.2f}–{s['end']:.2f}s"
            if line not in rows:
                rows.append(line)
    return '\n'.join(rows)


def _label(segment, source, width, rail, path):
    from PIL import Image, ImageDraw
    from vstudio.draw import load_font
    chinese = any('\u4e00' <= c <= '\u9fff' for c in segment['point'])
    if source['role'] == 'commentary':
        text = '我的理解' if chinese else 'My perspective'
    else:
        c = segment['citation']
        prefix = ('原文' if chinese else 'Passage') if source['image'] else ('原片' if chinese else 'Source')
        text = f"{prefix} · {c['title']} · {c['creator']}"
    font = load_font('cjk-bold', max(12, round(rail * .38)))
    image = Image.new('RGB', (width, rail), (20, 38, 34))
    draw = ImageDraw.Draw(image)
    pad = max(8, round(width * .025))
    while text and draw.textlength(text, font=font) > width - 2*pad:
        text = text[:-2].rstrip('…') + '…'
    draw.text((pad, rail/2), text, font=font, fill=(237, 245, 240), anchor='lm')
    image.save(path)


def render(doc, sources, destination, width=1280, height=720, preset='medium'):
    """One audible speaker at a time; pages use the creator's voice, films keep original sound."""
    validate(doc, sources)
    if width % 2 or height % 2 or not (160 <= width <= 3840 and 160 <= height <= 3840):
        raise ValueError('Choose an even-sized video canvas between 160 and 3840 pixels')
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    timeline, offset = [], 0.0
    with tempfile.TemporaryDirectory(prefix='reelfold-learning-') as work:
        parts = []
        for i, s in enumerate(doc['segments']):
            src = sources[s['source']]; dur = s['end'] - s['start']
            cmd = ['ffmpeg', '-y']
            if src['image']:
                cmd += ['-loop', '1', '-i', src['path']]
                voice = sources[s['voice']]
                cmd += ['-ss', str(s.get('voice_start', 0)), '-i', voice['path']]
                audio = '1:a:0'
            else:
                cmd += ['-ss', str(s['start']), '-i', src['path']]
                audio = '0:a:0'
            if not src['image'] and not src['has_audio']:
                cmd += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
                audio = '1:a:0'
            rail = max(24, round(height * .09 / 2) * 2)
            label = os.path.join(work, f'{i:03d}-label.png')
            _label(s, src, width, rail, label)
            label_input = 2 if src['image'] or not src['has_audio'] else 1
            cmd += ['-i', label]
            colour = '' if src['image'] else media.hdr_to_sdr_args(src['path'])
            vf = (colour + ',' if colour else '') + (
                f'scale={width}:{height-rail}:force_original_aspect_ratio=decrease:force_divisible_by=2:'
                'out_color_matrix=bt709:out_range=tv,'
                f'pad={width}:{height}:(ow-iw)/2:{rail}+(oh-{rail}-ih)/2,setsar=1,fps=30,format=yuv420p')
            part = os.path.join(work, f'{i:03d}.mp4')
            cmd += ['-t', str(dur), '-map', '[v]', '-map', audio,
                    *media.filter_complex_args(f'[0:v]{vf}[picture];[picture][{label_input}:v]overlay=0:0[v]'),
                    '-af', 'aresample=48000,apad', '-ac', '2',
                    *media.delivery_args(preset=preset, audio=True, encoder='libx264'), part]
            media.run(cmd); parts.append(part)
            timeline.append(dict(start=offset, end=offset+dur, source=s['source'],
                role=src['role'], point=s['point'], citation=s.get('citation'),
                source_start=s['start'], source_end=s['end']))
            offset += dur
        listing = os.path.join(work, 'parts.txt')
        with open(listing, 'w', encoding='utf-8') as f:
            f.write('\n'.join("file '" + p.replace("'", "'\\''") + "'" for p in parts))
        media.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', listing, '-c', 'copy',
                   '-movflags', '+faststart', destination])
    info = media.probe(destination)
    if not info['has_audio'] or abs(info['duration'] - offset) > max(.2, len(parts)/30):
        raise ValueError('Learning montage timing/audio did not match the approved edit')
    return dict(master=destination, duration=info['duration'], timeline=timeline,
                source_has_audio=True, files=[destination])
