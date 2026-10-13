"""The explainer's visuals, written by the routed AI: one HyperFrames scene per narration line, drawn as diagrams and
animated graphics on the voice's real cue times (the workflow's own frame-worker brief: WORKFLOW.md step 6,
references/design-truth*.md, frame-worker-dispatch.md, pitfalls.md) - never the narration as lines of text.

    author_scenes(item_dir, workflow_dir, ...) -> {ok, written [ids], failed {id: error}, provider, model, error,
                                                   error_code (needs-model | None), provider_name}

Every scene is one model call (parallel, a long time limit: a scene is a whole SVG + GSAP file), checked before it is
kept (``scene_problems``: the HyperFrames contract, no placeholder, a drawn graphic, not a wall of sentences); a scene
that fails its check is asked again once with the problems named, and one the renderer's own checks refuse
(``lint_scenes``: lint + the scene run in a browser) again with the finding and its fix. Scenes the AI wrote carry ``AI_MARK``, so a second
try only writes the ones still missing. No model / every call failing -> nothing is written that is not the AI's:
``error_code: needs-model`` and a plain sentence for the creator (the step waits in Needs you; no text-only video).
"""
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

AI_MARK = "<!-- reelfold:scene by=ai -->"
TASK = "planner"
# one scene: a whole SVG + GSAP file; Claude Code takes 1-4 min for one, up to 7 min with four at once on a busy
# machine (her MCP course, 14 scenes: 119-416 s each): a slow answer beats a fallback
SCENE_TIMEOUT = float(os.environ.get("VSTUDIO_SCENE_TIMEOUT") or 900)
PARALLEL = int(os.environ.get("VSTUDIO_SCENE_PARALLEL") or 4)
# Claude Code at its default effort thought 5.5 min over one scene (31k tokens); at medium it writes the same quality
# in ~1 min (measured on her MCP course, 2026-10-11)
EFFORT = os.environ.get("VSTUDIO_SCENE_EFFORT") or "medium"
PLACEHOLDER = re.compile(r"\bTODO\b|\bTBD\b|\bFIXME\b|lorem ipsum", re.I)
# a drawn shape: an SVG element in the markup, or one the script creates (createElementNS / a helper mk("rect", ...))
DRAWN = re.compile(r"<(?:path|rect|line|circle|ellipse|polygon|polyline)\b|"
                   r"[\"'](?:path|rect|line|circle|ellipse|polygon|polyline)[\"']", re.I)
PROVIDER_NAMES = {"claude-code": "Claude Code", "codex": "Codex", "anthropic": "Claude", "openai": "OpenAI",
                  "gemini": "Gemini", "openai-compatible": "your AI"}


class NeedsModel(RuntimeError):
    """The visuals need a model and none answered: ``code`` / ``params`` for the desk's own words."""
    code = "ai-needs-model"

    def __init__(self, message, provider=None, what="visuals"):
        super().__init__(message)
        self.params = dict(provider=provider or "", what=what)


def provider_name(provider):
    return PROVIDER_NAMES.get(provider or "", provider or "")


def routed_provider(task=TASK):
    try:
        from vstudio import llm
        return llm.route(task).provider
    except Exception:  # noqa: BLE001
        return None


def needs_model_message(provider=None, what="visuals"):
    """The plain sentence the creator reads when no model drew the visuals (or wrote the script)."""
    thing = "The script needs" if what == "script" else "The visuals need"
    if not provider or provider == "none":
        return f"{thing} an AI model — none is connected. Connect one in Settings › AI, then Try again."
    return (f"{thing} an AI model — {provider_name(provider)} didn't answer. Try again, or choose another model "
            f"in Settings › AI.")


# --------------------------------------------------------------------------- what a scene is made from
def _read(path, n=200_000):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(n)
    except (OSError, UnicodeDecodeError):
        return ""


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def scene_inputs(item_dir, workflow_dir):
    """-> {canvas, lang, scenes [{id, n, label, delivery, spoken, duration, cues [{t, te, text}], shots, last}]}
    from the item's scenes.config.json, the voice's scene windows + cues and SCRIPT.md. Raises OSError / ValueError
    when the voice timing is not there yet."""
    import sys
    cfg = _load(os.path.join(item_dir, "scenes.config.json"))
    win = _load(os.path.join(item_dir, "audio", "scenes.json"))["scenes"]
    cues = _load(os.path.join(item_dir, "audio", "scene_cues.json"))
    scripts = os.path.join(workflow_dir, "scripts")
    sys.path.insert(0, scripts)
    try:
        import canvas as CV
        from script_md import narration_lang, parse_script
        cv = CV.resolve(item_dir)
        try:
            lines = parse_script(os.path.join(item_dir, "SCRIPT.md"))
        except OSError:
            lines = []
        desc = CV.describe(cv)
    finally:
        sys.path.remove(scripts)
    by_n = {L["n"]: L for L in lines}
    out = []
    scs = cfg.get("scenes") or []
    for k, (sc, w) in enumerate(zip(scs, win)):
        L = by_n.get(w["frame"]) or {}
        out.append(dict(id=sc["id"], n=w["frame"], label=L.get("label") or "", delivery=L.get("delivery") or "",
                        spoken=L.get("spoken") or "", sub=L.get("en") if L.get("lang") == "zh" else L.get("zh"),
                        duration=float(w["duration"]), shots=sc.get("shots") or "",
                        cues=[dict(t=c["t"], te=c.get("te"), text=c.get("text") or c.get("en") or "")
                              for c in cues.get(str(w["frame"])) or []],
                        last=k == min(len(scs), len(win)) - 1))
    canvas = {k: cv[k] for k in ("W", "H", "legacy", "key", "safe", "caption", "math") if k in cv}
    canvas["describe"] = desc
    for k in ("math_narrow_from_y", "math_narrow_x1", "title_xy"):
        if cv.get(k) is not None:
            canvas[k] = cv[k]
    return dict(canvas=canvas, lang=narration_lang(lines) if lines else "en", scenes=out)


