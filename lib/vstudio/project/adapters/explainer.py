"""explainer: the voice checkpoint (paid TTS: voice / speed confirmed first, with a cost estimate)."""
import os
import re

from ..build import file_sha

VOICES = ["cedar", "marin", "alloy", "ash", "coral", "sage", "verse", "ballad"]
USD_PER_MIN = 0.015           # gpt-4o-mini-tts, workflows/explainer/WORKFLOW.md
PAID_ENGINES = ("openai", "elevenlabs")
CJK = re.compile(r"[㐀-鿿豈-﫿]")


def spoken_text(script_path):
    try:
        with open(script_path, encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        return []
    return [ln.strip() for ln in txt.splitlines() if ln.startswith("    ") and ln.strip()]


def spoken_words(script_path):
    return sum(len(re.findall(r"[A-Za-z0-9']+", s)) for s in spoken_text(script_path))


def spoken_minutes(script_path, speed=1.0):
    """(minutes, words, chars, lang): English at ~165 words/min, Chinese (中文讲解) at ~260 characters/min."""
    spoken = spoken_text(script_path)
    chars = sum(len(CJK.findall(s)) for s in spoken)
    words = sum(len(re.findall(r"[A-Za-z0-9']+", s)) for s in spoken)
    if chars > words:
        return (chars + words / 2) / (260.0 * speed), words, chars, "zh"
    return (words / (165.0 * speed) if words else 0.0), words, chars, "en"


def voice_payload(env, cp):
    script = os.path.join(env.item_dir, "SCRIPT.md")
    speed = float(env.params.get("speed") or 1.0)
    minutes, words, chars, lang = spoken_minutes(script, speed)
    engine = env.params.get("tts_engine") or "openai"
    cur = env.params.get("voice") or "cedar"
    if engine != "openai" and cur == "cedar":         # cedar is OpenAI's: show the voice that will really speak
        from vstudio import tts
        cur = "clone" if engine == "clone" else (tts.zh_voice(engine) if lang == "zh" else None) or \
            tts.DEFAULT_VOICE.get(engine) or engine
    paid = engine in PAID_ENGINES
    voices = VOICES if engine == "openai" else [cur]
    return dict(options=[dict(voice=v, current=v == cur) for v in voices], words=words, chars=chars, language=lang,
                engine=engine, paid=paid, minutes=round(minutes, 2),
                estimate_usd=round(minutes * USD_PER_MIN * 1.5, 3) if engine == "openai" else 0.0,
                digest=file_sha(script) or "none",
                default=dict(voice=cur, speed=speed, approve=True),
                previews=[dict(kind="markdown", path=script)])


def voice_apply(a):
    v = a.value or {}
    if not v.get("approve"):
        return dict(params={}, digest="not-approved")
    p = {}
    if v.get("voice"):
        p["voice"] = v["voice"]
    if v.get("speed"):
        p["speed"] = float(v["speed"])
    return dict(params={}, project_params=p) if p else dict(params={})


def draft_cues(ctx, cp, path, template=None, instruction=None, complete=None):
    """The subtitle pairing (``subtitles/cues.txt``) drafted by the engine: the workflow's own pairing
    (``pair_cues.py`` -> ``cues.draft.txt``, EN || ZH per cue) taken as it is - she checks it, she never retypes it.
    With an instruction ("make the Chinese shorter") the AI rewrites it from that draft (``drafts.generic``)."""
    draft = os.path.join(os.path.dirname(path), "cues.draft.txt")
    if not os.path.isfile(draft):
        return None
    if instruction:
        from .. import drafts as DR
        with open(draft, encoding="utf-8") as f:
            text = f.read()
        return DR.generic(ctx, cp, path, instruction=instruction, complete=complete, template_text=text)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(draft, encoding="utf-8") as f, open(path, "w", encoding="utf-8") as g:
        g.write(f.read())
    cues = 0
    with open(path, encoding="utf-8") as f:
        cues = sum(1 for ln in f if "||" in ln)
    return dict(by="rules", instruction=None, review=dict(kind="outline", lines=[], summary=dict(
        code="draft.items", params=dict(n=cues))))


# --------------------------------------------------------------------------- the script: lines, never raw notes
LINE_RE = re.compile(r"(?m)^## Line \d+")
NARR_RE = re.compile(r"(?m)^## Line \d+[^\n]*\n(?:(?!## Line )[^\n]*\n)*?    \S")
NOTES_NAME = "SCRIPT.notes.md"


def script_format_ok(path):
    """SCRIPT.md is in the explainer's format: at least one '## Line N' block with an indented narration line. Her
    lecture notes / a Notion export are not (they go to the drafter as materials, never straight to the storyboard)."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(2_000_000)
    except (OSError, UnicodeDecodeError):
        return False
    return bool(LINE_RE.search(text) and NARR_RE.search(text + "\n"))


def target_minutes(params, request=""):
    """How long the episode should be: "N 分钟" / "N minutes" in the request, else short (1.5) / long (7)."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–~到至]\s*(\d+(?:\.\d+)?))?\s*(?:分钟|min)", request or "")
    if m:
        lo = float(m.group(1))
        hi = float(m.group(2) or lo)
        return max(0.5, min(20.0, (lo + hi) / 2))
    return 1.5 if (params or {}).get("mode") == "short" else 7.0


