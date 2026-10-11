"""The useful end of a child process's output, for stage errors.

A failed render prints thousands of progress-bar redraws (``\\r``-separated), ``@hf-progress`` lines and JSON
trace records; a stage error built from "the last 1500 characters" then holds only progress bars and the real
reason (an ffmpeg / dyld / Python error line) is gone. :func:`tail` keeps the last ``n`` meaningful lines.

    from vstudio import proctail
    proctail.tail(stderr_text)            # -> "line\\nline\\n..." (<= 20 lines)
    proctail.is_noise("  45% |█████▌   | 120/300")  # True
"""
import os
import re

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
_NOISE = (
    re.compile(r"@hf-progress", re.I),
    re.compile(r"^\s*\[(INFO|DEBUG|TRACE)\]"),                       # hyperframes' structured log records
    re.compile(r"^\s*\{.*\"(phase|progress|elapsedMs|framesCompleted)\".*\}\s*$"),
    re.compile(r"[█▉▊▋▌▍▎▏░▒▓■□━─╸╺]{3,}"),                          # drawn bars
    re.compile(r"^\s*[\[(|]?[=#>\-. ]{6,}[\])|]?\s*\d{1,3}(\.\d+)?\s*%"),   # [=====>   ] 45%
    re.compile(r"^\s*\d{1,3}(\.\d+)?\s*%\s*([|\[(]|$)"),                # 45% |...
    re.compile(r"^\s*[⠁-⣿◐◓◑◒|/\\-]\s+\S.*\d+\s*/\s*\d+\s*$"),        # spinner + n/total
    re.compile(r"^\s*(frame|size)=\s*\d+.*(fps|time)=", re.I),       # ffmpeg -stats
    re.compile(r"^\s*(capturing|encoding|rendering)\b.*\d+\s*/\s*\d+", re.I),
    re.compile(r"^\s*\[initSession[:\]]"),                            # hyperframes per-worker session chatter
    re.compile(r"Keep editing by chatting|hyperframes\.dev/studio/download"),
)


def is_noise(line):
    s = _ANSI.sub("", line or "").strip()
    return not s or any(rx.search(s) for rx in _NOISE)


def lines(text):
    """Text -> clean lines (ANSI removed, a ``\\r`` redraw keeps only its last state)."""
    out = []
    for ln in str(text or "").replace("\r\n", "\n").split("\n"):
        if "\r" in ln:
            ln = next((p for p in reversed(ln.split("\r")) if p.strip()), "")
        out.append(_ANSI.sub("", ln).rstrip())
    return out


def tail(text, n=20, max_chars=2000):
    """The last ``n`` meaningful lines of ``text`` (progress / trace noise and blank lines removed), joined."""
    keep = [ln for ln in lines(text) if not is_noise(ln)]
    # a repeated line (the same warning per frame) counts once
    dedup = []
    for ln in keep:
        if not dedup or dedup[-1] != ln:
            dedup.append(ln)
    s = "\n".join(dedup[-n:])
    return s[-max_chars:] if len(s) > max_chars else s


def clean_error(msg, n=20, max_chars=2000):
    """A stage error ``"<head>: <captured output>"`` -> the head + the meaningful tail of the output."""
    s = str(msg or "")
    first, _, rest = s.partition("\n")
    head, sep, body = first.partition(": ")
    if not sep:
        head, body = "", first
    t = tail(body + "\n" + rest, n, max_chars)
    if not head:
        return t
    if not t:
        return f"{head}: (no error output)"
    return f"{head}:\n{t}" if "\n" in t else f"{head}: {t}"


# missing / broken external tools a stage needs (Node.js for HyperFrames, ffmpeg): code + params for the desk
_TOOLS = (
    ("node", re.compile(r"node unavailable|referenced from:\s*\S*/node\b|library not loaded\S*.*\bnode\b|"
                        r"npx \(node\) not found|env: node: no such file|node(\.js)? \S* ?is too old", re.I | re.S)),
    ("ffmpeg", re.compile(r"ffmpeg not found|ffprobe not found|vstudio_ff(mpeg|probe)=\S* does not exist|"
                          r"lacks filter\(s\)|unknown bitstream filter|no such file or directory: '?\S*ff(mpeg|probe)'|"
                          r"referenced from:\s*\S*/ff(mpeg|probe)\b|ff(mpeg|probe): (command )?not found", re.I)),
)


# failures with a known cause and a known fix the app can word ("the script wasn't in lines - draft it for me")
_KNOWN = ((re.compile(r"no '## Line N' blocks in SCRIPT\.md|SCRIPT\.md is not in the script format"),
           "stage-script-format", "draft-script"),)