# --------------------------------------------------------------------------- the brief
SYSTEM = """You are the motion designer of a 3Blue1Brown-style explainer channel. You write ONE scene of the video as a \
HyperFrames composition (HTML + SVG + GSAP) that is rendered frame by frame by a headless browser. The narration \
and the bilingual captions are already made; your scene is the PICTURE that explains what the voice says.

What a good scene is (the channel's own rules):
- One clear visual idea per narration cue: a diagram, a flow with arrows, boxes that connect, a comparison \
(before / after, left vs right), a table that fills in, a number that counts up, an equation built term by term, a \
timeline, a code card (a few lines of mono code), a stack of layers, a grid that multiplies. Things MOVE to explain: \
lines draw (strokeDashoffset), arrows travel, boxes slide in and connect, counts change, the old idea dims when the \
new one lights up.
- NEVER the narration as sentences on screen (the captions own that). On-screen text is short labels only: a title \
of <= 14 characters / 5 words, labels of <= 10 Chinese characters or 4 English words, numbers, code identifiers.
- Each cue in the cue table gets its own visible change, starting <= 0.15 s before the cue's start time. The scene's \
most complete moment (about 85 % of its duration) shows the whole diagram.
- Fill the drawing area: the main graphic spans most of the area's width; no tiny drawing in a corner, no empty half.

Design truth (dark chalkboard):
- Palette by role - canvas #0B1020 (painted by the index: never paint a background), ink #ECEEF2 (lines, plain \
labels), dim #6B7488 (axes, secondary labels, the scene title), faint #2A3247 (dividers, table rules), card \
#121A30 (card fill), blue #58C4DD (the main subject / data), yellow #F4D35E (the key idea, highlights), teal \
#5CD0B3 (good outcome, "after"), pink #E88CC4 (a second actor / integers), red #FC6255 (problems, errors, "before"). \
One colour = one meaning across the scene.
- Type: text in font-family "Course CJK" (declare it with the two @font-face rules below; it has Latin and Chinese), \
code / numbers in "JetBrains Mono" (bundled by the renderer: no @font-face). Sizes: scene title 44 (dim, top-left), \
labels 28-48, key numbers / formulas 56-96, code 24-34. No emoji, no icon fonts, no external images.
- Strokes 3 px, boxes radius 14 with a 3 px role-colour stroke (fill none or the card colour), pills fully rounded.
- Motion: power2.out for entrances (0.5-0.9 s), power1.inOut for moves, back.out(1.6) only for small pops, \
sine.inOut for the ambient drift (the whole group drifts <= 6 px over the scene so nothing is ever frozen). No glow, \
no blur, no particles, no shake. No exit animation unless it is the final scene (then a closing fade is allowed).

The HyperFrames contract (each rule cost a failed render once):
1. The file is exactly one <template> ... </template>. <style>, the markup and BOTH <script> tags go inside it.
2. Root: <div id="root" data-composition-id="SCENE_ID" data-width="W" data-height="H" data-duration="DURATION">, \
style #root { position: absolute; inset: 0; width: 100%; height: 100%; overflow: hidden; } and NO background.
3. Inside it ONE stage <div id="SCENE_ID-stage" class="clip" data-start="0" data-duration="DURATION" \
data-track-index="1"> holding a full-size <svg viewBox="0 0 W H"> (absolute, inset 0) - draw with SVG.
4. Prefix every other id and class with "SCENE_ID-".
5. Fonts: @font-face { font-family: "Course CJK"; src: url("assets/fonts/scene-cjk-w4.woff2") format("woff2"); \
font-weight: 400 500; } and the same with "assets/fonts/scene-cjk-w7.woff2" for font-weight: 600 900. Asset paths \
are project-root-relative, never "../".
6. <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>, then one IIFE that builds \
repeated SVG nodes with document.createElementNS where useful, makes ONE paused timeline \
`const tl = gsap.timeline({ paused: true });`, places every tween at an absolute time (the third argument), and \
ends with `window.__timelines["SCENE_ID"] = tl;`.
7. Never call tl.fromTo() twice on the same target (later animations of it: tl.to(), or immediateRender: false).
8. Deterministic: no Math.random, no Date, no repeat: -1, no CSS transitions / @keyframes, no setTimeout, no <audio>, \
no <video>.
8b. OFFLINE and self-contained: the scene renders in a sandboxed browser with NO network; the GSAP <script> above is \
the only outside file. Forbidden (the check refuses the scene): fetch(), XMLHttpRequest, WebSocket, EventSource, \
navigator.sendBeacon, import() / <script type="module">, any other <script src>, <iframe>, <img> / <image> / <link> \
/ @import / url() pointing at http(s), localStorage, sessionStorage, document.cookie. Every list, number, JSON and \
code line the scene shows is written INLINE in the script as a constant (`const steps = [...]`). A code card that \
SHOWS a request (e.g. `fetch("/tools")`) is fine as text in an SVG <text> or a string - never call it.
9. Keep everything inside the drawing area given in the brief: the captions own the bottom band.
10. Use the true minus sign "−" for negative numbers in visible text. Escape & < > in SVG text.

Reply with the complete file only: it starts with <template> and ends with </template>. No markdown fences, no prose."""


def _fmt_cues(cues):
    return "\n".join(f"| {c['t']:6.2f} | {(c.get('te') or c['t']):6.2f} | {c['text']} |" for c in cues)


def _outline(scenes, me):
    rows = []
    for s in scenes:
        mark = "  <- THIS SCENE" if s["id"] == me["id"] else ""
        gist = s["spoken"][:70] + ("…" if len(s["spoken"]) > 70 else "")
        rows.append(f"{s['n']:>2}. {s['label'] or s['id']}: {gist}{mark}")
    return "\n".join(rows)


