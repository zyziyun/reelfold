"""Local cut-boundary evidence, with authoritative IDs rather than visual timestamps.

Near-black is a pixel observation, not a verdict on whether a pause belongs in a
story. This module never removes frames or infers that dark footage is empty.
"""
import json
import math
import os
import re
import subprocess

from PIL import Image, ImageDraw, ImageStat

from . import footage, media


def decoded_window(source, start, end):
    """Decode actual frame PTS using the same unseeked timeline as trim rendering."""
    proc = subprocess.run([media.ffmpeg_bin(), '-hide_banner', '-i', source, '-vf',
        f'trim=start={start}:end={end},scale=320:-2,showinfo', '-fps_mode', 'passthrough',
        '-frames:v', '241', '-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
        capture_output=True, timeout=180)
    if proc.returncode:
        raise ValueError('Cannot decode exact boundary frames')
    rows = re.findall(r' n:\s*\d+ pts:\s*-?\d+ pts_time:([\d.e+-]+).*? s:(\d+)x(\d+)', proc.stderr.decode(errors='replace'))
    if not rows or len(rows) > 240:
        raise ValueError('Exact boundary frame budget exceeded or empty')
    frames, offset = [], 0
    for timestamp, width, height in rows:
        w, h = int(width), int(height)
        size = w * h * 3
        raw = proc.stdout[offset:offset + size]
        if len(raw) != size:
            raise ValueError('Incomplete exact boundary decode')
        frames.append((float(timestamp), Image.frombytes('RGB', (w, h), raw)))
        offset += size
    if offset != len(proc.stdout):
        raise ValueError('Exact boundary frame metadata mismatch')
    return frames


def context(source, segments, work, radius=1.0, step=.1, precise=False):
    if not (math.isfinite(radius) and math.isfinite(step) and .02 <= step <= radius <= 2):
        raise ValueError("Invalid boundary sampling window")
    if not segments or len(segments) > 20:
        raise ValueError("Boundary review requires 1–20 source ranges")
    info = media.probe(source)
    last = max(0, float(info['duration']) - 1 / (info.get('fps') or 24))
    os.makedirs(work, exist_ok=True)
    images, records = [], []
    for index, segment in enumerate(segments):
        for edge in ('start', 'end'):
            t = segment[edge]
            if type(t) not in (int, float) or not math.isfinite(t) or not 0 <= t <= info['duration']:
                raise ValueError("Boundary outside source")
            times = sorted({round(max(0, min(last, t - radius + j * step)), 4)
                            for j in range(math.ceil(2 * radius / step) + 1)})
            if edge == 'end' and t == info['duration']:
                times.append(float(t))  # Preserve the exclusive EOF, including its last frame.
            decoded = (decoded_window(source, max(0, t - radius), min(info['duration'], t + radius))
                       if precise else [(when, footage._frame(source, min(when, last), 320)) for when in times])
            if precise and edge == 'end' and t == info['duration']:
                decoded.append((float(t), decoded[-1][1]))
            tiles = []
            for j, (when, frame) in enumerate(decoded):
                sampled = min(when, last)
                if frame is None:
                    raise ValueError("Cannot decode required boundary evidence")
                gray = frame.convert('L')
                hist = gray.histogram()
                dark = sum(hist[:17]) / (gray.width * gray.height)
                fid = f'B{index}{edge[0]}F{j:02d}'
                records.append(dict(id=fid, segment=index, edge=edge, time=when, sampled_time=sampled,
                                    mean_luma=round(ImageStat.Stat(gray).mean[0], 3),
                                    dark_fraction=round(dark, 4), near_black=dark >= .98))
                tile = Image.new('RGB', (320, frame.height + 32), 'black')
                tile.paste(frame, (0, 0))
                ImageDraw.Draw(tile).text((6, frame.height + 5), f'{fid} | {when:.3f}s', fill='white')
                tiles.append(tile)
            height = tiles[0].height
            canvas = Image.new('RGB', (320 * 4, height * math.ceil(len(tiles) / 4)), '#303030')
            for j, tile in enumerate(tiles):
                canvas.paste(tile, ((j % 4) * 320, (j // 4) * height))
            path = os.path.join(work, f'boundary-{index}-{edge}.jpg')
            canvas.save(path, quality=90)
            images.append(path)
    text = ('Boundary IDs and times below are authoritative. near_black means >=98% of thumbnail pixels '
            'have luma <=16; it does NOT mean the shot is unwanted. Do not call a near_black sample a visible '
            'actor/action frame. Select boundary IDs, never infer timestamps from grid positions. '
            'At exclusive EOF, sampled_time identifies the last preceding frame. '
            'Samples are not continuous playback; preserve intentional pauses and complete actions.\n'
            + json.dumps(records))
    return text, images, records


def resolve(choices, records, segments):
    """Resolve bounded model choices to measured times; reject invented frame claims."""
    if not isinstance(choices, list) or len(choices) != len(segments):
        raise ValueError('Boundary review must cover every segment')
    lookup = {r['id']: r for r in records}
    out = []
    for i, choice in enumerate(choices):
        if not isinstance(choice, dict):
            raise ValueError('Boundary selection must be an object')
        row = dict(segments[i])
        for edge in ('start', 'end'):
            pick = choice.get(edge, {})
            if not isinstance(pick, dict):
                raise ValueError('Boundary selection must name an evidence frame')
            if not isinstance(pick.get('id'), str):
                raise ValueError('Boundary frame ID must be a string')
            sample = lookup.get(pick.get('id'))
            if not sample or sample['segment'] != i or sample['edge'] != edge:
                raise ValueError('Boundary review selected an unrelated or unknown frame')
            if type(pick.get('near_black')) is not bool or pick['near_black'] != sample['near_black']:
                raise ValueError('Boundary review contradicts measured black-frame evidence')
            if not isinstance(pick.get('reason'), str) or not pick['reason'].strip():
                raise ValueError('Boundary selection needs a source-based reason')
            row[edge] = sample['time']
        if row['start'] >= row['end']:
            raise ValueError('Boundary review reversed a source range')
        out.append(row)
    return out
