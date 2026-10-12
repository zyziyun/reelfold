#!/usr/bin/env python3
"""Pick the tests a change can affect (Desk CI and Engine, the quick tier). Stdlib only.

Usage: select_tests.py --suite desk|engine --changed FILE [--full] [--all] [--repo DIR]
  --changed  the changed files, one per line (repo-relative); `-` = stdin
  --full     the full tier (nightly, tags, release/**, tier=full, CI / lockfile changes): every test, no selection
  --all      the change list is unknown (a new branch, a manual quick run): every test of the quick tier
Writes key=value lines to $GITHUB_OUTPUT (stdout when unset) and a Markdown report of what was picked and why to
$GITHUB_STEP_SUMMARY (stderr when unset).

How a changed file maps to tests (the rules are in .github/test-map.yml):
  desk e2e (Playwright, apps/desk/tests/e2e)
    - a spec (or a helper / fixture it uses) changed: that spec.
    - renderer files: a static trace. The specs drive the built app, so their import graph never reaches the renderer
      (why Playwright's --only-changed is not enough); they find elements by data-testid instead. A changed renderer
      file contributes its own test ids; a file without any (a hook, a stylesheet, a helper) contributes those of the
      nearest files that import it. The specs that use one of those ids run.
    - src/shared: the same trace through its importers (type-only imports do not count); main / preload importers
      fall under the next rule.
    - main process, preload, the engine sidecar (apps/desk/engine) and the engine library (lib/): the `e2e:` globs in
      the map, specs named like the changed module (updater.ts -> update.spec.ts) and the specs whose python fixture
      imports the changed module. Nothing found: the smoke set (`e2e_smoke`, `e2e_real_smoke` for the engine).
    - `full:` globs: everything. `ignore:` globs: nothing.
  sidecar unittest (apps/desk/engine/tests) and engine pytest (tests/): a python import scan; the test modules
    whose import closure contains a changed module run (a changed test runs itself). An engine file no test imports:
    the tests that name it, plus the smoke set (`pytest_smoke` / `sidecar_smoke`).
  desk unit tests (vitest): `vitest related` on the changed desk files (decided in the job, it needs node_modules).
"""
import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict, deque

# ------------------------------------------------------------------------------------------------ the map file


def parse_map(path):
    """The subset of YAML .github/test-map.yml uses: top-level keys holding a list (`- item` lines or `[a, b]`) or a
    mapping (`key: [a, b]`, `key: 12`, or `key:` followed by `- item` lines). Comments start with ` #`."""
    data, top, sub = {}, None, None

    def scalar(s):
        s = s.strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
            return s[1:-1]
        return int(s) if re.fullmatch(r"\d+", s) else s

    def value(s):
        s = s.strip()
        if s.startswith("["):
            inner = s[1:s.rindex("]")].strip()
            return [scalar(x) for x in inner.split(",") if x.strip()] if inner else []
        return scalar(s)

    for raw in open(path, encoding="utf-8"):
        line = re.sub(r"(^|\s)#.*$", "", raw.rstrip("\n")).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        text = line.strip()
        if indent == 0:
            key, _, rest = text.partition(":")
            top, sub = key.strip(), None
            data[top] = value(rest) if rest.strip() else None
            continue
        if text.startswith("- "):
            item = scalar(text[2:])
            if sub is not None:
                data[top][sub].append(item)
            else:
                if data[top] is None:
                    data[top] = []
                data[top].append(item)
            continue
        m = re.match(r"""('[^']*'|"[^"]*"|[^:]+):\s*(.*)$""", text)
        if not m:
            raise SystemExit(f"{path}: cannot read {raw!r}")
        if data[top] is None:
            data[top] = {}
        k = scalar(m.group(1))
        if m.group(2):
            data[top][k], sub = value(m.group(2)), None
        else:
            data[top][k], sub = [], k
    return data


def glob_re(pattern):
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif c == "*":
            out, i = out + "[^/]*", i + 1
        elif c == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(c), i + 1
    return re.compile(out + r"\Z")


def matches(path, globs):
    return [g for g in globs if glob_re(g).match(path)]


# ------------------------------------------------------------------------------------------------ helpers


