"""Shot-to-shot colour match + film looks, baked into ONE 3D LUT per shot (a ``.cube`` read by ffmpeg's ``lut3d``,
an LGPL filter in the bundled build).

Why. ``match_exposure`` / ``deflicker`` even out brightness, but white balance, tint and saturation still jump between
drone shots flown at different times (a warm 20:59 sky, then a blue 22:16 one): at a dissolve the picture's colour
cast swings, which reads as cheap and trips the flicker QC's colour metric (``vstudio.flicker`` "colour"). Resolve
(Shot Match), Premiere (Auto Color), CapCut (colour match) all transfer colour statistics toward a reference shot; the
GPL ``color-matcher`` package can't be bundled, so this is our own closed-form transfer (MIT):

* statistics per shot: mean + covariance of 5 frames in BT.709 YCbCr (0-1);
* the film's reference: the medoid shot (the one closest to all others), or the shot the spec names;
* chroma (Cb, Cr): the MKL transform of Pitie & Kokaram ("The linear Monge-Kantorovitch linear colour mapping for
  example-based colour transfer", 2007) - T = Cs^-1/2 (Cs^1/2 Cr Cs^1/2)^1/2 Cs^-1/2 - with its eigenvalues clamped
  (0.8-1.25) and the mean shift capped, so a night shot next to a day shot keeps being a night shot;
* luma: Reinhard (mean + spread), the spread clamped (0.9-1.12) and the mean moved at most +-0.04;
* everything mixed at ``strength`` (default 0.6) toward the reference: the jump between shots gets smaller, the light
  of each shot stays its own.

Looks. Six film looks, our own procedural curves (MIT, no third-party LUT files): ``cinema-neutral``,
``kodak-2383-soft``, ``portra-warm``, ``fuji-cool``, ``mono-silver``, ``bleach-soft``; applied after the match at
``LOOK_STRENGTH`` (35 %) by default - never a teal-and-orange push, never a vignette (references/AESTHETICS.md P3).

    from vstudio import colormatch as CM
    st = {k: CM.stats(CM.sample(path, t0, dur)) for k, (path, t0, dur) in shots.items()}
    ref = CM.reference(st)                                   # the medoid shot's key
    table = CM.shot_lut(st[k], st[ref], grade_look="cinema-neutral")
    cube = CM.write_cube(table, cache_dir)                   # <sha1>.cube (content-addressed)
    vf = CM.lut3d_filter(cube)                               # lut3d=file='<path>':interp=tetrahedral
    CM.chroma_jump(st[a], st[b])                             # Cb / Cr mean step x 255 (the flicker QC's unit)

Tests: tests/test_colormatch.py (synthetic frames + a real ffmpeg lut3d render).
"""
import hashlib
import os
import subprocess

import numpy as np

LUT_N = 33                   # 33^3 grid: smooth enough for a gentle transfer, small file (~1 MB)
STRENGTH = 0.6               # how far each shot moves toward the reference
LOOK_STRENGTH = 0.35         # film looks are mixed in at 35 % (premium = barely there)
CHROMA_CAP = 0.06            # max Cb / Cr mean shift (0-1 units; x 255 = 15, the flicker QC colour unit)
LUMA_CAP = 0.04              # max luma mean shift
CHROMA_EIG = (0.8, 1.25)     # clamp of the MKL transform's eigenvalues (saturation change per axis)
LUMA_SPREAD = (0.9, 1.12)    # clamp of the luma spread ratio (contrast change)
SAMPLE_W = 160               # frames are measured at this width

_KR, _KB = 0.2126, 0.0722
_KG = 1 - _KR - _KB


# --------------------------------------------------------------------------------------------- colour spaces
def rgb_to_ycc(x):
    """RGB (..., 3) 0-1 -> BT.709 Y, Cb, Cr (Y 0-1, Cb / Cr centred on 0, +-0.5)."""
    x = np.asarray(x, np.float64)
    y = _KR * x[..., 0] + _KG * x[..., 1] + _KB * x[..., 2]
    return np.stack([y, (x[..., 2] - y) / (2 * (1 - _KB)), (x[..., 0] - y) / (2 * (1 - _KR))], -1)


