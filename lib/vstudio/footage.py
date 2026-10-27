"""What an AI drafter needs to know about footage it cannot watch: per clip the facts (length, shape, when it was
shot, where the drone flew from its DJI log) and a contact sheet that covers the WHOLE clip (labelled tiles), so a
model that can look at images picks real windows ("the deer at 0-6 s") instead of guessing from file names.

    from vstudio import footage
    f = footage.facts("DJI_0081.MP4")       # {file, dur, w, h, orientation, recorded "2026-06-11 20:45", time_of_day,
                                            #  gps [{t, lat, lon, alt}], city {en, zh}} (gps only from a DJI .SRT)
    footage.sheet("DJI_0081.MP4", "work/draft_sheets/0081.jpg")   # -> path (cached by the clip's size + mtime)
    text, images, facts = footage.context(["a.MP4", "b.MP4"], "work/draft_sheets", ids=["a", "b"])

``context`` uses ``vstudio.shots`` for the sheets: one tile per shot / moment (its best second, labelled with the
moment's span, best window and a quality score) and a facts line listing the moments, so the planner starts windows
inside a moment's best range instead of at a clip's first seconds. ``shots=False`` (or a failed analysis) falls back
to the fixed-interval ``sheet``.

Coordinates are for the model's eyes only (to tell which pier or which hillside a clip shows): drafters tell it never
to write them into on-screen text or post copy.
"""
import hashlib
import json
import math
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv", ".webm")
_STAMP = re.compile(r"(20\d\d-\d\d-\d\d) (\d\d:\d\d:\d\d)")
_NAME_TS = re.compile(r"(20\d\d)(\d\d)(\d\d)_?(\d\d)(\d\d)(\d\d)")
_TC = re.compile(r"(\d\d):(\d\d):(\d\d)[,.](\d{3}) -->")
_LAT = re.compile(r"\[latitude\s*:\s*(-?\d+(?:\.\d+)?)\]")
_LON = re.compile(r"\[lon(?:gi|gt)?tude\s*:\s*(-?\d+(?:\.\d+)?)\]")
_ALT = re.compile(r"rel_alt\s*:\s*(-?\d+(?:\.\d+)?)")
MAX_SRT = 16 * 1024 * 1024
# appended to a planner's footage header (vlog, photo story, generic drafts)
MOMENTS_NOTE = ("Each sheet has one tile per shot / moment (vstudio.shots): its id (S2 = shot 2, S2.3 = its third "
                "moment), the second shown, its span, its best window and a quality score 0-1 (sharp, steady, well "
                "exposed); the facts line lists them too. Start a window inside a moment's best window unless the "
                "story needs another second, and never run a window across a shot cut or onto a flash frame.")


def is_video(path):
    return isinstance(path, str) and path.lower().endswith(VIDEO_EXT) and os.path.isfile(path)


def _time_of_day(hhmm):
    try:
        h = int(hhmm[:2])
    except (TypeError, ValueError):
        return None
    return ("night" if h < 5 else "early morning" if h < 8 else "morning" if h < 12 else "afternoon" if h < 17
            else "evening" if h < 21 else "night")


def _srt_track(srt, n=5):
    """A DJI log -> (first wall-clock stamp, [{t, lat, lon, alt}] at ``n`` evenly spaced moments)."""
    try:
        with open(srt, encoding="utf-8", errors="replace") as f:
            txt = f.read(MAX_SRT)
    except OSError:
        return None, []
    blocks = txt.split("\n\n")
    first = _STAMP.search(txt)
    stamp = f"{first.group(1)} {first.group(2)[:5]}" if first else None
    pts = []
    for b in blocks:
        tc, la, lo = _TC.search(b), _LAT.search(b), _LON.search(b)
        if not (tc and la and lo):
            continue
        t = int(tc.group(1)) * 3600 + int(tc.group(2)) * 60 + int(tc.group(3)) + int(tc.group(4)) / 1000
        al = _ALT.search(b)
        lat, lon = float(la.group(1)), float(lo.group(1))
        if abs(lat) > 1e-6 or abs(lon) > 1e-6:
            pts.append(dict(t=round(t, 1), lat=round(lat, 5), lon=round(lon, 5),
                            alt=round(float(al.group(1)), 1) if al else None))
    if len(pts) > n:
        pts = [pts[round(k * (len(pts) - 1) / (n - 1))] for k in range(n)]
    return stamp, pts


