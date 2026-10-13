"""photo-story: the story checkpoint's spec (work/spec.py) is drafted by the AI from her request and what it SEES of
her footage (vstudio.footage contact sheets), never left as the SYNTHETIC demo - before this an autopilot photo story
always stopped at "write spec.py" (the generic drafter does not write Python).

The spec is a data module the renderer imports: the draft is accepted only when it is plain data
(drafts.data_module_ok). Stills the model asks for (a cover, a still shot) are cut from her clips into work/frames/;
a built-in music bed (vstudio.music, MIT) is laid under the voice when the request wants music. A told piece (history,
explainer; never a music-mode mood piece) is fact-checked (vstudio.factguard): unverifiable rankings softened or
dropped in its cue literals only, facts.md written for her review, the counts in the draft record (``facts``).
"""
import os
import re
import subprocess

from vstudio import factguard as FG

from .. import drafts as DR
from .. import manifests as M

SYSTEM = (
    "You write the spec of a narrated photo-story video (a Python module of plain data: NAME = literals, dict(...) "
    "and tuples; no import, no function, no other call) from the creator's request and her footage. Look at every "
    "contact sheet first and pick the clips and in-points (off=) from what you SEE, so each line of narration plays "
    "over the picture it talks about. Facts: only well-known, verifiable ones; never invent a date, number, name or "
    "event. Never write GPS coordinates into any text. Reply with JSON only: {\"content\": \"<the whole spec "
    "module>\", \"frames\": [{\"name\": \"<id>\", \"clip\": \"<clip id>\", \"t\": <seconds>}], \"summary\": \"<one "
    "sentence>\"}.")

GUIDE = """Notes for this spec (they override the template where they differ):
- MEDIA = dict(images=["frames", "../inputs"], videos="../inputs")  (paths relative to this spec's folder).
- A video shot's source is "v" + the clip id, e.g. ("v{first}", 1, "still", dict(off=12.0, audio="mute")): off = the
  second in the clip where the shot starts (from the contact sheet); weight = its share of the unit's narration time.
  1-2 shots per unit; "still" motion for moving drone footage (it already moves). Use only the clip ids listed.
- Stills: list in "frames" the frames to cut from clips ({{name, clip, t}}); refer to them by name (an image source,
  e.g. "cover_a") in COVER (hero / polaroids) and, if you like, in photo shots. Give at least 3 frames for the COVER.
- Voice: {lang_note}
- Each cue is (English, 中文); keep the English <= ~90 characters and the 中文 <= ~38 characters per cue, 1-3 cues per unit.
  Length: about {target} s {length_of} in total (Chinese ~4.3 characters per second, English ~2.6 words per second).
- Do not write PLATFORM, CANVAS, OUT, TTS voice / model / engine, VOICE, ROUTE or SAY. {bgm_note}
- This version is for {platforms}: its words are in {words_lang}. TITLE_ZH / TITLE_EN, SECTIONS / SECTIONS_EN (2-4
  short chapter names), COVER (kicker, title, subtitle, tagline (before, keyword, after), hero=dict(src=<frame>),
  polaroids from frames with short captions) and POST (title, intro, tags) in {words_lang}. YouTube / YouTube Shorts is
  ALWAYS English (title, subtitles, cover, post); Chinese goes to Xiaohongshu / Bilibili / Douyin. Also write POST_EN
  (an English POST) when POST is Chinese, or POST_ZH when POST is English - same facts, its own hashtags - and
  COVER_EN (the COVER's texts in English) when the COVER is Chinese.
- Subtitles are ONE language per platform (English on YouTube and the international platforms, 中文 on 小红书 / B站):
  still write every cue as (English, 中文) - each version shows its own line; never set SUBS unless the request asks
  for bilingual subtitles (then SUBS = "both"). Picture labels as "English · 中文" (e.g. "Space Needle · 太空针塔").
- Premium look (references/AESTHETICS.md P1-P9): LOOK = "cinema" (full-bleed picture, no header; leave LOOK out to
  get it). Transitions: only "fade" (a slow dissolve; the default, so you may omit tr) or "cut" - never flash, whip,
  leak, zoom, iris, ink, blinds, tear or slideup. Hold the beautiful shots: one shot per unit when the clip has a
  long steady move, at most two; pick in-points on steady, well-exposed moves (no take-off, no fast yaw). Picture
  labels (label=) only for real places, 1-4 words, no emoji; timeline tl= only for dated facts, in date order.
  COVER: hero=dict(src=<the single most beautiful still>), a short title (<= 3 words + year if any) and a short
  subtitle; no polaroids, tagline or kicker needed. Cues: calm, factual, short; no exclamation marks, no emoji.
- Never the word SYNTHETIC; never the template's example content."""


