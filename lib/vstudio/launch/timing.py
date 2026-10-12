"""Speed ramps for screen recordings: real UI recordings wait (a plan being made, a render finishing). The idle
stretches play fast, the actions play at normal speed, so a 20 s take reads in 8 s without speeding up typing.

    spans = idle_spans(shot)                         # [(t0, t1)] frozen stretches (ffmpeg freezedetect), cached
    segs = segments(0.0, 18.3, spans, rate=1.0)     # [(m0, m1, rate)] covering [0, 18.3]
    segs = fit(segs, 8.0)                            # faster everywhere when the scene is shorter than the ramped take
    to_scene(segs, 13.7)                             # media second -> scene second
"""
import json
import os
import re
import subprocess

IDLE_RATE = 4.0          # how fast a frozen stretch plays
KEEP = 0.35              # of every frozen stretch, this much still plays at normal speed (the result is seen)
MIN_IDLE = 0.8           # shorter pauses are part of the action
END_HOLD = 1.8           # a take that ends frozen ends on its result: hold that much of it at normal speed
NOISE = 0.00002          # freezedetect noise: UI typing changes few pixels, so the threshold is very low


def idle_spans(shot):
    """Frozen stretches of a video shot -> [(t0, t1)]; cached next to the file (``<file>.idle.json``)."""
    f = shot["file"]
    if shot.get("kind") == "image":
        return []
    if shot.get("idle") is not None:
        return [tuple(x) for x in shot["idle"]]
    cache = (shot.get("cache") or f) + ".idle.json"
    try:
        with open(cache, encoding="utf-8") as fh:
            c = json.load(fh)
        if c.get("mtime") == os.path.getmtime(f) and c.get("noise") == NOISE:
            return [tuple(x) for x in c["spans"]]
    except (OSError, ValueError):
        pass
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", f, "-vf", f"freezedetect=n={NOISE}:d={MIN_IDLE}",
                        "-map", "0:v", "-f", "null", "-"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"freezedetect failed on {f}: {r.stderr[-400:]}")
    starts = [float(x) for x in re.findall(r"freeze_start: ([0-9.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([0-9.]+)", r.stderr)]
    dur = float(shot.get("duration") or 0)
    spans = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else dur
        if spans and s - spans[-1][1] < 0.05:                 # freezedetect splits one long freeze in two
            spans[-1] = (spans[-1][0], e)
        else:
            spans.append((s, e))
    spans = [(round(a, 3), round(b, 3)) for a, b in spans if b - a >= MIN_IDLE]
    try:
        os.makedirs(os.path.dirname(os.path.abspath(cache)), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(dict(mtime=os.path.getmtime(f), noise=NOISE, spans=spans), fh)
    except OSError:
        pass
    return spans


def segments(a, b, spans, rate=1.0, idle_rate=IDLE_RATE):
    """[a, b] media seconds -> [(m0, m1, rate)]: idle spans (minus a KEEP lead-in) at idle_rate, the rest at rate."""
    out, t = [], a
    for s0, s1 in spans:
        if s1 >= b - 0.05 and s0 < b:                       # the final state is the payoff: show it, then stop
            b = min(b, max(s0, a) + END_HOLD)
            break
        s0, s1 = max(s0 + KEEP, a), min(s1, b)
        if s1 - s0 < 0.3:
            continue
        if s0 > t:
            out.append((t, s0, rate))
        out.append((s0, s1, max(rate, idle_rate)))
        t = s1
    if b > t:
        out.append((t, b, rate))
    return [(round(m0, 3), round(m1, 3), r) for m0, m1, r in out if m1 - m0 > 1e-3]


def length(segs):
    return sum((m1 - m0) / r for m0, m1, r in segs)


def fit(segs, dur):
    """Scale rates up when the ramped take is longer than ``dur`` (never slows down). The last segment (the
    result the take ends on) keeps its speed when the rest can absorb the difference."""
    n = length(segs)
    if n <= dur or n <= 0:
        return segs
    last = (segs[-1][1] - segs[-1][0]) / segs[-1][2]
    head = n - last
    if len(segs) > 1 and head > 0 and dur - last >= 0.35 * head:
        k = head / (dur - last)
        return [(m0, m1, round(r * k, 4)) for m0, m1, r in segs[:-1]] + [segs[-1]]
    k = n / dur
    return [(m0, m1, round(r * k, 4)) for m0, m1, r in segs]


def to_scene(segs, t):
    """Media second -> scene second (clamped to the segments)."""
    acc = 0.0
    for m0, m1, r in segs:
        if t <= m1:
            return acc + max(0.0, t - m0) / r
        acc += (m1 - m0) / r
    return acc


# ------------------------------------------------------------------------------------------------ motion (clips)
# Recordings she supplies (not made by capture.mjs) carry no focus boxes. Where the screen changes between frames is
# where the action is (the click, the typed field, the list that scrolls): a cheap low-res frame difference finds it.
MOTION_FPS = 5
MOTION_SIZE = (160, 100)
MOTION_DIFF = 14              # grey-level change that counts (UI anti-aliasing / video noise stays under it)
MOTION_MIN = 0.0015           # changed fraction of the frame that counts as an action
MOTION_FULL = 0.55            # a change bigger than this is a page switch: no focus (show the whole window)


def _cache_path(shot, kind):
    return (shot.get("cache") or shot["file"]) + f".{kind}.json"


def motion(shot):
    """Activity of a video shot -> {fps, energy [changed fraction per sample], focus [{t, x, y, w, h, kind}]};
    cached (``<cache or file>.motion.json``). Focus boxes are normalised and merged over a run of active samples."""
    if shot.get("kind") == "image":
        return dict(fps=MOTION_FPS, energy=[], focus=[])
    f = shot["file"]
    cache = _cache_path(shot, "motion")
    try:
        with open(cache, encoding="utf-8") as fh:
            c = json.load(fh)
        if c.get("mtime") == os.path.getmtime(f) and c.get("v") == 1:
            return c
    except (OSError, ValueError):
        pass
    import numpy as np
    w, h = MOTION_SIZE
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-v", "error", "-i", f, "-vf",
                        f"fps={MOTION_FPS},scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"could not read the frames of {os.path.basename(f)}: "
                           f"{r.stderr.decode('utf-8', 'replace')[-300:]}")
    fr = np.frombuffer(r.stdout, dtype=np.uint8)
    n = fr.size // (w * h)
    fr = fr[: n * w * h].reshape(n, h, w).astype(np.int16)
    energy, boxes = [0.0], [None]
    for i in range(1, n):
        ch = np.abs(fr[i] - fr[i - 1]) > MOTION_DIFF
        frac = float(ch.mean())
        energy.append(round(frac, 5))
        if MOTION_MIN <= frac <= MOTION_FULL:
            ys, xs = np.nonzero(ch)
            x0, x1 = np.percentile(xs, [4, 96])
            y0, y1 = np.percentile(ys, [4, 96])
            boxes.append((x0 / w, y0 / h, (x1 + 1) / w, (y1 + 1) / h))
        else:
            boxes.append(None)
    focus, run = [], None
    for i, b in enumerate(boxes + [None]):
        if b is not None:
            run = [i, i, *b] if run is None else [run[0], i, min(run[2], b[0]), min(run[3], b[1]),
                                                     max(run[4], b[2]), max(run[5], b[3])]
            continue
        if run is not None:
            i0, _, x0, y0, x1, y1 = run
            if (x1 - x0) * (y1 - y0) <= MOTION_FULL:
                focus.append(dict(t=round(max(0.0, (i0 - 1) / MOTION_FPS), 3), x=round(x0, 4), y=round(y0, 4),
                                  w=round(x1 - x0, 4), h=round(y1 - y0, 4), kind="motion"))
            run = None
    out = dict(v=1, mtime=os.path.getmtime(f), fps=MOTION_FPS, energy=energy, focus=focus)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(cache)), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(out, fh)
    except OSError:
        pass
    return out