def ycc_to_rgb(x):
    x = np.asarray(x, np.float64)
    y, cb, cr = x[..., 0], x[..., 1], x[..., 2]
    r = y + 2 * (1 - _KR) * cr
    b = y + 2 * (1 - _KB) * cb
    g = (y - _KR * r - _KB * b) / _KG
    return np.stack([r, g, b], -1)


# --------------------------------------------------------------------------------------------- statistics
def sample(path, t0=0.0, dur=None, n=5, vf=None):
    """``n`` RGB frames (float 0-1, SAMPLE_W wide) spread over [t0, t0 + dur] of a video (the middle of n equal parts:
    never the first / last frame, which a dissolve hides anyway). ``vf``: a filter run before the scale (a crop)."""
    from . import media
    if dur is None:
        dur = max(0.1, float(media.probe(path)["duration"] or 0) - t0)
    out = []
    for k in range(n):
        t = t0 + dur * (k + 0.5) / n
        chain = (vf + "," if vf else "") + f"scale={SAMPLE_W}:-2:flags=area,format=rgb24"
        r = subprocess.run([media.ffmpeg_bin(), "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", path,
                            "-frames:v", "1", "-vf", chain, "-f", "rawvideo", "-"], capture_output=True)
        if not r.stdout:
            continue
        a = np.frombuffer(r.stdout, np.uint8)
        h = a.size // (SAMPLE_W * 3)
        if h:
            out.append(a[:h * SAMPLE_W * 3].reshape(h, SAMPLE_W, 3).astype(np.float32) / 255.0)
    return out


def stats(frames):
    """Colour statistics of frames (a list of (H, W, 3) RGB 0-1 arrays, or one array) -> {mean [Y, Cb, Cr],
    cov (3x3), n}. Clipped pixels (blown highlights, crushed blacks) are left out: they carry no colour."""
    if isinstance(frames, np.ndarray) and frames.ndim == 3:
        frames = [frames]
    px = np.concatenate([np.asarray(f, np.float64).reshape(-1, 3) for f in frames]) if frames else np.zeros((0, 3))
    keep = (px.max(1) < 0.985) & (px.min(1) > 0.015)
    if keep.sum() > 64:
        px = px[keep]
    if len(px) < 2:
        return dict(mean=[0.5, 0.0, 0.0], cov=np.diag([0.04, 1e-3, 1e-3]).tolist(), n=0)
    y = rgb_to_ycc(px)
    return dict(mean=y.mean(0).tolist(), cov=np.cov(y.T).tolist(), n=int(len(px)))


def chroma_jump(a, b):
    """The colour-cast step between two shots: |mean Cb, Cr difference| x 255 (the flicker QC's colour unit)."""
    return float(np.hypot(*(np.asarray(a["mean"][1:]) - np.asarray(b["mean"][1:]))) * 255)


def distance(a, b):
    """How different two shots look: the chroma step + half the luma step (both x 255)."""
    return chroma_jump(a, b) + 0.5 * abs(a["mean"][0] - b["mean"][0]) * 255


def reference(st, prefer=None):
    """The film's reference shot among ``st`` ({key: stats}): ``prefer`` when it is a key, else the medoid (the shot
    with the smallest summed distance to all the others - a shot that looks like the film, not an outlier)."""
    keys = [k for k in st if st[k].get("n")]
    if not keys:
        return None
    if prefer in keys:
        return prefer
    return min(keys, key=lambda k: (sum(distance(st[k], st[j]) for j in keys), str(k)))


# --------------------------------------------------------------------------------------------- the transfer
def _sqrtm(m):
    w, v = np.linalg.eigh((m + m.T) / 2)
    return (v * np.sqrt(np.clip(w, 1e-9, None))) @ v.T


