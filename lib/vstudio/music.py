"""Background music library: the downloaded library of real CC0 tracks, built-in beds generated from code (no
third-party rights at all) + your own folders.

    from vstudio import music
    music.moods()                                   # ['calm', 'warm', 'bright', 'tech', 'story']
    music.mood_of("加一个轻的背景音乐，温暖一点")       # -> 'warm'
    path = music.resolve("calm", duration=95)       # a generated, cached 95 s bed (48 kHz wav, fades in / out)
    path = music.resolve("~/Music/Reelfold/x.mp3")  # a file passes through
    music.tracks()                                  # built-ins + files in your music folders (with mood / license)

    music.rank("卡点 快节奏", style="fun", need_beat=True, group="g1")   # fit + no repeats in the group / lately
    music.choose(..., project=pdir, item="main", group="g1")    # rank + record the pick (the diversity ledger)

    python -m vstudio.music list [--mood calm]
    python -m vstudio.music library [--json]          # the CC0 library: installed?, licence, BPM, energy
    python -m vstudio.music prefs --favourite lib:arpent | --ban lib:coy-koi | --clear lib:coy-koi
    python -m vstudio.music make --mood warm --duration 60 -o bed.wav [--seed 2]
    python -m vstudio.music pick "轻松一点的背景音乐" --duration 60 [-o bed.wav]

Built-in moods are synthesised here (FM e-piano, pads, Karplus-Strong plucks, sine bass, soft drums, a small
reverb), so they are free to use anywhere, commercially too. They are calm, simple beds meant to sit at -30 LUFS
under a voice, not foreground music. For real songs put files you have the rights to in a music folder:
``~/Music/Reelfold`` or persona ``music.dirs`` / env ``VSTUDIO_MUSIC_DIRS`` (os.pathsep-separated). A sidecar
``<file>.json`` {mood, license, source, title} labels a track; otherwise the mood is guessed from the file name.
Mixing and ducking under the voice: ``audio.mix_bed`` (output edit effect ``music-bed``, polish ``--music``).

The library (``music_library.json``, next to this file): ~50 real tracks, CC0 only (FreePD.com, Musopen), each with
its licence evidence, sha256, Beat This! BPM / downbeats, an energy curve and a loop span. The files are a first-run
download (desk: assets group ``music-library`` -> env ``VSTUDIO_MUSIC_LIBRARY``; CLI: ``python -m vstudio.assets
fetch music-library`` -> <cache>/models/music-library). ``validate_library`` refuses a licence that is not free for
bundling + published videos (NC / ND / platform-only licences). Picks are recorded in ``$VSTUDIO_HOME/
music_history.jsonl`` (one line per pick: track, project, item, group): ``rank`` keeps a track out of the other videos
of the same group (a goal / one request's batch) until the library is exhausted and pushes down the tracks of her last
``RECENT_N`` videos. Favourites / bans: ``$VSTUDIO_HOME/music.json`` (Settings › Music).
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

SR = 48000
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".aiff", ".aif")

# A minor = 57 (MIDI). Chords as scale-degree triads (+7th) in a key; progressions per mood.
_MAJ = [0, 2, 4, 5, 7, 9, 11]
_MIN = [0, 2, 3, 5, 7, 8, 10]
STYLES = {
    "calm": dict(bpm=72, key=60, scale=_MAJ, prog=[0, 5, 3, 4], lead="epiano", pattern="arp8", pad=0.5,
                 drums=None, bass=0.35, zh="平静 / 治愈", en="Calm, soft piano and pad"),
    "warm": dict(bpm=82, key=62, scale=_MAJ, prog=[3, 4, 2, 5], lead="epiano", pattern="chords", pad=0.35,
                 drums="lofi", bass=0.5, swing=0.12, zh="温暖 / lo-fi", en="Warm lo-fi chords, soft beat"),
    "bright": dict(bpm=108, key=65, scale=_MAJ, prog=[0, 4, 5, 3], lead="pluck", pattern="arp16", pad=0.3,
                   drums="pop", bass=0.5, zh="轻快 / 明亮", en="Bright plucks, light four-on-the-floor"),
    "tech": dict(bpm=100, key=57, scale=_MIN, prog=[0, 5, 2, 6], lead="pluck", pattern="pulse", pad=0.35,
                 drums="tech", bass=0.6, zh="科技 / 理性", en="Minor pulse arpeggio, tight hats"),
    "story": dict(bpm=64, key=57, scale=_MIN, prog=[5, 3, 0, 4], lead="epiano", pattern="sparse", pad=0.6,
                  drums=None, bass=0.3, zh="叙事 / 安静", en="Slow pad with sparse piano"),
}
KEYWORDS = {
    "calm": ["calm", "chill", "soft", "relax", "gentle", "light", "平静", "治愈", "轻", "柔", "安静的", "舒缓", "放松", "淡"],
    "warm": ["warm", "lofi", "lo-fi", "cozy", "vlog", "温暖", "温馨", "日常", "生活", "复盘", "暖"],
    "bright": ["bright", "upbeat", "happy", "fun", "energetic", "pop", "轻快", "欢快", "明亮", "活泼", "励志", "积极",
               "开心", "快节奏", "卡点"],
    "tech": ["tech", "ai", "code", "product", "explainer", "electronic", "科技", "理性", "技术", "产品", "讲解", "编程",
             "干货", "知识"],
    "story": ["story", "cinematic", "emotional", "sad", "piano", "叙事", "故事", "情绪", "文艺", "感性", "回忆", "电影感"],
}


def moods():
    return list(STYLES)


def mood_of(text, default="calm"):
    """A request / title / file name -> the best-matching mood (keyword hits; ``default`` when nothing matches)."""
    t = str(text or "").lower()
    best, score = default, 0
    for m, kws in KEYWORDS.items():
        s = sum(len(k) for k in kws if k in t)
        if m in t:
            s += 10
        if s > score:
            best, score = m, s
    return best


# ------------------------------------------------------------------ instruments
def _env(n, a, d, s, r, sr=SR):
    """ADSR (seconds; s = sustain level) over n samples, release inside n."""
    e = np.full(n, s, np.float32)
    na, nd, nr = int(a * sr), int(d * sr), int(r * sr)
    na = min(na, n)
    e[:na] = np.linspace(0, 1, na, endpoint=False) if na else e[:na]
    nd = min(nd, n - na)
    if nd > 0:
        e[na:na + nd] = np.linspace(1, s, nd, endpoint=False)
    nr = min(nr, n)
    if nr > 0:
        e[n - nr:] *= np.linspace(1, 0, nr)
    return e


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def epiano(midi, dur, vel=0.6, sr=SR):
    """2-operator FM electric piano: bell-ish attack that mellows, ~1.2 s natural decay."""
    n = int((dur + 1.2) * sr)
    t = np.arange(n) / sr
    f = _hz(midi)
    idx = 1.6 * np.exp(-t * 3.0) + 0.25
    y = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t))
    y += 0.25 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 2.0)
    e = np.exp(-t * (1.1 + midi / 120)) * _env(n, 0.004, 0.05, 1.0, 0.25)
    return (vel * 0.35 * y * e).astype(np.float32)


def pluck(midi, dur, vel=0.6, sr=SR, seed=0):
    """Karplus-Strong plucked string (decay ~0.8 s), soft lowpass."""
    f = _hz(midi)
    p = max(2, int(round(sr / f)))
    n = int((dur + 0.8) * sr)
    rng = np.random.default_rng(seed + midi)
    buf = rng.uniform(-1, 1, p).astype(np.float32)
    out = np.empty(n, np.float32)
    damp = 0.996 - (midi - 48) * 0.0004
    for i in range(0, n, p):                      # one period per step (vectorised inside the period)
        seg = buf.copy()
        out[i:i + p] = seg[:min(p, n - i)]
        buf = damp * 0.5 * (seg + np.roll(seg, -1))
    return (vel * 0.4 * out * _env(n, 0.002, 0.0, 1.0, 0.1)).astype(np.float32)


def pad(midis, dur, vel=0.5, sr=SR):
    """Slow detuned additive pad (a few odd/even partials per voice), soft attack / release."""
    n = int((dur + 0.6) * sr)
    t = np.arange(n) / sr
    y = np.zeros(n, np.float32)
    for m in midis:
        f = _hz(m)
        for det in (-0.12, 0.0, 0.11):
            ff = f * 2 ** (det / 12)
            for h, a in ((1, 1.0), (2, 0.35), (3, 0.18), (4, 0.08)):
                y += (a * np.sin(2 * np.pi * ff * h * t + det * 7)).astype(np.float32)
    y /= max(1, len(midis) * 3 * 1.6)
    return (vel * 0.3 * y * _env(n, min(0.9, dur / 3), 0.2, 0.85, 0.6)).astype(np.float32)


def bass(midi, dur, vel=0.6, sr=SR):
    n = int((dur + 0.15) * sr)
    t = np.arange(n) / sr
    f = _hz(midi)
    y = np.sin(2 * np.pi * f * t) + 0.15 * np.sin(2 * np.pi * 2 * f * t)
    return (vel * 0.5 * y * _env(n, 0.01, 0.1, 0.8, 0.12)).astype(np.float32)


def kick(vel=0.8, sr=SR):
    n = int(0.35 * sr)
    t = np.arange(n) / sr
    f = 45 + 90 * np.exp(-t * 30)
    ph = 2 * np.pi * np.cumsum(f) / sr
    return (vel * np.sin(ph) * np.exp(-t * 9)).astype(np.float32)


def noise_hit(dur, lo, hi, decay, vel, sr=SR, seed=0):
    n = int(dur * sr)
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n).astype(np.float32)
    X = np.fft.rfft(x)
    fr = np.fft.rfftfreq(n, 1 / sr)
    X[(fr < lo) | (fr > hi)] = 0
    x = np.fft.irfft(X, n).astype(np.float32)
    x /= max(1e-6, np.max(np.abs(x)))
    t = np.arange(n) / sr
    return (vel * x * np.exp(-t * decay)).astype(np.float32)


def reverb(x, sr=SR, t60=1.6, mix=0.22, seed=0):
    """Convolution with a decaying stereo noise tail (pre-delay 20 ms): a small hall."""
    n = int(t60 * sr)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / sr
    out = []
    for c in range(2):
        ir = rng.standard_normal(n) * np.exp(-6.9 * t / t60)
        ir[: int(0.02 * sr)] = 0
        ir /= np.sqrt(np.sum(ir ** 2))
        L = len(x) + n
        nfft = 1 << (L - 1).bit_length()
        y = np.fft.irfft(np.fft.rfft(x[:, c], nfft) * np.fft.rfft(ir, nfft), nfft)[:len(x)]
        out.append(y)
    wet = np.stack(out, 1).astype(np.float32)
    return ((1 - mix) * x + mix * wet).astype(np.float32)


# ------------------------------------------------------------------ composition
def _chord(style, degree, octave=0):
    sc, key = style["scale"], style["key"]
    notes = [key + 12 * octave + sc[(degree + k) % 7] + 12 * ((degree + k) // 7) for k in (0, 2, 4, 6)]
    return notes


def _add(buf, x, at, pan=0.0):
    i = int(at * SR)
    if i >= len(buf):
        return
    x = x[:len(buf) - i]
    lg, rg = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[i:i + len(x), 0] += x * lg * 1.414
    buf[i:i + len(x), 1] += x * rg * 1.414


def generate(mood="calm", duration=60.0, seed=0):
    """Synthesise a bed of ``duration`` s -> float32 (n, 2) at 48 kHz, peak ~-6 dBFS, fade in 2 s / out 4 s,
    ending on the home chord."""
    if mood not in STYLES:
        raise ValueError(f"mood must be one of {moods()}, got {mood!r}")
    st = STYLES[mood]
    rng = np.random.default_rng(seed)
    beat = 60.0 / st["bpm"]
    bar = 4 * beat
    nbars = max(2, int(np.ceil(duration / bar)))
    total = duration
    buf = np.zeros((int((total + 3.0) * SR), 2), np.float32)
    prog = list(st["prog"])
    if seed:
        k = int(rng.integers(0, len(prog)))
        prog = prog[k:] + prog[:k]
    sw = st.get("swing", 0.0)
    for b in range(nbars):
        t0 = b * bar
        last = b == nbars - 1
        deg = 0 if last else prog[b % len(prog)]
        ch = _chord(st, deg)
        intro = b < 1
        if st["pad"]:
            _add(buf, pad([n - 12 for n in ch[:3]] + [ch[3]], bar, st["pad"]), t0)
        if st["bass"] and not intro:
            for k in range(2 if st["bpm"] < 90 else 4):
                step = bar / (2 if st["bpm"] < 90 else 4)
                _add(buf, bass(ch[0] - 24, step * 0.9, st["bass"]), t0 + k * step)
        lead = epiano if st["lead"] == "epiano" else (lambda m, d, v: pluck(m, d, v, seed=seed))
        pat = st["pattern"]
        if last:
            for i, nt in enumerate(ch[:3]):
                _add(buf, lead(nt, bar, 0.5), t0 + i * 0.03, pan=(i - 1) * 0.3)
            continue
        if pat == "chords":
            for k in (0, 2.5) if not intro else (0,):
                at = t0 + k * beat + (sw * beat if k % 1 else 0)
                for i, nt in enumerate(ch):
                    _add(buf, lead(nt, beat * 1.5, 0.42 + 0.08 * rng.random()), at + i * 0.012, pan=(i - 1.5) * 0.2)
        elif pat in ("arp8", "arp16", "pulse"):
            div = 8 if pat == "arp8" else 16
            order = [0, 1, 2, 3, 2, 1] if pat == "arp8" else [0, 2, 1, 3]
            step = bar / div
            for k in range(div):
                if intro and k >= div // 2:
                    break
                nt = ch[order[k % len(order)]] + (12 if pat == "arp16" and k % 4 == 3 else 0)
                if pat == "pulse":
                    nt = ch[0] + (12 if k % 2 else 0) + (st["scale"][4] - st["scale"][0] if k % 8 >= 6 else 0)
                v = (0.5 if k % 4 == 0 else 0.33) * (0.9 + 0.2 * rng.random())
                at = t0 + k * step + (sw * step if k % 2 else 0)
                _add(buf, lead(nt, step * 1.6, v), at, pan=0.35 * np.sin(k))
        elif pat == "sparse":
            for k in sorted(rng.choice(8, size=3, replace=False)):
                nt = ch[int(rng.integers(0, 4))] + 12
                _add(buf, lead(nt, beat * 2, 0.35), t0 + k * bar / 8, pan=float(rng.uniform(-0.4, 0.4)))
        dr = st["drums"]
        if dr and not intro:
            for k in range(4):
                at = t0 + k * beat
                if dr in ("pop",) or (dr in ("lofi", "tech") and k in (0, 2)):
                    _add(buf, kick(0.55 if dr == "lofi" else 0.65), at)
                if dr == "pop" and k in (1, 3):
                    _add(buf, noise_hit(0.18, 900, 6000, 22, 0.22, seed=b * 4 + k), at)
                if dr == "lofi" and k in (1, 3):
                    _add(buf, noise_hit(0.12, 1500, 5000, 30, 0.12, seed=b * 4 + k), at + sw * beat * 0.3)
                for h in (0, 1) if dr != "tech" else (0, 1, 2, 3):
                    sub = beat / (2 if dr != "tech" else 4)
                    _add(buf, noise_hit(0.05, 7000, 16000, 70, 0.06 if h else 0.09, seed=b * 16 + k * 4 + h),
                         at + h * sub + (sw * sub if h % 2 else 0), pan=0.3)
    y = reverb(buf, t60=1.8 if mood in ("calm", "story") else 1.2, mix=0.28 if mood in ("calm", "story") else 0.18,
               seed=seed)
    n = int(total * SR)
    y = y[:n]
    t = np.arange(n) / SR
    g = np.clip(t / 2.0, 0, 1) * np.clip((total - t) / min(4.0, total / 3), 0, 1)
    y *= g[:, None]
    pk = float(np.max(np.abs(y))) or 1.0
    return (y * (0.5 / pk)).astype(np.float32)


# ------------------------------------------------------------------ library
def _cache():
    from .config import cache_dir
    return cache_dir("music")


def dirs():
    """Your music folders: env VSTUDIO_MUSIC_DIRS, persona music.dirs, ~/Music/Reelfold (existing ones only)."""
    out = [p for p in (os.environ.get("VSTUDIO_MUSIC_DIRS") or "").split(os.pathsep) if p]
    try:
        from .config import persona
        out += list(((persona().get("music") or {}).get("dirs")) or [])
    except Exception:  # noqa: BLE001
        pass
    out.append("~/Music/Reelfold")
    seen, res = set(), []
    for p in out:
        q = os.path.abspath(os.path.expanduser(str(p)))
        if q not in seen and os.path.isdir(q):
            seen.add(q)
            res.append(q)
    return res


def _sidecar(path):
    for p in (path + ".json", os.path.splitext(path)[0] + ".json"):
        if os.path.exists(p):
            try:
                with open(p) as f:
                    d = json.load(f)
                return d if isinstance(d, dict) else {}
            except (OSError, ValueError):
                return {}
    return {}


# ------------------------------------------------------------------ the CC0 library (a first-run download)
LIBRARY_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music_library.json")
LIBRARY_ENV = "VSTUDIO_MUSIC_LIBRARY"
# licences a bundled track may have: re-hosted / downloaded by the app (MIT) and used in her published videos with no
# per-video fee. CC BY only with its credit (``credit`` puts it in the post copy).
FREE_LICENCES = ("CC0-1.0", "PDM-1.0", "CC-BY-3.0", "CC-BY-4.0")
NEEDS_CREDIT = ("CC-BY-3.0", "CC-BY-4.0")
# never in the library: NonCommercial / NoDerivatives, licences that forbid redistribution in another product, and
# sources whose tracks are registered with Content ID (a CC0 copy still gets claimed)
FORBIDDEN = ("-nc", "-nd", "noncommercial", "noderiv", "youtube audio library", "pixabay", "mixkit", "uppbeat",
             "envato", "audiojungle", "epidemic", "artlist")
FORBIDDEN_ARTISTS = ("rafael krux", "orchestralis")      # also sold on Envato, registered with Content ID
LICENCE_TEXT = {"CC0-1.0": "CC0 1.0 (public domain)", "PDM-1.0": "Public Domain Mark 1.0",
                "CC-BY-3.0": "CC BY 3.0", "CC-BY-4.0": "CC BY 4.0"}
LICENCE_URL = {"CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
               "PDM-1.0": "https://creativecommons.org/publicdomain/mark/1.0/",
               "CC-BY-3.0": "https://creativecommons.org/licenses/by/3.0/",
               "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/"}
# the energy a built-in bed has (0..1), for the energy fit
BUILTIN_ENERGY = {"calm": 0.25, "warm": 0.45, "bright": 0.72, "tech": 0.65, "story": 0.3}
_LIB = {}


def library_doc():
    """The library manifest (cached by mtime): {kind, version, tracks: [...]}"""
    try:
        mt = os.path.getmtime(LIBRARY_JSON)
    except OSError:
        return dict(tracks=[])
    if _LIB.get("mt") != mt:
        with open(LIBRARY_JSON, encoding="utf-8") as f:
            _LIB.update(mt=mt, doc=json.load(f))
    return _LIB["doc"]


def library_dir():
    """Where the library's files are: env VSTUDIO_MUSIC_LIBRARY (the desk's asset folder) > <cache>/models/music-library
    (``python -m vstudio.assets fetch music-library``). None when neither exists."""
    env = os.environ.get(LIBRARY_ENV)
    if env and os.path.isdir(env):
        return env
    from .config import cache_dirs
    for d in cache_dirs("models", "music-library"):
        if os.path.isdir(d):
            return d
    return None


def validate_library(doc=None):
    """Licence + shape checks of the manifest -> a list of problems ([] = fine)."""
    import re
    doc = library_doc() if doc is None else doc
    errs, seen = [], set()
    need = ("id", "title", "artist", "licence", "licence_url", "source_url", "licence_evidence", "url", "file",
            "sha256", "size", "duration", "mood", "style", "tags", "energy", "energy_curve")
    for t in doc.get("tracks") or []:
        tid = t.get("id")
        miss = [k for k in need if t.get(k) in (None, "", [])]
        if miss:
            errs.append(f"{tid}: missing {', '.join(miss)}")
        if tid in seen:
            errs.append(f"{tid}: duplicate id")
        seen.add(tid)
        lic = str(t.get("licence") or "")
        blob = " ".join(str(t.get(k) or "") for k in ("licence", "licence_url", "source", "source_url", "url")).lower()
        if lic not in FREE_LICENCES:
            errs.append(f"{tid}: licence {lic!r} is not one of {', '.join(FREE_LICENCES)}")
        if lic in LICENCE_URL and str(t.get("licence_url") or "").rstrip("/") != LICENCE_URL[lic].rstrip("/"):
            errs.append(f"{tid}: licence_url {t.get('licence_url')!r} is not the {lic} deed")
        if any(x in blob for x in FORBIDDEN):
            errs.append(f"{tid}: a forbidden licence / source ({blob[:80]})")
        if str(t.get("artist") or "").lower() in FORBIDDEN_ARTISTS:
            errs.append(f"{tid}: {t.get('artist')} (Content ID claims on the same tracks elsewhere)")
        if lic in NEEDS_CREDIT and not (t.get("artist") and t.get("title")):
            errs.append(f"{tid}: {lic} needs a title and an artist for its credit")
        if not re.fullmatch(r"[0-9a-f]{64}", str(t.get("sha256") or "")):
            errs.append(f"{tid}: sha256")
        if not str(t.get("url") or "").startswith("https://"):
            errs.append(f"{tid}: url must be https")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.(mp3|ogg|flac|wav|m4a)", str(t.get("file") or "")):
            errs.append(f"{tid}: file name {t.get('file')!r}")
        if t.get("mood") not in STYLES:
            errs.append(f"{tid}: mood {t.get('mood')!r}")
        if t.get("bpm") is not None and not 50 <= float(t["bpm"]) <= 200:
            errs.append(f"{tid}: bpm {t['bpm']}")
    return errs


def _lib_track(t, d):
    lic = t["licence"]
    out = dict(id=f"lib:{t['id']}", title=t["title"], artist=t.get("artist"), mood=t["mood"], style=t.get("style"),
               tags=list(t.get("tags") or []), source="library", path=os.path.join(d, t["file"]) if d else None,
               license=LICENCE_TEXT.get(lic, lic), licence=lic, origin=t.get("source_url"),
               licence_evidence=t.get("licence_evidence"), bpm=t.get("bpm"), steady=bool(t.get("steady")),
               grid_bpm=t.get("bpm_detected") or t.get("bpm"),
               energy=t.get("energy"), duration=t.get("duration"), loop=t.get("loop"))
    if lic in NEEDS_CREDIT:
        out["attribution"] = (f'Music: "{t["title"]}" by {t["artist"]} ({t.get("source_url")}), licensed under '
                              f'{LICENCE_TEXT[lic]} ({LICENCE_URL[lic]})')
    out["credit"] = credit(out)
    return out


def library(installed=None):
    """The library's tracks (``installed``: True = only the ones on disk, False = only the missing ones, None = all,
    each with ``installed``)."""
    d = library_dir()
    out = []
    for t in library_doc().get("tracks") or []:
        x = _lib_track(t, d)
        x["installed"] = bool(x["path"] and os.path.isfile(x["path"]) and os.path.getsize(x["path"]) == t.get("size"))
        if installed is None or x["installed"] == installed:
            out.append(x)
    return out


def library_track(tid):
    """'lib:<id>' / '<id>' -> the manifest entry or None."""
    k = str(tid or "").split(":", 1)[-1]
    return next((t for t in library_doc().get("tracks") or [] if t["id"] == k), None)


def tracks(mood=None):
    """Built-in moods + the installed CC0 library + files in your music folders:
    [{id, title, mood, source builtin|library|file, path?, license, credit}]."""
    out = [dict(id=f"builtin:{m}", title=s["en"], title_zh=s["zh"], mood=m, source="builtin", bpm=s["bpm"],
                steady=True, energy=BUILTIN_ENERGY.get(m), tags=[], style="builtin",
                license="generated by Reelfold (MIT), free for any use") for m, s in STYLES.items()]
    out += library(installed=True)
    for d in dirs():
        for root, _, files in os.walk(d):
            for fn in sorted(files):
                if not fn.lower().endswith(AUDIO_EXT):
                    continue
                p = os.path.join(root, fn)
                sc = _sidecar(p)
                m = sc.get("mood") if sc.get("mood") in STYLES else mood_of(sc.get("title") or fn, default="calm")
                t = dict(id=p, title=sc.get("title") or os.path.splitext(fn)[0], mood=m, source="file", path=p,
                         license=sc.get("license") or "yours (check you may use it)", origin=sc.get("source"))
                for k in ("artist", "bpm", "attribution"):
                    if sc.get(k):
                        t[k] = sc[k]
                stem = os.path.splitext(fn)[0]
                if not sc.get("license") and stem.endswith("_KevinMacLeod"):     # fetch_music.sh (incompetech)
                    t.update(title=sc.get("title") or stem[:-len("_KevinMacLeod")].replace("_", " "),
                             artist="Kevin MacLeod", license="CC BY 4.0", origin="incompetech.com")
                t["credit"] = credit(t)
                out.append(t)
    return [t for t in out if mood is None or t["mood"] == mood]


def needs_credit(track):
    """A licence that asks for attribution (CC BY / CC BY-SA ...; not CC0, not the built-ins)."""
    lic = str((track or {}).get("license") or "").lower().replace("-", " ")
    return "cc by" in lic or "attribution" in lic


def credit(track):
    """The credit line a track's licence asks for in the post copy (None when it asks for none)."""
    t = track or {}
    if t.get("attribution"):
        return str(t["attribution"])
    if not needs_credit(t):
        return None
    who = f" by {t['artist']}" if t.get("artist") else ""
    src = f" ({t['origin']})" if t.get("origin") else ""
    lic = str(t.get("license"))
    url = " (https://creativecommons.org/licenses/by/4.0/)" if "4.0" in lic and "by" in lic.lower() else ""
    return f'Music: "{t.get("title")}"{who}{src}, licensed under {lic}{url}'