def scene_prompt(inp, sc, request="", instruction=None, problems=None, reference="", previous=None):
    cv = inp["canvas"]
    W, H = cv["W"], cv["H"]
    area = cv.get("math") or (80, 80, W - 80, 800)
    if cv.get("legacy", True):
        area = (80, 80, 1840, 800)
    lang = "Chinese (labels in Chinese; English technical terms stay English)" if inp["lang"] == "zh" else "English"
    bits = [
        f"Request of the creator: {request or '(none)'}",
        f"Episode outline (one scene per line):\n{_outline(inp['scenes'], sc)}",
        f"THIS SCENE: id `{sc['id']}` - \"{sc['label']}\" - duration {sc['duration']:.2f} s (scene-local time 0 = "
        f"its start; fixed). {'It is the FINAL scene: a closing fade is allowed.' if sc['last'] else 'Not the final scene: no exit animation.'}",
        f"Canvas: {W}x{H}. {cv['describe']}. Draw inside x {area[0]}-{area[2]}, y {area[1]}-{area[3]}"
        + (f"; below y {cv['math_narrow_from_y']} keep content left of x {cv['math_narrow_x1']}"
           if cv.get("math_narrow_from_y") else "") + ".",
        f"On-screen language: {lang}.",
        f"The writer's direction for this scene: {sc['delivery']}" if sc.get("delivery") else "",
        f"Narration of this scene (spoken, never shown as text):\n{sc['spoken']}",
        f"Voice cues (scene-local seconds; each one gets its own visual change):\n| start | end | spoken |\n"
        f"|---|---|---|\n{_fmt_cues(sc['cues'])}",
        f"Storyboard notes (a plan; the cue times above win):\n{sc['shots']}" if sc.get("shots") and
        not PLACEHOLDER.search(sc["shots"]) else "",
        f"The creator's instruction for the visuals: {instruction}" if instruction else "",
        f"A reference scene from another video of the channel (structure and craft only - its content, fonts and "
        f"canvas are not yours):\n{reference}" if reference else "",
        ("Your previous version of this scene was rejected for these problems - fix every one:\n- "
         + "\n- ".join(problems)) if problems else "",
        f"Your previous version (correct it; keep what works):\n{previous}" if previous else "",
        f"Write compositions/{sc['id']}.html now: SCENE_ID = {sc['id']}, W = {W}, H = {H}, DURATION = "
        f"{sc['duration']:.2f}.",
    ]
    return "\n\n".join(b for b in bits if b)


# --------------------------------------------------------------------------- checking a scene
def extract_template(text):
    """The <template>...</template> in a model's reply (fences / prose around it ignored) or None."""
    m = re.search(r"<template\b[^>]*>.*</template>", text or "", re.S | re.I)
    return m.group(0) if m else None


# what a scene's code may not call: the render is offline and deterministic. (pattern, what it is, how to fix it) - the
# fix goes back to the AI word for word in the repair round
_NET_FIX = ("the scene renders offline with no network: write the data inline in the script as a constant "
            "(const items = [...]); to SHOW a request on a code card, put it in an SVG <text> label, never call it")
FORBIDDEN_CODE = (
    (r"\bfetch\s*\(", "fetch()", "network", _NET_FIX),
    (r"\bXMLHttpRequest\b", "XMLHttpRequest", "network", _NET_FIX),
    (r"\bWebSocket\b", "WebSocket", "network", _NET_FIX),
    (r"\bEventSource\b", "EventSource", "network", _NET_FIX),
    (r"\bsendBeacon\b", "navigator.sendBeacon", "network", _NET_FIX),
    (r"(?<![\w.$])import\s*\(", "import()", "network", _NET_FIX),
    (r"\b(?:localStorage|sessionStorage)\b|document\.cookie", "browser storage", "storage",
     "the scene has no storage: keep state in plain variables of the script"),
    (r"Math\.random", "Math.random", "random", "renders must be deterministic: use fixed values"),
    (r"\bnew\s+Date\b|\bDate\.now\b", "Date", "random", "renders must be deterministic: use fixed values"),
    (r"\bset(?:Timeout|Interval)\b", "timers", "motion", "place every change on the GSAP timeline at its time"),
)
FORBIDDEN_MARKUP = (
    (r"<iframe\b", "an <iframe>", "network", _NET_FIX),
    (r"<(?:img|image|link|source)\b[^>]*(?:src|href)\s*=\s*[\"']?\s*(?:https?:)?//", "an outside file (<img> / <link>)",
     "network", "draw it with SVG shapes; no outside images or styles"),
    (r"@import\b|url\(\s*[\"']?\s*(?:https?:)?//", "an outside file in the CSS (@import / url(http…))", "network",
     "only the two @font-face rules of the brief load files"),
    (r"<script\b[^>]*type\s*=\s*[\"']?module", "<script type=\"module\">", "network",
     "use a plain <script> with one IIFE"),
    (r"<audio\b", "an <audio> element", "media", "the voice is added by the renderer"),
    (r"<video\b", "a <video> element", "media", "draw it with SVG"),
    (r"@keyframes", "CSS @keyframes", "motion", "use the GSAP timeline"),
)
GSAP_SRC = "https://cdn.jsdelivr.net/npm/gsap@"


