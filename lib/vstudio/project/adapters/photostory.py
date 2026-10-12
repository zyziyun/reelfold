"""photo-story: the story checkpoint's spec (work/spec.py) is drafted by the AI from her request and what it SEES of
her footage (vstudio.footage contact sheets), never left as the SYNTHETIC demo - before this an autopilot photo story
always stopped at "write spec.py" (the generic drafter does not write Python).

The spec is a data module the renderer imports: the draft is accepted only when it is plain data
(drafts.data_module_ok). Stills the model asks for (a cover, a still shot) are cut from her clips into work/frames/;
a built-in music bed (vstudio.music, MIT) is laid under the voice when the request wants music.
"""
import os
import re
import subprocess

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
- Narration language: {lang_note}
- Each cue is (English, 中文); keep the English <= ~90 characters and the 中文 <= ~38 characters per cue, 1-3 cues per unit.
  Length: about {target} s of narration in total (Chinese ~4.3 characters per second, English ~2.6 words per second).
- Do not write PLATFORM, CANVAS, OUT, TTS voice / model / engine, VOICE, ROUTE or SAY. {bgm_note}
- TITLE_ZH / TITLE_EN, SECTIONS / SECTIONS_EN (2-4 short chapter names), COVER (kicker, title, subtitle, tagline
  (before, keyword, after), hero=dict(src=<frame>), polaroids from frames with short captions) and POST (title, intro,
  tags) in the request's language for this version.
- Never the word SYNTHETIC; never the template's example content."""


def _frame(src, t, out):
    from vstudio import media
    ff = media.ffmpeg_bin() if hasattr(media, "ffmpeg_bin") else "ffmpeg"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run([ff, "-v", "error", "-y", "-ss", f"{max(0.0, float(t)):.2f}", "-i", src, "-frames:v", "1",
                    "-vf", "scale='min(2160,iw)':-2", "-q:v", "2", out], capture_output=True, timeout=120)
    return os.path.exists(out)


def _target(request):
    from .vlog import target_seconds
    return target_seconds(request, 75)


def _wants_music(request):
    from vstudio import music as MU
    return not MU.wants_none(request) and bool(re.search(r"music|配乐|音乐|piano|钢琴|bgm|score|soundtrack", request or "",
                                                         re.I))


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
    lang_zh = (ctx.params.get("language") == "zh") or bool(re.search(r"[一-鿿]", str(ctx.params.get("title")
                                                                                            or ""))) \
        or bool(re.search(r"中文|Chinese", str((ctx.data or {}).get("name") or ""), re.I))
    lang_note = ('this version is narrated in Chinese: TTS = dict(language="zh") (the narrator speaks the 中文 of each '
                 "cue; the English shows as the subtitle under it)." if lang_zh else
                 'this version is narrated in English: TTS = dict(language="en").')
    bgm = None
    if _wants_music(request):
        from vstudio import music as MU
        ranked = MU.rank(request, style="calm")
        mood = next((t["mood"] for t in ranked if t["source"] == "builtin"), "calm")
        made = MU.make(mood, round(target + 20, 1))
        bgm = os.path.join(work, f"music_{mood}{os.path.splitext(made)[1]}")
        import shutil
        os.makedirs(work, exist_ok=True)
        shutil.copyfile(made, bgm)
    bgm_note = (f'Music: BGM = "{os.path.basename(bgm)}", BGM_LUFS = -28, BGM_DUCK = -6 (a built-in bed already '
                f"made for this video)." if bgm else "BGM = None.")
    tpl = DR._read(template, DR.TEMPLATE_CHARS) if template else ""
    doc = DR._read(os.path.join(M.ROOT, (cp.get("author") or {}).get("doc") or "workflows/photo-story/WORKFLOW.md"),
                   20000)
    cur = DR._read(path, DR.TEMPLATE_CHARS) if instruction and DR.state(path, template, cp, ctx.recipe) in (
        "drafted", "hers") else ""
    guide = GUIDE.format(first=ids[0] if ids else "CLIP", lang_note=lang_note, target=int(target), bgm_note=bgm_note)
    body = "\n\n".join(x for x in [
        f"Request: {request or '(none)'}",
        f"This project: {(ctx.data or {}).get('name') or ''} {ctx.params.get('title') or ''}".strip(),
        ("Footage (clip id: facts; one contact sheet per clip is attached, tiles labelled with the clip's "
         f"seconds):\n{ftext}") if ftext else "",
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
    if not isinstance(text, str) or not DR.data_module_ok(text) or "SYNTHETIC" in text[:600]:
        return None
    cut = 0
    for fr in js.get("frames") or []:
        if not isinstance(fr, dict) or fr.get("clip") not in by_id or not re.match(r"^[\w-]{1,60}$",
                                                                                   str(fr.get("name") or "")):
            continue
        try:
            t = min(float(fr.get("t") or 0), max(0.0, by_id[fr["clip"]]["dur"] - 0.2))
        except (TypeError, ValueError):
            continue
        if _frame(by_id[fr["clip"]]["path"], t, os.path.join(work, "frames", f"{fr['name']}.jpg")):
            cut += 1
    os.makedirs(work, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    summ = str(js.get("summary") or "").strip()[:300]
    rv = DR.outline_review(path, None)
    if summ:
        rv["summary"] = dict(code="draft.generic", params=dict(text=summ))
    return dict(by="ai", provider=r.get("provider"), model=r.get("model"), instruction=instruction, review=rv,
                sheets=len(imgs), frames=cut, bgm=os.path.basename(bgm) if bgm else None,
                language="zh" if lang_zh else "en")


def spec_language(path):
    """The narration language a spec asks for (TTS language), for tests and the review."""
    try:
        m = re.search(r"language\s*=\s*['\"](\w+)['\"]", open(path, encoding="utf-8").read())
    except OSError:
        return None
    return m.group(1) if m else None