def _frame(src, t, out):
    from vstudio import media
    ff = media.ffmpeg_bin() if hasattr(media, "ffmpeg_bin") else "ffmpeg"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    try:                                   # a 4K HEVC seek on a busy machine can be slow: one still never sinks the draft
        subprocess.run([ff, "-v", "error", "-y", "-ss", f"{max(0.0, float(t)):.2f}", "-i", src, "-frames:v", "1",
                        "-vf", "scale='min(2160,iw)':-2", "-q:v", "2", out], capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        return False
    return os.path.exists(out)


def _target(request):
    from .vlog import target_seconds
    return target_seconds(request, 75)


def _wants_music(request):
    from vstudio import music as MU
    return not MU.wants_none(request) and bool(re.search(r"music|配乐|音乐|piano|钢琴|bgm|score|soundtrack", request or "",
                                                         re.I))


def narration_is_chinese(request, name=None, title=None, language=None, item=None, platforms=None):
    """This version's language: its own first (``language``; its platforms - YouTube is always English, 小红书 / B站
    Chinese, vstudio.platform.lang_for; "中文版" / "English version" in the project's name, an item id like
    zh-version / en-version, the language of its title), else what the request asks the narration to be."""
    if language in ("zh", "en"):
        return language == "zh"
    if platforms:
        from vstudio import platform as P
        langs = {P.lang_for(p, "en") for p in platforms}
        if any(P.lang_fixed(p) for p in platforms) or langs == {"en"}:
            return False                     # a version that goes to YouTube is English, whatever else it names
        if langs == {"zh"}:
            return True
    nm = f"{name or ''} {item or ''}"
    if re.search(r"english|英文|(^|[\s_-])en([\s_-]|$)", nm, re.I):
        return False
    if re.search(r"中文|chinese|(^|[\s_-])(zh|cn)([\s_-]|$)", nm, re.I):
        return True
    t = str(title or "").strip()
    if t:
        return bool(re.search(r"[\u4e00-\u9fff]", t))
    rq = str(request or "")
    return bool(re.search(r"(narrat\w*|voice[- ]?over|旁白|配音|讲解)[^.。]{0,30}(in )?(chinese|mandarin|中文)|"
                          r"(chinese|mandarin|中文)[^.。]{0,12}(narrat\w*|voice[- ]?over|旁白|配音)", rq, re.I))


def draft_spec(ctx, cp, path, template=None, instruction=None, complete=None):
    """Checkpoint ``story``: the spec from her request + footage (module doc). -> record or None."""
    from vstudio import footage
    request = ctx.request()
    vids = [p for v in ctx.inputs.values() for p in (v if isinstance(v, list) else [v]) if footage.is_video(p)]
    vids = list(dict.fromkeys(vids))
    work = os.path.dirname(path)
    ids = [os.path.splitext(os.path.basename(p))[0] for p in vids]
    ftext, imgs, facts = footage.context(vids, os.path.join(work, "draft_sheets"), ids=ids) if vids else ("", [], [])
    by_id = {f["id"]: f for f in facts}
    target = _target(request)
    plats = list(ctx.params.get("platforms") or [])
    lang_zh = narration_is_chinese(request, (ctx.data or {}).get("name"), ctx.params.get("title"),
                                   ctx.params.get("language"), ctx.item, plats)
    music_mode = str(ctx.params.get("mode") or "narration") == "music"
    from vstudio import narration as N
    vp = N.voice_plan("zh" if lang_zh else "en", ctx.params.get("tts_engine") or "auto")
    if music_mode:                           # a mood piece: no voice-over, music + a few refined on-screen lines
        vp = dict(vp, narrate=None, note=None)
        lang_note = ('no voice-over: MODE = "music"; the cues are a few refined on-screen lines (short, quiet, '
                     "poetic, never a running commentary), one per shot or two"
                     + ('; SUB_LEAD = "zh" (the 中文 line leads).' if lang_zh else "."))
    elif vp["narrate"] == "zh":
        lang_note = ('this version is narrated in Chinese: TTS = dict(language="zh") (the narrator speaks the 中文 of each '
                     "cue; the English shows as the subtitle under it).")
    elif lang_zh:
        lang_note = ('this Chinese version is narrated in English (no natural Chinese voice is set up): TTS = '
                     'dict(language="en") and SUB_LEAD = "zh" (the narrator reads the English of each cue; the 中文 '
                     "subtitle leads, the English sits under it). Write the English for the ear.")
    else:
        lang_note = 'this version is narrated in English: TTS = dict(language="en").'
    plat_names = ", ".join(plats) or "its platforms"
    bgm = music_bed(ctx, work, request, target, music_mode)
    bgm_note = (f'Music: BGM = "{bgm}", BGM_LUFS = -28, BGM_DUCK = -6 (already set for this video).' if bgm
                else "BGM = None.")
    tpl = DR._read(template, DR.TEMPLATE_CHARS) if template else ""
    doc = DR._read(os.path.join(M.ROOT, (cp.get("author") or {}).get("doc") or "workflows/photo-story/WORKFLOW.md"),
                   20000)
    cur = DR._read(path, DR.TEMPLATE_CHARS) if instruction and DR.state(path, template, cp, ctx.recipe) in (
        "drafted", "hers") else ""
    guide = GUIDE.format(first=ids[0] if ids else "CLIP", lang_note=lang_note, target=int(target), bgm_note=bgm_note,
                         length_of="of on-screen lines" if music_mode else "of narration", platforms=plat_names,
                         words_lang="Chinese" if lang_zh else "English")
    from vstudio.brain import steer as BST
    doc = BST.plan_doc(ctx.project_dir) if vids else None
    brain_line = BST.photo_line(doc, by_id) if doc else ""
    body = "\n\n".join(x for x in [
        f"Request: {request or '(none)'}",
        f"This project: {(ctx.data or {}).get('name') or ''} {ctx.params.get('title') or ''}".strip(),
        brain_line,
        ("Footage (clip id: facts; one contact sheet per clip is attached, tiles labelled with the clip's "
         f"seconds). {footage.MOMENTS_NOTE}\n{ftext}") if ftext else "",
        guide,
        f"Current spec (change only what the instruction asks):\n{cur}" if cur else "",
        f"Instruction from the creator: {instruction}" if instruction else "",
        f"Template (structure only):\n{tpl}" if tpl else "",
        f"Format guide:\n{doc}" if doc else "",
        f"Write the summary in {DR.LANGS.get(ctx.lang(), 'English')}."] if x)
    if complete is None:
        from vstudio import llm
        complete = llm.complete
    limit = min(1200.0, 300.0 + len(body) / 300.0 + 20.0 * len(imgs))
    r = complete("planner", SYSTEM, body, schema=True, max_tokens=16000, timeout=limit, cli_timeout=limit,
                 retries=1, effort="medium", **({"images": imgs} if imgs else {}))
    if not isinstance(r, dict) or r.get("provider") == "none":
        return None
    js = r.get("json") if isinstance(r.get("json"), dict) else {}
    text = js.get("content")
    if isinstance(text, str) and "SYNTHETIC" not in text[:600] and not DR.data_module_ok(text):
        # a long spec with one string left open (a Chinese intro broken over two lines) was thrown away and the step
        # waited for her: the model is shown what is wrong and fixes its own spec once
        r2 = complete("planner", SYSTEM, body + "\n\n" + _repair_note(text), schema=True, max_tokens=16000,
                      timeout=limit, cli_timeout=limit, retries=1, effort="medium")
        js2 = r2.get("json") if isinstance(r2, dict) and isinstance(r2.get("json"), dict) else {}
        if isinstance(js2.get("content"), str) and DR.data_module_ok(js2["content"]):
            r, js, text = r2, dict(js, **js2), js2["content"]
    if not isinstance(text, str) or not DR.data_module_ok(text) or "SYNTHETIC" in text[:600]:
        return None
    cut, made = 0, []
    for fr in _frames_asked(js, text):
        cid = _clip_id(fr.get("clip"), by_id)
        if cid is None or not re.match(r"^[\w-]{1,60}$", str(fr.get("name") or "")):
            continue
        try:
            t = min(float(fr.get("t") or 0), max(0.0, by_id[cid]["dur"] - 0.2))
        except (TypeError, ValueError):
            continue
        if _frame(by_id[cid]["path"], t, os.path.join(work, "frames", f"{fr['name']}.jpg")):
            cut += 1
            made.append(fr["name"])
    # a still the spec names that no frame was cut for would stop the render ("image not found"): it becomes one
    # of the frames that exist (a cover polaroid shows another still) - never a crash three stages later
    text = fix_video_refs(text, by_id)
    missing = [n for n in image_refs(text, set(by_id)) if n not in made and not os.path.exists(
        os.path.join(work, "frames", f"{n}.jpg"))]
    if missing:
        if not made:
            return None
        for n in missing:
            text = re.sub(rf"(?<=[\"':,|]){re.escape(n)}(?=[\"',|])", made[0], text)
    steered = []
    if doc:                                  # the plan's joins / label places (her changes always), still plain data
        text, steered = BST.photo_fix(text, doc, by_id)
    text = enforce_voice(text, vp, lang_zh, music_mode)
    text = label_language(text, lang_zh, complete)
    if bgm:
        text = enforce_bgm(text, work, bgm)
    fact_rec, facts_note = None, ""
    if not music_mode and FG.is_told(request):   # a told piece: its claims checked before the voice is made
        text, fact_rec, facts_note = FG.run(ctx, "spec", text, work, complete)
    if vp.get("narrate") == "en":
        text = add_respellings(text, complete)
    os.makedirs(work, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    summ = str(js.get("summary") or "").strip()[:300]
    note = N.note_text(vp.get("note"), ctx.lang())
    if note:                                 # why this Chinese version speaks English, and how to change it
        summ = f"{summ} {note}".strip()
    if facts_note:                           # what the fact check softened / dropped, and where facts.md is
        summ = f"{summ} {facts_note}".strip()
    rv = DR.outline_review(path, None)
    if summ:
        rv["summary"] = dict(code="draft.generic", params=dict(text=summ))
    return dict(by="ai", provider=r.get("provider"), model=r.get("model"), instruction=instruction, review=rv,
                sheets=len(imgs), frames=cut, bgm=os.path.basename(bgm) if bgm else None,
                language="zh" if lang_zh else "en", narration=vp.get("narrate"), voice_note=vp.get("note"),
                brain=len(steered), facts=fact_rec)


_AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")


def music_bed(ctx, work, request, target, music_mode):
    """The spec's BGM (a path relative to ``work``, the spec's folder) or None: her own music input (linked into
    ../inputs by the prepare stage), else a built-in bed (vstudio.music) when the request wants music - and always in
    music mode, whose timeline is cut on the bed's beats ("MODE music needs BGM" stopped every history video drafted
    as a mood piece without a music word)."""
    for v in (ctx.inputs or {}).values():
        for src in (v if isinstance(v, list) else [v]):
            if isinstance(src, str) and src.lower().endswith(_AUDIO_EXT) and os.path.isfile(src):
                linked = os.path.join(os.path.dirname(work), "inputs", os.path.basename(src))
                return (os.path.join("..", "inputs", os.path.basename(src)) if os.path.exists(linked)
                        else os.path.abspath(src))
    if not (music_mode or _wants_music(request)):
        return None
    from vstudio import music as MU
    pdir = getattr(ctx, "project_dir", None)
    # the library's best fit (her own tracks, the CC0 library, a built-in bed), not the track another video of the
    # same group has (a goal's history films each get their own) - noted for her recent videos' diversity; no CC BY
    # track (nothing here prints its credit)
    ranked = MU.choose(request, style="calm", need_beat=bool(music_mode), min_duration=target, no_credit=True,
                       project=pdir, item=getattr(ctx, "item", None), group=MU.group_of(pdir) if pdir else None)
    top = ranked[0] if ranked else dict(source="builtin", mood="calm", id="builtin:calm")
    import shutil
    os.makedirs(work, exist_ok=True)
    if top["source"] == "builtin":
        made = MU.make(top["mood"], round(target + 20, 1))
        name = f"music_{top['mood']}{os.path.splitext(made)[1]}"
    else:
        made = top["path"]
        name = f"music_{os.path.splitext(os.path.basename(made))[0][:60]}{os.path.splitext(made)[1]}"
    shutil.copyfile(made, os.path.join(work, name))
    return name


def enforce_bgm(text, work, bgm):
    """``BGM`` in the spec is the bed made for it, whatever the model wrote (None, left out, or a file that does not
    exist) - a file of hers the model chose that exists is kept."""
    cur = _spec_value(text, "BGM")
    if isinstance(cur, str) and cur.strip():
        p = os.path.expanduser(cur)
        if os.path.isfile(p if os.path.isabs(p) else os.path.join(work, p)):
            return text
    return _set_global(text, "BGM", bgm)


def _set_global(text, name, value):
    """``NAME = <value>`` in a spec module: the model's assignment replaced, else appended."""
    if isinstance(value, dict) and all(isinstance(k, str) and k.isidentifier() for k in value):
        line = f"{name} = dict(" + ", ".join(f"{k}={v!r}" for k, v in value.items()) + ")"
    else:
        line = f"{name} = {value!r}"
    pat = re.compile(rf"(?m)^{name}\s*=.*$")
    if pat.search(text):
        import ast
        try:
            tree = ast.parse(text)
            for st in tree.body:
                if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name) and st.targets[0].id == name:
                    lines = text.split("\n")
                    return "\n".join(lines[:st.lineno - 1] + [line] + lines[st.end_lineno:])
        except SyntaxError:
            pass
        return pat.sub(lambda _m: line, text, count=1)
    return text.rstrip("\n") + "\n" + line + "\n"


def enforce_voice(text, vp, lang_zh, music_mode=False):
    """The voice policy written into the spec, whatever the model wrote: the narration language (TTS language),
    which subtitle leads (SUB_LEAD) and MODE for a piece with no voice - never the built-in Chinese voice unless
    ``vp`` (narration.voice_plan) chose Chinese."""
    if music_mode:
        text = _set_global(text, "MODE", "music")
        return _set_global(text, "SUB_LEAD", "zh" if lang_zh else "en")
    tts_cfg = _spec_value(text, "TTS")
    tts_cfg = dict(tts_cfg) if isinstance(tts_cfg, dict) else {}
    tts_cfg["language"] = vp.get("narrate") or "en"
    text = _set_global(text, "TTS", tts_cfg)
    return _set_global(text, "SUB_LEAD", vp.get("sub_lead") or ("zh" if lang_zh else "en"))


_LABEL_SEP = re.compile(r"\s*[·•/／|｜]\s*")


def _label_literals(text):
    """[(node, value)] for every ``label=`` / ``tri_label=`` string literal in a spec module."""
    import ast
    out = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in ("label", "tri_label") and isinstance(kw.value, ast.Constant) and \
                        isinstance(kw.value.value, str):
                    out.append((kw.value, kw.value.value))
    return out


def _replace_nodes(text, repl):
    """``text`` with the source of each AST node in ``repl`` ([(node, new literal source)]) replaced - nothing else
    changes."""
    lines = text.split("\n")
    starts, k = [], 0
    for ln in lines:
        starts.append(k)
        k += len(ln.encode("utf-8")) + 1
    raw = text.encode("utf-8")
    spans = sorted(((starts[n.lineno - 1] + n.col_offset, starts[n.end_lineno - 1] + n.end_col_offset, src)
                    for n, src in repl), reverse=True)
    for a, b, src in spans:
        raw = raw[:a] + src.encode("utf-8") + raw[b:]
    return raw.decode("utf-8")


def label_language(text, lang_zh, complete=None):
    """Picture labels in this version's language, whatever the model wrote: a label with no part in it ("Space
    Needle" on a Chinese version, "太空针塔" on YouTube) is asked of the routed AI once and written "English · 中文"
    (the renderer shows the version's part; photostory ctx.shown). No AI answer -> unchanged (the renderer then hides
    such a label rather than showing the other language)."""
    lits = _label_literals(text)
    need = []
    for node, v in lits:
        parts = [x for x in _LABEL_SEP.split(v) if x.strip()]
        has_zh = any(re.search(r"[\u3400-\u9fff]", x) for x in parts)
        has_en = any(re.search(r"[A-Za-z]", x) and not re.search(r"[\u3400-\u9fff]", x) for x in parts)
        if (lang_zh and not has_zh) or (not lang_zh and not has_en):
            need.append((node, v))
    if not need:
        return text
    if complete is None:
        from vstudio import llm
        complete = llm.complete
    want = "Simplified Chinese" if lang_zh else "English"
    names = list(dict.fromkeys(v for _, v in need))
    try:
        r = complete("planner", "You translate short on-screen place labels of a documentary video. Reply with JSON "
                     "only: {\"labels\": {\"<label>\": \"<translation>\"}}. Use the established name of a real place "
                     "(太空针塔 for Space Needle); 1-6 words / 2-10 characters; no quotes, no emoji.",
                     f"Translate each label into {want}:\n" + "\n".join(names), schema=True, max_tokens=800,
                     timeout=120, cli_timeout=120, retries=1, effort="low")
    except Exception:  # noqa: BLE001 - a label left as is is hidden at render time, never a failed draft
        return text
    got = ((r or {}).get("json") or {}).get("labels") if isinstance(r, dict) else None
    if not isinstance(got, dict):
        return text
    repl = []
    for node, v in need:
        tr = str(got.get(v) or "").strip()
        ok = tr and (bool(re.search(r"[\u3400-\u9fff]", tr)) if lang_zh else bool(re.search(r"[A-Za-z]", tr) and
                                                                                   not re.search(r"[\u3400-\u9fff]", tr)))
        if ok:
            pair = f"{v} · {tr}" if lang_zh else f"{tr} · {v}"
            repl.append((node, repr(pair)))
    return _replace_nodes(text, repl) if repl else text


def _spec_value(text, name):
    import ast
    try:
        for st in ast.parse(text).body:
            if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name) and st.targets[0].id == name:
                return eval(compile(ast.Expression(st.value), "<spec>", "eval"), {"__builtins__": {}}, {"dict": dict})
    except Exception:  # noqa: BLE001
        return None
    return None


