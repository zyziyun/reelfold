"""LGPL-only ffmpeg filtergraphs: the grade, blur and denoise the recipes use, without GPL filters.

The desk app bundles an LGPL ffmpeg (``--disable-gpl``): ``eq``, ``hqdn3d``, ``boxblur``, ``smartblur``, ``zscale``,
``delogo``, ``perspective`` ... are not in it (``GPL_ONLY``), and a graph naming one fails the whole render with
"No such filter". Every graph the library and the workflows build goes through these helpers, and a graph that
comes from a user / persona / old project config (``grade: "eq=brightness=..."``) is translated at run time:

    from vstudio import ffmpeg_filters as F
    F.grade(brightness=0.05, contrast=1.12, saturation=1.18, gamma=1.04)   # -> "format=...,lutyuv=..."
    F.blur(sigma=30)                                                        # -> "gblur=sigma=30"
    F.lgpl("hqdn3d=1.2:1.2:3:3,eq=contrast=1.06:brightness=0.015")[0]      # -> an LGPL graph, same look
    F.filter_names("[0:v]scale=1280:-2,eq=gamma=1.1[v]")                   # -> ["scale", "eq"]

``grade`` reproduces ffmpeg's ``eq`` exactly on 8-bit video (the same per-plane lookup table: contrast / brightness /
gamma on luma, saturation on chroma) with ``lutyuv``, after a ``format`` with eq's own 8-bit pixel formats so the
lookup sees the values eq would have. ``tests/test_ffmpeg_filters.py`` renders both graphs and compares them.
"""
import math
import re
import struct

# filters a GPL ffmpeg has and the bundled LGPL build (apps/desk/packaging/ffmpeg/filters.txt) does not
GPL_ONLY = frozenset({
    "blackframe", "boxblur", "colormatrix", "cover_rect", "cropdetect", "delogo", "eq", "find_rect", "fspp",
    "histeq", "hqdn3d", "interlace", "kerndeint", "mcdeint", "mpdecimate", "nnedi", "owdenoise", "perspective",
    "phase", "pp", "pp7", "pullup", "repeatfields", "sab", "signature", "smartblur", "spp", "stereo3d",
    "super2xsai", "tinterlace", "uspp", "vaguedenoiser", "vidstabdetect", "vidstabtransform", "zscale",
    "frei0r", "frei0r_src", "libvmaf", "ocr",
})
# filters lgpl() rewrites (the others in GPL_ONLY have no LGPL look-alike and must not be emitted)
TRANSLATED = ("eq", "hqdn3d", "boxblur", "smartblur")
# eq's own pixel formats (libavfilter/vf_eq.c): the lutyuv below sees the 8-bit values eq would have seen
EQ_FORMATS = "yuv420p|yuv422p|yuv444p|yuv410p|yuv411p|yuv440p|yuvj420p|yuvj422p|yuvj444p|yuvj440p|gray"
_EQ_KEYS = ("contrast", "brightness", "saturation", "gamma", "gamma_r", "gamma_g", "gamma_b", "gamma_weight", "eval")
_EQ_DEFAULT = dict(contrast=1.0, brightness=0.0, saturation=1.0, gamma=1.0, gamma_r=1.0, gamma_g=1.0, gamma_b=1.0,
                   gamma_weight=1.0)
_EQ_RANGE = dict(contrast=(-1000.0, 1000.0), brightness=(-1.0, 1.0), saturation=(0.0, 3.0), gamma=(0.1, 10.0),
                 gamma_r=(0.1, 10.0), gamma_g=(0.1, 10.0), gamma_b=(0.1, 10.0), gamma_weight=(0.0, 1.0))
_FILTER_RE = re.compile(r"^(\s*(?:\[[^\]]*\]\s*)*)([A-Za-z0-9_]+)(@[A-Za-z0-9_]+)?(?:=(.*?))?((?:\s*\[[^\]]*\])*\s*)$",
                        re.S)


# ------------------------------------------------------------------ filtergraph syntax
def split_top(s, sep):
    """Split ``s`` on ``sep`` outside quotes, brackets and backslash escapes (filtergraph syntax)."""
    out, cur, quote, depth, i = [], [], False, 0, 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            cur.append(s[i:i + 2])
            i += 2
            continue
        if c == "'":
            quote = not quote
        elif not quote and c in "[(":
            depth += 1
        elif not quote and c in "])":
            depth -= 1
        if c == sep and not quote and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append("".join(cur))
    return out