END_BONUS = 1.0               # a stretch that ends on the take's last frame (its result) counts this much more


def best_window(shot, dur, spans, rate=1.0, start=0.0, end=None, anchor="end"):
    """The stretch of a long take that fills a ``dur`` s scene at ``rate`` (idle stretches ramped) -> (a, b) media
    seconds: the most action, and a take she trimmed ends on its result, so a stretch that ends there is preferred
    (``anchor`` "end"); "start" = from its first frame (the opening shot lands as recorded). A take that is already
    short enough plays whole."""
    end = float(end if end is not None else shot.get("duration") or 0.0)
    if length(segments(start, end, spans, rate)) <= dur * 1.05:
        return start, end
    if anchor == "start":
        lo, hi = start + 0.5, end
        for _ in range(18):
            mid = (lo + hi) / 2
            if length(segments(start, mid, spans, rate)) < dur:
                lo = mid
            else:
                hi = mid
        return start, round(hi, 3)
    en = motion(shot).get("energy") or []
    fps = MOTION_FPS

    def act(a, b):
        return sum(en[int(a * fps): int(b * fps) + 1])
    best, cands = None, []
    a = start
    while a < end - 0.5:
        lo, hi = a + 0.5, end                                  # the shortest b whose ramped length fills the scene
        if length(segments(a, hi, spans, rate)) < dur:
            break
        for _ in range(18):
            mid = (lo + hi) / 2
            if length(segments(a, mid, spans, rate)) < dur:
                lo = mid
            else:
                hi = mid
        cands.append((act(a, hi), a, hi))
        a += 0.25
    if not cands:
        return max(start, end - dur * rate), end
    top = max(c[0] for c in cands)
    # the stretch that reaches the end (the last start that still fills the scene) gets the result bonus
    last = max(cands, key=lambda c: c[1])
    for sc, a0, b0 in cands:
        sc = sc + (END_BONUS * top if (a0, b0) == last[1:] or b0 >= end - 0.05 else 0.0) + 1e-6 * a0
        if best is None or sc > best[0]:
            best = (sc, a0, b0)
    return round(best[1], 3), round(best[2], 3)


def window(segs, a, b):
    """The part of ``segs`` that plays between scene seconds ``a`` and ``b`` -> segs (media seconds, same rates): a
    scene that continues another one (a detail cut) picks the take up where the cut left it."""
    out, acc = [], 0.0
    for m0, m1, r in segs:
        d = (m1 - m0) / r
        s0, s1 = max(a, acc), min(b, acc + d)
        if s1 > s0 + 1e-4:
            out.append((round(m0 + (s0 - acc) * r, 3), round(m0 + (s1 - acc) * r, 3), r))
        acc += d
    return out