# words that say what a piece should feel like, beyond the mood keywords: (word, {mood: weight})
VIBES = [
    (("高级", "高端", "质感", "premium", "elegant", "classy", "luxury", "大片"), {"story": 3, "calm": 2}),
    (("秋", "红叶", "枫", "落叶", "autumn", "fall foliage", "foliage", "maple"), {"story": 3, "warm": 2, "calm": 1}),
    (("航拍", "drone", "aerial", "风景", "landscape", "scenery", "旅行", "travel"), {"story": 2, "calm": 2}),
    (("海", "ocean", "beach", "夏", "summer", "sunny"), {"bright": 2, "calm": 1}),
    (("night", "夜", "rain", "雨", "snow", "雪", "冬", "winter"), {"story": 2, "calm": 1}),
]
# what a vlog style asks of its bed: calm = slow crossfades (no drums), fun = a beat to cut on
STYLE_PRIOR = {"calm": {"calm": 2, "story": 2, "warm": 1}, "fun": {"bright": 3, "tech": 1, "warm": 1}}
NO_MUSIC = ("不要音乐", "不要配乐", "无配乐", "没有音乐", "不用配乐", "不配乐", "不加音乐", "no music", "without music",
            "silent", "no soundtrack")


def wants_none(text):
    t = str(text or "").lower()
    return any(k in t for k in NO_MUSIC)


