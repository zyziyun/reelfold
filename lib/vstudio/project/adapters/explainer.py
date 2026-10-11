"""explainer: the voice checkpoint (paid TTS: voice / speed confirmed first, with a cost estimate; a paid voice
without its key offers the free local voice instead)."""
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


def resolve_engine(params):
    """``tts_engine: auto`` (the recipe default) -> the voice actually available here (vstudio.tts.available_engine:
    her persona's engine, else OpenAI only with its key, else the free local voice). Never a paid engine without a
    key; a project that says ``auto`` with a key set keeps OpenAI (the stage keys of older projects do not move)."""
    from vstudio import tts
    return tts.available_engine()


def _voice_answer(params):
    a = ((params or {}).get("_answers") or {}).get("voice")
    return a.get("value") if isinstance(a, dict) and isinstance(a.get("value"), dict) else None


def voice_engine(params):
    """Which voice the item gets -> {engine (the one to make it with; None = none can run here), chosen (the
    plan's), need (the paid engine whose missing key stops the voice, else None), service, env}. ``need`` when the
    plan chose a paid engine without its key (``tts_engine: openai``, or an answer from before the engine was
    recorded, when OpenAI was the default), or chose a free voice this computer does not have and there is no OpenAI
    key either. The free voice installed here takes over when there is one (autopilot records it; Ask-me-first
    asks); with none, adding the key is the way (a question for her, never a traceback)."""
    from vstudio import tts
    p = params or {}
    chosen = str(p.get("tts_engine") or "auto").lower()
    chosen = tts.ALIASES.get(chosen, chosen)
    if chosen == "auto":
        chosen = tts.available_engine()
    ans = _voice_answer(p)
    legacy = ans is not None and not ans.get("engine") and bool(p.get("_tts_engine_auto"))
    free = tts.local_engine()
    if tts.missing_key(chosen):
        need = chosen
    elif legacy and chosen != "openai" and tts.missing_key("openai"):
        need = "openai"
    elif chosen in tts.LOCAL and not tts.installed(chosen) and tts.missing_key("openai"):
        need = "openai"
    else:
        need = None
    ok = not tts.missing_key(chosen) and tts.installed(chosen)
    engine = chosen if ok else (free if need else chosen)
    return dict(engine=engine, chosen=chosen, need=need, service=tts.SERVICE.get(need) if need else None,
                env=tts.KEY_ENV.get(need) if need else None)


def _narration_current(item_dir):
    """The narration is made and newer than the script: a key that went away later re-voices nothing."""
    narr, script = os.path.join(item_dir, "audio", "narration.wav"), os.path.join(item_dir, "SCRIPT.md")
    try:
        return os.path.getmtime(narr) >= os.path.getmtime(script)
    except OSError:
        return False


def voice_recheck(params):
    """The voice gate's extra key (``recheck``): set only while the voice waits on a missing key (``voice_engine``
    need), so a Try again re-opens the voice checkpoint (autopilot takes the free voice, Ask-me-first asks; with no
    free voice here, the key question stays); None otherwise (the gates of projects that have their key keep their
    keys)."""
    v = voice_engine(params)
    if not v["need"] or _narration_current((params or {}).get("_item_dir") or ""):
        return None
    return dict(need=v["need"], use=v["engine"])