def code_only(js):
    """A script without its comments and string literals (a code card's ``"fetch('/tools')"`` is text, not a call)."""
    out, i, n = [], 0, len(js or "")
    while i < n:
        c = js[i]
        if c == "/" and js.startswith("//", i):
            j = js.find("\n", i)
            i = n if j < 0 else j
        elif c == "/" and js.startswith("/*", i):
            j = js.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c in "'\"`":
            j = i + 1
            while j < n and js[j] != c:
                j += 2 if js[j] == "\\" else 1
            out.append(" '' ")
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def forbidden(html):
    """[(what, kind, fix)] for each forbidden API the scene's scripts call or its markup loads."""
    found = []
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html or "", re.S | re.I)
    code = "\n".join(code_only(body) for _a, body in scripts)
    for rx, what, kind, fix in FORBIDDEN_CODE:
        if re.search(rx, code):
            found.append((what, kind, fix))
    markup = re.sub(r"<script\b[^>]*>.*?</script>", "", html or "", flags=re.S | re.I)
    for rx, what, kind, fix in FORBIDDEN_MARKUP:
        if re.search(rx, markup, re.I) or (what.startswith("<script") and any(
                re.search(r"type\s*=\s*[\"']?module", a, re.I) for a, _b in scripts)):
            found.append((what, kind, fix))
    for attrs, _body in scripts:
        m = re.search(r"src\s*=\s*[\"']([^\"']+)", attrs)
        if m and not m.group(1).startswith(GSAP_SRC):
            found.append((f"the outside script {m.group(1)[:60]}", "network",
                          "the GSAP <script> of the brief is the only outside file"))
    seen, out = set(), []
    for f in found:
        if f[0] not in seen:
            seen.add(f[0])
            out.append(f)
    return out


def problem_kind(problems):
    """The plain reason a scene was refused, for the creator: network | format | text | motion | media | other."""
    t = " ".join(problems or []).lower()
    for kind, rx in (("network", r"network|outside file|outside script|iframe"), ("text", r"short labels|only text"),
                     ("motion", r"timers|keyframes|deterministic|infinite"),
                     ("format", r"template|composition-id|data-width|data-duration|class=\"clip\"|placeholder|asset"),
                     ("media", r"<audio>|<video>")):
        if re.search(rx, t):
            return kind
    return "other"


def scene_problems(html, sid, duration=None, W=None, H=None):
    """What keeps a scene file from rendering as a real explainer scene -> [plain problems] ([] = good)."""
    p = []
    if not html or not html.strip().lower().startswith("<template"):
        return ["the reply is not one <template> ... </template> file"]
    if not re.search(rf'data-composition-id\s*=\s*"{re.escape(sid)}"', html):
        p.append(f'the root needs data-composition-id="{sid}"')
    if not re.search(rf"""window\.__timelines\[\s*["']{re.escape(sid)}["']\s*\]\s*=""", html):
        p.append(f'the timeline must be registered as window.__timelines["{sid}"]')
    if "gsap" not in html or "gsap.timeline" not in html:
        p.append("one paused gsap.timeline is needed (GSAP script inside the template)")
    if not re.search(r'class\s*=\s*"[^"]*\bclip\b', html):
        p.append('the stage div needs class="clip" with data-start / data-duration / data-track-index')
    if W and H and not re.search(rf'data-width\s*=\s*"{int(W)}"', html):
        p.append(f'the root needs data-width="{int(W)}" data-height="{int(H)}"')
    if PLACEHOLDER.search(re.sub(r"<!--.*?-->", "", html, flags=re.S)):
        p.append("it still contains a placeholder (TODO / TBD)")
    if "../" in html:
        p.append('asset paths must be project-root-relative (no "../")')
    if re.search(r"repeat\s*:\s*-1", html):
        p.append("remove repeat: -1 (infinite tweens): every tween has an end on the timeline")
    for what, _kind, fix in forbidden(html):
        p.append(f"{what} is not allowed: {fix}")
    if len(DRAWN.findall(html)) < 3:
        p.append("draw the idea: diagrams / shapes / arrows in SVG (only text was found)")
    # a wall of sentences: many long text runs is the narration put on screen
    texts = [re.sub(r"<[^>]+>", "", t) for t in re.findall(r"<text\b[^>]*>(.*?)</text>", html, re.S)]
    texts += re.findall(r"textContent\s*=\s*[\"'`]([^\"'`]{0,200})", html)
    long_runs = [t for t in texts if len(re.findall(r"[㐀-鿿]", t)) > 22 or len(t.split()) > 12]
    if len(long_runs) >= 3:
        p.append("on-screen text must be short labels, not narration sentences (captions show those)")
    if duration is not None:
        m = re.search(r'id\s*=\s*"root"[^>]*data-duration\s*=\s*"([0-9.]+)"', html) or \
            re.search(r'data-duration\s*=\s*"([0-9.]+)"[^>]*id\s*=\s*"root"', html)
        if not m:
            p.append(f'the root needs data-duration="{duration:.2f}"')
        elif abs(float(m.group(1)) - float(duration)) > 0.6:
            p.append(f'data-duration must be {duration:.2f} (the scene is fixed to the voice)')
    return p


LINT = os.environ.get("VSTUDIO_SCENE_LINT", "1") != "0"


