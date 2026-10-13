"""Look at an HTML-rendered video before anyone else does: a HyperFrames project (an explainer's scenes, a launch-kit
film, a cover / slide page, any composition) drawn at sampled times and checked for what goes wrong only in a browser.

    python -m vstudio.look DIR [--count 12] [--at 1,2.5] [--video renders/x.mp4] [--caption-band 0.82] [--json]
    -> findings + a contact sheet (DIR/.look/contact-sheet.jpg); exit 1 when an error is found.

    from vstudio import look
    res = look.look("items/ep1")          # {ok, errors, warnings, passed, frames, sheet, ...}

Checks (each finding: {code, severity error|warning, message, fix, t?, file?, selector?, scene?}):
  look-nondeterministic  the same time drawn twice - in two shuffled orders, the way a person scrubs - gave two
                         pictures: something besides the time decides the frame (a clock, Math.random, state kept
                         between seeks, a tween that took its start from the screen, an onUpdate counter)
  look-font-failed       a font the page asks for did not load (the browser's own document.fonts, or a 404 on a
                         font file): the text falls back to another face
  look-text-clipped      text runs out of its box / the frame (``hyperframes check`` layout pass)
  look-safe-area         text in the caption band or at the frame's edge (where captions / platform UI sit)
  look-script-error      a script threw while the page ran (``hyperframes check`` runtime pass)
  look-audio-missing     an <audio> the composition plays is not there, has no sound stream, or is silent; or the
                         rendered video (``--video``) has no audio track while the composition has sound
  look-static            every sampled frame is the same picture (warning: nothing moves with time)
The browser work is ``npx hyperframes snapshot`` (twice, two shuffled orders of the same times) and ``npx hyperframes
check`` (runtime + layout, frame and caption-band checks); the comparison, the audio checks and the contact sheet are
done here. No Node / no answer from the CLI -> those checks are skipped and said so (``skipped``), never invented.

Learned from OpenFilm's ``look`` (github.com/openfilm/openfilm, MIT): draw every sampled frame twice in two shuffled
orders and compare; failed fonts; text cut by its box or the frame; missing sounds; a contact sheet.
"""
import argparse
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

RUN = None              # tests / embedders: fn(args, cwd, timeout) -> (returncode, stdout, stderr)
SAME_LIMIT = 6.0        # mean abs difference (0-255) of the worst 32 px block that is still anti-aliasing noise
BLOCK = 32
FONT_EXT = (".woff2", ".woff", ".ttf", ".otf")
SEVERITY = {"look-nondeterministic": "error", "look-font-failed": "error", "look-text-clipped": "error",
            "look-safe-area": "warning", "look-script-error": "error", "look-audio-missing": "error",
            "look-static": "warning", "look-lint": "error"}
FIX = {
    "look-nondeterministic": "make the picture depend only on the time: no Math.random / Date / counters in "
                             "onUpdate; use fromTo tweens with explicit start values; set state with tl.set at its time",
    "look-font-failed": "use a font the project ships (an @font-face whose file is in assets/fonts) or a system "
                        "family; check the url() path is project-root-relative",
    "look-text-clipped": "shorten the text, make it smaller, or let it wrap (max-width) so it fits its box and the "
                         "frame",
    "look-safe-area": "keep text out of the caption band at the bottom and away from the frame's edges",
    "look-script-error": "make the script run without errors (check the console message)",
    "look-audio-missing": "point the <audio> at an existing file with sound, or render with the audio track",
    "look-static": "animate on the timeline: every scene changes over its time",
    "look-lint": "fix what the renderer's lint names (its own hint follows)",
}


def _finding(code, message, **kw):
    d = dict(code=code, severity=kw.pop("severity", None) or SEVERITY[code], message=message, fix=FIX[code])
    d.update({k: v for k, v in kw.items() if v is not None})
    return d


# --------------------------------------------------------------------------- running the CLI
def hyperframes_spec():
    return os.environ.get("VSTUDIO_HYPERFRAMES") or "hyperframes"