def mkl(cov_s, cov_r):
    """The linear Monge-Kantorovitch map (Pitie & Kokaram 2007) taking covariance ``cov_s`` to ``cov_r``: the
    symmetric T with T cov_s T = cov_r that moves colours the least."""
    cs, cr = np.asarray(cov_s, np.float64), np.asarray(cov_r, np.float64)
    a = _sqrtm(cs)
    w, v = np.linalg.eigh((a + a.T) / 2)
    ainv = (v / np.clip(w, 1e-9, None)) @ v.T
    return ainv @ _sqrtm(a @ cr @ a) @ ainv


def _clamp_sym(t, lo, hi):
    w, v = np.linalg.eigh((t + t.T) / 2)
    return (v * np.clip(w, lo, hi)) @ v.T


def _cap(vec, cap):
    vec = np.asarray(vec, np.float64)
    n = float(np.linalg.norm(vec))
    return vec * (cap / n) if n > cap else vec


def transfer(src, ref, strength=STRENGTH):
    """The colour map of a shot with statistics ``src`` toward ``ref`` -> f(rgb (..., 3)) -> rgb, clamped and mixed
    at ``strength`` (module doc). Identity when either has no statistics or strength is 0."""
    if strength <= 0 or not src.get("n") or not ref.get("n"):
        return lambda x: np.asarray(x, np.float64)
    ms, mr = np.asarray(src["mean"]), np.asarray(ref["mean"])
    cs, cr = np.asarray(src["cov"]), np.asarray(ref["cov"])
    t = _clamp_sym(mkl(cs[1:, 1:] + np.eye(2) * 1e-6, cr[1:, 1:] + np.eye(2) * 1e-6), *CHROMA_EIG)
    dc = _cap(mr[1:] - ms[1:], CHROMA_CAP)
    k = float(np.clip(np.sqrt(max(cr[0, 0], 1e-9) / max(cs[0, 0], 1e-9)), *LUMA_SPREAD))
    dy = float(np.clip(mr[0] - ms[0], -LUMA_CAP, LUMA_CAP))

    def f(x):
        x = np.asarray(x, np.float64)
        y = rgb_to_ycc(x)
        o = np.empty_like(y)
        o[..., 0] = (y[..., 0] - ms[0]) * k + ms[0] + dy
        o[..., 1:] = (y[..., 1:] - ms[1:]) @ t.T + ms[1:] + dc
        return x + strength * (ycc_to_rgb(o) - x)
    return f


# --------------------------------------------------------------------------------------------- film looks
def _s_curve(x, g):
    """A mild filmic S (logistic, end points kept): g ~ 1.4 soft, 2.6 punchy."""
    lo, hi = 1 / (1 + np.exp(g / 2)), 1 / (1 + np.exp(-g / 2))
    return (1 / (1 + np.exp(-g * (x - 0.5))) - lo) / (hi - lo)


def _sat(x, s):
    y = (_KR * x[..., 0] + _KG * x[..., 1] + _KB * x[..., 2])[..., None]
    return y + (x - y) * s


def _shoulder(x, knee=0.82):
    """Soft highlight roll-off above ``knee`` (lights don't clip hard)."""
    over = np.clip(x - knee, 0, None)
    return np.where(x > knee, knee + over / (1 + over / (1 - knee) * 0.6), x)


def _tint(x, shadows=(0, 0, 0), highs=(0, 0, 0)):
    y = (_KR * x[..., 0] + _KG * x[..., 1] + _KB * x[..., 2])[..., None]
    w_s = np.clip(1 - y * 2, 0, 1)
    w_h = np.clip(y * 2 - 1, 0, 1)
    return x + w_s * np.asarray(shadows) + w_h * np.asarray(highs)


def _look_cinema_neutral(x):
    return _sat(_shoulder(_s_curve(x, 1.8)), 0.96)