# the app's free voice (Kokoro) before its one-time download (vstudio.tts.VoiceNotDownloaded): the desk offers it
_VOICE_MISSING = re.compile(r"free voice is not downloaded", re.I)


def voice_failure(text):
    """The free voice not downloaded yet -> {code: "tool-voice", params: {tool: "voice", fix: "download-voice"}}."""
    if _VOICE_MISSING.search(str(text or "")):
        return dict(code="tool-voice", params=dict(tool="voice", fix="download-voice"))
    return None


# the explainer's voice step (workflows/explainer/scripts/tts.py): every take of a line left out a sentence ->
# "TTS dropped sentences after retries (...):\n  line 02: ['地基先打好：Tool Calling。']" (one row per line)
_VOICE_DROPPED = re.compile(r"TTS dropped sentences after retries")
_DROPPED_ROW = re.compile(r"^\s*line (\d+): \[(.*)\]\s*$", re.M)
_QUOTED = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"")


def voice_dropped(text):
    """The voice kept leaving out a sentence -> {code: "stage-voice-dropped", params: {line (scene number), sentence
    (the first one left out), lines (how many scenes), fix: "rephrase-line"}}; else None."""
    t = str(text or "")
    m = _VOICE_DROPPED.search(t)
    if not m:
        return None
    rows = _DROPPED_ROW.findall(t[m.end():])
    if not rows:
        return dict(code="stage-voice-dropped", params=dict(fix="rephrase-line"))
    n, quoted = rows[0]
    q = _QUOTED.search(quoted)
    sentence = (q.group(1) if q and q.group(1) is not None else q.group(2) if q else quoted).strip()
    sentence = sentence.rstrip("。．.！!？?；; ")             # the words' own end mark: the message adds its own
    if len(sentence) > 80:
        sentence = sentence[:79].rstrip() + "…"
    return dict(code="stage-voice-dropped",
                params=dict(line=str(int(n)), sentence=sentence, lines=str(len(rows)), fix="rephrase-line"))


# a paid service without its key (vstudio.tts.MissingKey "No OpenAI key: OPENAI_API_KEY is not set ...", or an older
# "OPENAI_API_KEY is not set in the environment"): the service by name, never the env var / a traceback
_KEY_MISSING = re.compile(r"\bNo ([A-Za-z][\w .-]{1,30}?) key: ([A-Z][A-Z0-9_]*_API_KEY) is not set|"
                          r"\b([A-Z][A-Z0-9]*)_API_KEY is not set")
_SERVICES = {"OPENAI": "OpenAI", "ELEVENLABS": "ElevenLabs", "GEMINI": "Gemini", "HEDRA": "Hedra",
             "ANTHROPIC": "Anthropic", "FAL": "fal", "REPLICATE": "Replicate", "KLING": "Kling"}


def key_failure(text):
    """A missing API key -> {code: "ai-key-missing", params: {service, fix}} (fix: free-voice when the message offers
    the free local voice - Try again takes it - else add-key); else None."""
    t = str(text or "")
    m = _KEY_MISSING.search(t)
    if not m:
        return None
    service = m.group(1) or _SERVICES.get(m.group(3) or "", (m.group(3) or "").title())
    free = re.search(r"or use the free local voice", t, re.I)
    return dict(code="ai-key-missing", params=dict(service=service, fix="free-voice" if free else "add-key"))


# an ffmpeg failure the app itself caused: a filter / encoder / option the ffmpeg it runs does not have (a GPL filter
# on the bundled LGPL build), a graph it built wrong. Never "a file couldn't be read": nothing she can fix.
APP_BUG = re.compile(r"no such filter|filter not found|unknown encoder|encoder not found|unrecognized option|"
                     r"option not found|error (initializing|reinitializing|parsing) (a )?filter|error applying option|"
                     r"invalid filter ?graph|failed to (configure|inject) (the )?(output|input) (pad|filter)|"
                     r"error parsing (a )?filter ?(chain|graph)|error binding filtergraph", re.I)
_APP_BUG_NAMED = re.compile(r"no such filter|unknown encoder|encoder not found|unrecognized option|option not found", re.I)
# ffmpeg could not open / read one input: "<path>: <why>" (ffmpeg <= 6), "Error opening input file <path>." (7+)
_IO_WHY = (r"No such file or directory|Invalid data found when processing input|Permission denied|"
           r"Input/output error|Operation not permitted|moov atom not found|End of file")
_IO_PATH = (re.compile(rf"^\s*(?:\[[^\]]*\]\s*)?(?P<path>[^\[\n]+?): (?:{_IO_WHY})\s*$", re.I | re.M),
            re.compile(r"Error opening input file (?P<path>.+?)\.?\s*$", re.I | re.M),
            re.compile(r"(?:No such file or directory|Permission denied|Input/output error): '(?P<path>[^']+)'", re.I))