def voice_payload(env, cp):
    script = os.path.join(env.item_dir, "SCRIPT.md")
    speed = float(env.params.get("speed") or 1.0)
    minutes, words, chars, lang = spoken_minutes(script, speed)
    v = voice_engine(env.params)
    engine = v["engine"]
    cur = env.params.get("voice") or "cedar"
    derived = None
    if engine and engine != "openai" and cur in VOICES:   # OpenAI's voices: show the voice that will really speak
        from vstudio import tts
        cur = derived = "clone" if engine == "clone" else (tts.zh_voice(engine) if lang == "zh" else None) or \
            tts.DEFAULT_VOICE.get(engine) or engine
    paid = engine in PAID_ENGINES
    voices = VOICES if engine == "openai" else [cur] if engine else []
    base = file_sha(script) or "none"
    # the script and, for any voice but OpenAI's (the old default: its answers keep their digest), the engine
    mine = base if engine in (None, "openai") else f"{base}:{engine}"
    pay = dict(options=[dict(voice=x, engine=engine, current=x == cur) for x in voices], words=words, chars=chars,
               language=lang, engine=engine, paid=paid, minutes=round(minutes, 2),
               estimate_usd=round(minutes * USD_PER_MIN * 1.5, 3) if engine == "openai" else 0.0,
               # a missing key asks again (the earlier answer was for the paid voice); else the script decides
               digest=f"{base}:no-key:{v['need']}" if v["need"] else mine,
               derived_voice=derived,
               # no voice can run here (no key, no free voice): nothing to approve until the key is added
               default=dict(voice=cur, speed=speed, approve=True, engine=engine) if engine else None,
               previews=[dict(kind="markdown", path=script)])
    if v["need"]:
        pay["no_key"] = dict(service=v["service"], env=v["env"], engine=v["need"], free_engine=engine,
                             free_voice=cur if engine else None)
        if engine:
            pay["answered_digest"] = mine      # the free voice's answer: the digest its own payload will have
    return pay


def voice_apply(a):
    v = a.value or {}
    if not v.get("approve"):
        return dict(params={}, digest="not-approved")
    p = {}
    if v.get("voice") and v["voice"] != a.payload.get("derived_voice"):
        p["voice"] = v["voice"]          # a derived voice (cedar -> the local engine's own) stays derived per line
    if v.get("speed"):
        p["speed"] = float(v["speed"])
    if v.get("engine"):
        p["tts_engine"] = str(v["engine"])
    out = dict(params={}, project_params=p) if p else dict(params={})
    nk = a.payload.get("no_key") or {}
    if nk and v.get("engine") and v["engine"] != nk.get("engine") and a.payload.get("answered_digest"):
        out["digest"] = a.payload["answered_digest"]     # the free voice answers the script as it is now
    return out


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


# --------------------------------------------------------------------------- the storyboard: a shot plan, no TODO
_TODO_HINT = re.compile(r"TODO: what appears \(one visual per idea\)")
_TODO_TAIL = re.compile(r"\s*[—-]+\s*TODO\b")


def _load_cfg(path):
    import json as J
    with open(path, encoding="utf-8") as f:
        return J.load(f)


def storyboard_unfinished(path):
    """scenes.config.json as the storyboard stage writes it: shots that still say "TODO" (a decision nobody made)."""
    try:
        cfg = _load_cfg(path)
    except (OSError, ValueError):
        return False
    return any(re.search(r"\bTODO\b", str(sc.get("shots") or "")) for sc in cfg.get("scenes") or [])


def rules_shots(shots):
    """The stage's hints without their "TODO": what each beat should show, in words the scene author acts on."""
    out = _TODO_HINT.sub("one visual for this idea: draw its key term as a diagram / shape (no sentence on screen)",
                         shots or "")
    out = _TODO_TAIL.sub("", out)
    return re.sub(r"\bTODO\b:?\s*", "", out)


STORYBOARD_SYSTEM = ("You are the director of a 3Blue1Brown-style explainer channel. For each scene you plan the "
                     "visuals beat by beat: what the viewer SEES on each narration cue - a diagram, a flow with "
                     "arrows, boxes that connect, a comparison, a table filling in, a count-up, an equation built "
                     "term by term, a code card, a timeline - never the narration as text on screen (captions show "
                     "it). Reuse one visual metaphor across scenes where the story continues. Reply with JSON only.")


