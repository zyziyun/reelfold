"""The ``voiceover`` op of second-pass editing (成片二次编辑): a narration added over a finished clip.

    {op: "voiceover", mode: "intro" | "full" | "span", start?, end?, text?, text_zh?,
     lines?: [{start, end, text, text_zh?}], ask?: "<her words>", source?: "tts" | "take", take?: "<wav>",
     voice?: "<speaker>", duck_db?: -14, captions?: true}

  intro  a short opening from ``start`` (default the clip's start): ``text`` said from there
  full   the whole clip narrated: ``lines`` timed to its moments, placed in the gaps of on-camera speech - a line
         that would talk over her own voice is moved into the nearest gap that holds it, else left out (said so)
  span   ``text`` said from ``start`` (to ``end``)

No text (her ask only: 「加一下好玩的vlog的介绍tts」): the routed AI (task ``output_edit``) writes it from the clip's
transcript, its speech gaps and her words - English for the international versions, 中文 for the Chinese ones (each
version says its own language; YouTube is always English).

The voice of each language is cast by ``vstudio.voicecast`` (lively for a vlog, calm for a history piece ...); a
speaker she named (``voice``, or the project's own voice in project.yaml) wins. The audio source is pluggable
(``SOURCES``): ``tts`` synthesises each line (Qwen3-TTS 中文 / Kokoro English, the cast speaker + style), ``take`` lays
a recording she made (``take``: a wav / m4a) from ``start`` - the mix, ducking and captions are the same for both.

Render (``outrender.run_audio``): the voice track replaces nothing; everything under it (the clip's own sound and the
music bed) is ducked by ``duck_db`` while it speaks (0.12 s ramps), and its lines are captioned in the version's
language. The op is one step of the edit document: Undo / Before-after work as for any edit, and the step reads
"Voice-over 0:00–0:06" (``describe``).
"""
import os
import re

from vstudio.batch.util import read_json

CJK = re.compile(r"[㐀-鿿]")
MODES = ("intro", "full", "span")
DUCK_DB = -14.0
GAP_PAD = 0.15                 # s of air kept between her speech and a narration line
MAX_LINES = 40
VOICE_HOOK = None              # tests / embedders: fn(text, lang, voice dict, out_wav) -> out_wav (else vstudio.tts)
WRITE_HOOK = None              # tests: fn(system, prompt) -> {"lines": [...]} (else vstudio.llm, task output_edit)


def _err(code, en, zh=None, **params):
    from .outputs import OutputError
    return OutputError(code, en, zh, **params)


def is_zh(text):
    return bool(CJK.search(str(text or "")))


def seconds_for(text, speed=1.0):
    """About how long a line takes to say (Mandarin ~4.5 characters/s, English ~2.6 words/s)."""
    from vstudio.qwen_synth import expected_seconds
    return max(0.6, expected_seconds(str(text or "")) / max(0.5, float(speed or 1.0)))


# --------------------------------------------------------------------------- languages of the versions
def version_langs(rec, st, words=None):
    """The languages the output's versions show: its own (the platform it was made for, else the post copy's
    language, else the speech's), then every export's. -> ["zh", "en"] (first = the output's own)."""
    from vstudio import platform as P
    own = None
    if rec.get("platform"):
        own = P.lang_for(str(rec["platform"]).split(":")[0], None)
    own = own or rec.get("lang_hint")
    if not own and words:
        own = "zh" if is_zh(" ".join(w.get("w", "") for w in words[:80])) else "en"
    if not own and rec.get("profile") is not None:
        own = P.lang_for(rec["profile"].key, "en")
    out = [own or "en"]
    for x in st.get("exports") or []:
        lg = x.get("lang") or P.lang_for(str(x.get("target") or "").split(":")[0], None)
        if lg and lg not in out:
            out.append(lg)
    return out


def line_text(line, lang):
    """The words of a line for a version in ``lang`` (its ``text_<lang>`` / the text in that language), else None."""
    alt = line.get(f"text_{lang}")
    if alt:
        return str(alt)
    t = str(line.get("text") or "")
    if t and (lang == "zh") == is_zh(t):
        return t
    return None