_STAGE = re.compile(r"^\s*[\[【（(][^\]】）)]{0,40}(镜头|切到|切回|滚到|运行|指|展示|停|翻到|开场|收尾|动作|问|等)[^\]】）)]*[\]】）)]\s*$")


def _clean(text):
    """Notes -> plain narration paragraphs: no code / tables / stage directions / markdown marks / chat leftovers."""
    text = re.sub(r"```.*?```", "\n", text, flags=re.S)
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith(("|", "<", "---", "> 🟢", "🟢")) or _STAGE.match(s):
            continue
        s = re.sub(r"\*\*|__|`|\\", "", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        s = re.sub(r"^[>\-*•·\d.、)\s]+", "", s) if not s.startswith("#") else s
        if s:
            out.append(s)
    return out


def notes_to_script(text, lang="zh", minutes=7.0, title=""):
    """The rules' script (no model): her notes' own sentences, in order, cut into '## Line N' scenes of about 150
    characters (Chinese) / 45 words, until the length is reached. Plain, but always a valid line script."""
    zh = lang == "zh"
    budget = minutes * (260 if zh else 165)
    per = 110 if zh else 40
    size = (lambda s: len(re.findall(r"[㐀-鿿]", s)) + len(re.findall(r"[A-Za-z0-9]+", s)) / 2) if zh else \
        (lambda s: len(s.split()))
    lines, cur, label, used = [], "", None, 0.0
    for p in _clean(text):
        if p.startswith("#"):
            if cur:
                lines.append((label, cur)); used += size(cur); cur = ""
            label = re.sub(r"^#+\s*", "", p)[:40]
            continue
        for sent in re.split(r"(?<=[。！？!?])|(?<=\.)\s+", p):
            sent = sent.strip()
            if not sent:
                continue
            cur = (cur + ("" if zh else " ") + sent).strip()
            if size(cur) >= per:
                lines.append((label, cur)); used += size(cur); cur = ""
            if used >= budget:
                break
        if used >= budget:
            break
    if cur and used < budget:
        lines.append((label, cur))
    if not lines:
        lines = [(title or "Topic", (title or "…"))]
    out = [f"# SCRIPT — {title or 'explainer'} (drafted by rules from your notes: edit freely)", "",
           ("Narration: 中文讲解 (no model was available: these are your notes' own sentences, in order)." if zh else
            "Narration: English (no model was available: these are your notes' own sentences, in order)."), "", "---", ""]
    for k, (lab, body) in enumerate(lines, 1):
        lab = re.sub(r"[()\n]", " ", lab or f"Part {k}").strip() or f"Part {k}"
        out += [f"## Line {k} — {lab} (Frame {k})", "", "    " + body, ""]
    return "\n".join(out)


def draft_script(ctx, cp, path, template=None, instruction=None, complete=None):
    """The explainer's script step: the AI condenses her materials into one episode-sized '## Line N' script (her
    notes in SCRIPT.md itself are kept as ``inputs/SCRIPT.notes.md`` and read as material); when the reply is not
    a line script - or no model answers - the rules write one from the notes. Never her raw notes as the script."""
    import shutil
    from .. import drafts as DR
    if os.path.isfile(path) and not DR.is_template(path, template) and not script_format_ok(path):
        notes = os.path.join(os.path.dirname(path), "inputs", NOTES_NAME)
        os.makedirs(os.path.dirname(notes), exist_ok=True)
        shutil.move(path, notes)
        if template and os.path.isfile(template):
            shutil.copy(template, path)
    notes = os.path.join(os.path.dirname(path), "inputs", NOTES_NAME)
    if os.path.isfile(notes):
        got = ctx.inputs.get("script")
        got = [got] if isinstance(got, str) else list(got or [])
        if notes not in got:
            ctx.inputs["script"] = got + [notes]
    req = ctx.request()
    minutes = target_minutes(ctx.params, req)
    zh = ctx.lang() == "zh" or bool(re.search(r"中文|讲解|普通话|Chinese", req))
    scenes = max(4, round(minutes * 2))
    want = instruction or (
        f"Condense the materials into ONE explainer of about {minutes:g} minutes: about {scenes} '## Line N' scenes, "
        f"{'about ' + str(int(minutes * 260)) + ' Chinese characters' if zh else 'about ' + str(int(minutes * 165)) + ' words'}"
        " of narration in total. Keep the parts the request names, one idea per scene, the materials' own examples "
        "and analogies; drop stage directions, code listings and chat leftovers. "
        + ("Narrate in Chinese (中文讲解): the indented block is Chinese, English terms stay English, numbers as digits; "
           "no ZH: line." if zh else "Narrate in English with a ZH: subtitle line per scene."))
    rec = None
    try:
        rec = DR.generic(ctx, cp, path, template=template, instruction=want, complete=complete)
    except Exception:  # noqa: BLE001  (no model / a reply that failed: the rules below still write a script)
        rec = None
    if rec and script_format_ok(path):
        return rec
    texts = []
    for v in ctx.inputs.values():
        for p in (v if isinstance(v, list) else [v]):
            if isinstance(p, str) and p.lower().endswith((".md", ".txt")) and os.path.isfile(p):
                with open(p, encoding="utf-8", errors="replace") as f:
                    texts.append(f.read(400_000))
    if not texts:
        texts = [req]
    with open(path, "w", encoding="utf-8") as f:
        f.write(notes_to_script("\n\n".join(texts), "zh" if zh else "en", minutes,
                                str(ctx.params.get("title") or "")))
    return dict(by="rules", instruction=None, review=DR.outline_review(path, None))


# --------------------------------------------------------------------------- scenes: a plain set when no agent wrote any
_CJK_FONTS = (("cjk", ["scene-cjk-w4", "subtitle-cjk-w3"]), ("cjk-bold", ["scene-cjk-w7", "subtitle-cjk-w6"]))
_HF_FILES = {
    "hyperframes.json": {"$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                         "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
                         "paths": {"blocks": "compositions", "components": "compositions/components",
                                   "assets": "assets"}, "media": {"autoProxy": True}, "authoringSkill": "general-video"},
}


def _font_file(role):
    from vstudio import config
    try:
        return config.font(role)
    except Exception:  # noqa: BLE001  (an isolated $VSTUDIO_CACHE: the installed fonts live in the default one)
        p = os.path.join(os.path.expanduser("~/.cache/video-studio/fonts"), config.FONTS[role][0])
        return p if os.path.exists(p) else None


def _scene_html(sid, W, H, title, dur, cues, legacy, box):
    """One scene of kinetic text: the scene title, then each narration cue as a line that rises in on its word,
    the earlier ones dimmed above it (three on screen), numbers in the accent colour. Plain, readable, valid."""
    import html as H_
    import json as J
    x0, y0, x1, y1 = box
    fs = 52 if legacy else 58
    rows = [dict(t=round(max(0.2, c["t"] - 0.1), 2), text=H_.escape(c.get("text") or c.get("en") or ""))
            for c in cues if (c.get("text") or c.get("en"))]
    return f'''<template>
  <style>
    @font-face {{ font-family: "Course CJK"; src: url("assets/fonts/scene-cjk-w4.woff2") format("woff2"); font-weight: 400 500; }}
    @font-face {{ font-family: "Course CJK"; src: url("assets/fonts/scene-cjk-w7.woff2") format("woff2"); font-weight: 600 900; }}
    #root {{ position: absolute; inset: 0; width: 100%; height: 100%; overflow: hidden; }}
    #{sid}-stage {{ position: absolute; inset: 0; width: {W}px; height: {H}px; font-family: "Course CJK", sans-serif; }}
    #{sid}-title {{ position: absolute; left: {x0}px; top: {y0}px; width: {x1 - x0}px; font-size: {fs + 10}px; font-weight: 800; color: #F4D35E; line-height: 1.2; }}
    #{sid}-bar {{ position: absolute; left: {x0}px; top: {y0 + fs + 40}px; width: 120px; height: 6px; background: #58C4DD; border-radius: 3px; }}
    .{sid}-line {{ position: absolute; left: {x0}px; width: {x1 - x0}px; font-size: {fs}px; font-weight: 600; color: #ECEEF2; line-height: 1.35; opacity: 0; }}
    .{sid}-line b {{ color: #58C4DD; font-weight: 800; }}
  </style>
  <div id="root" data-composition-id="{sid}" data-width="{W}" data-height="{H}" data-duration="{dur}">
    <div id="{sid}-stage" class="clip" data-start="0" data-duration="{dur}" data-track-index="1">
      <div id="{sid}-title">{H_.escape(title)}</div><div id="{sid}-bar"></div>
      <div id="{sid}-lines"></div>
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <script>
    (function () {{
      const R = {J.dumps(rows, ensure_ascii=False)};
      const box = document.getElementById("{sid}-lines");
      const top = {y0 + fs + 90}, bottom = {y1}, step = {int(fs * 2.9)};
      const tl = gsap.timeline({{ paused: true }});
      tl.fromTo("#{sid}-title", {{ opacity: 0, y: 16 }}, {{ opacity: 1, y: 0, duration: 0.6, ease: "power2.out" }}, 0.1);
      tl.fromTo("#{sid}-bar", {{ scaleX: 0, transformOrigin: "0% 50%" }}, {{ scaleX: 1, duration: 0.6, ease: "power2.out" }}, 0.3);
      const els = R.map((r, i) => {{
        const d = document.createElement("div"); d.className = "{sid}-line"; d.id = "{sid}-l" + i;
        d.innerHTML = r.text.replace(/(\\d+(?:[.,]\\d+)?%?)/g, "<b>$1</b>"); box.appendChild(d); return d; }});
      els.forEach((d, i) => {{
        const slot = Math.min(i, 2);
        d.style.top = (top + slot * step) + "px";
        tl.fromTo(d, {{ opacity: 0, y: 24 }}, {{ opacity: 1, y: 0, duration: 0.5, ease: "power2.out" }}, R[i].t);
        if (i >= 1) for (let k = Math.max(0, i - 2); k < i; k++) {{
          const pos = top + (Math.min(i, 2) - (i - k)) * step;
          tl.to(els[k], {{ top: pos, opacity: k === i - 1 ? 0.55 : 0.3, duration: 0.4, ease: "power1.inOut" }}, R[i].t);
        }}
        if (i >= 3) tl.to(els[i - 3], {{ opacity: 0, duration: 0.3 }}, R[i].t);
      }});
      window.__timelines["{sid}"] = tl;
    }})();
  </script>
</template>
'''


def draft_scenes(ctx, cp, path, template=None, instruction=None, complete=None):
    """The scenes step when no agent wrote any: one kinetic-text scene per narration line (title + its cues rising
    in on their words), plus what the render needs that is not a stage yet - the HyperFrames project files, the CJK
    font subsets (captions + scenes) and the captions composition. An agent's own scenes always win (this only
    fills an empty folder); she can redraw any scene later."""
    import json as J
    import subprocess
    import sys
    item = ctx.item_dir
    try:
        cfg = J.load(open(os.path.join(item, "scenes.config.json"), encoding="utf-8"))
        win = J.load(open(os.path.join(item, "audio", "scenes.json"), encoding="utf-8"))["scenes"]
        cues = J.load(open(os.path.join(item, "audio", "scene_cues.json"), encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return None                                   # the timing is not there yet: nothing to draw from
    scripts = os.path.join(ctx.workflow_dir, "scripts")
    sys.path.insert(0, scripts)
    try:
        import canvas as CV
        from script_md import parse_script
        cv = CV.resolve(item)
        try:
            labels = {L["n"]: L["label"] for L in parse_script(os.path.join(item, "SCRIPT.md"))}
        except OSError:
            labels = {}
    finally:
        sys.path.remove(scripts)
    W, H = cv["W"], cv["H"]
    box = (120, 110, 1800, 800) if cv["legacy"] else tuple(cv["math"])
    os.makedirs(path, exist_ok=True)
    for sc, w in zip(cfg.get("scenes") or [], win):
        f = os.path.join(path, f"{sc['id']}.html")
        if not os.path.exists(f):
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(_scene_html(sc["id"], W, H, labels.get(w["frame"], ""), w["duration"],
                                     cues.get(str(w["frame"])) or [], cv["legacy"], box))
    for name, doc in _HF_FILES.items():
        p = os.path.join(item, name)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as fh:
                J.dump(doc, fh, indent=2)
    # fonts: every character the captions and the scenes use
    from vstudio.render import subset_font
    chars = ""
    try:
        chars = "".join(c.get("zh", "") + c.get("en", "") for c in J.load(open(os.path.join(item, "subtitles",
                                                                                         "cues.json"), encoding="utf-8")))
    except (OSError, ValueError):
        pass
    for f in os.listdir(path):
        if f.endswith(".html"):
            with open(os.path.join(path, f), encoding="utf-8") as fh:
                chars += fh.read()
    os.makedirs(os.path.join(item, "assets", "fonts"), exist_ok=True)
    for role, outs in _CJK_FONTS:
        src = _font_file(role)
        for o in outs:
            dst = os.path.join(item, "assets", "fonts", f"{o}.woff2")
            if src and not os.path.exists(dst):
                try:
                    subset_font(src, chars, dst)
                except Exception:  # noqa: BLE001  (no fonttools / brotli: the render falls back, visibly)
                    pass
    if os.path.exists(os.path.join(item, "subtitles", "cues.json")) and \
            not os.path.exists(os.path.join(path, "captions.html")):
        subprocess.run([sys.executable, os.path.join(scripts, "make_captions.py"), "-C", item],
                       capture_output=True, text=True)
    from .. import drafts as DR
    return dict(by="rules", instruction=None, review=dict(kind="outline", lines=[], summary=dict(
        code="draft.items", params=dict(n=len(cfg.get("scenes") or [])))))
