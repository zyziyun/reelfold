"""`intake goal`: one goal ("make as many videos as you can from this card, different themes") -> a SURVEY of the
footage and a plan of several videos, each one its own ordinary intake request.

    doc = make_goal("用 /Volumes/dji/DCIM 做多个视频", ["/Volumes/dji/DCIM"], platforms=["youtube", "xiaohongshu"])
    doc = edit_goal(doc, [{"op": "drop", "video": "v3"}, {"op": "rename", "video": "v1", "title": "..."}])

Survey (offline, read-only: nothing is written next to the footage - an SD card stays untouched):
  * walk the folders (symlinked files followed once; DJI ``PANORAMA/<n>`` tile folders count as one panorama each),
  * per clip its facts (``vstudio.footage.facts``: length, shape, when, the DJI ``.SRT`` flight track -> GPS and the
    nearest well-known city from ``vstudio.places``), per photo its EXIF time + GPS,
  * one small frame per clip (cached by path + size + mtime under the intake cache),
  * stories: items sorted by time, a new story after a gap of ``GAP_S`` or a move of more than ``MOVE_KM`` (both
    ends need GPS for the distance), then split where the light changes across a pause (day -> night: the mean
    brightness of the frames jumps by ``LIGHT_JUMP`` after at least ``LIGHT_GAP_S``),
  * a contact sheet per story (one tile per clip) - what the model looks at.

Plan: the routed model (task ``intake``) proposes the videos from the stories it sees: title, kind (``history`` - the
place has a story worth telling, facts must be well known and verifiable; ``film`` - it is just beautiful: music and a
few short reflective lines; ``reel`` - action, cut on the beat; ``vlog`` - a trip across stories; ``essay`` - a calm
reflective voice-over; ``photos`` - stills and panoramas), which stories, length, platforms. YouTube is always English;
Xiaohongshu / Bilibili / Douyin are Chinese. Without a model (or when it fails) a rule planner proposes one music film
per story with enough footage (``planner.fallback``). Every video carries ``request``: the sentence its own intake
plan starts from (``vstudio.intake plan --prompt <request> --inputs <clips>``), rebuilt by ``edit_goal`` whenever its
title / kind / length / stories change.
"""
import hashlib
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import inventory as I

KIND = "vstudio.intake.goal"
VERSION = 1
TASK = "intake"
GAP_S = 3 * 3600            # a pause this long starts a new story
MOVE_KM = 5.0               # ... and so does a move this far (both ends with GPS)
LIGHT_GAP_S = 15 * 60       # a light change only splits a story across a pause at least this long
LIGHT_JUMP = 0.2            # mean brightness 0..1 jumping this much = another light (golden hour -> night)
MIN_STORY_S = 12.0          # a story with less footage than this (and no photos) is left out of the rule plan
MAX_VIDEOS = 8
MAX_CLIPS = 400
MAX_PHOTOS = 800
SHEET_TILES = 15
KINDS = ("history", "film", "reel", "vlog", "essay", "photos")
CN_PLATFORMS = ("xiaohongshu", "bilibili", "douyin", "wechat-channels", "kuaishou", "weibo", "zhihu")
PLATFORM_WORD = {"youtube": "YouTube", "youtube-shorts": "YouTube Shorts", "tiktok": "TikTok",
                 "instagram": "Instagram", "facebook": "Facebook", "x": "X", "xiaohongshu": "Xiaohongshu",
                 "bilibili": "Bilibili", "douyin": "Douyin", "wechat-channels": "WeChat Channels",
                 "kuaishou": "Kuaishou", "weibo": "Weibo", "zhihu": "Zhihu"}
DEFAULT_PLATFORMS = ["youtube", "xiaohongshu", "bilibili"]
PANO_DIR = re.compile(r"^\d{3}_\d{4}$")
_NAME_TS = re.compile(r"(20\d\d)(\d\d)(\d\d)_?(\d\d)(\d\d)(\d\d)")
_TOD_ZH = {"night": "夜色", "early morning": "清晨", "morning": "上午", "afternoon": "午后", "evening": "黄昏"}
_TOD_FR = {"night": "la nuit", "early morning": "à l’aube", "morning": "le matin", "afternoon": "l’après-midi",
           "evening": "le soir"}

# --------------------------------------------------------------------------- goal-style requests
# "make several / many / as many as possible videos", "每个视频的主题可以不同", "并行做多个视频" ...
_MANY = re.compile(r"多个视频|几个视频|多条视频|多支|尽量多|尽可能多|好几个|几个类似|并行做|分别做|每个视频|多做几|"
                   r"(做|剪|出)\s*[2-9两三四五六七八九十]\s*(个|条|支)\s*(视频|片子|短片|vlog)|"
                   r"\b(several|multiple|many|a few|a bunch of|as many)\b.{0,24}\b(videos?|films?|edits?|cuts?|reels?)\b|"
                   r"\b(videos?|films?)\b.{0,30}\b(each|different) (theme|topic|story|mood)s?\b|"
                   r"\bmake\s+(\d|two|three|four|five|six|seven|eight)\s+(videos?|films?|edits?)\b|"
                   r"plusieurs vidéos|autant de vidéos", re.I)