def lint_scenes(scenes_dir, scenes, W, H, timeout=180):
    """The renderer's own checks of the scenes in ``scenes_dir`` (``npx hyperframes check``: its lint, then the scenes
    run in a browser - a script that throws blocks the render) -> {scene id: [error findings, with the fix]}. Run on a
    scratch copy with a minimal index (the checks start from the index); {} when there is no npx / it does not answer
    (the render reports it then)."""
    import shutil
    import subprocess
    import tempfile
    npx = shutil.which("npx")
    if not npx or not scenes:
        return {}
    with tempfile.TemporaryDirectory(prefix="vstudio-check-") as tmp:
        os.makedirs(os.path.join(tmp, "compositions"))
        hosts, t = [], 0.0
        for k, (sid, dur) in enumerate(scenes):
            src = os.path.join(scenes_dir, f"{sid}.html")
            if not os.path.exists(src):
                continue
            shutil.copy(src, os.path.join(tmp, "compositions", f"{sid}.html"))
            hosts.append(f'<div id="h{k}" data-composition-id="{sid}" data-composition-src="compositions/{sid}.html" '
                         f'data-start="{t:.2f}" data-duration="{dur:.2f}" data-track-index="{k + 1}" '
                         f'data-width="{W}" data-height="{H}"></div>')
            t += dur
        with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
            f.write(f'<!doctype html><html><head><meta charset="UTF-8"></head><body><div id="root" '
                    f'data-composition-id="main" data-start="0" data-width="{W}" data-height="{H}" '
                    f'data-duration="{t:.2f}">{"".join(hosts)}</div>'
                    # a root timeline: without one the browser pass never runs the scenes' scripts
                    '<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script><script>'
                    'window.__timelines = window.__timelines || {}; '
                    'window.__timelines["main"] = gsap.timeline({ paused: true });</script></body></html>')
        try:
            r = subprocess.run([npx, "hyperframes", "check", "--json", "--no-contrast", "--samples", "1"], cwd=tmp,
                               capture_output=True, text=True, timeout=timeout)
            doc = json.loads(r.stdout or "{}")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return {}
    out = {}
    if not isinstance(doc, dict):
        return out
    finds = list((doc.get("lint") or {}).get("findings") or []) + list((doc.get("runtime") or {}).get("findings") or [])
    for f in finds:
        if f.get("severity") != "error" or f.get("code") in ("http_error", "request_failed"):
            continue                      # the scratch copy has no fonts: their 404s are not the scene's
        msg = str(f.get("message") or "")
        m = re.search(r"compositions[/\\]([^/\\]+)\.html", str(f.get("sourceFile") or f.get("file") or "")) or \
            re.search(r"script error: (\S+) ", msg)
        if m:
            out.setdefault(m.group(1), []).append(
                f"renderer check {f.get('code')}: {msg} Fix: {f.get('fixHint') or 'make the script run without errors'}"
                .strip()[:600])
    return out


LOOK = os.environ.get("VSTUDIO_SCENE_LOOK", "1") != "0"


def look_problems(item_dir, scenes_dir, scenes, canvas):
    """The look of the scenes (``vstudio.look.look_scenes``): each drawn twice in shuffled order (a picture that
    changes = not seek-safe), fonts that cannot load (its CSS against the item's assets/fonts and the subsets the
    render makes; then the browser's own), text cut off or in the caption band -> {scene id: [problem + fix]}."""
    from vstudio import look as LK
    from .explainer import _CJK_FONTS
    W, H = canvas["W"], canvas["H"]
    band = None
    cap = canvas.get("caption")                # (x0, y0, x1, y1): the bilingual captions' band
    if isinstance(cap, (list, tuple)) and len(cap) == 4 and H:
        band = round(float(cap[1]) / H, 3)
    made = [f"assets/fonts/{o}.woff2" for _r, outs in _CJK_FONTS for o in outs]
    try:
        return LK.look_scenes(scenes_dir, scenes, W, H, assets=os.path.join(item_dir, "assets"), caption_band=band,
                              will_exist=made)
    except Exception:  # noqa: BLE001  (a look that cannot run is no reason to refuse the scenes)
        return {}


def is_ai_scene(path):
    return AI_MARK in _read(path, 400)


# --------------------------------------------------------------------------- writing them
def _complete():
    from vstudio import llm
    return llm.complete


class SceneRefused(RuntimeError):
    """A scene the AI wrote that still failed its check after the repair rounds: ``problems`` word for word."""

    def __init__(self, sid, problems):
        super().__init__(f"{sid}: " + "; ".join(problems[:4]))
        self.problems = list(problems)


REPAIRS = int(os.environ.get("VSTUDIO_SCENE_REPAIRS") or 2)


def _one(inp, sc, request, instruction, complete, reference, timeout, attempts=None, problems=None, previous=None,
         log=None):
    """One scene -> (html, info) or raises the last error. The first answer, then up to ``REPAIRS`` targeted repairs:
    each one gets its own previous version back with the check's exact findings and their fix ("fetch() is not
    allowed: ... write the data inline"). ``problems`` / ``previous`` given: a repair of a scene the renderer's lint
    refused."""
    W, H = inp["canvas"]["W"], inp["canvas"]["H"]
    last = None
    for k in range(attempts or (1 + REPAIRS)):
        prompt = scene_prompt(inp, sc, request, instruction, problems, reference, previous)
        r = complete(TASK, SYSTEM, prompt, schema=None, max_tokens=16000, timeout=timeout, cli_timeout=timeout,
                     retries=1, effort=EFFORT)
        if not isinstance(r, dict) or r.get("provider") == "none":
            raise NeedsModel(needs_model_message(None), None)
        html = extract_template(r.get("text") or "")
        problems = scene_problems(html, sc["id"], sc["duration"], W, H) if html else \
            ["the reply is not one <template> ... </template> file: reply with the complete file only"]
        if not problems:
            return html, dict(provider=r.get("provider"), model=r.get("model"), cost_usd=r.get("cost_usd") or 0.0,
                              repairs=k)
        previous = html or previous           # the repair corrects this version (kept: what works in it)
        last = SceneRefused(sc["id"], problems)
        if log:
            log(f"scene {sc['id']}: refused by the check ({'; '.join(problems)[:200]}) - asking for a fix")
    raise last