def _run(args, cwd, timeout=240):
    """``npx hyperframes <args>`` in ``cwd`` -> (code, stdout, stderr); (None, "", why) when it cannot run."""
    if RUN is not None:
        return RUN(args, cwd, timeout)
    try:
        from vstudio import node
        cmd = node.npx("-y", hyperframes_spec(), *args)
        env = node.child_env()
    except Exception as e:  # noqa: BLE001  (no Node: the browser checks are skipped, said so)
        return None, "", str(e)[:300]
    env.setdefault("npm_config_yes", "true")
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, "", str(e)[:300]
    return r.returncode, r.stdout or "", r.stderr or ""


def _strip(s):
    return re.sub(r"\x1b\[[0-9;]*m", "", s or "")


# --------------------------------------------------------------------------- times
def sample_times(duration, count=12, start=0.0):
    """``count`` times across [start, duration) (OpenFilm's spread: start + span * i / count), never the very end."""
    duration = float(duration)
    count = max(1, int(count))
    span = max(0.0, duration - start)
    return [round(min(duration - 1e-3, start + span * i / count + (span / count) / 2), 3) for i in range(count)]


def shuffled(times, seed):
    out = list(times)
    random.Random(seed).shuffle(out)
    return out


def composition_duration(project_dir):
    """data-duration of the root composition of index.html (or None)."""
    try:
        with open(os.path.join(project_dir, "index.html"), encoding="utf-8") as f:
            html = f.read(400_000)
    except OSError:
        return None
    m = re.search(r'<[^>]+data-composition-id\s*=\s*"[^"]*"[^>]*>', html)
    if m:
        d = re.search(r'data-duration\s*=\s*"([0-9.]+)"', m.group(0))
        if d:
            return float(d.group(1))
    return None


# --------------------------------------------------------------------------- snapshots and the comparison
def snapshot(project_dir, times, out_dir, timeout=240):
    """``hyperframes snapshot --at`` in this order -> ({t: png}, fonts_failed [family], error | None)."""
    os.makedirs(out_dir, exist_ok=True)
    code, out, err = _run(["snapshot", "--at", ",".join(f"{t:g}" for t in times), "--no-end", "-o", out_dir,
                           "--describe", "false", "."], project_dir, timeout)
    if code is None:
        return {}, [], err or "hyperframes did not run"
    text = _strip(out + "\n" + err)
    fonts = []
    for m in re.finditer(r"Fonts FAILED:\s*(.+)", text):
        fonts += [re.sub(r"\s*\(.*?\)\s*$", "", x).strip() for x in m.group(1).split(",") if x.strip()]
    frames = {}
    for p in glob.glob(os.path.join(out_dir, "frame-*-at-*s.png")):
        m = re.search(r"-at-([0-9.]+)s\.png$", p)
        if m:
            frames[round(float(m.group(1)), 3)] = p
    if code != 0 and not frames:
        return {}, fonts, (text.strip().splitlines() or ["snapshot failed"])[-1][:300]
    got = {}
    for t in times:
        k = min(frames, key=lambda x: abs(x - t), default=None)
        if k is not None and abs(k - t) < 0.01:
            got[t] = frames[k]
    return got, fonts, None


def block_diff(a, b, block=BLOCK):
    """The worst mean abs difference (0-255) over ``block`` px tiles of two images (0 = same); 255 when the sizes
    differ. Anti-aliasing noise on text edges stays a few units; a moved or recoloured shape does not."""
    import numpy as np
    from PIL import Image
    A = np.asarray(Image.open(a).convert("RGB"), dtype=np.int16)
    B = np.asarray(Image.open(b).convert("RGB"), dtype=np.int16)
    if A.shape != B.shape:
        return 255.0
    d = np.abs(A - B).mean(axis=2)
    h, w = d.shape
    H, W = (h + block - 1) // block, (w + block - 1) // block
    pad = np.zeros((H * block, W * block))
    pad[:h, :w] = d
    return float(pad.reshape(H, block, W, block).mean(axis=(1, 3)).max())


def _same_file(a, b):
    try:
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def compare(first, second, limit=SAME_LIMIT):
    """{t: png} x2 -> [t whose two pictures differ]."""
    bad = []
    for t in sorted(set(first) & set(second)):
        a, b = first[t], second[t]
        if _same_file(a, b):
            continue
        if block_diff(a, b) > limit:
            bad.append(t)
    return bad