def _filters(graph):
    """-> [[(lead, name, inst, args, tail), ...] per chain] (None for a piece that is not a filter)."""
    out = []
    for chain in split_top(graph, ";"):
        row = []
        for f in split_top(chain, ","):
            m = _FILTER_RE.match(f)
            row.append((m.group(1), m.group(2), m.group(3) or "", m.group(4), m.group(5)) if m and f.strip() else
                       (f, None, "", None, ""))
        out.append(row)
    return out


def filter_names(graph):
    """Every filter name in ``graph``, in order (pad labels, options and quoted expressions skipped)."""
    return [p[1] for row in _filters(graph or "") for p in row if p[1]]


def _num(v, default=None):
    v = (v or "").strip().strip("'\"")
    try:
        x = float(v)
    except ValueError:
        return default
    return x if math.isfinite(x) else default


def _opts(args, keys):
    """``a=1:b=2`` / ``1:2`` (positional in ``keys`` order) -> {key: raw value}; unknown keys kept as given."""
    out, pos = {}, 0
    for part in split_top(args or "", ":"):
        if not part.strip():
            continue
        k, eq_, v = part.partition("=")
        if eq_:
            out[k.strip()] = v
        else:
            if pos < len(keys):
                out[keys[pos]] = k
            pos += 1
    return out


def _f(x):
    return f"{x:.6g}"


# ------------------------------------------------------------------ builders
def grade(brightness=0.0, contrast=1.0, saturation=1.0, gamma=1.0, gamma_r=1.0, gamma_g=1.0, gamma_b=1.0,
          gamma_weight=1.0):
    """ffmpeg ``eq`` (same options, same maths) as an LGPL graph: ``format`` (eq's 8-bit formats) + ``lutyuv``.
    The identity grade -> ``"null"``."""
    # vf_eq.c keeps every option as av_clipf(): float precision (-0.07 -> -0.0700000003 decides a rounding)
    vals = {k: _f32(v) for k, v in dict(brightness=brightness, contrast=contrast, saturation=saturation, gamma=gamma,
                                         gamma_r=gamma_r, gamma_g=gamma_g, gamma_b=gamma_b,
                                         gamma_weight=gamma_weight).items()}
    for k, (lo, hi) in _EQ_RANGE.items():                  # eq's own option ranges
        vals[k] = min(hi, max(lo, vals[k]))
    if all(abs(vals[k] - _EQ_DEFAULT[k]) < 1e-9 for k in vals):
        return "null"
    gw = min(1.0, max(0.0, vals["gamma_weight"]))
    # vf_eq.c set_gamma: luma gamma * gamma_g; U: sqrt(gamma_b / gamma_g); V: sqrt(gamma_r / gamma_g)
    gy = vals["gamma"] * vals["gamma_g"]
    gu = math.sqrt(vals["gamma_b"] / vals["gamma_g"])
    gv = math.sqrt(vals["gamma_r"] / vals["gamma_g"])
    # every plane spelled out: lutyuv's default is clipval (TV range), eq leaves an untouched plane alone
    opts = [f"y='{_plane(vals['contrast'], vals['brightness'], gy, gw)}'",
            f"u='{_plane(vals['saturation'], 0.0, gu, gw)}'", f"v='{_plane(vals['saturation'], 0.0, gv, gw)}'"]
    return f"format=pix_fmts={EQ_FORMATS},lutyuv=" + ":".join(opts)


def _f32(x):
    return struct.unpack("f", struct.pack("f", float(x)))[0]


