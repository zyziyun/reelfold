#!/usr/bin/env python3
"""Every ffmpeg filter the engine can emit must exist in the desk app's bundled LGPL ffmpeg.

The bundled build (conda-forge ffmpeg ``lgpl`` variant, apps/desk/packaging/ffmpeg/<target>.txt) has no GPL filters
(eq, hqdn3d, boxblur, smartblur, zscale ...); a graph naming one stops a render with "No such filter". This check:

  1. scans the string literals of the engine's code (lib/vstudio, workflows/*/scripts, apps/desk/engine) for
     filtergraph tokens (``name=``, ``name,``, ``name[``, ``name;`` after a graph separator) and runs the graph
     builders (vstudio.ffmpeg_filters, the vlog / cut grade and fit chains, the translation of legacy ``eq=`` strings);
  2. fails on a filter that is not in the bundled build's list (apps/desk/packaging/ffmpeg/filters.txt, a snapshot of
     ``ffmpeg -filters`` of the darwin-arm64 build) unless it is gated on ``media.has_filter`` (GATED);
  3. keeps apps/desk/packaging/ffmpeg/engine-filters.txt = the filters the engine emits (``--write`` regenerates it);
     the runtime bundler (apps/desk/scripts/runtime/bundle.mjs verify) checks each built binary has all of them.

    python3 scripts/check_ffmpeg_filters.py                  # check (exit 1 on a missing filter / stale list)
    python3 scripts/check_ffmpeg_filters.py --write          # regenerate engine-filters.txt
    python3 scripts/check_ffmpeg_filters.py --snapshot FFMPEG    # refresh filters.txt from a bundled binary
    python3 scripts/check_ffmpeg_filters.py --binary FFMPEG      # this binary has every engine filter (bundle.mjs)
"""
import argparse
import ast
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "apps" / "desk" / "packaging" / "ffmpeg"
BUNDLED = PKG / "filters.txt"
ENGINE = PKG / "engine-filters.txt"
SCAN = ["lib/vstudio", "workflows/*/scripts", "apps/desk/engine/desk_engine"]
SKIP = {"lib/vstudio/ffmpeg_filters.py"}     # the translator names GPL filters on purpose; its output is exercised
# a GPL filter used only behind media.has_filter(): file -> {filter: why}
GATED = {"lib/vstudio/media.py": {"zscale": "hdr_to_sdr_args: only when has_filter('zscale'), else libplacebo"}}
# a graph token: after the start / a graph separator, followed by options, a pad label or the next filter
TOKEN = re.compile(r"(?:^|(?<=[,;\]\"'|]))([a-z][a-z0-9_]{1,30})(?:@[a-z0-9_]+)?(?==|,|\[|;|$)")
# literals that only look like a graph (an ffmpeg CLI option / codec list), never a filter
NOT_GRAPH = re.compile(r"^-|^[a-z0-9_]+$")


def read_list(path):
    if not path.exists():
        return set()
    return {ln.split("#", 1)[0].strip() for ln in path.read_text().splitlines()} - {""}