# words that ask for a kind of track (its style / tags): (words, tags)
TAG_WORDS = [
    (("钢琴", "piano", "古典", "classical"), ("piano",)),
    (("吉他", "民谣", "原声", "acoustic", "folk", "guitar", "ukulele", "尤克里里"), ("acoustic",)),
    (("史诗", "大片", "燃", "壮丽", "震撼", "epic", "cinematic", "trailer", "heroic", "电影感"), ("cinematic", "epic")),
    (("电子", "electronic", "edm", "synth", "beat", "节拍", "动感"), ("electronic",)),
    (("lofi", "lo-fi", "chill", "jazz", "爵士", "慵懒", "咖啡"), ("lofi", "jazz")),
    (("纪录", "历史", "documentary", "history", "historic", "ancient", "古迹", "博物馆"), ("documentary", "history")),
    (("中国风", "国风", "古风", "古筝", "二胡", "guzheng", "erhu", "chinese", "东方", "江南"), ("chinese", "asian")),
    (("科技", "产品", "发布", "promo", "corporate", "startup", "tech", "app", "saas", "商务"), ("corporate",)),
    (("流行", "pop", "indie", "阳光", "夏", "summer", "sunny"), ("pop",)),
    (("ambient", "氛围", "冥想", "meditation", "放空", "空灵"), ("ambient",)),
]
FAST_WORDS = ("卡点", "快节奏", "快剪", "燃", "动感", "节奏感", "fast", "energetic", "hype", "upbeat", "action", "运动",
              "冲浪", "摩托", "jet ski", "滑雪")