_PATH = re.compile(r"(?<![A-Za-z0-9_./~-])(/(?:Volumes|Users|home|mnt|media|tmp|private|var)/[^\s，。,;；:：、()（）\"'“”]+)")
_NUM_WORD = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def paths_in(prompt):
    """Folders / files named in the request's words (``/Volumes/dji/DCIM``) that exist on this computer."""
    out = []
    for m in _PATH.findall(prompt or ""):
        p = m.rstrip(".,!?)）】")
        if os.path.exists(p) and p not in out:
            out.append(p)
    return out[:8]


def is_goal(prompt, inputs=()):
    """A goal-style request: several videos asked for, from footage (a folder dropped or named in the words)."""
    if not _MANY.search(prompt or ""):
        return False
    return bool(paths_in(prompt) or any(os.path.isdir(p) for p in inputs or ()) or len(inputs or ()) >= 4)


def wanted(prompt):
    """How many videos she asked for (None: as many as the footage supports, up to MAX_VIDEOS)."""
    m = re.search(r"(\d+|two|three|four|five|six|seven|eight|[两二三四五六七八九十])\s*(个|条|支|videos?|films?)",
                  prompt or "", re.I)
    if not m:
        return None
    w = m.group(1).lower()
    n = int(w) if w.isdigit() else _NUM_WORD.get(w)
    return max(1, min(MAX_VIDEOS, n)) if n else None


# --------------------------------------------------------------------------- survey
def _emit(on_event, **kw):
    if on_event:
        on_event(dict(event="stage", ts=round(time.time(), 2), **kw))


def _epoch(stamp):
    """'2026-06-11 12:26[:28]' -> epoch seconds (local wall clock; only differences matter)."""
    if not stamp:
        return None
    try:
        fmt = "%Y-%m-%d %H:%M:%S" if len(stamp) > 16 else "%Y-%m-%d %H:%M"
        return time.mktime(time.strptime(stamp[:19], fmt))
    except ValueError:
        return None


def _name_stamp(path):
    m = _NAME_TS.search(os.path.basename(path))
    if not m:
        return None
    y, mo, d, hh, mi, s = m.groups()
    return f"{y}-{mo}-{d} {hh}:{mi}:{s}"


def _km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _photo_facts(path):
    """EXIF time + GPS (full precision: the stories need it; it is never written into any text)."""
    try:
        from PIL import Image
    except ImportError:
        return {}
    out = {}
    try:
        with Image.open(path) as im:
            ex = im.getexif()
            if not ex:
                return out
            try:
                t = ex.get_ifd(0x8769).get(0x9003) or ex.get(0x0132)
            except Exception:  # noqa: BLE001
                t = ex.get(0x0132)
            if t:
                out["recorded"] = str(t).replace(":", "-", 2)[:19]
            try:
                g = ex.get_ifd(0x8825)
            except Exception:  # noqa: BLE001
                g = None
            if g and 2 in g and 4 in g:
                def deg(v):
                    return float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
                lat, lon = deg(g[2]), deg(g[4])
                if abs(lat) > 1e-6 or abs(lon) > 1e-6:
                    out["lat"] = round(-lat if g.get(1) == "S" else lat, 5)
                    out["lon"] = round(-lon if g.get(3) == "W" else lon, 5)
    except Exception:  # noqa: BLE001
        return {}
    return out