def _plane(contrast, brightness, gamma, gw):
    """vf_eq.c create_lut for one plane as a lutyuv expression: v = c*(x-0.5)+0.5+b; v<=0 -> 0; else
    v = v*(1-gw) + v^(1/gamma)*gw; out = min(max, 256*v). The full scale is 255 (8-bit after EQ_FORMATS);
    ``minval``/``maxval`` give it for other depths (limited range: minval = 16 << (depth-8))."""
    fs = "if(minval,minval*16-1,maxval)"
    if contrast == 1 and brightness == 0 and gamma == 1:
        return "val"                                       # eq leaves this plane untouched
    if gamma == 1 and abs(contrast) < 8:
        # vf_eq.c check_values: gamma 1 -> process_c, fixed point: ((x * c) >> 12) + b, clipped to 0..255
        ci = int(contrast * 256 * 16)
        bi = int(int(100.0 * brightness + 100.0) * 511 / 200) - 128 - int(ci / 32)
        return f"clip(val*{ci}/4096{'+' if bi >= 0 else '-'}{abs(bi)}*({fs}+1)/256,0,{fs})"
    k = 0.5 + brightness
    x = f"({_f(contrast)}*(val/{fs}-0.5){'+' if k >= 0 else '-'}{_f(abs(k))})"
    if gamma == 1 or gw == 0:
        v = x
    elif gw >= 1:
        v = f"pow({x},{_f(1 / gamma)})"
    else:
        v = f"({x}*{_f(1 - gw)}+pow({x},{_f(1 / gamma)})*{_f(gw)})"
    return f"if(lte({x},0),0,min({fs},({fs}+1)*{v}))"


def blur(sigma, steps=None):
    """A Gaussian blur (``gblur``, LGPL): what the recipes used ``boxblur`` for."""
    s = max(0.01, float(sigma))
    return f"gblur=sigma={_f(s)}" + (f":steps={int(steps)}" if steps else "")


def box_blur(radius, power=2):
    """``boxblur=radius:power`` as a ``gblur`` of the same spread (a box of radius r has variance r(r+1)/3 per
    pass; ``power`` passes add up)."""
    r, p = max(0.0, float(radius)), max(1, int(power))
    return blur(math.sqrt(p * r * (r + 1) / 3.0) if r else 0.01)


def denoise(strength=1.0):
    """A light spatial denoise (``bilateral``, LGPL) where the recipes used ``hqdn3d``. ``strength`` 1 ~ hqdn3d's
    defaults (4:3:6:4.5), so ``hqdn3d=1.2:1.2:3:3`` (a polish pass) is ~0.3. Spatial on purpose: a temporal one
    (atadenoise) never returns a single frame on ffmpeg 6.1 (a cover graded from one raw frame hangs)."""
    s = min(4.0, max(0.05, float(strength)))
    return f"bilateral=sigmaS={_f(0.5 + 1.5 * s)}:sigmaR={_f(0.02 + 0.08 * s)}"


def dim(brightness):
    """Darken / lift a background fill (what ``eq=brightness=x`` did there)."""
    return grade(brightness=brightness)


def retime(src_fps, speed, fps, tol=0.02, slowmo="mci"):
    """``setpts`` (speed) + a frame-rate change to ``fps`` with an even cadence.

    ``fps=`` alone keeps the nearest source frame: when (source fps x speed) / fps is not a whole number (a 59.94p
    drone clip at 1.2x -> 72 fps -> 30 keeps 2, 3, 2, 2, 3 ... frames apart; 29.97p at 1.3x drops every 4th) the
    motion stutters - an aerial pan visibly judders. A whole ratio (60p at 1x / 0.5x, 30p at 1x) decimates cleanly
    with ``fps``; anything else is resampled by ``framerate`` (each output frame blends the two source frames
    around its time), which keeps the motion even.

    Slow motion that needs more frames than the source has (30p at 0.5x, 60p at 0.25x into 30 fps): motion-compensated
    ``minterpolate`` (``slowmo="mci"``, LGPL, in the bundled build) - the FALLBACK for RIFE (``vstudio.rife.slowmo``,
    which callers use first when ``rife.available()``); ``slowmo="blend"`` keeps the old frame blend."""
    speed = float(speed or 1.0)
    src = float(src_fps or 0) or float(fps)
    head = "" if abs(speed - 1.0) < 1e-6 else f"setpts=PTS/{speed:g},"
    r = src * speed / float(fps)
    if r >= 1 - tol and abs(r - round(r)) <= tol * round(r):
        return f"{head}fps={fps:g}"
    if r < 1 - tol and slowmo == "mci":
        return f"{head}minterpolate=fps={fps:g}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1:scd=none"
    return f"{head}framerate=fps={fps:g}:interp_start=0:interp_end=255:scene=100"