def contact_sheet(frames, out, marks=None, cols=None, cell_w=360):
    """A grid of the sampled frames, each labelled with its time; ``marks`` {t: label} get a red frame and the label
    (a frame that differed, text cut ...). -> out (JPEG)."""
    from PIL import Image, ImageDraw
    ts = sorted(frames)
    if not ts:
        return None
    marks = marks or {}
    first = Image.open(frames[ts[0]])
    cell_h = max(1, round(cell_w * first.height / max(1, first.width)))
    n = len(ts)
    cols = cols or (n if n <= 4 else 3 if n <= 9 else 4)
    rows = (n + cols - 1) // cols
    pad, head = 6, 22
    sheet = Image.new("RGB", (cols * (cell_w + pad) + pad, rows * (cell_h + head + pad) + pad), (17, 17, 17))
    dr = ImageDraw.Draw(sheet)
    for i, t in enumerate(ts):
        im = Image.open(frames[t]).convert("RGB").resize((cell_w, cell_h))
        x = pad + (i % cols) * (cell_w + pad)
        y = pad + (i // cols) * (cell_h + head + pad)
        sheet.paste(im, (x, y + head))
        label = f"#{i + 1}  {t:g}s"
        if t in marks:
            dr.rectangle([x - 2, y + head - 2, x + cell_w + 1, y + head + cell_h + 1], outline=(255, 59, 48), width=3)
            label += f"  {marks[t]}"
        dr.text((x + 2, y + 4), label[:60], fill=(255, 120, 110) if t in marks else (230, 230, 230))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out, quality=88)
    return out


# --------------------------------------------------------------------------- the renderer's checks
def check_args(samples=6, caption_band=None, edge=True):
    a = ["check", ".", "--json", "--no-contrast", "--samples", str(int(samples))]
    if edge:
        a += ["--frame-check", "severity=warning;tol=4"]
    if caption_band:
        a += ["--caption-zone", f"x0=0;y0={float(caption_band):.3f};x1=1;y1=1;severity=warning"]
    return a


def from_check(doc):
    """``hyperframes check --json`` -> findings (fonts, text cut / off the frame, the caption band, script errors)."""
    out = []
    if not isinstance(doc, dict):
        return out
    for f in (doc.get("lint") or {}).get("findings") or []:
        if f.get("severity") != "error":
            continue
        code = str(f.get("code") or "")
        msg = str(f.get("message") or code)[:300]
        kind = "look-audio-missing" if re.search(r"audio|media_", code) else "look-lint"
        out.append(_finding(kind, msg, file=f.get("sourceFile"), hint=f.get("fixHint"), rule=code))
    for f in (doc.get("runtime") or {}).get("findings") or []:
        url = str(f.get("url") or "")
        msg = str(f.get("message") or "")
        if f.get("code") in ("http_error", "request_failed"):
            if url.lower().split("?")[0].endswith(FONT_EXT) or re.search(r"\.(woff2?|ttf|otf)\b", msg, re.I):
                if f.get("code") == "http_error":
                    out.append(_finding("look-font-failed", f"font file not loaded: {msg}",
                                        file=f.get("sourceFile"), t=f.get("time")))
            continue
        if f.get("severity") == "error":
            out.append(_finding("look-script-error", msg[:300], file=f.get("sourceFile"), t=f.get("time")))
    for f in (doc.get("layout") or {}).get("findings") or []:
        code = f.get("code") or ""
        text = str(f.get("text") or "")[:60]
        times = f.get("times") or ([f.get("time")] if f.get("time") is not None else [])
        base = dict(file=f.get("sourceFile"), selector=f.get("selector"), t=times[0] if times else None,
                    times=times or None, hint=f.get("fixHint"))
        if code in ("text_box_overflow", "canvas_overflow", "text_overflow", "text_clipped"):
            # text on its way in shows once; cut in two samples or more (or by its own box) is a finding
            if code == "canvas_overflow" and len(times) < 2:
                continue
            out.append(_finding("look-text-clipped", f"\"{text}\" {f.get('message') or 'is cut off'}", **base))
        elif code in ("caption_zone_collision",) or code.startswith("frame_"):
            out.append(_finding("look-safe-area", f"\"{text}\" {f.get('message') or 'is outside the safe area'}",
                                **base))
    return out


