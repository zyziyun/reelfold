"""Local cut-boundary evidence, with authoritative IDs rather than visual timestamps.

Near-black is a pixel observation, not a verdict on whether a pause belongs in a
story. This module never removes frames or infers that dark footage is empty.
"""
import json
import math
import os

from PIL import Image, ImageDraw, ImageStat

from . import footage, media


def context(source, segments, work, radius=1.0, step=.1):
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
            tiles = []
            for j, when in enumerate(times):
                frame = footage._frame(source, when, 320)
                if frame is None:
                    raise ValueError("Cannot decode required boundary evidence")
                gray = frame.convert('L')
                hist = gray.histogram()
                dark = sum(hist[:17]) / (gray.width * gray.height)
                fid = f'B{index}{edge[0]}F{j:02d}'
                records.append(dict(id=fid, segment=index, edge=edge, time=when,
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