def author_scenes(item_dir, workflow_dir, request="", instruction=None, complete=None, only=None, out_dir=None,
                  keep_ai=True, parallel=None, timeout=None, log=None, lint=None):
    """Write the scenes the item still needs (every scene without an AI-written file in ``out_dir``, default
    <item>/compositions; ``keep_ai=False``: all of them) -> the result dict in the module doc. A failing scene is
    left unwritten (never a placeholder); the first wave failing entirely stops the rest (a model that does not
    answer is not asked 14 times)."""
    log = log or (lambda m: None)
    complete = complete or _complete()
    out_dir = out_dir or os.path.join(item_dir, "compositions")
    os.makedirs(out_dir, exist_ok=True)
    inp = scene_inputs(item_dir, workflow_dir)
    ref_path = os.path.join(workflow_dir, "assets", "reference-scene.html" if inp["canvas"].get("legacy", True)
                            else "reference-scene-portrait.html")
    reference = _read(ref_path, 9000)
    todo = [s for s in inp["scenes"] if (only is None or s["id"] in only) and
            not (keep_ai and is_ai_scene(os.path.join(out_dir, f"{s['id']}.html")))]
    routed = routed_provider()
    res = dict(ok=True, written=[], failed={}, why={}, provider=None, model=None, cost_usd=0.0, error=None,
               error_code=None, provider_name=provider_name(routed), total=len(inp["scenes"]))
    if not todo:
        return res
    if routed in (None, "none"):
        msg = needs_model_message(None)
        return dict(res, ok=False, failed={s["id"]: "no model" for s in todo}, error=msg, error_code="needs-model")
    lock = threading.Lock()
    stop = threading.Event()
    limit = float(timeout or SCENE_TIMEOUT)

    def work(sc):
        if stop.is_set():
            raise RuntimeError("skipped: the model did not answer the first scenes")
        t0 = time.time()
        html, info = _one(inp, sc, request, instruction, complete, reference, limit, log=log)
        path = os.path.join(out_dir, f"{sc['id']}.html")
        tmp = path + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(AI_MARK + "\n" + html + "\n")
        os.replace(tmp, path)
        log(f"scene {sc['id']}: written by {info.get('provider')} in {time.time() - t0:.0f} s")
        return info

    n = max(1, min(int(parallel or PARALLEL), len(todo)))
    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = {ex.submit(work, sc): sc for sc in todo}
        for fut in as_completed(futs):
            sc = futs[fut]
            try:
                info = fut.result()
            except NeedsModel as e:
                stop.set()
                with lock:
                    res["failed"][sc["id"]] = str(e)
                continue
            except Exception as e:  # noqa: BLE001  (one scene: recorded, the others go on)
                with lock:
                    res["failed"][sc["id"]] = str(e)[:300]
                    if isinstance(e, SceneRefused):
                        res["why"][sc["id"]] = problem_kind(e.problems)
                    if not res["written"] and len(res["failed"]) >= n:
                        stop.set()       # the whole first wave failed: the model is not answering
                log(f"scene {sc['id']}: {str(e)[:200]}")
                continue
            with lock:
                res["written"].append(sc["id"])
                res["provider"], res["model"] = info.get("provider"), info.get("model")
                res["cost_usd"] += float(info.get("cost_usd") or 0.0)
    # the renderer's checks on what was drawn (its lint, then the scenes run in a browser), then the look (each scene
    # drawn twice in shuffled order, its fonts, text cut / in the caption band: vstudio.look): a scene they refuse
    # is asked again with the finding and its fix - two rounds (the browser pass only runs once the lint is clean)
    linted, looked = set(), {}
    for _round in range(2 if (LINT if lint is None else lint) and res["written"] else 0):
        by_id = {s["id"]: s for s in inp["scenes"]}
        todo_ = [(i, by_id[i]["duration"]) for i in res["written"] if i in by_id]
        bad = {k: v for k, v in lint_scenes(out_dir, todo_, inp["canvas"]["W"], inp["canvas"]["H"]).items()
               if k in by_id}
        if not bad and LOOK:
            bad = {k: v for k, v in look_problems(item_dir, out_dir, todo_, inp["canvas"]).items() if k in by_id}
            for k, v in bad.items():
                looked[k] = v
        if not bad:
            break
        linted |= set(bad)
        for sid, problems in bad.items():
            path = os.path.join(out_dir, f"{sid}.html")
            prev = _read(path).replace(AI_MARK, "").strip()
            try:
                html, _info = _one(inp, by_id[sid], request, instruction, complete, reference, limit, attempts=2,
                                   problems=problems, previous=prev, log=log)
            except Exception as e:  # noqa: BLE001  (the first version stays: the render may still take it)
                log(f"scene {sid}: lint fix failed: {str(e)[:160]}")
                continue
            with open(path, "w", encoding="utf-8") as f:
                f.write(AI_MARK + "\n" + html + "\n")
            log(f"scene {sid}: fixed after the renderer's check ({len(problems)} finding(s))")
    res["linted"] = sorted(linted)
    res["looked"] = {k: v[:3] for k, v in looked.items()}
    if res["failed"]:
        res["ok"] = False
        errs = " ".join(res["failed"].values()).lower()
        model_down = re.search(r"timed? ?out|no model|did not answer|401|auth|not logged|quota|rate.?limit|"
                               r"no usable provider|unavailable|not found|cli failed|overloaded", errs)
        res["error_code"] = "needs-model" if model_down else "scene-failed"
        res["error"] = needs_model_message(routed) if model_down else failed_message(inp["scenes"], res)
    return res


WHY_WORDS = {"network": "it tried to load data from the internet, which a video can't do",
             "format": "the AI's file was not a scene the renderer can play",
             "text": "the AI kept putting sentences on screen instead of a drawing",
             "motion": "its animation was not on the video's timeline",
             "media": "it tried to add sound or video of its own",
             "other": "it did not pass the renderer's check"}


def failed_message(scenes, res):
    """"Scene 14 of 14 couldn't be drawn: it tried to load data from the internet ..." in plain words."""
    n_of = {s["id"]: s["n"] for s in scenes}
    ids = list(res["failed"])
    first = ids[0]
    why = WHY_WORDS.get((res.get("why") or {}).get(first) or "other", WHY_WORDS["other"])
    total = res.get("total") or len(scenes)
    if len(ids) == 1:
        return f"Scene {n_of.get(first, first)} of {total} couldn't be drawn: {why}. Try again."
    nums = ", ".join(str(n_of.get(i, i)) for i in ids[:6]) + ("…" if len(ids) > 6 else "")
    return f"{len(ids)} of {total} scenes couldn't be drawn (scenes {nums}): {why}. Try again."