def _storyboard_prompt(cfg, lines, request, instruction):
    import json as J
    by_n = {L["n"]: L for L in lines}
    rows = []
    for k, sc in enumerate(cfg.get("scenes") or []):
        L = by_n.get(k + 1) or {}
        beats = re.findall(r'^- ([0-9.]+s) \("([^"]*)"\)', str(sc.get("shots") or ""), re.M)
        rows.append(dict(id=sc.get("id"), label=L.get("label"), direction=L.get("delivery") or None,
                         narration=L.get("spoken"), beats=[dict(at=a, words=w) for a, w in beats]))
    return "\n\n".join(x for x in [
        f"Request: {request or '(none)'}",
        f"Instruction from the creator: {instruction}" if instruction else "",
        "Scenes (narration + the beats: the time each cue starts and its first words):\n"
        + J.dumps(rows, ensure_ascii=False, indent=1),
        'Write each scene\'s shot plan as text, one beat per line, exactly in this shape:\n'
        'Scene title fades in at 0.2s.\n- 0.3s ("<the beat\'s words>"): <what appears / moves: concrete shapes, '
        'labels <= 10 characters, colours by role>\n...\nAmbient: whole group drifts up 6px over the scene.\n'
        'Keep every beat time and its words. No "TODO", no placeholders.',
        'Reply {"scenes": [{"id": "<scene id>", "shots": "<the plan>"}], "summary": "<one sentence>"} with every '
        'scene id above, in order.'] if x)


def draft_storyboard(ctx, cp, path, template=None, instruction=None, complete=None):
    """The storyboard checkpoint (scenes.config.json's shot plans): the routed AI plans each beat's visual from the
    narration and the cue times; no model / a reply that does not fit -> the stage's hints with every "TODO" turned
    into words (``by: rules``; the autopilot does not approve that one - the visuals need a model)."""
    import json as J
    import sys
    try:
        cfg = _load_cfg(path)
    except (OSError, ValueError):
        return None
    scripts = os.path.join(ctx.workflow_dir, "scripts")
    sys.path.insert(0, scripts)
    try:
        from script_md import parse_script
        try:
            lines = parse_script(os.path.join(os.path.dirname(path), "SCRIPT.md"))
        except OSError:
            lines = []
    finally:
        sys.path.remove(scripts)
    scenes = cfg.get("scenes") or []
    rec = None
    if complete is None:
        from vstudio import llm
        complete = llm.complete
    try:
        r = complete("planner", STORYBOARD_SYSTEM, _storyboard_prompt(cfg, lines, ctx.request(), instruction),
                     schema=True, max_tokens=16000, timeout=480, cli_timeout=480, retries=1, effort="medium")
        js = r.get("json") if isinstance(r, dict) and r.get("provider") != "none" else None
        got = {str(x.get("id")): str(x.get("shots") or "") for x in (js or {}).get("scenes") or []
               if isinstance(x, dict)}
        if scenes and all(got.get(sc.get("id"), "").strip() and not re.search(r"\bTODO\b", got[sc["id"]])
                          for sc in scenes):
            for sc in scenes:
                sc["shots"] = got[sc["id"]].strip()
            rec = dict(by="ai", provider=r.get("provider"), model=r.get("model"), instruction=instruction,
                       review=dict(kind="outline", summary=dict(code="draft.generic", params=dict(
                           text=str(js.get("summary") or "").strip()[:300])) if js.get("summary") else dict(
                           code="draft.items", params=dict(n=len(scenes))),
                           lines=[dict(code="draft.line", params=dict(label=sc["id"])) for sc in scenes[:12]]))
    except Exception:  # noqa: BLE001  (no model, a timeout: the rules plan below)
        rec = None
    if rec is None:
        for sc in scenes:
            sc["shots"] = rules_shots(sc.get("shots"))
        rec = dict(by="rules", instruction=None, review=dict(kind="outline", lines=[], summary=dict(
            code="draft.items", params=dict(n=len(scenes)))))
    with open(path, "w", encoding="utf-8") as f:
        f.write(J.dumps(cfg, indent=1, ensure_ascii=False) + "\n")
    return rec


# --------------------------------------------------------------------------- scenes: drawn by the routed AI
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


def scenes_unfinished(path):
    """The scenes folder lacks a scene of scenes.config.json, or one still has a placeholder."""
    from .explainer_scenes import scenes_complete
    return os.path.isdir(path) and not scenes_complete(path)


