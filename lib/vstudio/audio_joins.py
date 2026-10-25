"""Measured edit-join evidence. Signal changes prompt review, not an audible-defect verdict."""
import math

import numpy as np

from . import audio, media


def _levels(samples):
    if not len(samples) or not np.isfinite(samples).all():
        raise ValueError('audio join: incomplete or non-finite audio')
    return 20 * np.log10(np.maximum(np.sqrt(np.mean(samples.astype(float) ** 2, axis=0)), 1e-6))


def inspect(source, segments, window=.1):
    """Compare retained sides with continuous source at both cut points, channel by channel.

    A >12 dB edit change with audible energy and >6 dB excess over both original
    boundaries needs listening. This is not a LUFS measurement, clipping detector,
    speech detector, or permission to fade a word/reaction. No media is changed.
    """
    if not math.isfinite(window) or not .02 <= window <= .5:
        raise ValueError('audio join: window must be 20–500 ms')
    if not isinstance(segments, list) or not segments or len(segments) > 100:
        raise ValueError('audio join: provide at most 100 kept ranges')
    info = media.probe(source)
    duration = info['duration']
    end = -1
    for segment in segments:
        a, b = segment.get('start'), segment.get('end')
        if (type(a) not in (int, float) or type(b) not in (int, float)
                or not math.isfinite(a + b) or not 0 <= a < b <= duration or a < end):
            raise ValueError('audio join: invalid chronological source ranges')
        end = b
    if not info['has_audio']:
        return dict(method='source-window-rms', listening_verified=False, joins=[], has_audio=False)
    joins, output_time = [], 0.0
    for left, right in zip(segments, segments[1:]):
        output_time += left['end'] - left['start']
        a, b = left['end'], right['start']
        if b - a < 1 / audio.SR:
            continue  # no actual source discontinuity
        w = min(window, left['end'] - left['start'], right['end'] - right['start'],
                duration - a, b)
        if w < .02:
            joins.append(dict(time=output_time, source_out=a, source_in=b, needs_review=True,
                              reason='Insufficient source audio around this cut'))
            continue
        def level(t):
            x = audio.decode_audio(source, sr=audio.SR, channels=2, start=t, dur=w)
            if len(x) < round(w * audio.SR) - 2:
                raise ValueError('audio join: source audio ended before the review window')
            return _levels(x)
        before, after = level(a - w), level(b)
        original_out, original_in = level(a), level(b - w)
        change = after - before
        baseline = np.maximum(np.abs(original_out - before), np.abs(after - original_in))
        flag = (np.abs(change) > 12) & (np.maximum(before, after) > -45) & (np.abs(change) - baseline > 6)
        joins.append(dict(time=round(output_time, 6), source_out=a, source_in=b, window=w,
                          before_dbfs=before.tolist(), after_dbfs=after.tolist(), change_db=change.tolist(),
                          original_out_change_db=(original_out-before).tolist(),
                          original_in_change_db=(after-original_in).tolist(), needs_review=bool(flag.any()),
                          reason='Listen for an edit-created level change' if flag.any() else None))
    return dict(method='source-window-rms', listening_verified=False, joins=joins, has_audio=True)