# --------------------------------------------------------------------------- a scene no model could draw
FALLBACK_MARK = "<!-- reelfold:scene by=fallback -->"
_STOP = set("a an the and or but of to in on for with is are was be it this that these those as at by from so we you "
            "they i our your its their then than into over just also very can will".split())


def _esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cue_label(text, cjk=10, words=4):
    """A short on-screen label from a cue's words: its first clause, <= ``cjk`` Chinese characters or ``words``
    English words (the captions say the rest)."""
    t = " ".join(str(text or "").split())
    clauses = [c.strip() for c in re.split(r"[，。！？；：、,.!?;:()（）\"“”]+", t) if c.strip()]
    first = clauses[0] if clauses else t
    if re.search(r"[㐀-鿿]", first):
        width = lambda x: sum(1.0 if re.match(r"[㐀-鿿]", ch) else 0.5 for ch in x)  # noqa: E731
        if width(first) <= cjk:
            return first
        out = ""
        for tok in re.findall(r"[㐀-鿿]|[^㐀-鿿\s]+|\s+", first):   # never cut inside a Latin word
            if width(out + tok) > cjk - 1:
                break
            out += tok
        return out.strip() + "…"
    ws = [w for w in re.findall(r"[\w'’+#/-]+", first) if w.lower() not in _STOP] or first.split()
    return " ".join(ws[:words])


def _lines(label, cjk):
    """A label in at most two lines (a box is narrow when there are five)."""
    if cjk or len(label) <= 14 or " " not in label:
        return [label]
    ws = label.split()
    h = (len(ws) + 1) // 2
    return [" ".join(ws[:h]), " ".join(ws[h:])]