# --------------------------------------------------------------------------- the voice
def _project_voice(rec):
    """A voice she named for the project (project.yaml params / items ``voice``), or None."""
    from vstudio import voicecast as VC
    if rec.get("kind") != "project" or not rec.get("owner"):
        return None
    try:
        import yaml
        with open(os.path.join(rec["owner"], "project.yaml"), encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
    except Exception:  # noqa: BLE001
        return None
    item = str(rec.get("id") or "").split("/")[0]
    vals = [((d.get("overrides") or {}).get(item) or {}).get("voice")]
    vals += [(it.get("params") or {}).get("voice") for it in d.get("items") or [] if isinstance(it, dict)
             and it.get("id") == item]
    vals.append((d.get("params") or {}).get("voice"))
    for v in vals:
        p = VC.explicit(v)
        if p:
            return p
    return None


def _kind(rec, ask):
    from vstudio import voicecast as VC
    owner = os.path.basename(str(rec.get("owner") or ""))
    return VC.kind_of(ask, rec.get("title"), owner) or "vlog"


def cast_voices(rec, langs, ask=None, named=None):
    """The voice of each language: the speaker she named (``named`` / the project's), else the casting for the clip's
    kind (rules: no model call in an edit) -> {lang: {engine, speaker, style, reason, by}}."""
    from vstudio import voicecast as VC
    out = {}
    mine = VC.explicit(named) if named else None
    mine = mine or _project_voice(rec)
    kind = _kind(rec, ask)
    for lang in langs:
        try:
            eng = VC.narration_engine(lang)
        except Exception:  # noqa: BLE001  (no voice engine here: the render says so)
            eng = None
        if mine and lang in (VC.find(mine["speaker"]) or {}).get("native", []):
            out[lang] = VC.record(dict(mine, style=mine.get("style") or VC.style_for(kind, lang)
                                       if mine["engine"] == "qwen" else None, reason="your voice", by="you"))
            continue
        c = VC.cast(lang, eng, kind=kind, instruction=ask if ask and named else None, complete=False) if eng else None
        out[lang] = VC.record(c) if c else dict(engine=eng, reason="the voice of this computer", by="rules")
    return out


# --------------------------------------------------------------------------- placing the lines
def speech_spans(words, pad=GAP_PAD):
    """Where someone speaks on camera: merged [a, b] around the words."""
    spans = []
    for w in words or []:
        a, b = float(w["t"]) - pad, float(w["te"]) + pad
        if spans and a <= spans[-1][1] + 0.25:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    return spans


def gaps(words, start, end, pad=GAP_PAD):
    """The stretches of [start, end] where nobody speaks -> [[a, b]]."""
    out, cur = [], start
    for a, b in speech_spans(words, pad):
        if b <= cur:
            continue
        if a >= end:
            break
        if a - cur > 0.3:
            out.append([round(cur, 3), round(min(a, end), 3)])
        cur = max(cur, b)
    if end - cur > 0.3:
        out.append([round(cur, 3), round(end, 3)])
    return out


def _overlap(a, b, spans):
    return sum(max(0.0, min(b, y) - max(a, x)) for x, y in spans)


def place(lines, words, start, end, warns, avoid=True):
    """Each line at its time, its length the time its longest version takes; with ``avoid`` (a full narration) a line
    over her speech moves into the nearest gap that holds it (after its time first), else it is left out
    (``warns``). An intro / span stays where she asked for it (her voice is ducked under it)."""
    from .outputs import msg
    spans = speech_spans(words) if avoid else []
    out, cursor = [], start
    for ln in lines:
        need = max(seconds_for(ln.get("text")), seconds_for(ln.get("text_zh") or ""))
        a = max(float(ln.get("start", cursor)), cursor)
        b = a + need
        if spans and _overlap(a, b, spans) > 0.15 * need:
            fits = [g for g in gaps(words, cursor, end) if g[1] - g[0] >= need * 0.8]
            after = [g for g in fits if g[0] >= a - 0.5]
            g = (after or fits or [None])[0]
            if g is None:
                warns.append(msg("voiceover-line-dropped", "a narration line would talk over your own voice and no "
                                 "pause holds it: left out", "有一句旁白会盖住你自己的声音，又没有足够长的停顿，已略过",
                                 text=str(ln.get("text") or ln.get("text_zh") or "")[:60]))
                continue
            a = g[0]
            b = min(g[1], a + need)
        if a >= end - 0.3:
            warns.append(msg("voiceover-too-long", "the narration is longer than the clip: the last lines are left out",
                             "旁白比视频长，最后几句略过"))
            break
        b = min(b, end)
        out.append(dict({k: v for k, v in ln.items() if k in ("text", "text_zh", "text_en")},
                        start=round(a, 3), end=round(b, 3)))
        cursor = b + 0.1
    return out


def split_text(text):
    """A block of narration -> sentences."""
    parts = [p.strip() for p in re.split(r"(?<=[。！？!?；;])|(?<=[.])\s+", str(text or "")) if p and p.strip()]
    return parts or ([str(text).strip()] if str(text or "").strip() else [])


def _pair_lines(text, text_zh):
    en, zh = split_text(text), split_text(text_zh)
    n = max(len(en), len(zh))
    return [dict({k: v for k, v in (("text", en[i] if i < len(en) else None),
                                    ("text_zh", zh[i] if i < len(zh) else None)) if v}) for i in range(n)]


# --------------------------------------------------------------------------- writing it (no text given)
WRITE_SYSTEM = (
    "You write a short voice-over narration for a finished video. Times are seconds on the video's timeline. Write "
    "lines a narrator says over the picture, in the gaps where nobody speaks on camera (never over the speaker's own "
    "voice). Keep it natural and fitting the creator's ask and the video's kind (a fun vlog: lively and warm; a "
    "history piece: calm). Each line is short (Chinese <= 24 characters, English <= 14 words) and its slot is long "
    "enough to say it. Reply with JSON only: {\"lines\": [{\"start\": s, \"end\": s, \"text\": \"<English>\", "
    "\"text_zh\": \"<中文>\"}]} - give text (English) and / or text_zh (中文) as the languages asked.")


def write_lines(rec, words, start, end, mode, ask, langs):
    """The routed AI writes the narration -> [{start, end, text?, text_zh?}]. Raises needs-model without one."""
    import json
    from vstudio import subs
    said = [f"{c.start:.1f}-{c.end:.1f} {c.text}" for c in subs.cues_from_words(words, max_chars=24)][:200] \
        if words else []
    body = dict(ask=str(ask or "")[:300], mode=mode, span=[round(start, 2), round(end, 2)],
                duration=round(rec["info"]["duration"], 2), title=rec.get("title"),
                languages=["English (text)" if lg == "en" else "Chinese (text_zh)" if lg == "zh" else lg
                           for lg in langs],
                speech=said, gaps=gaps(words, start, end),
                length=("one or two lines from the start (an intro)" if mode == "intro" else
                        "the whole video, a line every few seconds of picture" if mode == "full" else
                        "one or two lines in the span"))
    prompt = json.dumps(body, ensure_ascii=False)
    try:
        if WRITE_HOOK is not None:
            j = WRITE_HOOK(WRITE_SYSTEM, prompt)
        else:
            from vstudio import llm
            if llm.route("output_edit").provider == "none":
                raise RuntimeError("no model")
            r = llm.complete("output_edit", WRITE_SYSTEM, prompt, schema=True, max_tokens=3000, cli_timeout=180)
            j = r.get("json")
    except Exception as e:  # noqa: BLE001
        raise _err("needs-model", "writing the narration needs an AI model (Settings › AI) - or give the text",
                   "写旁白需要 AI 模型（设置 › AI），或者直接给出旁白文字", error=str(e)[:200]) from None
    rows = (j or {}).get("lines") if isinstance(j, dict) else None
    out = []
    for x in rows or []:
        if not isinstance(x, dict):
            continue
        ln = {k: str(x[k]).strip()[:200] for k in ("text", "text_zh") if isinstance(x.get(k), str) and x[k].strip()}
        if ln:
            try:
                ln["start"] = float(x.get("start", start))
            except (TypeError, ValueError):
                ln["start"] = start
            out.append(ln)
    if not out:
        raise _err("needs-model", "the AI wrote no narration - try again or give the text",
                   "AI 没写出旁白——再试一次或直接给出文字")
    return out


# --------------------------------------------------------------------------- the op
def normalize(doc, st, op, tl, dur, warns):
    """-> the normalized op {id, seq, mode, start, end, lines, voices, source, take?, duck_db, captions}."""
    from . import outputs as O
    mode = str(op.get("mode") or ("full" if op.get("lines") and len(op["lines"]) > 2 else "intro")).lower()
    if mode not in MODES:
        raise _err("bad-param", "mode: intro | full | span", "mode：intro / full / span", name="mode", value=mode)
    source = str(op.get("source") or "tts").lower()
    if source not in SOURCES:
        raise _err("bad-param", f"source: {' | '.join(SOURCES)}", "来源：tts / take", name="source", value=source)
    t0 = st["trim"][0] or 0.0
    t1 = st["trim"][1] if st["trim"][1] is not None else dur
    start = O._src_time(op["start"], "start", op, tl, dur) if op.get("start") is not None else round(t0, 3)
    end = O._src_time(op["end"], "end", op, tl, dur) if op.get("end") is not None else round(t1, 3)
    if end - start < 0.5:
        raise _err("bad-time", "a voice-over needs at least 0.5s", "旁白至少 0.5 秒", start=start, end=end)
    W = O.words(doc, required=False) if doc.rec["info"]["has_audio"] else []
    langs = version_langs(doc.rec, st, W)
    n = dict(op="voiceover", mode=mode, source=source, start=start, end=end,
             duck_db=float(min(0.0, max(-30.0, float(op.get("duck_db", DUCK_DB))))),
             captions=op.get("captions", True) is not False)
    if op.get("ask"):
        n["ask"] = str(op["ask"])[:200]
    if source == "take":
        take = op.get("take")
        if not (isinstance(take, str) and os.path.isfile(take)):
            raise _err("bad-param", "take: the recording file", "take：录音文件", name="take", value=take)
        from vstudio import media
        n["take"] = os.path.abspath(take)
        n["take_sig"] = O.file_sig(take)
        n["end"] = round(min(end, start + float(media.probe(take).get("duration") or 0.0)), 3)
    lines = [dict(x) for x in op.get("lines") or [] if isinstance(x, dict)][:MAX_LINES]
    for x in lines:
        if x.get("start") is not None:
            x["start"] = O._src_time(x["start"], "start", op, tl, dur)
    if not lines and (op.get("text") or op.get("text_zh")):
        lines = _pair_lines(op.get("text"), op.get("text_zh") or op.get("text_zh_cn"))
        for x in lines:
            x["start"] = start
    if not lines and source == "tts":
        lines = write_lines(doc.rec, W, start, end, mode, op.get("ask"), langs)
    for x in lines:
        x.setdefault("start", start)
    if source == "take":                        # her recording: its lines are its captions, at their times
        placed = [dict(x, end=x.get("end") or n["end"]) for x in lines]
    else:
        placed = place(lines, W, start, end, warns, avoid=mode == "full")
    if source == "tts" and not placed:
        raise _err("voiceover-no-room", "there is no pause long enough for a voice-over without talking over the "
                   "speech", "没有足够长的停顿可以加旁白而不盖住原来的人声")
    n["lines"] = placed
    missing = [lg for lg in langs if source == "tts" and not any(line_text(x, lg) for x in placed)]
    if missing:
        warns.append(O.msg("voiceover-language", "the narration has no line in " + ", ".join(missing) + ": those "
                           "versions say it in the language written", "旁白缺少 " + "、".join(missing) +
                           " 的文字：这些版本用已写的语言说", langs=missing))
    given = {lg: v for lg, v in (op.get("voices") or {}).items() if isinstance(v, dict) and v.get("engine")} \
        if isinstance(op.get("voices"), dict) else {}
    if source == "tts" and given:                # a replayed op (the AI's proposal applied): its voices as cast
        n["voices"] = {lg: {k: v[k] for k in ("engine", "speaker", "style", "reason", "by") if v.get(k)}
                       for lg, v in given.items()}
    elif source == "tts":
        n["voices"] = cast_voices(doc.rec, [lg for lg in langs if any(line_text(x, lg) for x in placed)] or
                                  [("zh" if is_zh(placed[0].get("text") or placed[0].get("text_zh")) else "en")],
                                  ask=op.get("ask"), named=op.get("voice"))
    if mode == "intro" and W and _overlap(placed[0]["start"], placed[-1]["end"], speech_spans(W)) > 0.3:
        warns.append(O.msg("voiceover-over-speech", "the intro starts while you speak: your voice is ducked under it",
                           "开头旁白和你说话重叠：你的声音会被压低"))
    n["id"], n["seq"] = O._new_id(st, "vo")
    return n


def replayable(n):
    """A normalized voice-over as the op to apply (its written lines and cast voices kept: applying the AI's proposal
    says what the proposal said, no second writing / casting)."""
    keep = ("mode", "source", "start", "end", "lines", "voices", "take", "duck_db", "captions", "ask")
    return dict({k: n[k] for k in keep if n.get(k) is not None}, op="voiceover")


def describe(op):
    from .outputs import msg
    a, b = op["start"], (op["lines"][-1]["end"] if op.get("lines") else op["end"])
    sp = ", ".join(sorted({v.get("speaker") for v in (op.get("voices") or {}).values() if v.get("speaker")}))
    clock = lambda s: f"{int(s // 60)}:{int(s % 60):02d}"     # noqa: E731
    return msg("op-voiceover", f"Voice-over {clock(a)}–{clock(b)}" + (f" ({sp})" if sp else ""),
               f"旁白 {clock(a)}–{clock(b)}" + (f"（{sp}）" if sp else ""), start=a, end=b, mode=op["mode"],
               lines=len(op.get("lines") or []), speaker=sp or None, source=op.get("source"), id=op.get("id"))


# --------------------------------------------------------------------------- render: the track
def spec_for(vo, lang, tl):
    """One voice-over as a version in ``lang`` renders it (edited seconds) -> {lines [[a, b, text]], voice, ...} or
    None (nothing in that span is left after the cuts)."""
    lines, used = [], None
    for x in vo.get("lines") or []:
        txt = line_text(x, lang) or x.get("text") or x.get("text_zh") or ""
        sp = tl.span(x["start"], x["end"])
        if sp and str(txt).strip():
            lines.append([round(sp[0], 3), round(sp[1], 3), str(txt)])
            used = used or ("zh" if is_zh(txt) else "en")
    if not lines and vo.get("source") != "take":
        return None
    out = dict(id=vo["id"], source=vo.get("source") or "tts", lines=lines, duck_db=vo.get("duck_db", DUCK_DB),
               captions=vo.get("captions", True), lang=used or lang)
    if out["source"] == "tts":
        out["voice"] = (vo.get("voices") or {}).get(out["lang"]) or {}
    else:
        sp = tl.span(vo["start"], vo["end"])
        if not sp:
            return None
        out.update(take=vo["take"], take_sig=vo.get("take_sig"), at=round(sp[0], 3), until=round(sp[1], 3))
    return out


def _tts_line(v, text, wav, workdir, k):
    """A line said by the cast voice (Qwen3-TTS / Kokoro) -> its wav."""
    voice = v.get("voice") or {}
    if VOICE_HOOK is not None:
        return VOICE_HOOK(text, v["lang"], voice, wav)
    from vstudio import tts
    from vstudio import voicecast as VC
    eng = voice.get("engine")
    if eng == "qwen" and not tts.qwen_ready():
        eng = None
    eng = eng or VC.narration_engine(v["lang"])
    sp = voice.get("speaker") if voice.get("engine") == eng else None
    if not sp:
        sp = tts.zh_voice(eng) if v["lang"] == "zh" else tts.default_voice(eng)
    got = tts.synth(text, engine=eng, voice=sp, instructions=voice.get("style") if eng == "qwen" else None, out=wav)
    if got and got != wav:
        import shutil
        shutil.copy2(got, wav)
    return wav


def _tts_source(v, duration, workdir):
    """``tts``: each line synthesised and laid at its time (said up to 1.35x faster when it is longer than its slot)."""
    import numpy as np
    from vstudio import audio as A
    from vstudio import media as m
    n = int(round(max(duration, 0.5) * A.SR))
    x = np.zeros((n, 2), np.float32)
    lines = v["lines"]
    for k, (a, b, text) in enumerate(lines):
        wav = os.path.join(workdir, f"vo-{v['id']}-{k:03d}.wav")
        _tts_line(v, text, wav, workdir, k)
        y = A.decode_audio(wav, sr=A.SR, channels=2)
        nxt = lines[k + 1][0] if k + 1 < len(lines) else duration
        slot = max(0.3, nxt - a - 0.08)
        have = len(y) / A.SR
        if have > slot:
            fast = os.path.join(workdir, f"vo-{v['id']}-{k:03d}.fast.wav")
            m.run(["ffmpeg", "-y", "-i", wav, "-af", m.atempo_chain(min(1.35, have / slot)), "-ar", str(A.SR), fast])
            y = A.decode_audio(fast, sr=A.SR, channels=2)
        i0 = int(round(a * A.SR))
        if i0 < n:
            seg = y[: n - i0]
            x[i0: i0 + len(seg)] += seg
    return x


def _take_source(v, duration, workdir):
    """``take``: her recording laid from its start (cut at its end)."""
    import numpy as np
    from vstudio import audio as A
    n = int(round(max(duration, 0.5) * A.SR))
    x = np.zeros((n, 2), np.float32)
    y = A.decode_audio(v["take"], sr=A.SR, channels=2)
    i0 = int(round(v["at"] * A.SR))
    i1 = min(n, int(round(v["until"] * A.SR)))
    if i0 < i1:
        seg = y[: i1 - i0]
        x[i0: i0 + len(seg)] += seg
    return x


SOURCES = {"tts": _tts_source, "take": _take_source}


def active(x, sr, thresh=0.01):
    """Where the voice track sounds -> a 0/1 envelope (20 ms frames)."""
    import numpy as np
    mono = np.abs(x).max(axis=1) if x.ndim > 1 else np.abs(x)
    fr = max(1, int(0.02 * sr))
    k = len(mono) // fr
    env = np.zeros(len(mono), np.float32)
    if k:
        on = mono[: k * fr].reshape(k, fr).max(axis=1) > thresh
        env[: k * fr] = np.repeat(on.astype(np.float32), fr)
    return env


def duck_envelope(env, sr, duck_db, hold=0.25, ramp=0.12):
    """1.0 where the voice is silent, ``duck_db`` under it (held ``hold`` s across short pauses, ramped)."""
    import numpy as np
    on = env.copy()
    h = int(hold * sr)
    if h > 1 and on.any():
        on = (np.convolve(on, np.ones(h, np.float32), mode="same") > 0).astype(np.float32)
    g = 1.0 - on * (1.0 - 10 ** (float(duck_db) / 20.0))
    r = int(ramp * sr)
    if r > 1:
        g = np.convolve(np.pad(g, (r, r), mode="edge"), np.ones(r, np.float32) / r, mode="same")[r:-r]
    return g.astype(np.float32)


def mix_in(x, vos, duration, workdir):
    """The clip's sound ``x`` (n, 2) with every voice-over laid over it, the sound ducked under each -> (n, 2)."""
    import numpy as np
    from vstudio import audio as A
    out = x
    for v in vos:
        y = SOURCES[v["source"]](v, duration, workdir)
        if len(y) < len(out):
            y = np.pad(y, ((0, len(out) - len(y)), (0, 0)))
        y = y[: len(out)]
        g = duck_envelope(active(y, A.SR), A.SR, v.get("duck_db", DUCK_DB))
        out = out * g[:, None] + y
    return np.clip(out, -1.0, 1.0).astype(np.float32)


def read_take_lines(path):
    """The lines of a take's transcript next to it (``<take>.json`` {words}), if any - for her recording's captions."""
    j = read_json(os.path.splitext(path)[0] + ".json", None)
    return (j or {}).get("lines") if isinstance(j, dict) else None