def facts(path):
    """One clip -> its facts (module doc). Never raises for a missing log: gps is then []."""
    from . import media, places
    info = media.probe(path)
    w, h = (info["h"], info["w"]) if abs(info.get("rotation") or 0) % 180 == 90 else (info["w"], info["h"])
    out = dict(file=os.path.basename(path), dur=round(float(info["duration"] or 0), 1), w=w, h=h,
               orientation="vertical" if h > w else "horizontal", fps=round(info.get("fps") or 0, 2))
    srt = places.srt_for(path)
    stamp, pts = _srt_track(srt) if srt else (None, [])
    if not stamp:
        m = _NAME_TS.search(os.path.basename(path))
        if m:
            y, mo, d, hh, mi, _s = m.groups()
            stamp = f"{y}-{mo}-{d} {hh}:{mi}"
    if stamp:
        out["recorded"] = stamp
        out["time_of_day"] = _time_of_day(stamp[11:16])
    if pts:
        out["gps"] = pts
        mid = pts[len(pts) // 2]
        c = places.nearest(mid["lat"], mid["lon"])
        if c:
            out["city"] = dict(en=c["en"], zh=c["zh"])
        alts = [p["alt"] for p in pts if p.get("alt") is not None]
        if alts:
            out["max_alt_m"] = max(alts)
    return out


def _frame(src, t, width):
    from . import media
    ff = media.ffmpeg_bin() if hasattr(media, "ffmpeg_bin") else "ffmpeg"
    # Do not round a final-frame PTS forward past the last decodable frame.
    seek = math.floor(t * 1_000_000) / 1_000_000
    try:
        r = subprocess.run([ff, "-v", "error", "-ss", f"{seek:.6f}", "-i", src, "-frames:v", "1", "-vf",
                            f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                           capture_output=True, timeout=90)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if not r.stdout:
        return None
    import io
    from PIL import Image
    try:
        return Image.open(io.BytesIO(r.stdout)).convert("RGB")
    except Exception:  # noqa: BLE001
        return None


def tiles_for(dur, every=6.0, lo=6, hi=20):
    """How many tiles cover a clip of ``dur`` s (one every ``every`` s, at least ``lo``, at most ``hi``) and when."""
    n = int(max(lo, min(hi, round(dur / every))))
    step = dur / n if n else dur
    return [round(step * (k + 0.5), 1) for k in range(n)]


def sheet(src, out, thumb_w=320, cols=5, every=6.0, times=None):
    """A contact sheet that covers the whole clip (fast seeks, one frame per tile, each labelled with its time)."""
    from PIL import Image, ImageDraw, ImageFont
    st = os.stat(src)
    key = hashlib.sha1(json.dumps([os.path.abspath(src), st.st_size, int(st.st_mtime), thumb_w, cols, every, times]).encode()
                       ).hexdigest()[:12]
    side = out + ".key"
    if os.path.exists(out) and os.path.exists(side) and open(side).read().strip() == key:
        return out
    from . import media
    dur = float(media.probe(src)["duration"] or 0)
    ts = tiles_for(dur, every) if times is None else times
    with ThreadPoolExecutor(max_workers=4) as ex:
        frames = list(ex.map(lambda t: (t, _frame(src, t, thumb_w)), ts))
    if times is not None and any(im is None for _, im in frames):
        raise RuntimeError("A requested sequence frame could not be decoded")
    frames = [(t, im) for t, im in frames if im is not None]
    if not frames:
        raise RuntimeError(f"no frames from {os.path.basename(src)}")
    tw, th = frames[0][1].size
    lab = 24
    rows = (len(frames) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tw, rows * (th + lab)), "black")
    d = ImageDraw.Draw(canvas)
    try:
        from .config import font
        fnt = ImageFont.truetype(font("mono-bold"), 17)
    except Exception:  # noqa: BLE001
        fnt = ImageFont.load_default()
    for k, (t, im) in enumerate(frames):
        x, y = (k % cols) * tw, (k // cols) * (th + lab)
        canvas.paste(im.resize((tw, th)), (x, y))
        d.text((x + 6, y + th + 3), f"{t:.1f}s", fill="white", font=fnt)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    canvas.save(out, quality=82)
    with open(side, "w") as f:
        f.write(key)
    return out


def line(fid, f):
    """One clip's facts as a line the model reads."""
    bits = [f"{fid}: {f['file']}", f"{f['dur']} s", f"{f['w']}x{f['h']} {f['orientation']}"]
    if f.get("recorded"):
        bits.append(f"shot {f['recorded']} ({f.get('time_of_day')})")
    if f.get("city"):
        bits.append(f"near {f['city']['en']}")
    if f.get("gps"):
        g = f["gps"]
        bits.append("drone track " + " -> ".join(f"t={p['t']}s {p['lat']},{p['lon']}" +
                                                 (f" alt {p['alt']} m" if p.get("alt") is not None else "")
                                                 for p in (g[0], g[len(g) // 2], g[-1])))
    return "; ".join(bits)


def sequence_context(source, sheet_dir, every=.5, max_frames=240, fid="source"):
    """Bounded, paginated temporal evidence; report the actual gap, never imply playback."""
    if not math.isfinite(every) or every <= 0 or max_frames < 2:
        raise ValueError("Invalid sequence sampling budget")
    f = facts(source)
    duration = float(f["dur"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Sequence source has no usable duration")
    # Avoid seeking past the last frame. Keep both the opening and the ending.
    end = max(0, duration - .1)
    count = min(max_frames, max(2, math.ceil(end / every) + 1))
    gap = end / (count - 1)
    times = [round(i * gap, 4) for i in range(count)]
    images = [sheet(source, os.path.join(sheet_dir, f"sequence-{i // 20:03d}.jpg"),
                    times=times[i:i + 20]) for i in range(0, count, 20)]
    text = (line(fid, f) + f"; {count} sampled frames across {len(images)} ordered sheets; "
            f"actual sampling gap {gap:.3f}s. These are still samples, not continuous playback. "
            "Fast actions between samples may be invisible. Preserve uncertain action boundaries; "
            "do not claim frame-accurate verification from these sheets.")
    return text, images, [dict(f, sample_times=times, sampling_gap=gap)]


def context(paths, sheet_dir, ids=None, max_clips=24, echo=None, shots=True, every=6.0, temporal=False):
    """Clips -> (text: one facts line per clip, images: one contact sheet per clip, [facts]). Sheets that fail are
    left out (the facts line stays). With ``shots`` each facts dict also carries ``moments`` (vstudio.shots).
    ``every`` controls periodic sampling when shot sheets are disabled (or unavailable); tiles remain capped at 20."""
    vids = [p for p in paths if is_video(p)][:max_clips]
    ids = list(ids or [os.path.splitext(os.path.basename(p))[0] for p in vids])
    lines, images, all_facts = [], [], []

    def one(k):
        p = vids[k]
        try:
            f = facts(p)
        except Exception as e:  # noqa: BLE001
            return k, None, None, str(e)
        img = os.path.join(sheet_dir, f"{ids[k]}.jpg")
        if shots:
            try:
                from . import shots as S
                a = S.analyze(p, echo=echo)
                f = dict(f, moments=[dict(id=m["id"], start=m["start"], end=m["end"], best=m["best"],
                                          score=m["score"]) for m in S.moments(a)],
                         shots_line=S.line(a), flashes=a.get("flashes") or [])
                return k, f, S.sheet(p, img, a), None
            except Exception as e:  # noqa: BLE001 - the whole-clip sheet below
                if echo:
                    echo(f"footage: shots of {os.path.basename(p)} failed ({e}); whole-clip sheet")
        try:
            img = sheet(p, img, every=every)
        except Exception as e:  # noqa: BLE001
            return k, f, None, str(e)
        return k, f, img, None
    with ThreadPoolExecutor(max_workers=3) as ex:
        res = sorted(ex.map(one, range(len(vids))), key=lambda r: r[0])
    for k, f, img, err in res:
        if f is None:
            if echo:
                echo(f"footage: {os.path.basename(vids[k])}: {err}")
            continue
        all_facts.append(dict(f, id=ids[k], path=vids[k]))
        lines.append(line(ids[k], f) + (f"; {f['shots_line']}" if f.get("shots_line") else "")
                     + (f"; contact sheet: {os.path.basename(img)}" if img else ""))
        if img:
            images.append(img)
    if temporal and all_facts:
        if len(all_facts) > 120:
            raise ValueError("Temporal evidence needs at least two frames per clip within its 240-frame budget")
        # Bound the whole request, not just each source. Long/many clips get a
        # coarser reported gap; a quality-ranked still never proves an action.
        budget = max(2, min(80, 240 // len(all_facts)))
        for index, f in enumerate(all_facts):
            note, ordered, sampled = sequence_context(f["path"],
                os.path.join(sheet_dir, f"temporal-{index:03d}"), max_frames=budget, fid=f["id"])
            lines.append(note + "; ordered sheets: " + ", ".join(ordered))
            images.extend(ordered)
            f.update(sample_times=sampled[0]["sample_times"], sampling_gap=sampled[0]["sampling_gap"])
    return "\n".join(lines), images, all_facts
