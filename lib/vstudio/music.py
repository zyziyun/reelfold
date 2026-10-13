"""Background music library: built-in beds generated from code (no third-party rights at all) + your own folders.

    from vstudio import music
    music.moods()                                   # ['calm', 'warm', 'bright', 'tech', 'story']
    music.mood_of("加一个轻的背景音乐，温暖一点")       # -> 'warm'
    path = music.resolve("calm", duration=95)       # a generated, cached 95 s bed (48 kHz wav, fades in / out)
    path = music.resolve("~/Music/Reelfold/x.mp3")  # a file passes through
    music.tracks()                                  # built-ins + files in your music folders (with mood / license)

    python -m vstudio.music list [--mood calm]
    python -m vstudio.music make --mood warm --duration 60 -o bed.wav [--seed 2]
    python -m vstudio.music pick "轻松一点的背景音乐" --duration 60 [-o bed.wav]

Built-in moods are synthesised here (FM e-piano, pads, Karplus-Strong plucks, sine bass, soft drums, a small
reverb), so they are free to use anywhere, commercially too. They are calm, simple beds meant to sit at -30 LUFS
under a voice, not foreground music. For real songs put files you have the rights to in a music folder:
``~/Music/Reelfold`` or persona ``music.dirs`` / env ``VSTUDIO_MUSIC_DIRS`` (os.pathsep-separated). A sidecar
``<file>.json`` {mood, license, source, title} labels a track; otherwise the mood is guessed from the file name.
Mixing and ducking under the voice: ``audio.mix_bed`` (output edit effect ``music-bed``, polish ``--music``).
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


def tracks(mood=None):
    """Built-in moods + files in your music folders: [{id, title, mood, source builtin|file, path?, license}]."""
    out = [dict(id=f"builtin:{m}", title=s["en"], title_zh=s["zh"], mood=m, source="builtin", bpm=s["bpm"],
                license="generated by Reelfold (MIT), free for any use") for m, s in STYLES.items()]
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


def rank(text="", style=None, n=None):
    """The library ranked for a request: ``text`` (her words, the title), ``style`` (a vlog style: calm / fun) ->
    tracks, best first, each with ``score`` and ``why`` (the words that matched). Your own files of a fitting mood
    come before the built-in of that mood."""
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
    out = []
    for tr in tracks():
        s = score.get(tr["mood"], 0.0) + (0.5 if tr["source"] == "file" else 0.0)
        out.append(dict(tr, score=round(s, 2), why=list(dict.fromkeys(why.get(tr["mood"]) or []))))
    out.sort(key=lambda x: (-x["score"], 0 if x["source"] == "file" else 1, moods().index(x["mood"])))
    return out[:n] if n else out


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
    if s:
        for t in tracks():
            if t["source"] == "file" and (t["title"] == s or os.path.basename(t["path"]) == s):
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