def _look_kodak_2383_soft(x):
    x = _s_curve(x, 2.3)
    x = _tint(x, shadows=(-0.004, 0.0, 0.008), highs=(0.018, 0.006, -0.02))
    return _sat(_shoulder(x), 0.92)


def _look_portra_warm(x):
    x = 0.03 + 0.97 * _s_curve(x, 1.4)                        # lifted, soft blacks
    x = _tint(x, shadows=(0.006, 0.002, -0.004), highs=(0.02, 0.008, -0.018))
    return _sat(_shoulder(x), 0.9)


def _look_fuji_cool(x):
    x = _s_curve(x, 1.8)
    x = _tint(x, shadows=(-0.006, 0.004, 0.006), highs=(-0.01, 0.0, 0.016))
    return _sat(_shoulder(x), 0.95)


def _look_mono_silver(x):
    y = _KR * x[..., 0] + _KG * x[..., 1] + _KB * x[..., 2]
    y = _shoulder(_s_curve(y, 2.2))
    return np.stack([y * 1.0, y * 0.994, y * 0.982], -1)


def _look_bleach_soft(x):
    return _sat(_shoulder(_s_curve(x, 2.6)), 0.74)


LOOKS = {
    "cinema-neutral": _look_cinema_neutral,
    "kodak-2383-soft": _look_kodak_2383_soft,
    "portra-warm": _look_portra_warm,
    "fuji-cool": _look_fuji_cool,
    "mono-silver": _look_mono_silver,
    "bleach-soft": _look_bleach_soft,
}
LOOK_NAMES = tuple(LOOKS)
LOOK_LABELS = {
    "cinema-neutral": ("Cinema neutral", "电影中性"),
    "kodak-2383-soft": ("Kodak 2383 print, soft", "柯达 2383 胶片（柔）"),
    "portra-warm": ("Portra warm", "Portra 暖调"),
    "fuji-cool": ("Fuji cool", "富士冷调"),
    "mono-silver": ("Silver mono", "银盐黑白"),
    "bleach-soft": ("Soft bleach bypass", "柔和漂白"),
}
_ALIASES = {"none": None, "off": None, "": None, "neutral": "cinema-neutral", "kodak": "kodak-2383-soft",
            "2383": "kodak-2383-soft", "portra": "portra-warm", "fuji": "fuji-cool", "mono": "mono-silver",
            "bw": "mono-silver", "black-and-white": "mono-silver", "bleach": "bleach-soft",
            "电影": "cinema-neutral", "胶片": "kodak-2383-soft", "暖调": "portra-warm", "冷调": "fuji-cool",
            "黑白": "mono-silver"}


def look_name(name):
    """A look's canonical name (aliases: kodak, portra, 黑白 ...); None = no look. Unknown -> ValueError."""
    if name is None or name is False:
        return None
    n = str(name).strip().lower()
    if n.startswith("look:"):
        n = n[5:]
    if n in LOOKS:
        return n
    if n in _ALIASES:
        return _ALIASES[n]
    raise ValueError(f"unknown look {name!r}: one of {', '.join(LOOK_NAMES)} or none")


def look(name, strength=LOOK_STRENGTH):
    """f(rgb) -> rgb of a film look mixed in at ``strength``; identity for None."""
    n = look_name(name)
    if n is None or strength <= 0:
        return lambda x: np.asarray(x, np.float64)
    fn = LOOKS[n]
    return lambda x: np.asarray(x, np.float64) + strength * (fn(np.asarray(x, np.float64)) - np.asarray(x, np.float64))


# --------------------------------------------------------------------------------------------- LUTs
def identity(n=LUT_N):
    """(n, n, n, 3) grid indexed [b, g, r] (the .cube order: red changes fastest)."""
    v = np.linspace(0, 1, n)
    b, g, r = np.meshgrid(v, v, v, indexing="ij")
    return np.stack([r, g, b], -1)