def run_check(project_dir, samples=6, caption_band=None, timeout=240):
    """-> (findings, error | None)."""
    code, out, err = _run(check_args(samples, caption_band), project_dir, timeout)
    if code is None:
        return [], err or "hyperframes did not run"
    try:
        doc = json.loads(out or "{}")
    except ValueError:
        m = re.search(r"\{.*\}\s*$", out or "", re.S)
        try:
            doc = json.loads(m.group(0)) if m else {}
        except ValueError:
            doc = {}
    if not doc or doc.get("error"):
        return [], str(doc.get("error") or _strip(err).strip()[-300:] or "check gave no answer")
    found = from_check(doc)
    if doc.get("browserSkipped"):
        found.append(dict(code="look-skipped", severity="info", message="layout not checked: the renderer's lint "
                          "found errors first", fix=""))
    return found, None


# --------------------------------------------------------------------------- sound
def _audio_srcs(project_dir):
    srcs = []
    for p in [os.path.join(project_dir, "index.html")] + glob.glob(os.path.join(project_dir, "compositions", "*.html")):
        try:
            with open(p, encoding="utf-8") as f:
                html = f.read(400_000)
        except OSError:
            continue
        for m in re.finditer(r"<audio\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", html, re.I):
            srcs.append((os.path.relpath(p, project_dir), m.group(1)))
    return srcs


def _max_volume(path):
    try:
        from vstudio import media
        ff = media.ffmpeg_bin()
    except Exception:  # noqa: BLE001
        ff = shutil.which("ffmpeg")
    if not ff:
        return None
    r = subprocess.run([ff, "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    m = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", r.stderr or "")
    if not m:
        return None
    return float("-inf") if m.group(1) == "-inf" else float(m.group(1))


def _has_audio(path):
    try:
        from vstudio import media
        return bool(media.probe(path).get("has_audio"))
    except Exception:  # noqa: BLE001
        return None


def check_audio(project_dir, video=None):
    """Every <audio src> of the composition exists, has a sound stream and is not silent; the rendered ``video``
    has an audio track when the composition plays sound."""
    out = []
    srcs = _audio_srcs(project_dir)
    for page, src in srcs:
        if re.match(r"^(?:https?:)?//|^data:", src):
            continue
        p = os.path.normpath(os.path.join(project_dir, src.split("#")[0].split("?")[0]))
        if not os.path.isfile(p):
            out.append(_finding("look-audio-missing", f"sound not found: {src}", file=page))
            continue
        if _has_audio(p) is False:
            out.append(_finding("look-audio-missing", f"{src} has no sound stream", file=page))
            continue
        mv = _max_volume(p)
        if mv is not None and mv < -60:
            out.append(_finding("look-audio-missing", f"{src} is silent (peak {mv:g} dB)", file=page,
                                severity="warning"))
    if video and srcs and os.path.isfile(video) and _has_audio(video) is False:
        out.append(_finding("look-audio-missing", f"{os.path.basename(video)} has no audio track although the "
                            "composition plays sound", file=os.path.basename(video)))
    return out


# --------------------------------------------------------------------------- static font check (no browser)
GENERIC = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif", "ui-serif",
           "ui-monospace", "ui-rounded", "emoji", "math", "fangsong", "inherit", "initial", "unset", "revert",
           "-apple-system", "blinkmacsystemfont", "helvetica", "helvetica neue", "arial", "pingfang sc",
           "hiragino sans gb", "microsoft yahei", "noto sans sc", "noto sans cjk sc", "source han sans sc",
           "segoe ui", "roboto", "inter", "menlo", "monaco", "consolas", "courier new", "georgia", "times new roman",
           "times", "courier", "verdana", "tahoma", "trebuchet ms", "sf pro display", "sf pro text", "sf mono",
           "avenir", "avenir next", "futura", "gill sans", "optima", "palatino", "didot", "baskerville", "songti sc",
           "heiti sc", "stheiti", "kaiti sc", "noto sans", "noto serif", "dejavu sans", "liberation sans", "var"}