def fallback_scene(inp, sc):
    """A simple, valid diagram drawn from the scene's own cues - one box per idea, joined by arrows that draw on the
    voice's cue times, the newest lit, the whole flow at the end - for a scene the AI could not draw (never the
    narration as lines of text, never a placeholder). Carries ``FALLBACK_MARK``: the next redo draws it again."""
    cv = inp["canvas"]
    W, H = cv["W"], cv["H"]
    x0, y0, x1, y1 = (80, 80, 1840, 800) if cv.get("legacy", True) else (cv.get("math") or (80, 80, W - 80, 800))
    sid, dur = sc["id"], float(sc["duration"])
    cues = [c for c in sc.get("cues") or [] if (c.get("text") or "").strip()] or \
        [dict(t=0.3, text=sc.get("spoken") or sc.get("label") or sid)]
    if len(cues) < 2:         # one cue: its clauses are the steps, spread over the scene
        parts = [c.strip() for c in re.split(r"[，。！？；,.!?;]+", cues[0]["text"]) if len(c.strip()) > 1][:3]
        if len(parts) > 1:
            t0 = float(cues[0].get("t") or 0.3)
            cues = [dict(t=t0 + i * (dur - t0) * 0.6 / len(parts), text=x) for i, x in enumerate(parts)]
    k = min(len(cues), 5)
    picks = [cues[int(i * len(cues) / k)] for i in range(k)]
    cjk = inp.get("lang") == "zh"
    labels = [cue_label(c["text"]) or str(i + 1) for i, c in enumerate(picks)]
    title = cue_label(sc.get("label") or "", cjk=12, words=4) or ""
    roles = ["#58C4DD", "#5CD0B3", "#E88CC4", "#58C4DD", "#5CD0B3"]
    top = y0 + (90 if title else 20)
    across = (x1 - x0) >= (y1 - top)
    gap = 70
    if across:
        bw = min(380, ((x1 - x0) - gap * (k - 1)) / k)
        bh = 150
        total = bw * k + gap * (k - 1)
        boxes = [(x0 + ((x1 - x0) - total) / 2 + i * (bw + gap), top + ((y1 - top) - bh) / 2) for i in range(k)]
    else:
        bw = min(760, x1 - x0)
        bh = min(150, ((y1 - top) - gap * (k - 1)) / k)
        total = bh * k + gap * (k - 1)
        boxes = [(x0 + ((x1 - x0) - bw) / 2, top + ((y1 - top) - total) / 2 + i * (bh + gap)) for i in range(k)]
    fs = 30 if k >= 4 else 36
    # a faint spine under the flow: the boxes sit on one line of thought
    if across:
        sy = boxes[0][1] + bh + 46
        svg = [f'<line id="{sid}-spine" x1="{boxes[0][0]:.1f}" y1="{sy:.1f}" x2="{boxes[-1][0] + bw:.1f}" '
               f'y2="{sy:.1f}" stroke="#2A3247" stroke-width="3"/>']
    else:
        sx = boxes[0][0] - 36
        svg = [f'<line id="{sid}-spine" x1="{sx:.1f}" y1="{boxes[0][1]:.1f}" x2="{sx:.1f}" '
               f'y2="{boxes[-1][1] + bh:.1f}" stroke="#2A3247" stroke-width="3"/>']
    if title:
        svg.append(f'<text id="{sid}-title" x="{x0}" y="{y0 + 44}" font-size="44" fill="#6B7488" '
                   f'class="{sid}-t">{_esc(title)}</text>')
    for i, ((bx, by), lab) in enumerate(zip(boxes, labels)):
        col = "#F4D35E" if i == k - 1 and k > 1 else roles[i]
        ls = _lines(lab, cjk)
        cy = by + bh / 2 - (len(ls) - 1) * fs * 0.6
        tx = "".join(f'<tspan x="{bx + bw / 2:.1f}" y="{cy + j * fs * 1.2 + fs * 0.35:.1f}">{_esc(t)}</tspan>'
                     for j, t in enumerate(ls))
        svg.append(f'<g id="{sid}-n{i}" opacity="0"><rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" '
                   f'height="{bh:.1f}" rx="14" fill="#121A30" stroke="{col}" stroke-width="3"/>'
                   f'<circle cx="{bx + 28:.1f}" cy="{by + 28:.1f}" r="12" fill="{col}"/>'
                   f'<text text-anchor="middle" font-size="{fs}" fill="#ECEEF2" class="{sid}-t">{tx}</text></g>')
        if i:
            (px, py) = boxes[i - 1]
            if across:
                ax0, ay0, ax1, ay1 = px + bw + 8, py + bh / 2, bx - 14, by + bh / 2
                head = f"{ax1 + 12:.1f},{ay1:.1f} {ax1 - 2:.1f},{ay1 - 9:.1f} {ax1 - 2:.1f},{ay1 + 9:.1f}"
            else:
                ax0, ay0, ax1, ay1 = px + bw / 2, py + bh + 8, bx + bw / 2, by - 14
                head = f"{ax1:.1f},{ay1 + 12:.1f} {ax1 - 9:.1f},{ay1 - 2:.1f} {ax1 + 9:.1f},{ay1 - 2:.1f}"
            ln = abs(ax1 - ax0) + abs(ay1 - ay0)
            svg.append(f'<line id="{sid}-a{i}" x1="{ax0:.1f}" y1="{ay0:.1f}" x2="{ax1:.1f}" y2="{ay1:.1f}" '
                       f'stroke="#6B7488" stroke-width="3" stroke-dasharray="{ln:.1f}" stroke-dashoffset="{ln:.1f}"/>'
                       f'<polygon id="{sid}-h{i}" points="{head}" fill="#6B7488" opacity="0"/>')
    tl = []
    if title:
        tl.append(f'tl.to(q("title"), {{ opacity: 1, duration: 0.6, ease: "power2.out" }}, 0.1);')
    full = round(dur * 0.85, 2)
    for i, c in enumerate(picks):
        at = round(max(0.15, min(float(c.get("t") or 0) - 0.1, dur - 1.0)), 2)
        if i:
            tl.append(f'tl.to(q("a{i}"), {{ strokeDashoffset: 0, duration: 0.45, ease: "power1.inOut" }}, '
                      f'{max(0.0, at - 0.3):.2f});')
            tl.append(f'tl.to(q("h{i}"), {{ opacity: 1, duration: 0.2 }}, {at - 0.05:.2f});')
            tl.append(f'tl.to(q("n{i - 1}"), {{ opacity: 0.55, duration: 0.4, ease: "power1.inOut" }}, {at:.2f});')
        tl.append(f'tl.to(q("n{i}"), {{ opacity: 1, y: 0, duration: 0.6, ease: "power2.out" }}, {at:.2f});')
    if k > 1 and full > (picks[-1].get("t") or 0) + 0.8:
        olds = ", ".join(f'q("n{i}")' for i in range(k - 1))
        tl.append(f'tl.to([{olds}], {{ opacity: 1, duration: 0.5, ease: "power1.inOut" }}, {full:.2f});')
    if sc.get("last"):
        tl.append(f'tl.to(q("drift"), {{ opacity: 0, duration: 0.6, ease: "power1.inOut" }}, {max(0.0, dur - 0.7):.2f});')
    hide = "gsap.set(q('title'), { opacity: 0 });" if title else ""
    body = "\n          ".join(svg)
    steps = "\n      ".join(tl)
    return f"""{FALLBACK_MARK}
<template>
  <style>
    @font-face {{ font-family: "Course CJK"; src: url("assets/fonts/scene-cjk-w4.woff2") format("woff2"); font-weight: 400 500; }}
    @font-face {{ font-family: "Course CJK"; src: url("assets/fonts/scene-cjk-w7.woff2") format("woff2"); font-weight: 600 900; }}
    #root {{ position: absolute; inset: 0; width: 100%; height: 100%; overflow: hidden; }}
    #{sid}-stage {{ position: absolute; inset: 0; }}
    #{sid}-svg {{ position: absolute; inset: 0; width: 100%; height: 100%; display: block; }}
    .{sid}-t {{ font-family: "Course CJK", sans-serif; }}
  </style>
  <div id="root" data-composition-id="{sid}" data-width="{W}" data-height="{H}" data-duration="{dur:.2f}">
    <div id="{sid}-stage" class="clip" data-start="0" data-duration="{dur:.2f}" data-track-index="1">
      <svg id="{sid}-svg" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
        <g id="{sid}-drift">
          {body}
        </g>
      </svg>
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <script>
    (function () {{
      const q = (n) => document.getElementById("{sid}-" + n);
      window.__timelines = window.__timelines || {{}};
      {hide}
      for (let i = 0; i < {k}; i++) gsap.set(q("n" + i), {{ y: 16 }});
      const tl = gsap.timeline({{ paused: true }});
      tl.to(q("drift"), {{ y: -6, duration: {dur:.2f}, ease: "sine.inOut" }}, 0);
      {steps}
      window.__timelines["{sid}"] = tl;
    }})();
  </script>
</template>
"""


def scenes_complete(path, item_dir=None):
    """Every scene of scenes.config.json has its composition, and none still carries a placeholder."""
    item_dir = item_dir or os.path.dirname(path.rstrip("/\\"))
    try:
        ids = [s["id"] for s in _load(os.path.join(item_dir, "scenes.config.json")).get("scenes") or []]
    except (OSError, ValueError, KeyError, TypeError):
        return True                                  # nothing to compare with: the folder decides
    for sid in ids:
        f = os.path.join(path, f"{sid}.html")
        if not os.path.isfile(f) or PLACEHOLDER.search(re.sub(r"<!--.*?-->", "", _read(f), flags=re.S)):
            return False
    return True