# ------------------------------------------------------------------ translation
def translate(name, args):
    """One GPL filter (name, raw option string) -> an LGPL graph piece, or None (no look-alike / options that
    are expressions, not numbers)."""
    if name == "eq":
        o = _opts(args, _EQ_KEYS)
        if o.pop("eval", "init") not in ("init", "'init'"):
            return None
        kw = {}
        for k, v in o.items():
            if k not in _EQ_DEFAULT:
                return None
            x = _num(v)
            if x is None:
                return None
            kw[k] = x
        return grade(**kw)
    if name == "hqdn3d":
        o = _opts(args, ("luma_spatial", "chroma_spatial", "luma_tmp", "chroma_tmp"))
        ls = _num(o.get("luma_spatial"), 4.0)
        return denoise(ls / 4.0 if ls is not None else 1.0)
    if name == "boxblur":
        o = _opts(args, ("luma_radius", "luma_power", "chroma_radius", "chroma_power", "alpha_radius", "alpha_power"))
        r = _num(o.get("luma_radius", o.get("lr")), None)
        p = _num(o.get("luma_power", o.get("lp")), 2.0)
        return box_blur(r if r is not None else 10, p or 2)
    if name == "smartblur":
        o = _opts(args, ("luma_radius", "luma_strength", "luma_threshold"))
        r = _num(o.get("luma_radius", o.get("lr")), 1.0) or 1.0
        s = _num(o.get("luma_strength", o.get("ls")), 1.0)
        s = 1.0 if s is None else s
        if s > 0:
            return blur(r * s / 2.0)
        if s < 0:
            return f"unsharp=5:5:{_f(min(1.5, -s * 1.5))}:5:5:0"
        return "null"
    return None


def lgpl(graph, available=None):
    """``graph`` with every GPL filter of TRANSLATED rewritten to its LGPL look-alike -> (graph, [rewritten names]).
    ``available``: only rewrite filters missing from this set (a binary's filter list); None = rewrite always.
    A filter that cannot be translated is kept as it is."""
    if not graph or not any(t in graph for t in TRANSLATED):
        return graph, []
    done, chains = [], []
    for row in _filters(graph):
        parts = []
        for lead, name, inst, args, tail in row:
            if name is None:
                parts.append(lead)
                continue
            piece = f"{lead}{name}{inst}" + (f"={args}" if args is not None else "") + tail
            if name in TRANSLATED and (available is None or name not in available):
                t = translate(name, args)
                if t is not None:
                    done.append(name)
                    piece = f"{lead}{t}{tail}"
            parts.append(piece)
        chains.append(",".join(parts))
    return ";".join(chains), done


def lgpl_graph(graph):
    """A user / config grade at the point it is used: a filter string (``"eq=..."`` translated, ``lgpl(graph)[0]``)
    or a dict of eq options (``{brightness: -0.06, contrast: 1.08}`` -> ``grade(**d)``). None / "" -> ""."""
    if isinstance(graph, dict):
        return grade(**{k: float(v) for k, v in graph.items()})
    return lgpl(graph)[0] if graph else ""


# the talking-head vertical polish grade (was "hqdn3d=1.2:1.2:3:3,eq=contrast=1.06:brightness=0.015:saturation=1.07:
# gamma=1.02,colorbalance=rs=-0.02:bs=0.015:rm=-0.01,cas=0.45")
DEFAULT_TH_GRADE = (f"{denoise(0.3)},{grade(contrast=1.06, brightness=0.015, saturation=1.07, gamma=1.02)},"
                    "colorbalance=rs=-0.02:bs=0.015:rm=-0.01,cas=0.45")

FILTER_ARGS = ("-vf", "-filter:v", "-filter_complex", "-af", "-filter:a")


def portable_argv(cmd, available):
    """An ffmpeg argv with its -vf / -filter_complex values passed through ``lgpl(.., available)`` -> (argv, names);
    the argv itself when nothing changed."""
    if not any(a in FILTER_ARGS for a in cmd):
        return cmd, []
    out, done = list(cmd), []
    for i, a in enumerate(out[:-1]):
        if a in FILTER_ARGS and isinstance(out[i + 1], str):
            out[i + 1], d = lgpl(out[i + 1], available)
            done += d
    return (out, done) if done else (cmd, [])


__all__ = ["GPL_ONLY", "TRANSLATED", "grade", "blur", "box_blur", "denoise", "dim", "translate", "lgpl", "lgpl_graph",
           "filter_names", "split_top", "portable_argv"]