def _video_item(path):
    from vstudio import footage
    f = footage.facts(path)
    stamp = _name_stamp(path) or f.get("recorded")
    it = dict(kind="video", path=path, name=os.path.basename(path), dur=f.get("dur") or 0.0, w=f.get("w"),
              h=f.get("h"), orientation=f.get("orientation"), recorded=stamp, t=_epoch(stamp),
              time_of_day=f.get("time_of_day"))
    g = f.get("gps") or []
    if g:
        mid = g[len(g) // 2]
        it.update(lat=mid["lat"], lon=mid["lon"])
        if f.get("max_alt_m") is not None:
            it["alt_m"] = f["max_alt_m"]
    return it


def _frame_cache(path):
    st = os.stat(path)
    key = hashlib.sha1(json.dumps([os.path.abspath(path), st.st_size, int(st.st_mtime)]).encode()).hexdigest()[:16]
    d = os.path.join(I.cache_root(), "goal", "frames")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{key}.jpg")


def _frame(path, dur, width=320):
    """One small frame from 40% into the clip (cached) -> (jpg path, mean brightness 0..1) or (None, None)."""
    out = _frame_cache(path)
    if not os.path.exists(out):
        import subprocess
        from vstudio import media
        ff = media.ffmpeg_bin() if hasattr(media, "ffmpeg_bin") else "ffmpeg"
        # the keyframe nearest 40% in: a 4K HEVC clip on an SD card decodes one frame, not a whole GOP
        t = f"{max(0.0, (dur or 0) * 0.4):.2f}"
        for fast in (True, False):            # no keyframe after that point (a short clip): decode normally
            try:
                subprocess.run([ff, "-v", "error", "-y", *(["-skip_frame", "nokey"] if fast else []), "-ss", t,
                                "-i", path, "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", out],
                               capture_output=True, timeout=90)
            except (subprocess.TimeoutExpired, OSError):
                return None, None
            if os.path.exists(out) and os.path.getsize(out) > 0:
                break
        else:
            return None, None
    try:
        from PIL import Image, ImageStat
        with Image.open(out) as im:
            return out, round(ImageStat.Stat(im.convert("L")).mean[0] / 255.0, 3)
    except Exception:  # noqa: BLE001
        return out, None


class _FactsCache:
    """Photo facts by path + size + mtime (``<intake cache>/goal/photos.json``): a second survey of the same card
    reads no photo again."""

    def __init__(self):
        self.path = os.path.join(I.cache_root(), "goal", "photos.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.d = json.load(f)
        except (OSError, ValueError):
            self.d = {}
        self.dirty = False

    @staticmethod
    def _key(p):
        st = os.stat(p)
        return f"{os.path.abspath(p)}|{st.st_size}|{int(st.st_mtime)}"

    def get(self, p):
        try:
            return self.d.get(self._key(p))
        except OSError:
            return None

    def put(self, p, facts):
        try:
            self.d[self._key(p)] = facts
            self.dirty = True
        except OSError:
            pass
        return facts

    def save(self):
        if not self.dirty:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + f".{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.d, f)
        os.replace(tmp, self.path)


def scan(inputs, on_event=None, frames=True, workers=4):
    """Inputs -> {items [video / photo / panorama], notes}. Read-only; frames go to the intake cache."""
    _emit(on_event, stage="scan", inputs=len(inputs or []))
    files, notes = I.walk(inputs, max_files=MAX_CLIPS + MAX_PHOTOS + 4000)
    vids, photos, panos = [], [], {}
    for fp, _root in files:
        k = I.kind_of(fp)
        parent = os.path.dirname(fp)
        if k == "video":
            vids.append(fp)
        elif k == "image" and fp.lower().endswith((".jpg", ".jpeg", ".heic", ".dng", ".png")):
            if PANO_DIR.match(os.path.basename(parent)) and "PANORAMA" in parent.upper():
                panos.setdefault(parent, []).append(fp)
            elif not fp.lower().endswith(".dng"):
                photos.append(fp)
    if len(vids) > MAX_CLIPS:
        notes.append(f"stopped at {MAX_CLIPS} clips")
        vids = vids[:MAX_CLIPS]
    if len(photos) > MAX_PHOTOS:
        notes.append(f"stopped at {MAX_PHOTOS} photos")
        photos = photos[:MAX_PHOTOS]
    _emit(on_event, stage="scan", files=len(vids) + len(photos) + len(panos))
    items = []
    done = [0]
    n = len(vids)

    def one_video(p):
        try:
            it = _video_item(p)
        except Exception as e:  # noqa: BLE001  (an unreadable clip is a note, never the end of the survey)
            notes.append(f"unreadable clip {os.path.basename(p)} ({type(e).__name__})")
            return None
        if frames:
            it["frame"], it["light"] = _frame(p, it["dur"])
        done[0] += 1
        _emit(on_event, stage="probe", file=os.path.basename(p), i=done[0], n=n, kind="video")
        return it
    with ThreadPoolExecutor(max_workers=workers) as ex:
        items += [x for x in ex.map(one_video, vids) if x]
    cache = _FactsCache()

    def one_photo(p):
        f = cache.get(p)
        if f is None:
            f = cache.put(p, _photo_facts(p))
        stamp = f.get("recorded") or _name_stamp(p)
        return dict(kind="photo", path=p, name=os.path.basename(p), recorded=stamp, t=_epoch(stamp),
                    lat=f.get("lat"), lon=f.get("lon"))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for k, it in enumerate(ex.map(one_photo, photos)):
            items.append(it)
            if k % 25 == 0 or k == len(photos) - 1:
                _emit(on_event, stage="probe", file=it["name"], i=k + 1, n=len(photos), kind="image")
    cache.save()
    for d, tiles in sorted(panos.items()):
        tiles.sort()
        f = _photo_facts(tiles[0])
        stamp = f.get("recorded")
        items.append(dict(kind="panorama", path=d, name=os.path.basename(d), tiles=len(tiles), first=tiles[0],
                          recorded=stamp, t=_epoch(stamp), lat=f.get("lat"), lon=f.get("lon")))
    for it in items:
        it.setdefault("lat", None)
        it.setdefault("lon", None)
    return dict(items=items, notes=notes)


def _geo(c):
    pts = [(x["lat"], x["lon"]) for x in c if x.get("lat") is not None and x.get("lon") is not None]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def cluster(items):
    """Items -> stories (lists of items, in time order): time + place first, then the light."""
    timed = sorted([x for x in items if x.get("t") is not None], key=lambda x: x["t"])
    untimed = [x for x in items if x.get("t") is None]
    out, cur = [], []
    for x in timed:
        if cur:
            gap = x["t"] - cur[-1]["t"]
            here = (x["lat"], x["lon"]) if x.get("lat") is not None else None
            there = _geo(cur[-6:])
            moved = here is not None and there is not None and _km(here, there) > MOVE_KM
            if gap > GAP_S or moved or time.strftime("%Y-%m-%d", time.localtime(x["t"])) != \
                    time.strftime("%Y-%m-%d", time.localtime(cur[-1]["t"])):
                out.append(cur)
                cur = []
        cur.append(x)
    if cur:
        out.append(cur)
    split = []
    for c in out:
        part = [c[0]]
        for a, b in zip(c, c[1:]):
            la, lb = a.get("light"), b.get("light")
            if la is not None and lb is not None and b["t"] - a["t"] >= LIGHT_GAP_S and abs(la - lb) >= LIGHT_JUMP:
                split.append(part)
                part = []
            part.append(b)
        split.append(part)
    # files with no time at all: one story per folder
    by_dir = {}
    for x in untimed:
        by_dir.setdefault(os.path.dirname(x["path"]), []).append(x)
    split += [sorted(v, key=lambda x: x["name"]) for _k, v in sorted(by_dir.items())]
    return [c for c in split if c]


def _sheet(story_id, items, out_dir):
    """A contact sheet of one story: one labelled tile per clip / photo (at most SHEET_TILES)."""
    from PIL import Image, ImageDraw, ImageFont
    tiles = [x for x in items if x.get("frame") and os.path.exists(x["frame"])]
    if len(tiles) < 5:                       # a story of photos: a few of them (each a full-size read off the card)
        ph = [x for x in items if x["kind"] == "photo"]
        tiles += [ph[int(k * len(ph) / 8)] for k in range(min(8, len(ph)))] if len(ph) > 8 else ph
    if len(tiles) > SHEET_TILES:
        step = len(tiles) / SHEET_TILES
        tiles = [tiles[int(k * step)] for k in range(SHEET_TILES)]
    if not tiles:
        return None
    tw, th, lab, cols = 320, 180, 22, 5
    rows = (len(tiles) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tw, rows * (th + lab)), "black")
    d = ImageDraw.Draw(canvas)
    try:
        from vstudio.config import font
        fnt = ImageFont.truetype(font("mono-bold"), 15)
    except Exception:  # noqa: BLE001
        fnt = ImageFont.load_default()
    for k, x in enumerate(tiles):
        try:
            with Image.open(x.get("frame") or x["path"]) as im:
                im.draft("RGB", (tw * 2, th * 2))
                im = im.convert("RGB")
                im.thumbnail((tw, th))
                ox, oy = (k % cols) * tw + (tw - im.width) // 2, (k // cols) * (th + lab) + (th - im.height) // 2
                canvas.paste(im, (ox, oy))
        except Exception:  # noqa: BLE001
            continue
        stamp = (x.get("recorded") or "")[11:16]
        label = f"{os.path.splitext(x['name'])[0][-9:]} {stamp}" + (f" {x['dur']:.0f}s" if x.get("dur") else "")
        d.text(((k % cols) * tw + 6, (k // cols) * (th + lab) + th + 3), label, fill="white", font=fnt)
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f"{story_id}.jpg")
    canvas.save(p, quality=80)
    return p


def _dominant_tod(items):
    from vstudio.footage import _time_of_day
    tods = [_time_of_day((x.get("recorded") or "")[11:16]) for x in items if x.get("recorded")]
    tods = [t for t in tods if t]
    return max(set(tods), key=tods.count) if tods else None


def stories(scan_doc, sheet_dir=None):
    """The scan -> story summaries (what the plan card shows and the model reads)."""
    from vstudio import places
    out = []
    for k, c in enumerate(cluster(scan_doc["items"])):
        sid = f"s{k + 1}"
        vids = [x for x in c if x["kind"] == "video"]
        phs = [x for x in c if x["kind"] == "photo"]
        pns = [x for x in c if x["kind"] == "panorama"]
        geo = _geo(c)
        city = places.nearest(geo[0], geo[1]) if geo else None
        alts = [x["alt_m"] for x in vids if x.get("alt_m") is not None]
        stamps = sorted(x["recorded"] for x in c if x.get("recorded"))
        lights = [x["light"] for x in c if x.get("light") is not None]
        s = dict(id=sid, place=dict(en=city["en"], zh=city["zh"], km=round(city["km"], 1)) if city else None,
                 start=stamps[0] if stamps else None, end=stamps[-1] if stamps else None,
                 date=stamps[0][:10] if stamps else None, time_of_day=_dominant_tod(c),
                 videos=len(vids), photos=len(phs), panoramas=len(pns),
                 seconds=round(sum(x.get("dur") or 0 for x in vids), 1),
                 aerial=bool(alts and max(alts) > 20), vertical=sum(1 for x in vids if x.get("orientation") == "vertical"),
                 light=round(sum(lights) / len(lights), 2) if lights else None,
                 geo=[round(geo[0], 3), round(geo[1], 3)] if geo else None,
                 clips=[x["path"] for x in vids], stills=[x["path"] for x in phs],
                 panorama_dirs=[x["path"] for x in pns],
                 thumbs=([x["frame"] for x in vids if x.get("frame")] or [x["path"] for x in phs] or
                         [x["first"] for x in pns if x.get("first")])[:4],
                 folder=os.path.basename(c[0]["path"].rstrip(os.sep)) if c[0]["kind"] == "panorama" else
                 os.path.basename(os.path.dirname(c[0]["path"])),
                 short_clips=sum(1 for x in vids if (x.get("dur") or 0) < 15))
        if sheet_dir:
            try:
                s["sheet"] = _sheet(sid, c, sheet_dir)
            except Exception:  # noqa: BLE001  (no sheet: the model reads the facts line alone)
                s["sheet"] = None
        out.append(s)
    return out


def story_line(s):
    """One story as a line the model reads (coordinates for its eyes only, never for any text)."""
    bits = [f"{s['id']}: {s['videos']} clips ({s['seconds']:.0f} s)"]
    if s["photos"]:
        bits.append(f"{s['photos']} photos")
    if s["panoramas"]:
        bits.append(f"{s['panoramas']} panoramas")
    if s.get("start"):
        bits.append(f"shot {s['start']} -> {(s.get('end') or '')[11:16]} ({s.get('time_of_day') or '?'})")
    if s.get("place"):
        bits.append(f"near {s['place']['en']} ({s['place']['km']} km from its centre)")
    if s.get("geo"):
        bits.append(f"GPS {s['geo'][0]},{s['geo'][1]}")
    bits.append("aerial (drone)" if s.get("aerial") else "ground / handheld or no flight log")
    if s.get("vertical"):
        bits.append(f"{s['vertical']} vertical clips")
    if s.get("short_clips"):
        bits.append(f"{s['short_clips']} clips under 15 s")
    if s.get("light") is not None:
        bits.append(f"brightness {s['light']}")
    if s.get("sheet"):
        bits.append(f"contact sheet {os.path.basename(s['sheet'])}")
    return "; ".join(bits)


# --------------------------------------------------------------------------- the request each video starts from
def _j(xs):
    return " and ".join(xs) if len(xs) <= 2 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _langs(platforms):
    """'Chinese for Xiaohongshu and Bilibili, English for YouTube' - YouTube (every non-Chinese platform) is English."""
    zh = [PLATFORM_WORD.get(p.split(":")[0], p) for p in platforms if p.split(":")[0] in CN_PLATFORMS]
    en = [PLATFORM_WORD.get(p.split(":")[0], p) for p in platforms if p.split(":")[0] not in CN_PLATFORMS]
    if zh and en:
        return f"Chinese for {_j(zh)}, English for {_j(en)}"
    return "Chinese" if zh else "English"


def _narrate(platforms):
    zh = [PLATFORM_WORD.get(p.split(":")[0], p) for p in platforms if p.split(":")[0] in CN_PLATFORMS]
    en = [PLATFORM_WORD.get(p.split(":")[0], p) for p in platforms if p.split(":")[0] not in CN_PLATFORMS]
    if zh and en:
        return f"Narrate in Chinese for {_j(zh)} and in English for {_j(en)}"
    return f"Narrate in {'Chinese' if zh else 'English'}"


def _where(v, by_id):
    names = []
    for sid in v.get("stories") or []:
        s = by_id.get(sid) or {}
        n = (s.get("place") or {}).get("en")
        if n and n not in names:
            names.append(n)
    return " and ".join(names[:3]) if names else None


def request_text(v, by_id):
    """The intake request of one video (English: the planner reads it; her languages are named per platform)."""
    L = int(v.get("length_s") or 60)
    plats = v.get("platforms") or DEFAULT_PLATFORMS
    words = [PLATFORM_WORD.get(p.split(":")[0], p) for p in plats]
    export = "Export for " + _j(words)
    where = _where(v, by_id)
    brief = (v.get("brief") or v.get("title") or "").strip().rstrip(".")
    aerial = any((by_id.get(s) or {}).get("aerial") for s in v.get("stories") or [])
    shots = ("drone shots" if aerial else "shots") + (f" of {where}" if where else "")
    trip = ("drone shots" if aerial else "shots") + (f" ({where})" if where else "")
    kind = v.get("kind") if v.get("kind") in KINDS else "film"
    title = f'Title: "{v["title"]}". ' if v.get("title") else ""
    if kind == "history":
        body = (f"Make a {L}-second history explainer from these {shots}: {brief}. "
                f"{_narrate(plats)}; state only well-known, verifiable facts, with on-screen place "
                f"labels. Calm cinematic music under the voice.")
    elif kind == "reel":
        body = (f"Make a {L}-second upbeat short from these {shots}: {brief}. Fast cuts on the beat, "
                f"energetic music, no voice. Vertical first.")
    elif kind == "vlog":
        body = (f"Make a {L}-second trip vlog from these {trip}: {brief}. No voice, warm music, short "
                f"place and time captions ({_langs(plats)}).")
    elif kind == "essay":
        body = (f"Make a {L}-second reflective essay from these {shots}: {brief}. A calm, high-end "
                f"reflective voice-over ({_langs(plats)}), soft piano, slow cuts.")
    elif kind == "photos":
        body = (f"Make a {L}-second photo story from these photos{f' of {where}' if where else ''}: {brief}. Slow "
                f"moves over each still, a premium music bed, short reflective lines on screen ({_langs(plats)}).")
    else:
        body = (f"Make a {L}-second cinematic film from these {shots}: {brief}. No voice, a slow premium "
                f"music bed and a few short high-end reflective lines on screen ({_langs(plats)}). Unhurried cuts "
                f"that follow the light.")
    return f"{title}{body} {export}."


def _inputs_of(v, by_id):
    clips, stills = [], []
    for sid in v.get("stories") or []:
        s = by_id.get(sid) or {}
        clips += s.get("clips") or []
        stills += s.get("stills") or []
    if v.get("kind") == "photos":
        return stills[:60] or clips
    return clips or stills[:60]


def _finish_video(v, by_id, platforms):
    v["kind"] = v.get("kind") if v.get("kind") in KINDS else "film"
    v["platforms"] = [p for p in (v.get("platforms") or platforms or DEFAULT_PLATFORMS) if isinstance(p, str)][:8]
    if v["kind"] == "reel" and "youtube" in v["platforms"]:
        v["platforms"] = ["youtube-shorts" if p == "youtube" else p for p in v["platforms"]]
    secs = sum((by_id.get(s) or {}).get("seconds") or 0 for s in v.get("stories") or [])
    stills = sum((by_id.get(s) or {}).get("photos") or 0 for s in v.get("stories") or [])
    try:
        L = int(v.get("length_s") or 0)
    except (TypeError, ValueError):
        L = 0
    cap = max(20, int(secs * 0.8)) if secs else max(20, stills * 4)
    v["length_s"] = max(15, min(180, L or min(90, cap), cap if secs or stills else 180))
    v["inputs"] = _inputs_of(v, by_id)
    v["clips"] = sum((by_id.get(s) or {}).get("videos") or 0 for s in v.get("stories") or [])
    v["request"] = request_text(v, by_id)
    return v


# --------------------------------------------------------------------------- the plan (model, else rules)
SYSTEM = """You plan a set of short videos from one person's footage (a drone SD card, a trip folder). She asked for
as many good videos as the footage supports, each with its own theme. You get the STORIES the footage falls into
(clips grouped by time and place, with the nearest well-known city and one contact sheet per story - look at every
sheet) and her request.

Propose videos (at most {max_videos}{exact}). Rules:
- Use the footage: every story with something worth showing should end up in a video; a story too thin on its own
  can join a related one (same trip, same place, same light). Never invent footage.
- kind per video:
  history - the place has a real story (a landmark, a waterfront, a historic town): a narrated explainer. Only when
    you can name the place from what you SEE plus the city; the facts it will state must be well known and
    verifiable (no superlatives you cannot check).
  film - the footage is simply beautiful (golden hour, mountains, sea): music and a few short high-end reflective
    lines, no voice.
  reel - action or energy (a boat, a jet ski, traffic, a festival): fast cuts on the beat, vertical first, 25-40 s.
  vlog - a trip across several stories/days: warm music, place and time captions.
  essay - a mood (autumn, solitude, a city at night): a calm reflective voice-over.
  photos - mostly photos / panoramas.
- Vary the kinds when the footage allows; do not make two videos of the same story with the same kind.
- length_s: what the footage can carry (about half the story's seconds for a film, never more than 0.8 of it), 20-120.
- title: short, specific, in English; title_zh: the same in Chinese.
- brief: ONE English sentence for the editor: what is in the shots and the angle (the landmarks you recognise; for
  history the topics to cover - no dates, numbers or "first / largest" claims: the writer checks those against
  well-known sources). Never GPS coordinates.
- theme and why: one short line each, in {ui_lang}, for her plan card.
- platforms: the ids she asked for ({platforms}); YouTube is always English, Xiaohongshu / Bilibili Chinese (the
  editor handles the languages - just list the platforms).
- goal: one short line in {ui_lang} restating her goal.

Return ONE JSON object: {{"goal": "...", "videos": [{{"title": "...", "title_zh": "...", "kind": "history|film|reel|vlog|essay|photos",
"stories": ["s1"], "length_s": 60, "brief": "...", "theme": "...", "why": "...", "platforms": ["youtube", ...]}}]}}"""

UI_LANG_NAME = {"en": "English", "zh": "Simplified Chinese", "fr": "French"}
GOAL_LINE = {"en": "As many videos as the footage supports, each with its own theme",
             "zh": "用这些素材尽量多做几个视频，每个主题不同",
             "fr": "Autant de vidéos que les images le permettent, chacune avec son thème"}
THEME = {"film": {"en": "Music and a few short lines", "zh": "配乐 + 几句短句", "fr": "Musique et quelques phrases"},
         "reel": {"en": "Fast cuts on the beat", "zh": "卡点快剪", "fr": "Montage rapide sur le rythme"},
         "vlog": {"en": "Trip vlog with place captions", "zh": "旅行 vlog + 地点字幕", "fr": "Vlog de voyage"},
         "history": {"en": "History of the place", "zh": "讲讲这个地方的历史", "fr": "L’histoire du lieu"},
         "essay": {"en": "Reflective voice-over", "zh": "安静的旁白随笔", "fr": "Voix off contemplative"},
         "photos": {"en": "Photo story", "zh": "照片故事", "fr": "Récit en photos"}}
WHY = {"en": "{n} clips, {secs} s of footage", "zh": "{n} 段素材，共 {secs} 秒", "fr": "{n} plans, {secs} s d’images"}


def _ui(ui_lang):
    c = (ui_lang or "en").split("-")[0].lower()
    return c if c in UI_LANG_NAME else "en"


def rule_videos(story_list, platforms, ui_lang="en", want=None):
    """No model: one video per story with enough footage, biggest first; a trip vlog over the small leftovers."""
    lang = _ui(ui_lang)
    by_story = {s["id"]: s for s in story_list}
    big = sorted([s for s in story_list if s["seconds"] >= MIN_STORY_S or s["photos"] >= 6],
                 key=lambda s: -(s["seconds"] + 3 * s["photos"]))
    cap = want or MAX_VIDEOS
    out = []
    for s in big[:cap]:
        place = (s.get("place") or {})
        tod = s.get("time_of_day") or ""
        en_place, zh_place = place.get("en") or (s.get("date") or "Footage"), place.get("zh") or (s.get("date") or "素材")
        photos_only = not s["videos"]
        kind = "photos" if photos_only else ("reel" if s["short_clips"] >= 8 and s["seconds"] < 150 else "film")
        title = f"{en_place} · {tod}" if tod else en_place
        out.append(dict(title=title, title_zh=f"{zh_place} · {_TOD_ZH.get(tod, '')}".rstrip(" ·"), kind=kind,
                        stories=[s["id"]], brief=f"{s['videos']} clips{' at ' + tod if tod else ''}"
                        f"{' near ' + place['en'] if place.get('en') else ''}",
                        theme=THEME[kind][lang], why=WHY[lang].format(n=s["videos"] or s["photos"], secs=int(s["seconds"])),
                        platforms=list(platforms)))
    # two stories of one place and light ("Seattle · evening" twice): the day, then the clock tells them apart
    for k, v in enumerate(out):
        s = by_story[v["stories"][0]]
        twins = [x for x in out if x["title"] == v["title"]]
        if len(twins) > 1 and s.get("start"):
            dates = {by_story[x["stories"][0]].get("date") for x in twins}
            tag = s["start"][5:10] if len(dates) == len(twins) else s["start"][11:16]
            v["title"], v["title_zh"] = f"{v['title']} · {tag}", f"{v['title_zh']} · {tag}"
    left = [s for s in story_list if s not in big[:cap]]
    days = {s.get("date") for s in left if s.get("date")}
    if len(out) < cap and len(left) >= 3 and len(days) >= 2 and sum(s["seconds"] for s in left) >= 30:
        out.append(dict(title="On the road", title_zh="路上", kind="vlog", stories=[s["id"] for s in left],
                        brief="short moments from several days, in time order", theme=THEME["vlog"][lang],
                        why=WHY[lang].format(n=sum(s["videos"] for s in left), secs=int(sum(s["seconds"] for s in left))),
                        platforms=list(platforms)))
    return out


def _model_videos(prompt, story_list, platforms, ui_lang, want, provider=None, model=None, call=None, timeout=None,
                  on_event=None):
    from vstudio import llm as LLM
    route = LLM.route(TASK, provider, model)
    info = dict(provider=route.provider, model=route.model)
    if route.provider == "none" and call is None:
        info.update(fallback=True, reason="no model routed for task intake (rule planner)")
        return None, None, info
    _emit(on_event, stage="model", provider=route.provider, model=route.model)
    lang = _ui(ui_lang)
    system = SYSTEM.format(max_videos=want or MAX_VIDEOS, exact=f"; she asked for {want}" if want else "",
                           ui_lang=UI_LANG_NAME[lang], platforms=", ".join(platforms))
    body = "\n".join([f"Request: {prompt}", "", "Stories:"] + [story_line(s) for s in story_list])
    imgs = [s["sheet"] for s in story_list if s.get("sheet")][:LLM.MAX_IMAGES]
    t0 = time.time()
    try:
        if call is not None:
            res = call(system, body, imgs)
        else:
            limit = min(900.0, 240.0 + len(body) / 300.0 + 20.0 * len(imgs))
            res = LLM.complete(TASK, system, body, schema=True, provider=provider, model=model, max_tokens=8000,
                               timeout=limit, cli_timeout=timeout or limit, effort="medium", retries=1,
                               **({"images": imgs} if imgs else {}))
    except Exception as e:  # noqa: BLE001  (auth / network / CLI: the rule planner, and say why)
        info.update(fallback=True, reason=f"{type(e).__name__}: {str(e)[:240]}", seconds=round(time.time() - t0, 1),
                    failure=LLM.failure_code(e))
        return None, None, info
    info.update(provider=res.get("provider") or info["provider"], model=res.get("model") or info["model"],
                seconds=round(time.time() - t0, 1), cost_usd=res.get("cost_usd", 0.0))
    js = res.get("json") if isinstance(res.get("json"), dict) else {}
    vids = js.get("videos")
    if not isinstance(vids, list) or not vids:
        info.update(fallback=True, reason="the model returned no videos")
        return None, None, info
    info["fallback"] = False
    return vids, (js.get("goal") if isinstance(js.get("goal"), str) else None), info


def _clean(raw, by_id, platforms, lang):
    out, used = [], set()
    for v in raw:
        if not isinstance(v, dict):
            continue
        st = [s for s in (v.get("stories") or []) if isinstance(s, str) and s in by_id]
        if not st:
            continue
        kind = v.get("kind") if v.get("kind") in KINDS else "film"
        sig = (tuple(sorted(st)), kind)
        if sig in used:
            continue
        used.add(sig)
        pl = [p for p in (v.get("platforms") or []) if isinstance(p, str) and re.match(r"^[a-z][a-z-]{0,30}$", p)]
        out.append(dict(title=str(v.get("title") or "")[:80].strip() or "Untitled",
                        title_zh=str(v.get("title_zh") or "")[:60].strip() or None, kind=kind, stories=st,
                        length_s=v.get("length_s"), brief=str(v.get("brief") or "")[:400],
                        theme=str(v.get("theme") or THEME[kind][lang])[:120], why=str(v.get("why") or "")[:200],
                        platforms=pl or list(platforms)))
    return out


def make_goal(prompt, inputs, platforms=None, ui_lang=None, provider=None, model=None, call=None, on_event=None,
              frames=True, timeout=None):
    """Survey + plan -> the goal document (module doc)."""
    from . import rules as R
    t0 = time.time()
    inputs = list(dict.fromkeys([*(inputs or []), *paths_in(prompt)]))
    if not inputs:
        raise ValueError("no folder to survey: drop the folder or name it in the request")
    lang = _ui(ui_lang)
    named, _unsup = R.platforms_of(prompt)
    plats = [p for p in (named or [x.split(":")[0] for x in platforms or []] or DEFAULT_PLATFORMS)]
    sc = scan(inputs, on_event=on_event, frames=frames)
    gid = hashlib.sha1(f"{prompt}\0{inputs}\0{time.time()}".encode()).hexdigest()[:12]
    sheet_dir = os.path.join(I.cache_root(), "goal", gid)
    _emit(on_event, stage="cluster", files=len(sc["items"]))
    st = stories(sc, sheet_dir=sheet_dir if frames else None)
    by_id = {s["id"]: s for s in st}
    want = wanted(prompt)
    raw, goal_line, info = (None, None, dict(provider="none", fallback=True, reason="no footage"))
    if st:
        raw, goal_line, info = _model_videos(prompt, st, plats, lang, want, provider, model, call, timeout, on_event)
    vids = _clean(raw, by_id, plats, lang) if raw else []
    if not vids:
        info["fallback"] = True
        vids = rule_videos(st, plats, lang, want)
    if want:
        vids = vids[:want]
    vids = vids[:MAX_VIDEOS]
    for k, v in enumerate(vids):
        v["id"] = f"v{k + 1}"
        _finish_video(v, by_id, plats)
    _emit(on_event, stage="write", files=len(vids))
    totals = dict(videos=sum(s["videos"] for s in st), photos=sum(s["photos"] for s in st),
                  panoramas=sum(s["panoramas"] for s in st), seconds=round(sum(s["seconds"] for s in st), 1),
                  days=sorted({s["date"] for s in st if s.get("date")}))
    info["seconds"] = round(time.time() - t0, 1)
    return dict(kind=KIND, version=VERSION, id=gid, created=time.time(), prompt=prompt, inputs=inputs,
                goal=(goal_line or GOAL_LINE[lang])[:200], platforms=plats, ui_lang=lang, want=want,
                survey=dict(stories=st, totals=totals, notes=sc["notes"][:20]), videos=vids, planner=info)


# --------------------------------------------------------------------------- edits on the plan card
def edit_goal(doc, ops):
    """Her edits on the plan card -> the same document with every touched video's ``request`` rebuilt.
    ops: {op: drop, video} | {op: rename, video, title} | {op: kind, video, kind} | {op: length, video, length_s}
         | {op: merge, videos: [v1, v2]} (the first keeps its title; the stories are joined) | {op: restore, video}
         | {op: platforms, video?, platforms} (no video: every video)"""
    if doc.get("kind") != KIND:
        raise ValueError("not a goal document")
    by_id = {s["id"]: s for s in (doc.get("survey") or {}).get("stories") or []}
    vids = {v["id"]: v for v in doc.get("videos") or []}

    def get(vid):
        if vid not in vids:
            raise ValueError(f"no video {vid}")
        return vids[vid]
    for op in ops or []:
        kind = op.get("op")
        if kind == "drop":
            get(op.get("video"))["dropped"] = True
        elif kind == "restore":
            get(op.get("video")).pop("dropped", None)
        elif kind == "rename":
            t = str(op.get("title") or "").strip()[:80]
            if not t:
                raise ValueError("title: 1-80 chars")
            get(op.get("video"))["title"] = t
        elif kind == "kind":
            if op.get("kind") not in KINDS:
                raise ValueError(f"kind: {' | '.join(KINDS)}")
            v = get(op.get("video"))
            v["kind"] = op["kind"]
            v["theme"] = THEME[op["kind"]][_ui(doc.get("ui_lang"))]
        elif kind == "length":
            n = op.get("length_s")
            if not isinstance(n, (int, float)) or not 10 <= n <= 600:
                raise ValueError("length_s: 10-600")
            get(op.get("video"))["length_s"] = int(n)
        elif kind == "merge":
            ids = op.get("videos") or []
            if len(ids) < 2:
                raise ValueError("merge: two or more videos")
            first = get(ids[0])
            for vid in ids[1:]:
                other = get(vid)
                first["stories"] = list(dict.fromkeys([*first["stories"], *other["stories"]]))
                first["length_s"] = min(180, int(first.get("length_s") or 60) + int(other.get("length_s") or 0) // 2)
                other["dropped"] = True
                other["merged_into"] = first["id"]
        elif kind == "platforms":
            pl = [p for p in op.get("platforms") or [] if isinstance(p, str) and re.match(r"^[a-z][a-z-]{0,30}$", p)]
            if not pl:
                raise ValueError("platforms: one or more platform ids")
            for v in ([get(op["video"])] if op.get("video") else vids.values()):
                v["platforms"] = pl
            if not op.get("video"):
                doc["platforms"] = pl
        else:
            raise ValueError(f"unknown op {kind}")
    for v in vids.values():
        _finish_video(v, by_id, doc.get("platforms"))
    doc["edited"] = time.time()
    return doc