def _repair_note(text):
    """What is wrong with a drafted spec that is not a plain-data module, for the model's one repair."""
    import ast
    try:
        ast.parse(text)
        why = "a statement that is not NAME = <literal> (no import, call, attribute, loop or function)"
    except SyntaxError as e:
        why = f"SyntaxError at line {e.lineno}: {e.msg}"
    return (f"Your previous reply's content is not a plain-data Python module ({why}). Return the whole reply "
            f"again with the content fixed: every string closed on its line (join long text with adjacent "
            f"\"...\" \"...\" pieces inside parentheses), only NAME = literals.\n\nPrevious content:\n{text}")


def _frames_asked(js, text):
    """The stills to cut: the reply's ``frames``, and a ``frames = [...]`` list the model put in the spec itself."""
    out = [f for f in js.get("frames") or [] if isinstance(f, dict)]
    import ast
    try:
        for st in ast.parse(text).body:
            if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id.lower() == "frames"
                                                  for t in st.targets):
                v = ast.literal_eval(st.value) if not isinstance(st.value, ast.List) else [
                    {k.arg: ast.literal_eval(k.value) for k in e.keywords} if isinstance(e, ast.Call) else
                    ast.literal_eval(e) for e in st.value.elts]
                out += [f for f in v if isinstance(f, dict)]
    except (SyntaxError, ValueError):
        pass
    seen, uniq = set(), []
    for f in out:
        if f.get("name") not in seen:
            seen.add(f.get("name"))
            uniq.append(f)
    return uniq