def font_problems(html, project_dir=None, will_exist=()):
    """Fonts a page asks for that cannot load, read from its CSS: an @font-face whose file is not in the project
    (nor in ``will_exist``, files a later step makes) and a font-family used first in a stack that is neither
    declared nor a generic / common system family -> findings."""
    out = []
    css = "\n".join(re.findall(r"<style\b[^>]*>(.*?)</style>", html or "", re.S | re.I))
    css += "\n" + " ".join(re.findall(r"style\s*=\s*\"([^\"]*)\"", html or ""))
    declared = set()
    for face in re.findall(r"@font-face\s*\{(.*?)\}", css, re.S | re.I):
        fam = re.search(r"font-family\s*:\s*['\"]?([^;'\"]+)", face, re.I)
        if fam:
            declared.add(fam.group(1).strip().lower())
        for url in re.findall(r"url\(\s*['\"]?([^)'\"]+)", face, re.I):
            if re.match(r"^(?:https?:)?//|^data:", url) or project_dir is None:
                continue
            rel = os.path.normpath(url.split("?")[0].split("#")[0])
            if os.path.basename(rel) in {os.path.basename(x) for x in will_exist}:
                continue
            if not os.path.isfile(os.path.join(project_dir, rel)):
                out.append(_finding("look-font-failed", f"font file {url} is not in the project",
                                    font=fam.group(1).strip() if fam else None))
    body = re.sub(r"@font-face\s*\{.*?\}", "", css, flags=re.S | re.I)
    for stack in re.findall(r"font-family\s*:\s*([^;}]+)", body, re.I):
        first = stack.split(",")[0].strip().strip("'\"").lower()
        if first and not first.startswith("var(") and first not in declared and first not in GENERIC:
            # a warning: the page may mean the fallback (a reference scene's "JetBrains Mono", monospace)
            out.append(_finding("look-font-failed", f"font-family {first!r} is not declared with @font-face and is "
                                "not a system font: it shows in the fallback face", font=first, severity="warning"))
    seen, uniq = set(), []
    for f in out:
        if f["message"] not in seen:
            seen.add(f["message"])
            uniq.append(f)
    return uniq


# --------------------------------------------------------------------------- the look
def look(project_dir, times=None, count=12, duration=None, out_dir=None, caption_band=None, video=None,
         check=True, samples=6, timeout=240):
    """Draw, check, compare -> {ok, project, duration, times, errors, warnings, passed, skipped, frames {t: png},
    sheet, findings}. ``ok`` False when an error-severity finding was made."""
    project_dir = os.path.abspath(project_dir)
    out_dir = out_dir or os.path.join(project_dir, ".look")
    dur = duration or composition_duration(project_dir)
    findings, passed, skipped = [], [], []
    frames = {}
    if times is None and not dur:
        skipped.append("no duration on the root composition: say the times to look at (--at)")
        times = []
    times = [round(float(t), 3) for t in (times if times is not None else sample_times(dur, count))]
    if times:
        shutil.rmtree(os.path.join(out_dir, "a"), ignore_errors=True)
        shutil.rmtree(os.path.join(out_dir, "b"), ignore_errors=True)
        first, fonts, err = snapshot(project_dir, shuffled(times, 1), os.path.join(out_dir, "a"), timeout)
        if err:
            skipped.append(f"frames not drawn: {err}")
        else:
            second, fonts2, err2 = snapshot(project_dir, shuffled(times, 2), os.path.join(out_dir, "b"), timeout)
            frames = first
            for fam in sorted(set(fonts) | set(fonts2)):
                findings.append(_finding("look-font-failed", f"font failed to load: {fam}", font=fam))
            if err2:
                skipped.append(f"second pass not drawn: {err2}")
            else:
                bad = compare(first, second)
                for t in bad:
                    findings.append(_finding("look-nondeterministic", f"the same time drew two different pictures "
                                             f"at {t:g}s (compare {first[t]} with {second[t]})", t=t,
                                             a=first[t], b=second[t]))
                if not bad and first:
                    passed.append(f"{len(first)} frames drawn twice in two shuffled orders: same time, same picture")
            if len(first) > 1 and len({open(p, 'rb').read() for p in first.values()}) == 1:
                findings.append(_finding("look-static", "every sampled frame is the same picture"))
    if check:
        cf, err = run_check(project_dir, samples, caption_band, timeout)
        if err:
            skipped.append(f"renderer check not run: {err}")
        else:
            if any(f["code"] == "look-skipped" for f in cf):
                skipped.append("layout not checked: the renderer's lint found errors first")
            elif not any(f["code"] in ("look-text-clipped", "look-safe-area") for f in cf):
                passed.append("no text cut off or outside the safe area")
            # one finding per thing: the browser's font failure over a 404 of its file, one cut text per element
            fonts_seen = any(f["code"] == "look-font-failed" for f in findings)
            seen = set()
            for f in cf:
                if f["code"] == "look-skipped" or (f["code"] == "look-font-failed" and fonts_seen):
                    continue
                key = (f["code"], f.get("selector"), f.get("file")) if f.get("selector") else None
                if key and key in seen:
                    continue
                seen.add(key)
                findings.append(f)
    have = {f["message"] for f in findings if f["code"] == "look-audio-missing"}
    findings += [f for f in check_audio(project_dir, video)
                 if not any(os.path.basename(f["message"].split(": ")[-1]) in h for h in have)]
    marks = {}
    for f in findings:
        for t in f.get("times") or ([f["t"]] if f.get("t") is not None else []):
            k = min(frames, key=lambda x: abs(x - float(t)), default=None)
            if k is not None and abs(k - float(t)) <= max(0.5, (dur or 0) / max(1, len(frames)) / 2):
                marks.setdefault(k, f["code"].replace("look-", ""))
    sheet = contact_sheet(frames, os.path.join(out_dir, "contact-sheet.jpg"), marks) if frames else None
    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] != "error"]
    return dict(ok=not errors, project=project_dir, duration=dur, times=times, errors=errors, warnings=warnings,
                passed=passed, skipped=skipped, frames={f"{t:g}": p for t, p in sorted(frames.items())}, sheet=sheet,
                findings=findings)