def ffmpeg_filters(binary):
    out = subprocess.run([binary, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=60).stdout
    names = set()
    for line in out.splitlines():
        m = re.match(r"^\s*[TSCA.|]{2,3}\s+([A-Za-z0-9_]+)\s", line)
        if m:
            names.add(m.group(1))
    return names


def known():
    """Every filter name a full ffmpeg has (the bundled list + the GPL-only ones)."""
    sys.path.insert(0, str(ROOT / "lib"))
    from vstudio import ffmpeg_filters as F
    return read_list(BUNDLED) | set(F.GPL_ONLY)


def _strings(path):
    """String literals of a Python file (f-string constant parts each on their own), with line numbers."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    except (SyntaxError, UnicodeDecodeError):
        return
    doc = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                doc.add(id(first.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc:
            yield node.lineno, node.value


def _shell_strings(path):
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        for m in re.finditer(r"\"([^\"]*)\"|'([^']*)'", line):
            yield i, m.group(1) if m.group(1) is not None else m.group(2)


def static_uses(names):
    """{filter: [(file, line), ...]} for every graph token in the engine's string literals that names a filter."""
    uses = {}
    files = []
    for pat in SCAN:
        for base in ROOT.glob(pat):
            files += [p for p in base.rglob("*") if p.suffix in (".py", ".sh") and "tests" not in p.parts
                      and "__pycache__" not in p.parts]
    for p in sorted(set(files)):
        rel = p.relative_to(ROOT).as_posix()
        if rel in SKIP:
            continue
        for line, s in (_strings(p) if p.suffix == ".py" else _shell_strings(p)):
            if NOT_GRAPH.match(s.strip()) and "=" not in s:
                continue
            for m in TOKEN.finditer(s):
                n = m.group(1)
                if n in names:
                    uses.setdefault(n, []).append((rel, line))
    return uses


def built_graphs():
    """Graphs the builders produce (defaults + every legacy string the examples / old configs carry)."""
    sys.path.insert(0, str(ROOT / "lib"))
    sys.path.insert(0, str(ROOT / "workflows" / "vlog" / "scripts"))
    from vstudio import cut, ffmpeg_filters as F
    graphs = [F.grade(brightness=0.05, contrast=1.12, saturation=1.18, gamma=1.04), F.grade(gamma=1.1, gamma_r=1.2),
              F.dim(-0.08), F.blur(20), F.box_blur(30, 3), F.denoise(0.3), F.DEFAULT_TH_GRADE,
              cut.fit_chain("1920:1080", "blur").replace("{L}", "x")]
    for legacy in ("eq=brightness=-0.06:contrast=1.08:saturation=1.05:gamma=0.96", "eq=brightness=0.04",
                   "eq=contrast=1.22:brightness=-0.07:saturation=1.3", "eq=1.06:0.015", "smartblur=1.5:-0.35",
                   "smartblur=2:0.5", "boxblur=lr=10:lp=2", "hqdn3d=1.2:1.2:3:3,eq=contrast=1.06:brightness=0.015:"
                   "saturation=1.07:gamma=1.02,colorbalance=rs=-0.02:bs=0.015:rm=-0.01,cas=0.45"):
        graphs.append(F.lgpl_graph(legacy))
    import build_vlog as V
    V.vlog_persona = lambda: {}
    cfg = dict(res=[1920, 1080], fit="blur", warm=True, sharpen=True)
    graphs += [V.grade_chain(cfg, 0.08), V.fit_chain(cfg)]
    from funvlog import frames
    graphs.append(frames.grade_chain(frames.DEFAULT_FUN_GRADE))
    return graphs


def built_uses():
    sys.path.insert(0, str(ROOT / "lib"))
    from vstudio import ffmpeg_filters as F
    out = {}
    for g in built_graphs():
        for n in F.filter_names(g):
            out.setdefault(n, []).append(("<builder>", g[:80]))
    return out


def check(write=False):
    bundled = read_list(BUNDLED)
    if not bundled:
        print(f"!! {BUNDLED.relative_to(ROOT)} missing: run --snapshot with the bundled ffmpeg")
        return 1
    uses = static_uses(known())
    for n, where in built_uses().items():
        uses.setdefault(n, []).extend(where)
    errors = []
    for n, where in sorted(uses.items()):
        if n in bundled:
            continue
        files = {w[0] for w in where}
        if all(n in GATED.get(f, {}) for f in files):
            continue
        errors.append(f"{n}: not in the bundled LGPL ffmpeg - used at " +
                      ", ".join(f"{f}:{ln}" for f, ln in where[:6]) +
                      " (use vstudio.ffmpeg_filters, or gate it on media.has_filter and list it in GATED)")
    emitted = sorted(n for n in uses if n in bundled)
    body = ("# ffmpeg filters the engine can emit (scripts/check_ffmpeg_filters.py --write); every bundled ffmpeg\n"
            "# must have them (apps/desk/scripts/runtime/bundle.mjs verify)\n" + "\n".join(emitted) + "\n")
    if write:
        ENGINE.write_text(body)
        print(f"wrote {ENGINE.relative_to(ROOT)} ({len(emitted)} filters)")
    elif not ENGINE.exists() or ENGINE.read_text() != body:
        errors.append(f"{ENGINE.relative_to(ROOT)} is stale: run python3 scripts/check_ffmpeg_filters.py --write")
    for e in errors:
        print("!!", e)
    if not errors:
        print(f"ffmpeg filters ok: {len(emitted)} used, all in the bundled LGPL build")
    return 1 if errors else 0


def check_binary(binary):
    have = ffmpeg_filters(binary)
    need = read_list(ENGINE)
    missing = sorted(need - have)
    if missing:
        print(f"!! {binary} lacks filter(s) the engine uses: {', '.join(missing)}")
        return 1
    print(f"ffmpeg filters ok: {binary} has all {len(need)} engine filters")
    return 0


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--write", action="store_true", help="regenerate engine-filters.txt")
    a.add_argument("--snapshot", metavar="FFMPEG", help="refresh filters.txt from this (bundled) ffmpeg")
    a.add_argument("--binary", metavar="FFMPEG", help="check this ffmpeg has every engine filter")
    o = a.parse_args(argv)
    if o.snapshot:
        names = sorted(ffmpeg_filters(o.snapshot))
        ver = subprocess.run([o.snapshot, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
        BUNDLED.write_text(f"# `ffmpeg -filters` of the desk's bundled LGPL ffmpeg ({ver.strip()}, darwin-arm64)\n"
                           "# refresh: python3 scripts/check_ffmpeg_filters.py --snapshot <runtime>/ffmpeg/bin/ffmpeg\n"
                           + "\n".join(names) + "\n")
        print(f"wrote {BUNDLED.relative_to(ROOT)} ({len(names)} filters)")
        return 0
    if o.binary:
        return check_binary(o.binary)
    return check(write=o.write)


if __name__ == "__main__":
    sys.exit(main())