def _clip_id(cid, by_id):
    """The model's clip id -> a real one: exact, else the one whose DJI number (``_0336_``) matches."""
    if cid in by_id:
        return cid
    m = re.search(r"_(\d{3,5})_[A-Z]$|_(\d{3,5})$", str(cid or ""))
    num = (m.group(1) or m.group(2)) if m else None
    hits = [k for k in by_id if num and re.search(rf"_{num}(_[A-Z])?$", k)]
    return hits[0] if len(hits) == 1 else None


def fix_video_refs(text, by_id):
    """A video shot naming a clip that is not there ("vDJI_..._0336_D" with another clip's time stamp) -> the clip
    with that DJI number when exactly one has it."""
    def sub(m):
        cid = m.group(1)
        if cid in by_id:
            return m.group(0)
        real = _clip_id(cid, by_id)
        return "v" + real if real else m.group(0)
    return re.sub(r"(?<=[\"':,|])v([A-Za-z0-9][\w-]{2,80})(?=[\"',|])", sub, text)


SOURCE_KINDS_NO_IMAGE = ("route",)


def image_refs(text, video_ids):
    """The still images a spec's SCRIPT shots and COVER name (not "v<clip>" videos, not route maps)."""
    import ast
    names = []

    def src(v):
        if not isinstance(v, str) or not v:
            return
        kind, _, rest = v.partition(":")
        if rest and kind in SOURCE_KINDS_NO_IMAGE:
            return
        for n in re.split(r"[,|]", rest if rest else v):
            n = n.strip()
            if n and not (n.startswith("v") and n[1:] in video_ids):
                names.append(n)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    for st in tree.body:
        if not (isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name)):
            continue
        name = st.targets[0].id
        try:
            val = eval(compile(ast.Expression(st.value), "<spec>", "eval"), {"__builtins__": {}}, {"dict": dict}) \
                if name in ("SCRIPT", "COVER") else None
        except Exception:  # noqa: BLE001
            continue
        if name == "SCRIPT":
            for unit in val or []:
                for shot in (unit[2] if len(unit) > 2 else []):
                    src(shot[0] if shot else None)
        elif name == "COVER" and isinstance(val, dict):
            hero = val.get("hero") or {}
            for k in ("src", "a", "b"):
                src(hero.get(k))
            for pz in val.get("polaroids") or []:
                src((pz or {}).get("src"))
    return list(dict.fromkeys(names))