def scene_support(item, path, log=None):
    """What the render needs besides the scenes: the HyperFrames project file, the CJK font subsets (every character
    the captions and the scenes use: made again, the scenes changed) and the captions composition."""
    import json as J
    import subprocess
    import sys
    for name, doc in _HF_FILES.items():
        p = os.path.join(item, name)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as fh:
                J.dump(doc, fh, indent=2)
    from vstudio.render import subset_font
    chars = ""
    try:
        with open(os.path.join(item, "subtitles", "cues.json"), encoding="utf-8") as fh:
            chars = "".join(c.get("zh", "") + c.get("en", "") for c in J.load(fh))
    except (OSError, ValueError):
        pass
    for f in sorted(os.listdir(path)):
        if f.endswith(".html"):
            with open(os.path.join(path, f), encoding="utf-8") as fh:
                chars += fh.read()
    os.makedirs(os.path.join(item, "assets", "fonts"), exist_ok=True)
    for role, outs in _CJK_FONTS:
        src = _font_file(role)
        for o in outs:
            dst = os.path.join(item, "assets", "fonts", f"{o}.woff2")
            if src:
                try:
                    subset_font(src, chars, dst)
                except Exception as e:  # noqa: BLE001  (no fonttools / brotli: the render falls back, visibly)
                    if log:
                        log(f"font subset {o}: {e}")
    if os.path.exists(os.path.join(item, "subtitles", "cues.json")) and \
            not os.path.exists(os.path.join(path, "captions.html")):
        from .. import manifests as M
        scripts = os.path.join(M.WORKFLOWS, "explainer", "scripts")
        subprocess.run([sys.executable, os.path.join(scripts, "make_captions.py"), "-C", item],
                       capture_output=True, text=True)


def _scenes_review(item, written, total):
    return dict(kind="outline", summary=dict(code="draft.items", params=dict(n=total)),
                lines=[dict(code="draft.line", params=dict(label=x)) for x in written[:12]])


def draft_scenes(ctx, cp, path, template=None, instruction=None, complete=None):
    """The scenes step: the routed AI draws every scene (``explainer_scenes``: diagrams and motion on the voice's cue
    times; the scenes it already drew are kept unless she asked for a change), then what the render needs that is
    not a stage yet (``scene_support``). No model, or not every scene drawn: ``NeedsModel`` / an error - nothing that
    is not the AI's is written, the step waits for her with a plain sentence (never a text-only video). Her own /
    her agent's scenes (no AI mark, every scene there) are "hers" and never reach this."""
    from . import explainer_scenes as S
    item = ctx.item_dir
    if not all(os.path.exists(os.path.join(item, *p)) for p in (("scenes.config.json",), ("audio", "scenes.json"),
                                                                 ("audio", "scene_cues.json"))):
        return None                                   # the timing is not there yet: nothing to draw from
    os.makedirs(path, exist_ok=True)
    res = S.author_scenes(item, ctx.workflow_dir, request=ctx.request(), instruction=instruction, complete=complete,
                          out_dir=path, keep_ai=instruction is None)
    if not res["ok"]:
        if res.get("error_code") == "needs-model":
            raise S.NeedsModel(res["error"], S.routed_provider())
        raise RuntimeError(res["error"] or "the scenes could not be drawn")
    scene_support(item, path)
    done = [s for s in sorted(os.listdir(path)) if s.endswith(".html") and s != "captions.html"]
    return dict(by="ai", provider=res.get("provider"), model=res.get("model"), instruction=instruction,
                review=_scenes_review(item, [d[:-5] for d in done], res["total"]))


# --------------------------------------------------------------------------- redo the visuals of a finished one
def _rendered(env_or_item_dir, item_id=None):
    item = env_or_item_dir
    rd = os.path.join(item, "renders")
    try:
        return any(f.endswith(".mp4") for f in os.listdir(rd))
    except OSError:
        return False


def scenes_current(project, cp, item):
    """A finished explainer's visuals (the clip page's "Redo the visuals"): who drew them -> {pick: None, choice: ai |
    rules | her, options: []}, or None (not rendered yet)."""
    from .. import drafts as DR
    rows = {r["id"]: r for r in project.jobs_rows()}
    row = rows.get(item) or {}
    item_dir = os.path.join(project.dir, "items", row.get("_base_item") or item)
    comp = os.path.join(item_dir, "compositions")
    if not _rendered(item_dir) or not os.path.isdir(comp):
        return None
    side = DR.read_side(comp, cp["id"]) or {}
    return dict(pick=None, choice=side.get("by") or "her", options=[])