def bake(*fns, n=LUT_N):
    """The composition fns[-1](...fns[0](rgb)) sampled on an n^3 grid, clipped to 0-1."""
    t = identity(n)
    for f in fns:
        t = f(t)
    return np.clip(t, 0.0, 1.0)


def shot_lut(src, ref, grade_look=None, strength=STRENGTH, look_strength=LOOK_STRENGTH, n=LUT_N):
    """The one LUT of a shot: colour match toward ``ref`` (``src`` / ``ref`` = stats; None = no match), then the look."""
    fns = []
    if src is not None and ref is not None and src is not ref:
        fns.append(transfer(src, ref, strength))
    fns.append(look(grade_look, look_strength))
    return bake(*fns, n=n)


def is_identity(table, tol=1.5 / 255):
    return bool(np.abs(table - identity(table.shape[0])).max() <= tol)


def apply(table, rgb):
    """A LUT applied to an image in numpy (trilinear) - photos and stills, which never pass through ffmpeg.
    ``rgb``: float (H, W, 3) in 0-255 or 0-1 (returned in the same scale)."""
    a = np.asarray(rgb, np.float32)
    scale = 255.0 if a.max() > 1.5 else 1.0
    n = table.shape[0]
    p = np.clip(a / scale, 0, 1) * (n - 1)
    i0 = np.minimum(p.astype(np.int32), n - 2)
    f = p - i0
    r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]
    fr, fg, fb = f[..., 0:1], f[..., 1:2], f[..., 2:3]
    tb = table.astype(np.float32)

    def at(db, dg, dr):
        return tb[b0 + db, g0 + dg, r0 + dr]
    c00 = at(0, 0, 0) * (1 - fr) + at(0, 0, 1) * fr
    c01 = at(0, 1, 0) * (1 - fr) + at(0, 1, 1) * fr
    c10 = at(1, 0, 0) * (1 - fr) + at(1, 0, 1) * fr
    c11 = at(1, 1, 0) * (1 - fr) + at(1, 1, 1) * fr
    c0 = c00 * (1 - fg) + c01 * fg
    c1 = c10 * (1 - fg) + c11 * fg
    return (c0 * (1 - fb) + c1 * fb) * scale


def cube_text(table, title="vstudio colour match"):
    n = table.shape[0]
    lines = [f'TITLE "{title}"', f"LUT_3D_SIZE {n}", "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0"]
    flat = table.reshape(-1, 3)
    lines += [f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in flat]
    return "\n".join(lines) + "\n"


def write_cube(table, folder, title="vstudio colour match"):
    """Write ``table`` as ``<sha1 of its content>.cube`` in ``folder`` (once) -> the path."""
    txt = cube_text(table, title)
    os.makedirs(folder, exist_ok=True)
    p = os.path.join(folder, hashlib.sha1(txt.encode()).hexdigest()[:16] + ".cube")
    if not os.path.exists(p):
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            f.write(txt)
        os.replace(tmp, p)
    return p


def read_cube(path):
    """A .cube file -> (n, n, n, 3) table (for tests and her own looks)."""
    n, rows = None, []
    with open(path) as f:
        for ln in f:
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("LUT_3D_SIZE"):
                n = int(s.split()[1])
            elif s[0].isdigit() or s[0] in "-.":
                rows.append([float(v) for v in s.split()[:3]])
    return np.asarray(rows, np.float64).reshape(n, n, n, 3)


def lut3d_filter(path):
    """The ffmpeg filter that applies a .cube file: the path quoted for the filtergraph (single quotes keep spaces and
    commas literal; a drive colon is escaped for the option parser: C\\:/Users/...; backslashes become /)."""
    p = os.path.abspath(path).replace("\\", "/")
    if "'" in p:
        raise ValueError(f"a LUT path with a quote cannot be passed to lut3d: {p!r}")
    return "lut3d=file='" + p.replace(":", "\\:") + "':interp=tetrahedral"