def _english_cues(text):
    import ast
    try:
        for st in ast.parse(text).body:
            if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name) and st.targets[0].id == "SCRIPT":
                v = eval(compile(ast.Expression(st.value), "<spec>", "eval"), {"__builtins__": {}}, {"dict": dict})
                return " ".join(e for unit in v for e, _z in unit[1]).replace("**", "")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _all_known(phrase, lex):
    """Every word of a respelling is an everyday word of the voice's dictionary (no acronym, no made-up syllable)."""
    toks = re.findall(r"[A-Za-z']+", phrase)
    return bool(toks) and all(t == t.lower() and (t in lex.golds or t in lex.silvers) for t in toks)


def add_respellings(text, complete):
    """An English narration on the local voice: the names it cannot say (in neither its dictionary nor the curated
    name lexicon, vstudio.kokoro_lexicon - Puget, Elliott, Dreyfus were spelled out letter by letter) get respellings
    made of words it knows, from one short model call, kept only when every word of the respelling is known; written
    as ``SAY_TTS`` (tts.py reads it with SAY). A curated name is never respelled ("Elliott" -> "ell yacht" was heard
    as "El Yacht")."""
    try:
        from vstudio import kokoro_g2p as K
        from misaki import en
        g2p = en.G2P(trf=False, british=False, fallback=None, unk="")
        lex = g2p.lexicon
    except Exception:  # noqa: BLE001  (no local English voice here: nothing to respell)
        return text
    words = K.unknown_words(_english_cues(text), g2p)[:40]
    keep, tried = {}, {}
    for _round in range(2):                      # once more for the ones whose respelling used unknown syllables
        todo = [w for w in words if w not in keep]
        if not todo:
            break
        note = ("\nThese were rejected (a part is not an everyday word): " +
                "; ".join(f"{w} -> {tried[w]}" for w in todo if w in tried)) if tried else ""
        try:
            r = complete("planner", "You write pronunciation respellings for a text-to-speech voice that only knows "
                         "common English words.", "For each word, give how it is said as 1-4 everyday lowercase "
                         "English words whose sounds add up to it (Dreyfus -> \"dray fuss\", Tacoma -> \"tack oh "
                         "ma\"), keeping the name's own vowels and stress (\"ell yacht\" for Elliott is wrong: it is "
                         "heard as a yacht); no capitals, no made-up syllables; leave out a word you cannot respell "
                         "faithfully. Reply with JSON only: {\"<word>\": \"<respelling>\"}."
                         "\nWords: " + ", ".join(todo) + note,
                         schema=True, max_tokens=1500, timeout=180, cli_timeout=180, retries=1, effort="low")
        except Exception:  # noqa: BLE001
            break
        js = r.get("json") if isinstance(r, dict) and isinstance(r.get("json"), dict) else {}
        for w, rs in js.items():
            if w in todo and isinstance(rs, str) and rs.strip():
                if _all_known(rs, lex):
                    keep[w] = rs.strip()
                else:
                    tried[w] = rs.strip()
    if not keep:
        return text
    return text.rstrip("\n") + "\n\n# how the local voice says the names it does not know (spoken forms, never shown)\n" \
        f"SAY_TTS = {keep!r}\n"