VOICE_STAGES = ("prepare", "storyboard", "cue_draft", "voice", "narration", "transcribe", "align", "windows")


def scenes_remake(env, cp, choice):
    """Redo the visuals of a finished explainer, the voice kept: every scene drawn again by the routed AI (into a
    new folder first: no model -> ``NeedsModel`` and the old video stays as it was), then index -> render -> export
    re-run by the project's runner (only those: the narration, its cues and timing are not touched; a project whose
    voice would be made again is refused). ``choice``: an instruction for the visuals ("more diagrams") or None.
    -> {answer None (recorded here, before the run), scenes, provider, status}."""
    import shutil
    import time as T
    from . import explainer_scenes as S
    from .. import drafts as DR
    from .common import author_payload
    item, path = env.item_dir, os.path.join(env.item_dir, "compositions")
    if not _rendered(item):
        raise RuntimeError("visuals: the video is not made yet")
    for need in (("audio", "narration.wav"), ("audio", "scenes.json"), ("audio", "scene_cues.json")):
        if not os.path.exists(os.path.join(item, *need)):
            raise RuntimeError("visuals: the narration timing is missing (" + "/".join(need) + ")")
    p = env.project
    voice = [s for s in (p.stale().get(env.job) or []) if s in VOICE_STAGES or s.startswith("cp_") and
             s[3:] in ("script", "storyboard", "voice", "cues")]
    if voice:
        raise RuntimeError("visuals: the narration would be made again (" + ", ".join(voice) + " changed) - run "
                           "the project first")
    env.at("cp_" + cp["id"])
    stamp = T.strftime("%Y%m%d-%H%M%S")
    # outside the stage folders: the run below re-runs the gate, which empties its folder (the backup went with it)
    keep = os.path.join(env.state_dir, "remake", env.job, "visuals")
    os.makedirs(keep, exist_ok=True)
    new = os.path.join(keep, f"compositions.new-{stamp}")
    os.makedirs(new, exist_ok=True)
    instruction = choice if choice and choice not in ("ai", "redo") else None
    env.log(f"remake visuals: drawing {item} again" + (f" ({instruction})" if instruction else ""))
    res = S.author_scenes(item, env.workflow_dir, request=_request(p), instruction=instruction, out_dir=new,
                          keep_ai=False, log=env.log)
    if not res["ok"]:
        shutil.rmtree(new, ignore_errors=True)
        if res.get("error_code") == "needs-model":
            raise S.NeedsModel(res["error"], S.routed_provider())
        raise RuntimeError(res["error"] or "visuals: the scenes could not be drawn")
    old = os.path.join(keep, f"compositions.before-{stamp}")
    if os.path.isdir(path):
        shutil.move(path, old)
        cap = os.path.join(old, "captions.html")
        if os.path.exists(cap):
            shutil.copy2(cap, os.path.join(new, "captions.html"))
    shutil.move(new, path)
    scene_support(item, path, log=env.log)
    DR.write_side(path, cp["id"], dict(by="ai", provider=res.get("provider"), model=res.get("model"),
                                       instruction=instruction, review=_scenes_review(item, res["written"],
                                                                                      res["total"])))
    try:
        env.write_payload(cp, author_payload(env, cp))
    except Exception as e:  # noqa: BLE001  (the payload is a view; the answer below is what counts)
        env.log(f"scenes payload skipped: {str(e)[:160]}")
    p.answer(cp["id"], dict(done=True), items=[env.job], replan=True)
    events = getattr(env, "emit", None)
    out = p.run(only=[env.job], on_event=(lambda ev: events(ev) if ev.get("event") not in (
        "run-start", "project-end") else None) if events else None)
    if out.get("exit_code") not in (0, 7):            # done, or the new video waits for her review
        raise RuntimeError("visuals: the new scenes were drawn but the video was not made again (" +
                           str(out.get("status")) + ")")
    return dict(answer=None, scenes=res["written"], provider=res.get("provider"), model=res.get("model"),
                status=out.get("status"), keep_live=out.get("exit_code") != 0, backup=old if os.path.isdir(old)
                else None)


def _request(project):
    d = project.data
    return "\n".join(x for x in (d.get("prompt") or "", d.get("name") or "") if x)