def by_scene(findings, windows):
    """Findings -> {scene id: [findings]} by their file (compositions/<id>.html) or their time in ``windows``
    [(id, start, end)] (scene-local times of a scratch project laid end to end)."""
    out = {}
    for f in findings:
        sid = None
        m = re.search(r"compositions[/\\]([^/\\]+)\.html", str(f.get("file") or ""))
        if m:
            sid = m.group(1)
        elif f.get("t") is not None:
            t = float(f["t"])
            sid = next((i for i, a, b in windows if a - 1e-3 <= t < b), None)
        if sid:
            out.setdefault(sid, []).append(f)
    return out


def problem_text(f):
    """One finding as a problem line for the AI's repair round (what, where, the fix)."""
    where = f" at {float(f['t']):g}s" if f.get("t") is not None else ""
    sel = f" ({f['selector']})" if f.get("selector") else ""
    hint = f" {f['hint']}" if f.get("hint") else ""
    return f"look check {f['code']}{where}{sel}: {f['message']} Fix: {f['fix']}.{hint}"[:600]


def report(res, lang="en"):
    zh = lang == "zh"
    lines = [("画面检查" if zh else "Look") + f": {res['project']}" + (f" ({res['duration']:g}s)" if res.get("duration")
                                                                       else "")]
    for f in res["errors"]:
        lines.append(f"✗ {f['message']}" + (f" — {f['fix']}" if f.get("fix") else ""))
    for f in res["warnings"]:
        lines.append(f"! {f['message']}")
    lines += [f"✓ {p}" for p in res["passed"]] + [f"- skipped: {s}" for s in res["skipped"]]
    if res.get("sheet"):
        lines.append(f"→ {res['sheet']}")
    return "\n".join(lines)