def spec_language(path):
    """The narration language a spec asks for (TTS language), for tests and the review."""
    try:
        m = re.search(r"language\s*=\s*['\"](\w+)['\"]", open(path, encoding="utf-8").read())
    except OSError:
        return None
    return m.group(1) if m else None



# --------------------------------------------------------------------------- the other platforms (stage ``platforms``)
def _canvas(name):
    from vstudio import platform as P
    try:
        p = P.profile(name)
        return int(p.w), int(p.h)
    except (KeyError, ValueError):
        return None


def more_platforms(env):
    """The story is laid out for the first platform (render / cover / export ``--platform``); every other one gets
    its own copy: another canvas (Bilibili 16:9 next to a 3:4 Xiaohongshu story) is rendered again on the same voice
    and timing - a photo story's header, picture box and subtitle band are laid out per canvas, a reframed file
    would crop them - and every platform gets its own cover and post copy (its title / hashtag rules) in
    ``out/<platform>/``. -> {files, platforms: [{platform, file, cover, post}]}"""
    plats = list(env.params.get("platforms") or [])
    spec = os.path.join(env.item_dir, "work", "spec.py")
    first = _canvas(plats[0]) if plats else None
    scripts = os.path.join(env.workflow_dir, "scripts", "photostory")
    py = env.fmt("{python}")
    mode = env.params.get("mode") or "narration"
    out, files = [], []
    for p in plats[1:]:
        slug = re.sub(r"[^a-z0-9]+", "-", p.lower()).strip("-")
        d = os.path.join(env.item_dir, "out", slug)
        os.makedirs(d, exist_ok=True)
        rec = dict(platform=p)
        cv = _canvas(p)
        if cv and cv != first:
            vid = os.path.join(d, "story.mp4")
            env.run([py, os.path.join(scripts, "render.py"), spec, "--out", vid, "--platform", p, "--mode", mode],
                    log=f"render-{slug}.log")
            rec["file"] = vid
            files.append(vid)
        else:
            rec["file"] = os.path.join(env.item_dir, "out", "story.mp4")     # the same canvas: the same video
        cov = os.path.join(d, "cover.png")
        env.run([py, os.path.join(scripts, "cover.py"), spec, "--out", cov, "--platform", p], log=f"cover-{slug}.log")
        env.run([py, os.path.join(scripts, "export.py"), spec, "--out", d, "--platform", p, "--mode", mode,
                 "--no-voice"], log=f"export-{slug}.log")
        rec.update(cover=cov, post=os.path.join(d, "post.md"))
        ab = sorted(os.path.join(d, f) for f in os.listdir(d) if f.startswith("cover.ab") and f.endswith(".jpg"))
        if ab:                                       # YouTube: the A/B trio for Test & Compare (cover.ab.md says how)
            rec["cover_ab"] = ab
        files += [cov, rec["post"]] + ab
        out.append(rec)
    from ..build import file_sha
    return dict(files=[f for f in files if os.path.exists(f)], platforms=out,
                digest="".join(file_sha(f) or "" for f in files if os.path.exists(f))[:64] or "none")