SLOW_WORDS = ("舒缓", "慢", "安静", "治愈", "放松", "slow", "calm", "gentle", "peaceful", "relax", "高级", "质感")
GRID_BPM = (70.0, 160.0)      # the beat tempi a reel can be cut to
RECENT_N = 6                  # her last N videos' tracks are pushed down (not excluded)
GROUP_PENALTY = 100.0         # another video of the same group already has it: only when nothing else is left
HISTORY = "music_history.jsonl"
PREFS = "music.json"


def _home():
    return os.path.abspath(os.path.expanduser(os.environ.get("VSTUDIO_HOME") or "~/.config/vstudio"))


def prefs():
    """Her favourites / bans: {favourites: [track id], banned: [track id]} ($VSTUDIO_HOME/music.json)."""
    try:
        with open(os.path.join(_home(), PREFS), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return dict(favourites=[str(x) for x in d.get("favourites") or []], banned=[str(x) for x in d.get("banned") or []])


def set_pref(track_id, favourite=None, banned=None):
    """Favourite / ban a track (None = leave as is) -> the prefs. A ban drops a favourite and vice versa."""
    tid = str(track_id or "").strip()
    if not tid or len(tid) > 4096:
        raise ValueError("track id")
    d = prefs()
    for key, on in (("favourites", favourite), ("banned", banned)):
        if on is None:
            continue
        lst = [x for x in d[key] if x != tid]
        if on:
            lst.append(tid)
            other = "banned" if key == "favourites" else "favourites"
            d[other] = [x for x in d[other] if x != tid]
        d[key] = lst
    os.makedirs(_home(), exist_ok=True)
    tmp = os.path.join(_home(), PREFS + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, os.path.join(_home(), PREFS))
    return d


def history(limit=None):
    """The picks, oldest first, the latest per (project, item) only: [{at, track, title, project, item, group}]."""
    rows = []
    try:
        with open(os.path.join(_home(), HISTORY), encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and r.get("track"):
                    rows.append(r)
    except OSError:
        return []
    last = {}
    for r in rows:
        k = (r.get("project") or "", r.get("item") or "") if r.get("project") else (id(r),)
        last.pop(k, None)
        last[k] = r
    out = list(last.values())
    return out[-limit:] if limit else out


def pick_of(project, item):
    """The track this video was given last (None when it has none yet)."""
    me = (os.path.abspath(project) if project else None, item)
    for r in reversed(history()):
        if (r.get("project"), r.get("item")) == me and r.get("track") != "none":
            return r["track"]
    return None


def record(track, project=None, item=None, group=None, title=None):
    """Note a pick (a later pick of the same project + item replaces it)."""
    if not track:
        return
    import time
    os.makedirs(_home(), exist_ok=True)
    pdir = os.path.abspath(project) if project else None
    prev = next((r for r in reversed(history()) if pdir and (r.get("project"), r.get("item")) == (pdir, item)), None)
    row = dict(at=round(time.time(), 3), track=str(track), title=title, project=pdir, item=item, group=group)
    if prev:
        row["since"] = _first(prev)               # when this video first got a track (its place in the queue)
    with open(os.path.join(_home(), HISTORY), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _first(r):
    return float(r.get("since") or r.get("at") or 0)


def _avoid(project, item, group, recent):
    """-> ({track: why} of the same group, {track: rank 0 = newest} of her last ``recent`` videos), this video's own
    pick left out and, once it has one, only the picks made before its first one (first come, first served: asking
    again - her answer, a resumed run - gives the same ranking)."""
    me = (os.path.abspath(project) if project else None, item)
    rows = history()
    mine = [r for r in rows if me[0] and (r.get("project"), r.get("item")) == me]
    cut = _first(mine[-1]) if mine else None
    rows = [r for r in rows if not (me[0] and (r.get("project"), r.get("item")) == me)
            and (cut is None or _first(r) < cut)]
    same = {}
    if group:
        for r in rows:
            if r.get("group") == group:
                same[r["track"]] = r.get("title") or r["track"]
    seen, newest = [], {}
    for r in reversed(rows):
        key = (r.get("project"), r.get("item"))
        if key in seen:
            continue
        seen.append(key)
        newest.setdefault(r["track"], len(seen) - 1)
        if len(seen) >= recent:
            break
    return same, newest


def target_energy(text="", style=None, shot_s=None):
    """0..1: how lively the music should be for these words / this style / these shot lengths (None: no opinion)."""
    t = str(text or "").lower()
    votes = []
    if style == "fun" or any(k in t for k in FAST_WORDS):
        votes.append(0.8)
    if style == "calm" or any(k in t for k in SLOW_WORDS):
        votes.append(0.3)
    if shot_s:
        votes.append(float(np.clip(1.0 - (float(shot_s) - 1.0) / 7.0, 0.15, 0.9)))
    return round(float(np.mean(votes)), 2) if votes else None


def target_bpm(shot_s=None):
    """The tempo a cut every ~2 beats of ``shot_s`` s asks for (85..135), None without shot lengths."""
    if not shot_s:
        return None
    return float(np.clip(120.0 / float(shot_s), 85.0, 135.0))


def rank(text="", style=None, n=None, *, shot_s=None, need_beat=False, min_duration=None, project=None, item=None,
         group=None, recent=RECENT_N, no_credit=False):
    """The library ranked for a request: ``text`` (her words, the title), ``style`` (a vlog style: calm / fun),
    ``shot_s`` (the edit's mean shot length: energy + tempo), ``need_beat`` (a beat-cut reel: tracks with a steady
    pulse only), ``min_duration`` (s: shorter real tracks go down; a built-in is made to any length), ``group`` /
    ``project`` / ``item`` (diversity: a track another video of the group has is last unless nothing else is left; her
    last ``recent`` videos' tracks go down) -> tracks, best first, each with ``score`` and ``why`` (the words that
    matched) and ``fit`` (what else counted). Your own files of a fitting mood come first, then the CC0 library, then
    the built-in beds; favourites go up, banned tracks are left out (and, ``no_credit``, the ones whose licence asks
    for a credit where nothing would print it)."""
    t = str(text or "").lower()
    score, why = {m: 0.0 for m in STYLES}, {m: [] for m in STYLES}
    for m, kws in KEYWORDS.items():
        for k in kws:
            if k in t:
                score[m] += 1.0 + 0.2 * len(k)
                why[m].append(k)
    for words, w in VIBES:
        hit = [k for k in words if k in t]
        if hit:
            for m, x in w.items():
                score[m] += x
                why[m].append(hit[0])
    for m, x in (STYLE_PRIOR.get(style or "") or {}).items():
        score[m] += x
    tags_hit = []
    for words, tags in TAG_WORDS:
        hit = [k for k in words if k in t]
        if hit:
            tags_hit.append((hit[0], set(tags)))
    e_want = target_energy(text, style, shot_s)
    bpm_want = target_bpm(shot_s) if need_beat or shot_s else None
    pf = prefs()
    fav, ban = set(pf["favourites"]), set(pf["banned"])
    same, recent_rank = _avoid(project, item, group, recent)
    out = []
    pool = tracks()
    allowed = [x for x in pool if x["id"] not in ban and x.get("path", "") not in ban] or pool
    if no_credit:
        allowed = [x for x in allowed if not x.get("credit")] or [x for x in pool if x["source"] == "builtin"]
    by_id = {x["id"]: x for x in pool}
    used_bpm = [float(by_id[k]["bpm"]) for k in same if k in by_id and by_id[k].get("bpm")]
    used_style = {by_id[k].get("style") for k in same if k in by_id} - {None, "builtin"}
    for tr in allowed:
        s = score.get(tr["mood"], 0.0) + {"file": 0.5, "library": 0.3}.get(tr["source"], 0.0)
        w = list(dict.fromkeys(why.get(tr["mood"]) or []))
        fit = []
        tset = set(tr.get("tags") or []) | {tr.get("style") or ""}
        for word, tags in tags_hit:
            if tset & tags:
                s += 2.0
                w.append(word)
        en = tr.get("energy") if tr.get("energy") is not None else BUILTIN_ENERGY.get(tr["mood"])
        if e_want is not None and en is not None:
            d = abs(float(en) - e_want)
            s += 1.5 * (1.0 - 2.0 * d)
            fit.append(f"energy {float(en):.2f} for {e_want:.2f}")
        bpm = tr.get("bpm")
        if need_beat:
            # the beat a cut follows is the one the tracker finds (a double-time 192 is no 96 for the reel)
            grid = float(tr.get("grid_bpm") or bpm or 0)
            if not (bpm and tr.get("steady")) or not GRID_BPM[0] <= grid <= GRID_BPM[1]:
                s -= 20.0
                fit.append("no steady beat to cut on")
            elif bpm_want:
                s += 1.0 - min(2.0, abs(grid - bpm_want) / 25.0)
                fit.append(f"{grid:.0f} BPM for cuts every ~{120.0 / bpm_want:.1f} s" if shot_s else
                           f"{grid:.0f} BPM")
            else:
                s += 0.5
                fit.append(f"{grid:.0f} BPM, steady")
        if min_duration and tr["source"] != "builtin" and tr.get("duration") and \
                float(tr["duration"]) < float(min_duration) and not tr.get("loop"):
            s -= 3.0
            fit.append(f"only {float(tr['duration']):.0f} s")
        if tr["id"] in fav or tr.get("path") in fav:
            s += 1.5
            fit.append("a favourite")
        if tr["id"] in same:
            s -= GROUP_PENALTY
            fit.append("another video of this group has it")
        else:
            if tr["id"] in recent_rank:
                k = recent_rank[tr["id"]]
                s -= 4.0 * (1.0 - k / max(1, recent))
                fit.append("one of your recent videos has it")
            # the group's videos differ in tempo and kind of music too
            if bpm and any(abs(float(bpm) - u) < 6.0 for u in used_bpm):
                s -= 1.0
                fit.append("a tempo another video of this group has")
            if tr.get("style") in used_style:
                s -= 0.5
        out.append(dict(tr, score=round(s, 2), why=list(dict.fromkeys(w)), fit=fit))
    out.sort(key=lambda x: (-x["score"], {"file": 0, "library": 1}.get(x["source"], 2), moods().index(x["mood"]),
                            x["id"]))
    return out[:n] if n else out


def choose(text="", style=None, n=None, project=None, item=None, group=None, record_pick=True, **kw):
    """``rank`` + note the best one as this video's pick (under a lock, so videos of a group made at the same time
    do not take the same track) -> the ranked list (its first is the pick)."""
    from . import oscompat
    os.makedirs(_home(), exist_ok=True)
    with open(os.path.join(_home(), HISTORY + ".lock"), "a") as lk:
        oscompat.lock(lk)
        try:
            ranked = rank(text, style, n, project=project, item=item, group=group, **kw)
            if record_pick and ranked:
                record(ranked[0]["id"], project=project, item=item, group=group, title=ranked[0].get("title"))
        finally:
            oscompat.unlock(lk)
    return ranked


def reason(t):
    """One plain line: why this track (her words, the fit, the licence)."""
    words = ", ".join(f"“{w}”" for w in (t.get("why") or [])[:3])
    bits = [f"matches {words}" if words else None] + [x for x in (t.get("fit") or [])
                                                      if "group" not in x and "recent" not in x][:2]
    who = f" — {t['artist']}" if t.get("artist") else ""
    lic = "" if t["source"] == "builtin" else f" ({t.get('license')})"
    return f"{t['title']}{who}: " + ("; ".join(b for b in bits if b) or f"a {t['mood']} track") + lic


def group_of(project_dir):
    """The group a project belongs to (a goal's videos / one request's batch: project.yaml ``group``) or None."""
    try:
        import yaml
        with open(os.path.join(project_dir, "project.yaml"), encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
        g = d.get("group")
        return str(g) if g else None
    except (OSError, ValueError, ImportError):
        return None


def path_of(track):
    """A ranked / picked track -> a playable file (a built-in made to 60 s for listening)."""
    tid = str((track or {}).get("track") or (track or {}).get("id") or "")
    if (track or {}).get("path") and os.path.exists(track["path"]):
        return track["path"]
    if tid.startswith("builtin:") or (track or {}).get("source") == "builtin":
        return make((track or {}).get("mood") or tid.split(":", 1)[-1], 60.0)
    if tid.startswith("lib:"):
        return resolve(tid)
    return None


def _key(mood, duration, seed):
    return hashlib.sha1(json.dumps([mood, round(float(duration), 2), int(seed), 1]).encode()).hexdigest()[:12]


def make(mood="calm", duration=60.0, out=None, seed=0):
    """Generate (or reuse the cached) built-in bed -> wav path."""
    from . import audio as A
    if out is None:
        out = os.path.join(_cache(), f"{mood}-{_key(mood, duration, seed)}.wav")
        if os.path.exists(out):
            return out
    tmp = out + ".part.wav"
    A.write_wav(tmp, generate(mood, duration, seed), SR)
    os.replace(tmp, out)
    return out


def detect_beat(path, sr=11025, lo_bpm=70, hi_bpm=180):
    """Beat grid of a music file -> (period s, phase s): Beat This! when its checkpoint is downloaded (phase on a
    downbeat), else onset strength (spectral flux) -> tempo by autocorrelation, phase by the comb that collects the
    most onsets. Cached by path + mtime. Used to put a film's cuts on the beat."""
    import subprocess
    from . import beatthis
    nn = beatthis.available()
    key = hashlib.sha1(json.dumps([os.path.abspath(path), os.path.getmtime(path), 2 if nn else 1]).encode()
                       ).hexdigest()[:12]
    cache = os.path.join(_cache(), f"beat-{key}.json")
    try:
        with open(cache, encoding="utf-8") as fh:
            c = json.load(fh)
        return float(c["period"]), float(c["phase"])
    except (OSError, ValueError, KeyError):
        pass
    if nn:                                          # Beat This! (vstudio.beatthis): phase on the first downbeat
        try:
            got = _beat_this_grid(path, lo_bpm, hi_bpm)
        except Exception:  # noqa: BLE001 - fall back to the onset comb below
            got = None
        if got:
            try:
                with open(cache, "w", encoding="utf-8") as fh:
                    json.dump(dict(period=got[0], phase=got[1], backend="beat_this"), fh)
            except OSError:
                pass
            return got
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-t", "90", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"could not read {os.path.basename(path)}: {r.stderr.decode('utf-8', 'replace')[-200:]}")
    x = np.frombuffer(r.stdout, dtype=np.float32)
    hop, n = 128, 1024
    if x.size < n * 8:
        raise ValueError(f"{os.path.basename(path)} is too short to find a beat")
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)) * 10)
    flux = np.maximum(np.diff(mag, axis=0), 0).sum(axis=1)
    flux = flux - np.convolve(flux, np.ones(16) / 16, mode="same")        # local mean out: onsets, not loudness
    flux = np.maximum(flux, 0)
    fps = sr / hop
    ac = np.correlate(flux, flux, mode="full")[flux.size - 1:]
    lags = np.arange(int(fps * 60 / hi_bpm), int(fps * 60 / lo_bpm) + 1)
    # a faint preference for ~110 bpm so a half / double tempo does not win on noise
    w = np.exp(-0.5 * (np.log2((60 * fps / lags) / 110.0) / 0.9) ** 2)
    lag = int(lags[np.argmax(ac[lags] * w)])
    # refine: the autocorrelation peak near 8 beats away pins the tempo 8x finer (no drift over a minute)
    lagf = float(lag)
    for mult in (4, 8, 16):
        c0 = int(round(lagf * mult))
        if c0 + 6 >= ac.size:
            break
        win = np.arange(c0 - 4, c0 + 5)
        pk = int(win[np.argmax(ac[win])])
        a, b, c = ac[pk - 1], ac[pk], ac[pk + 1]
        den = a - 2 * b + c
        lagf = (pk + (0.5 * (a - c) / den if den else 0.0)) / mult
    period = lagf / fps
    best, phase = -1.0, 0.0
    for k in range(int(lagf)):
        idx = np.arange(k, flux.size, lagf).astype(int)
        sc = float(flux[idx].sum())
        if sc > best:
            best, phase = sc, k / fps
    phase = (phase + (n / 2 + hop) / sr) % period            # frame index -> the time of the onset itself
    try:
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(dict(period=period, phase=phase), fh)
    except OSError:
        pass
    return round(period, 5), round(phase, 4)


def _beat_this_grid(path, lo_bpm, hi_bpm):
    """(period, phase) from Beat This! over the first 90 s: a least-squares line through the beats (one tempo; a
    double-time stretch thinned out), phase = the first downbeat modulo the period. None if no steady beat."""
    from . import beatthis
    from .audio import decode_audio
    from .beats import _fit
    x = decode_audio(str(path), sr=beatthis.SR, channels=1)[:, 0][:beatthis.SR * 90]
    b, d = beatthis.track(x, beatthis.SR)
    if len(b) < 8:
        return None
    ibi = float(np.median(np.diff(b)))
    keep = [b[0]]
    for t in b[1:]:
        if t - keep[-1] >= 0.7 * ibi:
            keep.append(t)
    period, offset, _res, _idx = _fit(np.asarray(keep))
    if not lo_bpm * 0.5 <= 60.0 / period <= hi_bpm * 2:
        return None
    anchor = float(d[0]) if len(d) else offset
    return round(float(period), 5), round(anchor % period, 4)


def beat_grid(spec):
    """(period s, phase s) of a music spec (a built-in mood: exact, from its tempo; a file: detect_beat) or None."""
    if not spec:
        return None
    s = str(spec)
    if s.startswith("builtin:"):
        s = s.split(":", 1)[1]
    if s in STYLES:
        return 60.0 / STYLES[s]["bpm"], 0.0
    if s.startswith("lib:"):
        t = library_track(s)
        if t and t.get("steady") and t.get("bpm_detected") and t.get("downbeats"):
            period = 60.0 / float(t["bpm_detected"])
            return round(period, 5), round(float(t["downbeats"][0]) % period, 4)
        try:
            s = resolve(s)
        except ValueError:
            return None
    p = os.path.expanduser(s)
    if os.path.exists(p):
        try:
            return detect_beat(p)
        except (RuntimeError, ValueError):
            return None
    return None


def resolve(spec, duration=60.0, seed=0, text=None):
    """``spec`` = an existing file | 'builtin:<mood>' | a mood | a library track title | None (mood from ``text``:
    your own track of that mood, else the built-in) -> a playable file path. Built-ins are generated to
    ``duration`` (cached). Anything else raises ValueError."""
    if spec and os.path.exists(os.path.expanduser(str(spec))):
        return os.path.abspath(os.path.expanduser(str(spec)))
    s = str(spec or "").strip()
    if s.startswith("builtin:"):
        s = s.split(":", 1)[1]
    if s in STYLES:
        return make(s, duration, seed=seed)
    if s.startswith("lib:"):
        t = next((x for x in library() if x["id"] == s), None)
        if not t:
            raise ValueError(f"no library track {s!r}")
        if not t["installed"]:
            raise ValueError(f"the music library is not downloaded yet ({t['title']}): Settings › Downloads, or "
                             "python -m vstudio.assets fetch music-library")
        return t["path"]
    if s:
        for t in tracks():
            if t["source"] in ("file", "library") and (t["title"] == s or os.path.basename(t["path"]) == s):
                return t["path"]
        raise ValueError(f"no music file, mood or library track called {spec!r} (moods: {', '.join(moods())})")
    m = mood_of(text or "")
    own = tracks(m)
    files = [t for t in own if t["source"] == "file"]
    if files:                                          # your own track of that mood first
        return files[int(seed) % len(files)]["path"]
    return make(m, duration, seed=seed)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m vstudio.music", description="Background music library.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list")
    a.add_argument("--mood", choices=moods())
    a.add_argument("--json", action="store_true")
    b = sub.add_parser("make")
    b.add_argument("--mood", default="calm", choices=moods())
    b.add_argument("--duration", type=float, default=60.0)
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("-o", "--out", required=True)
    lb = sub.add_parser("library")
    lb.add_argument("--json", action="store_true")
    pr = sub.add_parser("prefs")
    pr.add_argument("--favourite")
    pr.add_argument("--ban")
    pr.add_argument("--clear")
    c = sub.add_parser("pick")
    c.add_argument("text")
    c.add_argument("--duration", type=float, default=60.0)
    c.add_argument("-o", "--out")
    x = ap.parse_args(argv)
    if x.cmd == "list":
        rows = tracks(x.mood)
        if x.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for t in rows:
                print(f"{t['mood']:>7}  {t['source']:<7}  {t['title']}  ({t['license']})")
            if not dirs():
                print("  (no music folders yet: put licensed tracks in ~/Music/Reelfold or set persona music.dirs)")
    elif x.cmd == "library":
        rows = library()
        if x.json:
            print(json.dumps(dict(dir=library_dir(), tracks=rows, prefs=prefs(), problems=validate_library()),
                             ensure_ascii=False, indent=1))
        else:
            for t in rows:
                mark = "+" if t["installed"] else "-"
                print(f"{mark} {t['mood']:>6} {t['style'] or '':<11} {str(t['bpm'] or ''):>6} "
                      f"{t['title']} - {t['artist']} ({t['license']})")
            print(f"{sum(t['installed'] for t in rows)}/{len(rows)} installed in {library_dir() or '(not downloaded)'}")
    elif x.cmd == "prefs":
        d = prefs()
        if x.favourite:
            d = set_pref(x.favourite, favourite=True)
        if x.ban:
            d = set_pref(x.ban, banned=True)
        if x.clear:
            d = set_pref(x.clear, favourite=False, banned=False)
        print(json.dumps(d, indent=1))
    elif x.cmd == "make":
        print(make(x.mood, x.duration, x.out, x.seed))
    else:
        p = resolve(None, x.duration, text=x.text)
        if x.out:
            import shutil
            shutil.copy(p, x.out)
            p = x.out
        print(f"{mood_of(x.text)}: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