def _cli(argv=None):
    ap = argparse.ArgumentParser(prog="python -m vstudio.look", description=__doc__.split("\n\n")[0])
    ap.add_argument("project", help="a HyperFrames project folder (index.html)")
    ap.add_argument("--count", type=int, default=12, help="frames across the composition (default 12)")
    ap.add_argument("--at", help="comma list of seconds instead of --count")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--video", help="the rendered video (checked for its audio track)")
    ap.add_argument("--caption-band", type=float, help="top of the caption band as a fraction of the height (0.82)")
    ap.add_argument("--no-check", action="store_true", help="skip hyperframes check (layout / runtime)")
    ap.add_argument("--out")
    ap.add_argument("--lang", default="en", choices=["en", "zh"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    times = [float(x) for x in a.at.split(",") if x.strip()] if a.at else None
    res = look(a.project, times=times, count=a.count, duration=a.duration, out_dir=a.out,
               caption_band=a.caption_band, video=a.video, check=not a.no_check)
    print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else report(res, a.lang))
    return 0 if res["ok"] else 1


def scratch_project(scenes_dir, scenes, W, H, assets=None):
    """A temporary HyperFrames project of ``scenes`` [(id, duration)] laid end to end (``assets``: a folder linked
    in as assets/ so fonts load) -> (folder, windows [(id, start, end)]). The caller removes the folder."""
    tmp = tempfile.mkdtemp(prefix="vstudio-look-")
    os.makedirs(os.path.join(tmp, "compositions"))
    if assets and os.path.isdir(assets):
        try:
            os.symlink(os.path.abspath(assets), os.path.join(tmp, "assets"), target_is_directory=True)
        except OSError:
            shutil.copytree(assets, os.path.join(tmp, "assets"))
    hosts, windows, t = [], [], 0.0
    for k, (sid, dur) in enumerate(scenes):
        src = os.path.join(scenes_dir, f"{sid}.html")
        if not os.path.exists(src):
            continue
        shutil.copy(src, os.path.join(tmp, "compositions", f"{sid}.html"))
        hosts.append(f'<div id="h{k}" data-composition-id="{sid}" data-composition-src="compositions/{sid}.html" '
                     f'data-start="{t:.2f}" data-duration="{dur:.2f}" data-track-index="{k + 1}" '
                     f'data-width="{W}" data-height="{H}"></div>')
        windows.append((sid, t, t + float(dur)))
        t += float(dur)
    with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html><head><meta charset="UTF-8"></head><body><div id="root" '
                f'data-composition-id="main" data-start="0" data-width="{W}" data-height="{H}" '
                f'data-duration="{t:.2f}">{"".join(hosts)}</div>'
                '<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script><script>'
                'window.__timelines = window.__timelines || {}; '
                'window.__timelines["main"] = gsap.timeline({ paused: true });</script></body></html>')
    return tmp, windows


def look_scenes(scenes_dir, scenes, W, H, assets=None, caption_band=None, per_scene=2, will_exist=(), timeout=300):
    """The look of each scene file: drawn twice in shuffled order (``per_scene`` times inside each scene), its fonts
    (the page's CSS against the project's files, then the browser's), text cut / in the caption band -> {scene id:
    [problem lines for the AI]} (only errors and the caption band; {} when nothing is wrong or nothing could run)."""
    out = {}
    project = os.path.dirname(os.path.abspath(assets)) if assets else None
    for sid, _dur in scenes:
        p = os.path.join(scenes_dir, f"{sid}.html")
        try:
            with open(p, encoding="utf-8") as f:
                html = f.read()
        except OSError:
            continue
        for f in font_problems(html, project, will_exist):
            if f["severity"] == "error":                  # a file that is not there; a fallback face is no repair
                out.setdefault(sid, []).append(problem_text(f))
    if not scenes:
        return out
    tmp, windows = scratch_project(scenes_dir, scenes, W, H, assets)
    try:
        times = []
        for _sid, a, b in windows:
            span = b - a
            times += [round(a + span * (i + 0.5) / per_scene, 3) for i in range(per_scene)]
        res = look(tmp, times=times, duration=windows[-1][2] if windows else None, caption_band=caption_band,
                   check=True, samples=max(3, min(24, len(windows) * 2)), timeout=timeout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for sid, fs in by_scene([f for f in res["findings"] if f["severity"] == "error" or f["code"] == "look-safe-area"],
                            windows).items():
        lines = out.setdefault(sid, [])
        for f in fs:
            if f["code"] == "look-font-failed" and any("look-font-failed" in x for x in lines):
                continue
            lines.append(problem_text(f))
    # a font the browser could not load is every scene's that asks for it (no time / file on the finding)
    fam = [f for f in res["findings"] if f["code"] == "look-font-failed" and not f.get("file") and f.get("font")]
    for sid, _a, _b in windows:
        try:
            with open(os.path.join(scenes_dir, f"{sid}.html"), encoding="utf-8") as fh:
                html = fh.read()
        except OSError:
            continue
        for f in fam:
            if f["font"].lower() in html.lower() and not any("look-font-failed" in x for x in out.get(sid, [])):
                out.setdefault(sid, []).append(problem_text(f))
    return out


if __name__ == "__main__":
    sys.exit(_cli())