_FF_CONTEXT = re.compile(r"ff(mpeg|probe)|error opening input|invalid data found|moov atom", re.I)
_MEDIA_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mts", ".m2ts", ".insv", ".lrv", ".webm", ".mxf", ".3gp",
              ".wav", ".mp3", ".m4a", ".aac", ".flac", ".aif", ".aiff", ".ogg", ".opus", ".caf",
              ".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff", ".dng", ".gif"}
_IO = re.compile(rf"{_IO_WHY}|error opening input|could not open|moov atom", re.I)


def cause(text):
    """The line that says why an ffmpeg run failed (an APP_BUG line, else an open / IO error line), or ""."""
    lns = [ln.strip() for ln in lines(text) if ln.strip()]
    for rx in (_APP_BUG_NAMED, APP_BUG, _IO):
        hit = next((ln for ln in reversed(lns) if rx.search(ln)), None)
        if hit:
            return hit
    return ""


def _volume_of(path):
    """(volume name, mounted?) for a path on an external drive (/Volumes/<name>/..., /media/<user>/<name>/...)."""
    m = re.match(r"^/Volumes/([^/]+)/", path) or re.match(r"^/(?:media|run/media)/[^/]+/([^/]+)/", path)
    if not m:
        return None, True
    root = path[:m.end() - 1]
    return m.group(1), os.path.ismount(root) or os.path.isdir(root)


def media_failure(text):
    """ffmpeg could not open / read an input -> {code: "media-unmounted" (the drive it is on is not connected) |
    "media-unreadable", params: {file (base name), volume}}; else None. Only real open / IO errors count: a filter or
    encoder error is APP_BUG, never this."""
    t = str(text or "")
    if APP_BUG.search(t):
        return None
    # an output it could not write (a folder that is gone) is not her footage
    t = "\n".join(ln for ln in t.splitlines() if not re.search(r"\boutput\b", ln, re.I))
    if not _IO.search(t):
        return None
    path = None
    for rx in _IO_PATH:
        for m in rx.finditer(t):
            p = m.group("path").strip().strip("'\"")
            if p.startswith(("/", "~")) or re.match(r"^[A-Za-z]:[\\/]", p) or "." in os.path.basename(p):
                path = p
    is_media = bool(path) and os.path.splitext(path)[1].lower() in _MEDIA_EXT
    if not (_FF_CONTEXT.search(t) or is_media):
        return None                        # a script's own missing file (a config, a json): not her footage
    if path and not is_media and os.path.basename(path).lower().startswith(("ffmpeg", "ffprobe")):
        return None
    if not path:
        return dict(code="media-unreadable", params={})
    vol, mounted = _volume_of(path)
    params = dict(file=os.path.basename(path))
    if vol:
        params["volume"] = vol
    return dict(code="media-unreadable" if mounted else "media-unmounted", params=params)


def tool_failure(text):
    """An error caused by a missing / broken external tool -> {code: "tool-node" | "tool-ffmpeg",
    params: {tool, fix}}; a missing API key -> key_failure(); the free voice not downloaded -> voice_failure(); a voice that kept leaving out a sentence ->
    voice_dropped(); a known stage failure -> {code: "stage-script-format", params: {fix}}; an ffmpeg error the
    app caused (APP_BUG: no such filter / unknown encoder ...) -> {code: "app-bug", params: {}}; ffmpeg could not
    open / read an input -> media_failure(); else None.
    fix: brew-reinstall-node | install-node | reinstall-app | install-ffmpeg | draft-script | download-voice |
    rephrase-line."""
    t = str(text or "")
    low = t.lower()
    key = key_failure(t) or voice_failure(t) or voice_dropped(t)
    if key:
        return key
    for rx, code, fix in _KNOWN:
        if rx.search(t):
            return dict(code=code, params=dict(fix=fix))
    if APP_BUG.search(t):
        return dict(code="app-bug", params={})
    for tool, rx in _TOOLS:
        if rx.search(t):
            if tool == "node":
                brew = ("homebrew" in low or "/cellar/" in low or "brew reinstall" in low) and "too old" not in low
                fix = "brew-reinstall-node" if brew else "install-node"
            else:
                bundled = "reelfold.app" in low or "/runtime/ffmpeg" in low or "vstudio_ff" in low
                fix = "reinstall-app" if bundled else "install-ffmpeg"
            return dict(code=f"tool-{tool}", params=dict(tool=tool, fix=fix))
    return media_failure(t)