def read(repo, rel):
    try:
        with open(os.path.join(repo, rel), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def walk(repo, top, exts):
    out = []
    for dp, dns, fns in os.walk(os.path.join(repo, top)):
        dns[:] = [d for d in dns if d not in ("node_modules", "__pycache__", ".git", "out", "dist", "test-results")]
        for fn in fns:
            if fn.endswith(exts):
                out.append(os.path.relpath(os.path.join(dp, fn), repo).replace(os.sep, "/"))
    return sorted(out)


def stem(path):
    b = os.path.basename(path)
    for suf in (".spec.ts", ".test.ts", ".d.ts"):
        if b.endswith(suf):
            return b[: -len(suf)]
    return os.path.splitext(b)[0]


def name_affinity(path, specs):
    """specs named like the changed module: equal stems, or one a prefix of the other (5+ letters)."""
    s = stem(path).lower().replace("_", "").replace("-", "")
    if s in ("index", "init", "__init__", "main", "app", "common", "util", "utils", "types"):
        return []
    hits = []
    for spec in specs:
        t = stem(spec).lower().replace("-", "")
        if s == t or (min(len(s), len(t)) >= 5 and (s.startswith(t) or t.startswith(s))):
            hits.append(spec)
    return hits


# ------------------------------------------------------------------------------------------------ TypeScript graph

TS_EXT = (".ts", ".tsx", ".mts", ".js", ".mjs", ".cjs")
TS_IMPORT = re.compile(
    r"""(?:^|[\s;}])(?:import|export)\s+(type\s+)?(?:[\w*{}\s,$]+?\s+from\s+)?['"]([^'"]+)['"]"""
    r"""|import\(\s*['"]([^'"]+)['"]\s*\)|require\(\s*['"]([^'"]+)['"]\s*\)""",
    re.M,
)


class TsGraph:
    def __init__(self, repo, roots):
        self.repo = repo
        self.files = [f for r in roots for f in walk(repo, r, TS_EXT + (".css", ".html", ".json"))]
        self.fileset = set(self.files)
        self.deps = defaultdict(set)      # file -> files it imports (runtime imports only)
        self.rdeps = defaultdict(set)
        for f in self.files:
            if not f.endswith(TS_EXT + (".html",)):
                continue
            text = read(repo, f)
            specs = []
            if f.endswith(".html"):
                specs = [(False, m) for m in re.findall(r"""src=['"]([^'"]+)['"]""", text)]
            else:
                for m in TS_IMPORT.finditer(text):
                    type_only = bool(m.group(1))
                    spec = m.group(2) or m.group(3) or m.group(4)
                    specs.append((type_only, spec))
            for type_only, spec in specs:
                if type_only or not spec.startswith((".", "/")):
                    continue
                dep = self.resolve(f, spec)
                if dep:
                    self.deps[f].add(dep)
                    self.rdeps[dep].add(f)

    def resolve(self, frm, spec):
        base = os.path.normpath(os.path.join(os.path.dirname(frm), spec.lstrip("/") if spec.startswith("/") else spec))
        base = base.replace(os.sep, "/")
        if spec.startswith("/"):        # vite: from the html's folder
            base = os.path.normpath(os.path.join(os.path.dirname(frm), spec[1:])).replace(os.sep, "/")
        cands = [base] + [base + e for e in TS_EXT + (".json", ".css")] + [base + "/index" + e for e in TS_EXT]
        if base.endswith(".js"):
            cands.insert(1, base[:-3] + ".ts")
            cands.insert(2, base[:-3] + ".tsx")
        return next((c for c in cands if c in self.fileset), None)

    def closure(self, f):
        seen, todo = {f}, [f]
        while todo:
            for d in self.deps.get(todo.pop(), ()):
                if d not in seen:
                    seen.add(d)
                    todo.append(d)
        return seen


TESTID_ATTR = re.compile(r"""(?:data-testid|testId|testid)\s*[=:]\s*""")
STR_LIT = re.compile(r"""'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`""", re.S)


def literal_tokens(chunk):
    """(exact strings, template prefixes) of the string literals in a piece of code."""
    exact, prefix = set(), set()
    for m in STR_LIT.finditer(chunk):
        s = m.group(1) if m.group(1) is not None else m.group(2) if m.group(2) is not None else m.group(3)
        if m.group(3) is not None and "${" in s:
            p = s.split("${", 1)[0]
            if len(p) >= 3 and re.search(r"[a-zA-Z]", p):
                prefix.add(p)
        elif s:
            exact.add(s)
    return exact, prefix


def renderer_testids(text):
    """The test ids a renderer file renders: the string literals right after data-testid= / testId= / testid:."""
    exact, prefix = set(), set()
    for m in TESTID_ATTR.finditer(text):
        i = m.end()
        if i < len(text) and text[i] == "{":           # an expression: its literals, up to the matching brace
            depth, j = 0, i
            while j < len(text):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            chunk = text[i + 1 : j]
        else:
            chunk = text[i : i + 200].split("\n", 1)[0]
            sm = STR_LIT.match(chunk)
            chunk = sm.group(0) if sm else ""
        e, p = literal_tokens(chunk)
        exact |= {x for x in e if re.fullmatch(r"[\w:.-]+", x)}
        prefix |= p
    return exact, prefix


def spec_tokens(text):
    exact, prefix = literal_tokens(text)
    for s in list(exact):                                # locator('[data-testid="x"]'), [data-testid^="x-"]
        for m in re.finditer(r"""data-testid(\^?)=\\?["']?([\w:.-]+)""", s):
            (prefix if m.group(1) else exact).add(m.group(2))
    return exact, prefix


def ids_match(r_exact, r_prefix, s_exact, s_prefix):
    if r_exact & s_exact:
        return sorted(r_exact & s_exact)[:3]
    for p in r_prefix:
        for s in s_exact:
            if s.startswith(p):
                return [p + "*"]
        for q in s_prefix:
            if p.startswith(q) or q.startswith(p):
                return [p + "*"]
    for q in s_prefix:
        for e in r_exact:
            if e.startswith(q):
                return [e]
    return []


# ------------------------------------------------------------------------------------------------ python graph

PY_IMPORT = re.compile(r"^[ \t]*(?:from[ \t]+(\.*[\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n#]+)|import[ \t]+([^\n#]+))", re.M)


class PyGraph:
    """A static import graph of the repo's python. Module search roots: every folder with python in it that a test or
    the engine puts on sys.path (lib/, the desk engine, the workflow scripts, test folders, fixtures)."""

    def __init__(self, repo, roots, tops):
        self.repo = repo
        self.files = [f for t in tops for f in walk(repo, t, (".py",))]
        self.fileset = set(self.files)
        self.roots = roots
        self.modules = defaultdict(set)    # dotted name (relative to a root) -> files
        for f in self.files:
            for r in self.roots:
                if f.startswith(r + "/"):
                    rel = f[len(r) + 1 : -3]
                    parts = rel.split("/")
                    if parts[-1] == "__init__":
                        parts = parts[:-1]
                    if parts and all(p.isidentifier() for p in parts):
                        self.modules[".".join(parts)].add(f)
        self.deps = {}

    def _pkg_inits(self, dotted):
        out = set()
        parts = dotted.split(".")
        for i in range(1, len(parts)):
            out |= {f for f in self.modules.get(".".join(parts[:i]), ()) if f.endswith("__init__.py")}
        return out

    def _resolve(self, dotted):
        if dotted in self.modules:
            return set(self.modules[dotted]) | self._pkg_inits(dotted)
        return set()

    def deps_of(self, f, lazy=True):
        """the files f imports; lazy=False: module-level imports only (not those inside a function)"""
        key = (f, lazy)
        if key in self.deps:
            return self.deps[key]
        text = read(self.repo, f)
        if not lazy:
            text = "\n".join(l for l in text.split("\n") if not l[:1].isspace())
        out = set()
        pkg = None
        for r in self.roots:
            if f.startswith(r + "/"):
                pkg = f[len(r) + 1 :].rsplit("/", 1)[0].replace("/", ".") if "/" in f[len(r) + 1 :] else ""
                break
        for m in PY_IMPORT.finditer(text):
            if m.group(3):
                for name in m.group(3).split(","):
                    name = name.strip().split(" as ")[0].strip()
                    out |= self._resolve(name)
                continue
            mod, names = m.group(1), m.group(2).strip("() \t\n")
            if mod.startswith("."):
                dots = len(mod) - len(mod.lstrip("."))
                if pkg is None:
                    continue
                base = pkg.split(".") if pkg else []
                base = base[: len(base) - (dots - 1)] if dots > 1 else base
                mod = ".".join([p for p in base + [mod.lstrip(".")] if p])
            out |= self._resolve(mod)
            for name in names.split(","):
                name = name.strip().split(" as ")[0].strip()
                if name and name != "*":
                    out |= self._resolve(f"{mod}.{name}" if mod else name)
        # importlib / `python -m` / subprocess strings naming a module of the engine
        for s in re.findall(r"""['"]((?:vstudio|desk_engine|desk_mock)(?:\.\w+)+)['"]""", text):
            out |= self._resolve(s)
        out.discard(f)
        self.deps[key] = out
        return out

    def closure(self, f, lazy=lambda path: False):
        """f and what it imports, transitively. f's own imports count wherever they are (a test imports inside its
        test functions); past f, only module-level imports, unless lazy(path): the engine imports lazily inside
        functions everywhere, and following those would make nearly every test depend on nearly every module."""
        seen, todo = {f}, [f]
        while todo:
            g = todo.pop()
            for d in self.deps_of(g, lazy=g == f or lazy(g)):
                if d not in seen:
                    seen.add(d)
                    todo.append(d)
        return seen


# ------------------------------------------------------------------------------------------------ selection


class Report:
    """one line of text on top, then a table: suite | test | why"""

    def __init__(self):
        self.head, self.lines = [], []

    def note(self, line):
        self.head.append(line)

    def add(self, line):
        self.lines.append(line)

    def markdown(self):
        table = ["| suite | test | why |", "|---|---|---|"] + self.lines if self.lines else []
        return "\n".join(self.head + ([""] if self.head and table else []) + table)


def is_test_code(path):
    return path.startswith(("tests/", "apps/desk/engine/tests/", "apps/desk/tests/"))


def py_tests_for(changed, tests, graph, smoke, text_of, rep, label):
    """Test files (of `tests`) whose import closure contains a changed python file; a changed test runs itself."""
    picked = {}
    closures = {t: graph.closure(t, lazy=is_test_code) for t in tests}
    for f in changed:
        if f in closures:
            picked.setdefault(f, "changed")
            continue
        hits = [t for t, c in closures.items() if f in c]
        why = "imports " + f
        if not hits:   # not imported anywhere: tests that name the file (scripts run as a subprocess, data files)
            base = os.path.basename(f)
            hits = [t for t in tests if base in text_of(t)]
            why = "names " + base
        if not hits:
            hits, why = [t for t in smoke if t in closures], f"smoke ({f}: no test imports or names it)"
        for t in hits:
            picked.setdefault(t, why)
    for t, why in sorted(picked.items()):
        rep.add(f"| {label} | `{t}` | {why} |")
    return sorted(picked)


def select_desk(repo, changed, cfg, rep):
    desk = "apps/desk/"
    e2e_dir = desk + "tests/e2e/"
    specs = [f for f in walk(repo, e2e_dir.rstrip("/"), (".spec.ts",))]
    spec_set = set(specs)
    ts = TsGraph(repo, [desk + "src", e2e_dir.rstrip("/"), desk + "adapters"])
    spec_closure = {s: ts.closure(s) for s in specs}
    spec_ids = {}
    for s in specs:
        ex, pre = set(), set()
        for f in spec_closure[s]:
            if f.startswith(e2e_dir):
                e, p = spec_tokens(read(repo, f))
                ex |= e
                pre |= p
        spec_ids[s] = (ex, pre)
    spec_text = {s: read(repo, s) for s in specs}
    use = defaultdict(int)
    for ex, _ in spec_ids.values():
        for i in ex:
            use[i] += 1
    landmarks = {i for i, n in use.items() if n >= int(cfg.get("e2e_landmark_specs") or 8)}
    py = PyGraph(repo, PY_ROOTS, PY_TOPS)
    e2e_map = cfg.get("e2e") or {}
    no_trace = cfg.get("e2e_no_trace") or []
    smoke = [e2e_dir + s for s in cfg.get("e2e_smoke") or []]
    real_smoke = [e2e_dir + s for s in cfg.get("e2e_real_smoke") or []]
    picked = {}

    def pick(spec_list, why):
        for s in spec_list:
            if s in spec_set:
                picked.setdefault(s, why)

    def by_map(f):
        hits = []
        for g, lst in e2e_map.items():
            if glob_re(g).match(f):
                hits += [e2e_dir + x for x in (lst if isinstance(lst, list) else [lst])]
        return hits

    # the python files each spec's fixtures import (fixture/real_project.py ...), for engine changes
    fixture_py = [f for f in walk(repo, e2e_dir + "fixture", (".py",))]
    spec_py = defaultdict(set)
    for s in specs:
        for fx in fixture_py:
            if os.path.basename(fx) in spec_text[s]:
                spec_py[s] |= py.closure(fx, lazy=is_test_code)
    engine_server = desk + "engine/server.py"
    everything = lambda path: True               # noqa: E731  (does the desk load it at all: lazy imports count)
    engine_closure = py.closure(engine_server, everything) | {
        c for f in walk(repo, desk + "engine/desk_engine", (".py",)) for c in py.closure(f, everything)
    }

    for f in changed:
        if f in spec_set:
            pick([f], "changed spec")
            continue
        importers = [s for s in specs if f in spec_closure[s]]
        if importers:
            pick(importers, f"imports {f}")
        if f.startswith(e2e_dir + "fixture/"):
            pick([s for s in specs if os.path.basename(f) in spec_text[s]], f"uses fixture {os.path.basename(f)}")
            continue
        if f.startswith(e2e_dir):
            continue
        mapped = by_map(f)
        pick(mapped, f"map: {f}")
        if matches(f, no_trace):
            continue
        if f.startswith(desk + "src/renderer/") or f.startswith(desk + "src/shared/"):
            hits, main_files = trace_renderer(ts, f, specs, spec_ids, repo, landmarks)
            for s, ids in hits.items():
                pick([s], f"test ids {', '.join(ids)} ({f})")
            for m in main_files:
                pick(by_map(m), f"map: {m} (imports {f})")
                pick(name_affinity(m, specs), f"named like {m} (imports {f})")
            if not hits and not mapped:
                pick(smoke, f"smoke ({f}: no spec uses its test ids)")
            elif main_files:
                pick(smoke, f"smoke (main process code imports {f})")
            continue
        if f.startswith(desk + "src/"):            # main, preload
            named = name_affinity(f, specs)
            pick(named, f"named like {f}")
            pick(smoke, f"smoke (main process: {f})")
            continue
        if f.startswith(desk + "engine/") or f.startswith("lib/"):
            if f.startswith(desk + "engine/tests/") and not f.startswith(desk + "engine/tests/fixtures/"):
                continue                            # the sidecar unittests (their own job)
            named = name_affinity(f, specs)
            pick(named, f"named like {f}")
            fx = [s for s in specs if f in spec_py[s]]
            pick(fx, f"its python fixture imports {f}")
            if f.endswith(".py") and f not in engine_closure and not f.startswith(desk + "engine/"):
                continue                            # engine code the desk never loads
            if not (mapped or named or fx):
                is_mock = "/fixtures/desk_mock/" in f
                pick(smoke if is_mock else real_smoke, f"smoke ({f}: no spec mapped)")
            continue
        if f.startswith(desk + "adapters/"):
            continue                                # imported by the specs that use them (above)
        if f.endswith(".py") or f.endswith(TS_EXT):
            if not mapped and not importers and f.startswith(desk):
                pick(smoke, f"smoke ({f}: unmapped desk code)")
    for s, why in sorted(picked.items()):
        rep.add(f"| e2e | `{s[len(e2e_dir):]}` | {why} |")
    return sorted(picked)


def trace_renderer(ts, f, specs, spec_ids, repo, landmarks, max_depth=6):
    """specs -> matched test ids; and the main / preload files reached on the way up."""
    hits, main_files = {}, set()
    frontier, seen = [f], {f}
    for _ in range(max_depth):
        nxt = []
        for g in frontier:
            if "/src/main/" in g or "/src/preload/" in g:
                main_files.add(g)
                continue
            text = read(repo, g)
            r_ex, r_pre = renderer_testids(text) if g.endswith((".tsx", ".ts")) else (set(), set())
            if r_ex or r_pre:
                # landmarks (ids most specs wait on: home, the studio list, the composer) only count when the file
                # renders nothing more specific that a spec uses
                specific = {s: ids_match(r_ex - landmarks, r_pre, *spec_ids[s]) for s in specs}
                specific = {s: ids for s, ids in specific.items() if ids}
                if not specific:
                    specific = {s: ids for s in specs for ids in [ids_match(r_ex, r_pre, *spec_ids[s])] if ids}
                for s, ids in specific.items():
                    hits.setdefault(s, ids)
                if g != f or hits:
                    continue                        # stop here: this view owns what it renders
            for imp in ts.rdeps.get(g, ()):
                if imp not in seen and "/tests/" not in imp:
                    seen.add(imp)
                    nxt.append(imp)
        frontier = nxt
        if not frontier:
            break
    return hits, main_files


def shard(specs, weights, default_weight, max_shards, per_shard):
    est = {s: weights.get(os.path.basename(s), default_weight) for s in specs}
    total = sum(est.values())
    n = max(1, min(max_shards, math.ceil(total / per_shard), len(specs)))
    bins = [[0, []] for _ in range(n)]
    for s in sorted(specs, key=lambda x: -est[x]):     # longest first, onto the lightest shard
        b = min(bins, key=lambda x: x[0])
        b[0] += est[s]
        b[1].append(s)
    return [sorted(b[1]) for b in bins], total


# what the Engine workflow tests (engine.yml's path filter)
ENGINE_SCOPE = ("lib/", "workflows/", "tests/", "scripts/", "references/", "SKILL.md", "apps/desk/packaging/ffmpeg/")
PY_ROOTS = ["lib", "apps/desk/engine", "apps/desk/engine/tests", "apps/desk/engine/tests/fixtures", "tests",
            "apps/desk/tests/e2e/fixture", "scripts"]
PY_TOPS = ["lib", "apps/desk/engine", "apps/desk/tests/e2e/fixture", "tests", "workflows", "scripts"]


def add_workflow_roots(repo):
    """the workflow scripts' folders (each test puts the one it needs on sys.path)"""
    roots = set()
    for f in walk(repo, "workflows", (".py",)):
        d = os.path.dirname(f)
        while d.count("/") >= 2 and os.path.isfile(os.path.join(repo, d, "__init__.py")):
            d = os.path.dirname(d)
        roots.add(d)
    for r in sorted(roots):
        if r not in PY_ROOTS:
            PY_ROOTS.append(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=["desk", "engine"], required=True)
    ap.add_argument("--changed", required=True)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--map", default=".github/test-map.yml")
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)
    cfg = parse_map(os.path.join(repo, a.map))
    raw = sys.stdin.read() if a.changed == "-" else open(a.changed, encoding="utf-8").read()
    changed = sorted({l.strip() for l in raw.splitlines() if l.strip()})
    add_workflow_roots(repo)
    out, rep = {}, Report()

    full_globs = (cfg.get("full") or []) + (cfg.get(f"full_{a.suite}") or [])
    full_hit = [f for f in changed if matches(f, full_globs)]
    everything = a.full or a.all or bool(full_hit)
    if a.full:
        reason = "the full tier"
    elif a.all:
        reason = "the change list is unknown (new branch / manual run)"
    else:
        reason = f"{full_hit[0]} changed (`full` in test-map.yml)" if full_hit else ""
    relevant = [f for f in changed if not matches(f, cfg.get("ignore") or [])]
    out["relevant"] = "true" if everything or relevant else "false"     # false: only `ignore:` files (docs) changed

    if a.suite == "desk":
        weights = cfg.get("e2e_weights") or {}
        if everything:
            n = 4
            out["e2e"] = "all"
            out["e2e_matrix"] = json.dumps({"include": [{"index": i, "shard": f"{i}/{n}", "args": f"--shard={i}/{n}"} for i in range(1, n + 1)]})
            out["sidecar"] = "all"
            out["sidecar_tests"] = ""
            out["unit"] = "all"
            out["scripts"] = "true"
            rep.note(f"**Everything** runs: {reason}.")
        else:
            specs = select_desk(repo, relevant, cfg, rep)
            if specs:
                shards, est = shard(specs, weights, int(cfg.get("e2e_default_weight") or 20), 4,
                                    int(cfg.get("e2e_seconds_per_shard") or 300))
                n = len(shards)
                out["e2e"] = "some"
                out["e2e_matrix"] = json.dumps({"include": [
                    {"index": i, "shard": f"{i}/{n}", "args": " ".join(p[len("apps/desk/"):] for p in sh)}
                    for i, sh in enumerate(shards, 1)]})
                rep.note(f"{len(specs)} of {len(walk(repo, 'apps/desk/tests/e2e', ('.spec.ts',)))} e2e specs, "
                         f"about {round(est / 60, 1)} min of tests, {n} shard(s).")
            else:
                out["e2e"] = "none"
                out["e2e_matrix"] = json.dumps({"include": [{"index": 0, "shard": "-", "args": ""}]})
            py = PyGraph(repo, PY_ROOTS, PY_TOPS)
            side_dir = "apps/desk/engine/tests"
            side_tests = [f for f in walk(repo, side_dir, (".py",)) if os.path.basename(f).startswith("test_")
                          and "/fixtures/" not in f]
            side_changed = [f for f in relevant if f.startswith("apps/desk/engine/") or f.startswith("lib/") and f.endswith(".py")]
            side = py_tests_for(side_changed, side_tests, py, [f"{side_dir}/{t}" for t in cfg.get("sidecar_smoke") or []],
                                lambda t: read(repo, t), rep, "sidecar") if side_changed else []
            out["sidecar"] = "some" if side else "none"
            out["sidecar_tests"] = " ".join(stem(t) for t in side)
            unit_files = [f[len("apps/desk/"):] for f in relevant if f.startswith("apps/desk/")
                          and f.endswith(TS_EXT + (".json", ".css"))]
            out["unit"] = "some" if unit_files else "none"
            out["unit_files"] = " ".join(unit_files)
            if unit_files:
                rep.add(f"| unit | `vitest related` | {len(unit_files)} changed desk file(s) |")
            out["scripts"] = "true" if any(f.startswith("apps/desk/scripts/") for f in relevant) else "false"
            if out["scripts"] == "true":
                rep.add("| scripts | App Store lint + runtime | apps/desk/scripts changed |")
            if not (specs or side or unit_files or out["scripts"] == "true"):
                rep.note("Nothing to run: no desk test can see this change.")
    else:
        if everything:
            out["pytest"] = "all"
            out["pytest_files"] = ""
            rep.note(f"**Every engine test** runs: {reason}.")
        else:
            py = PyGraph(repo, PY_ROOTS, PY_TOPS)
            tests = [f for f in walk(repo, "tests", (".py",)) if os.path.basename(f).startswith("test_")]
            scope = [f for f in relevant if f.startswith(ENGINE_SCOPE)]
            sel = py_tests_for(scope, tests, py, [f"tests/{t}" for t in cfg.get("pytest_smoke") or []],
                               lambda t: read(repo, t), rep, "pytest") if scope else []
            out["pytest"] = "some" if sel else "none"
            out["pytest_files"] = " ".join(sel)
            rep.note(f"{len(sel)} of {len(tests)} test files." if sel else
                     "Nothing to run: no engine test can see this change (check_skill still runs).")

    gh_out = os.environ.get("GITHUB_OUTPUT")
    with (open(gh_out, "a", encoding="utf-8") if gh_out else sys.stdout) as fh:
        for k, v in out.items():
            fh.write(f"{k}={v}\n")
    title = "Desk tests" if a.suite == "desk" else "Engine tests"
    body = f"### {title} picked for this change\n\n" + rep.markdown() + "\n"
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as fh:
            fh.write(body)
    print(body, file=sys.stderr)


if __name__ == "__main__":
    main()
