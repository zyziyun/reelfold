"""Text-to-speech with a content-addressed cache.

    from vstudio import tts
    wav = tts.synth("Welcome back.", engine="openai", voice="cedar", out="audio/vo/line01.wav")
    wav = tts.synth("Repeat after me.", engine="kokoro", speed=0.85)       # Apple Silicon, offline
    tts.pick_engine()                                                       # first available

Engines (all optional imports, nothing is needed until you call one):
  openai  gpt-4o-mini-tts (supports ``instructions`` = delivery direction). Key from the
          OPENAI_API_KEY environment variable ONLY. ``openai`` package if installed, else plain HTTPS.
  kokoro  Kokoro-82M via ``mlx_audio`` (Apple Silicon, offline): the free English voice.
  qwen    Qwen3-TTS 1.7B CustomVoice via ``mlx_audio`` (Apple Silicon, offline, Apache-2.0): the free Chinese voice -
          native Mandarin speakers (serena, vivian, uncle_fu, dylan = Beijing, eric = Sichuan; ``QWEN_ZH_VOICES``),
          tones / polyphones / English terms read by the model itself. A Chinese line meant for the free voice goes
          here (``zh_engine``); the Kokoro Mandarin voice (zf_xiaobei) is only used when asked for by name.
          One take per child process (vstudio.qwen_synth); ``qwen_model()`` like ``kokoro_model()``.
  edge    Microsoft Edge neural voices via ``edge_tts`` (needs network, no key). Unofficial: it talks to the Read
          Aloud service of Microsoft's Edge browser, which is not a public API (no terms for other apps; it has gone
          down for days at a time, e.g. 403 since 2026-10-10) - for your own use, opt in by name; never the default
          and not in the desk app (edge-tts is LGPL).
  clone   your OWN voice, cloned from a short reference recording: Qwen3-TTS (Base) via ``mlx_audio``
          (Apple Silicon, offline). Needs ``ref_wav`` (5-15 s of clean speech) + ``ref_text`` (its exact
          transcript), passed as arguments or set in persona.local.yaml (never commit the recording):
              tts:
                clone:
                  ref_wav: ~/voice/ref.wav
                  ref_text: "exact words spoken in ref.wav"
                  model: mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16    # optional
                  language: English                                     # optional (auto from text)
          ``seed`` makes a take reproducible; retries with different seeds = different takes. The loaded
          model stays in memory for the process. Cache key includes a hash of the reference audio + text.
  openai-compatible  any self-hosted ``/v1/audio/speech`` server (Kokoro-FastAPI, openedai-speech, LocalAI, ...):
          env VSTUDIO_TTS_BASE_URL or persona ``tts.server.base_url``, optional ``api_key_env`` (env var NAME),
          ``model``, ``voice`` (persona ``tts.server.*``; env VSTUDIO_TTS_API_KEY_ENV / VSTUDIO_TTS_MODEL).
  elevenlabs  ElevenLabs API (optional): ELEVENLABS_API_KEY from the environment ONLY; voice = a voice id
          (persona ``tts.elevenlabs_voice``), model eleven_multilingual_v2; speed 0.7-1.2.
"auto" = persona ``tts.engine`` / env VSTUDIO_TTS_ENGINE, else kokoro (Apple Silicon) -> edge -> openai.
Chinese text on the free voice: ``zh_engine("kokoro")`` -> "qwen" when it is ready here (``qwen_ready``).
``available_engine()`` is the voice a plan defaults to (the explainer): persona ``tts.engine``, else a paid engine
only when its key is set, else the free local voice (``local_engine()``). A paid engine without its key raises
``MissingKey`` (a plain message naming the service and the fix); ``missing_key(engine)`` says so beforehand.
``providers()`` (and ``python -m vstudio.llm providers``) lists what works on this machine.
Output is always 48 kHz mono 16-bit wav. Cache: ``$VSTUDIO_CACHE/tts/<sha1>.wav`` keyed by
engine+model+voice+speed+instructions+text, so re-running a script never pays twice.
Voice defaults: persona ``tts.<engine>_voice`` else DEFAULT_VOICE; for Chinese text ``zh_voice(engine)`` (persona
``tts.<engine>_voice_zh`` else ZH_VOICE; the app's Settings > Voice choice comes first for qwen: the JSON file at env
VSTUDIO_TTS_PREFS, ``{"zh_voice": "vivian"}``, read on every call). Kokoro voices carry their language in the prefix (``zf_xiaobei`` =
Mandarin, ``af_heart`` = US English, ``jf_alpha`` = Japanese ...) and it is passed on as Kokoro's ``lang_code``;
Mandarin needs ``pip install "misaki[zh]"``, English ``misaki[en]``.
Kokoro's model: ``kokoro_model()`` = env VSTUDIO_KOKORO_MODEL (a local folder: config.json, kokoro-v1_0.safetensors,
voices/<id>.safetensors - the desk app downloads one, see apps/desk/packaging/assets.json ``tts-kokoro``), else persona
``tts.kokoro_model``, else the Hugging Face repo DEFAULT_MODEL["kokoro"] (mlx-audio downloads it). With a local folder
nothing is fetched; a voice it lacks is an error naming the voices it has. VSTUDIO_TTS_MODELS_MANAGED=1 (the app): the
voice is never fetched by the engine - without VSTUDIO_KOKORO_MODEL it raises ``VoiceNotDownloaded``.
Without espeak-ng (the app's runtime: GPL, not bundled) an English word missing from misaki's dictionaries is spelled
from its known pieces / letters (vstudio.kokoro_g2p.SpellFallback). A Mandarin voice reads the English terms of a
中文讲解 (MCP, Tool Calling, API) with misaki's English G2P, acronyms letter by letter (vstudio.kokoro_g2p).
``split_in_two(text)`` / ``synth_split(...)``: a line a voice fails on, said as two takes joined by a short pause (the
explainer's voice stage retries a failed line this way once before it stops, naming the line).
Unified from preproduction ``make_drill.tts/pick_engine/to_wav``, explainer ``tts.py`` (urllib
OpenAI call with per-line direction), photo-story ``tts.main.synth`` (cache by text+voice+instructions).
"""
import asyncio
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from . import media

DEFAULT_VOICE = {"openai": "cedar", "kokoro": "af_heart", "edge": "en-US-AriaNeural", "clone": "ref",
                 "openai-compatible": "af_heart", "elevenlabs": "21m00Tcm4TlvDq8ikWAM", "qwen": "serena", "system": "Tingting"}
DEFAULT_MODEL = {"openai": "gpt-4o-mini-tts", "kokoro": "mlx-community/Kokoro-82M-bf16", "edge": None,
                 "qwen": "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
                 "clone": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16", "openai-compatible": "kokoro",
                 "elevenlabs": "eleven_multilingual_v2", "system": None}
# Chinese voices (中文讲解); openai's voices are multilingual, clone speaks like its reference
ZH_VOICE = {"kokoro": "zf_xiaobei", "edge": "zh-CN-XiaoxiaoNeural", "openai": "cedar", "openai-compatible": None,
            "elevenlabs": None, "clone": None, "qwen": "serena", "system": "Tingting"}
# the free Chinese voice's Mandarin speakers (Settings > Voice; samples in apps/desk resources)
QWEN_ZH_VOICES = ("serena", "vivian", "uncle_fu", "dylan", "eric")
KOKORO_LANGS = "abefhijpz"          # Kokoro's lang codes = the first letter of its voice ids
ENGINES = ("openai", "kokoro", "qwen", "edge", "clone", "openai-compatible", "elevenlabs", "system")
ALIASES = {"compatible": "openai-compatible", "tts-server": "openai-compatible", "eleven": "elevenlabs",
           "11labs": "elevenlabs", "edge-tts": "edge", "qwen3-clone": "clone", "qwen3": "qwen", "qwen3-tts": "qwen",
           "qwen-tts": "qwen"}
LANG_NAMES = {"en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "de": "German", "fr": "French",
              "es": "Spanish", "it": "Italian", "pt": "Portuguese", "ru": "Russian"}
_CLONE_MODELS = {}
SR = 48000
# engines that need a key (env var the app fills from the keychain) and the service it is for
KEY_ENV = {"openai": "OPENAI_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}
SERVICE = {"openai": "OpenAI", "elevenlabs": "ElevenLabs"}
KOKORO_MODEL_ENV = "VSTUDIO_KOKORO_MODEL"      # a local Kokoro folder (the desk app's download)
QWEN_MODEL_ENV = "VSTUDIO_QWEN_TTS_MODEL"      # a local Qwen3-TTS folder (the desk app's download, tts-qwen-zh)
QWEN_OFF_ENV = "VSTUDIO_QWEN_TTS"            # "off": the free Chinese voice is never used (tests; a creator's choice)
PREFS_ENV = "VSTUDIO_TTS_PREFS"               # the app's voice choices (Settings > Voice): {"zh_voice", "zh_local"}
MANAGED_ENV = "VSTUDIO_TTS_MODELS_MANAGED"     # the app downloads voice models; the engine never fetches them


class MissingKey(RuntimeError):
    """A paid engine without its key: the message names the service and the fix (proctail words it for the app).
    ``free``: a free voice is installed here (the message offers it), else adding the key is the way."""

    def __init__(self, engine, free=True):
        self.engine, self.env, self.service = engine, KEY_ENV.get(engine, ""), SERVICE.get(engine, engine)
        self.free = bool(free)
        super().__init__(f"No {self.service} key: {self.env} is not set. Add your {self.service} key in Settings > AI"
                         + (", or use the free local voice." if free else
                            " (no free voice is installed on this computer)."))


class VoiceNotDownloaded(RuntimeError):
    """The app's free voice (Kokoro) - or its Chinese voice (Qwen3-TTS, ``chinese=True``) - is not downloaded yet: the
    desk offers the download (vstudio.proctail.voice_failure)."""

    def __init__(self, chinese=False):
        self.chinese = bool(chinese)
        super().__init__("The free Chinese voice is not downloaded yet: download it in Settings > Voice, then try "
                         "again." if chinese else "The free voice is not downloaded yet: download it in Settings > "
                         "Downloads (Free voice), then try again.")


def _cache_dir():
    try:
        from .config import CACHE
    except Exception:
        CACHE = os.path.expanduser("~/.cache/video-studio")
    d = os.path.join(CACHE, "tts")
    os.makedirs(d, exist_ok=True)
    return d


def _tts_cfg():
    try:
        from .config import persona
        return persona().get("tts") or {}
    except Exception:  # noqa: BLE001
        return {}


def server_config():
    """The openai-compatible TTS server: dict(base_url, api_key_env, model, voice) from env / persona tts.server."""
    c = _tts_cfg().get("server") or {}
    return dict(base_url=os.environ.get("VSTUDIO_TTS_BASE_URL") or c.get("base_url"),
                api_key_env=os.environ.get("VSTUDIO_TTS_API_KEY_ENV") or c.get("api_key_env"),
                model=os.environ.get("VSTUDIO_TTS_MODEL") or c.get("model"), voice=c.get("voice"))


def pick_engine(name="auto"):
    """Engine to use: ``name`` unless "auto" -> persona ``tts.engine`` / env VSTUDIO_TTS_ENGINE -> kokoro (Apple
    Silicon + mlx_audio) -> edge -> openai (OPENAI_API_KEY set). Raises RuntimeError if none. From preproduction
    ``make_drill.pick_engine``."""
    name = ALIASES.get(str(name or "auto").lower(), str(name or "auto").lower())
    if name == "auto":
        conf = os.environ.get("VSTUDIO_TTS_ENGINE") or _tts_cfg().get("engine")
        if conf and str(conf).lower() != "auto":
            name = ALIASES.get(str(conf).lower(), str(conf).lower())
    if name != "auto":
        return name
    if platform.system() == "Darwin" and platform.machine() == "arm64" and importlib.util.find_spec("mlx_audio"):
        return "kokoro"
    if importlib.util.find_spec("edge_tts") or shutil.which("edge-tts"):
        return "edge"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    raise RuntimeError("no TTS engine: pip install mlx-audio (Apple Silicon) | edge-tts | openai (+OPENAI_API_KEY)")


def missing_key(engine):
    """The env var a paid ``engine`` needs and does not have (None: no key needed, or it is set)."""
    env = KEY_ENV.get(ALIASES.get(str(engine or "").lower(), str(engine or "").lower()))
    return env if env and not os.environ.get(env) else None


def _persona_engine():
    conf = os.environ.get("VSTUDIO_TTS_ENGINE") or _tts_cfg().get("engine")
    if conf and str(conf).lower() != "auto":
        return ALIASES.get(str(conf).lower(), str(conf).lower())
    return None


LOCAL = ("kokoro", "qwen", "clone", "edge")      # free voices (edge: Microsoft's online voices, no key)


def installed(engine):
    """Can ``engine`` run here at all (its package is installed; a key is ``missing_key``'s business)?"""
    if engine in ("kokoro", "clone", "qwen"):
        return platform.system() == "Darwin" and platform.machine() == "arm64" and \
            bool(importlib.util.find_spec("mlx_audio"))
    if engine == "system":
        from .system_voice import chinese_voices
        return bool(chinese_voices())
    if engine == "edge":
        return bool(importlib.util.find_spec("edge_tts") or shutil.which("edge-tts"))
    return True


def kokoro_ready():
    """Kokoro's model is here or may be fetched on use (False only in the app before its download)."""
    return os.path.isdir(kokoro_model()) or not os.environ.get(MANAGED_ENV)


def qwen_model(model=None):
    """Qwen3-TTS model: ``model`` > env VSTUDIO_QWEN_TTS_MODEL > persona ``tts.qwen_model`` > DEFAULT_MODEL (HF repo)."""
    m = str(model or os.environ.get(QWEN_MODEL_ENV) or _tts_cfg().get("qwen_model") or DEFAULT_MODEL["qwen"])
    return os.path.expanduser(m) if m.startswith("~") else m


def qwen_ready():
    """The free Chinese voice can speak here: Apple Silicon + mlx-audio, and its model is on disk or may be fetched on
    use (False in the app before its download). env VSTUDIO_QWEN_TTS=off: never (Kokoro's rules as before)."""
    if os.environ.get(QWEN_OFF_ENV, "").strip().lower() in ("off", "0", "false", "no"):
        return False
    return installed("qwen") and (os.path.isdir(qwen_model()) or not os.environ.get(MANAGED_ENV))


def zh_engine(engine):
    """The engine that says a Chinese line meant for ``engine``: the free voice (kokoro) -> qwen when it is ready here
    (Kokoro's Mandarin sounds robotic); any other engine speaks Chinese itself."""
    e = ALIASES.get(str(engine or "").lower(), str(engine or "").lower())
    if prefs().get("zh_engine") == "system":
        return "system"
    return "qwen" if e == "kokoro" and qwen_ready() else e


def local_engine():
    """The free voice installed here: kokoro (Apple Silicon + mlx-audio), else edge (edge-tts); None = none is."""
    return next((e for e in ("kokoro", "edge") if installed(e)), None)


def available_engine(name="auto"):
    """The voice a plan defaults to: ``name`` unless "auto" -> persona ``tts.engine`` / VSTUDIO_TTS_ENGINE -> openai
    when OPENAI_API_KEY is set -> the free local voice. Never a paid engine without its key."""
    name = ALIASES.get(str(name or "auto").lower(), str(name or "auto").lower())
    if name != "auto":
        return name
    # nothing free installed and no key: kokoro by name (free; the voice step says what is missing, never a charge)
    return _persona_engine() or ("openai" if not missing_key("openai") else local_engine() or "kokoro")


def providers(probe=True):
    """[{provider, kind, ready, detail}] for every TTS engine on this machine (nothing is synthesised)."""
    mac_arm = platform.system() == "Darwin" and platform.machine() == "arm64"
    mlx = bool(importlib.util.find_spec("mlx_audio"))
    edge = bool(importlib.util.find_spec("edge_tts") or shutil.which("edge-tts"))
    try:
        clone_ok, clone_d = True, "reference set in persona tts.clone"
        clone_config()
    except RuntimeError:
        clone_ok, clone_d = False, "needs persona tts.clone.ref_wav + ref_text"
    rows = [dict(provider="openai", kind="api", ready=bool(os.environ.get("OPENAI_API_KEY")),
                 detail="gpt-4o-mini-tts, key set" if os.environ.get("OPENAI_API_KEY") else "needs OPENAI_API_KEY"),
            dict(provider="kokoro", kind="local", ready=mac_arm and mlx and kokoro_ready(),
                 detail=("pip install mlx-audio (Apple Silicon)" if not (mac_arm and mlx) else
                         f"mlx-audio Kokoro-82M, {kokoro_model()}" if kokoro_ready() else
                         "mlx-audio Kokoro-82M, not downloaded yet (Settings > Downloads)")),
            dict(provider="qwen", kind="local", ready=qwen_ready(),
                 detail=("pip install mlx-audio (Apple Silicon)" if not (mac_arm and mlx) else
                         f"mlx-audio Qwen3-TTS (Chinese voice), {qwen_model()}" if qwen_ready() else
                         "mlx-audio Qwen3-TTS (Chinese voice), not downloaded yet (Settings > Voice)")),
            dict(provider="edge", kind="api (no key)", ready=edge,
                 detail=("edge-tts (Microsoft's Edge read-aloud voices, unofficial: may stop working)" if edge else
                         "pip install edge-tts (unofficial Microsoft online voices, opt-in)")),
            dict(provider="clone", kind="local", ready=mac_arm and mlx and clone_ok,
                 detail=("mlx-audio Qwen3-TTS; " if mac_arm and mlx else "needs mlx-audio (Apple Silicon); ") + clone_d),
            dict(provider="elevenlabs", kind="api", ready=bool(os.environ.get("ELEVENLABS_API_KEY")),
                 detail="key set" if os.environ.get("ELEVENLABS_API_KEY") else "needs ELEVENLABS_API_KEY (optional)")]
    rows.append(dict(provider="system", kind="local", ready=installed("system"),
                     detail="Installed macOS Chinese voices (offline)"))
    sc = server_config()
    if sc["base_url"]:
        up = False
        if probe:
            from .llm import _probe_url
            up = _probe_url(sc["base_url"].rstrip("/") + "/models", strict=False)[0] or \
                _probe_url(sc["base_url"].rstrip("/") + "/audio/voices", strict=False)[0]
        rows.append(dict(provider="openai-compatible", kind="local", ready=up,
                         detail=f"{sc['base_url']}: " + ("up" if up else "no server answering" if probe else "not probed")))
    else:
        rows.append(dict(provider="openai-compatible", kind="local", ready=False,
                         detail="set VSTUDIO_TTS_BASE_URL (Kokoro-FastAPI, openedai-speech, LocalAI, ...)"))
    return rows


def default_voice(engine="auto"):
    """The voice ``synth`` uses for ``engine`` when none is passed (persona tts.<engine>_voice, else
    DEFAULT_VOICE) - for logging. engine "auto" resolves through ``pick_engine``."""
    return _voice(pick_engine(engine), None)


# ---------------------------------------------------------------------------------------- Chinese narration policy
# A Chinese version is narrated in Chinese by a natural voice: the free Chinese voice (Qwen3-TTS, once it is on this
# computer - it IS the better voice, so a downloaded Qwen3-TTS narrates by default), OpenAI with its key, the
# creator's cloned voice, a voice she set in her persona, a TTS server. Kokoro's Mandarin (zf_*) sounds robotic: only
# when she switched it on (Settings > Voice, persona tts.zh_local: true) and Qwen3-TTS is not here. Without any of
# them, English narration with Chinese subtitles leading (or no voice at all for a mood / scenery piece), and the plan
# card offers the Chinese voice's download (intake.plan.voice_risks).
ZH_LOCAL_ENV = "VSTUDIO_ZH_LOCAL_VOICE"
ZH_LOCAL_NOTE = {
    "en": "The free Chinese voice is not on this computer yet, so the Chinese version uses English narration with "
          "Chinese subtitles. Download it in Settings > Voice (about 3 GB, Apple silicon) for natural Chinese "
          "narration, or add an OpenAI key or your own cloned voice.",
    "zh": "免费的中文配音还没下载到这台电脑，所以中文版先用英文旁白 + 中文字幕。在「设置 > 配音」下载它（约 3 GB，"
          "Apple 芯片），就能有自然的中文旁白；也可以添加 OpenAI 密钥，或克隆自己的声音。"}


def _truthy(v):
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "on")


def zh_local_opt_in():
    """She asked for Kokoro's Mandarin voice anyway (used only while the free Chinese voice is not downloaded): the
    switch in Settings > Voice (``prefs()["zh_local"]``), env VSTUDIO_ZH_LOCAL_VOICE=1, persona ``tts.zh_local: true``
    or ``voice.zh_local: true``."""
    if _truthy(prefs().get("zh_local")):
        return True
    if _truthy(os.environ.get(ZH_LOCAL_ENV, "")):
        return True
    if _truthy(_tts_cfg().get("zh_local")):
        return True
    try:
        from .config import persona
        return _truthy((persona().get("voice") or {}).get("zh_local"))
    except Exception:  # noqa: BLE001
        return False


def zh_voice_engine(engine="auto"):
    """The engine that would read a Chinese narration well enough to use it by default, or None (then: English
    narration with Chinese subtitles). The free voice -> the free Chinese voice (qwen) when it is ready here, else
    Kokoro's Mandarin only when ``zh_local_opt_in``; OpenAI with its key, ElevenLabs with its key, a cloned voice with
    its reference, a TTS server, Microsoft's online voices (edge) -> that engine. An engine that cannot run here (no
    key, no reference, the Chinese voice not downloaded) -> None."""
    e = available_engine(engine)
    if prefs().get("zh_engine") == "system":
        return "system"  # explicit choice: an unavailable voice must fail clearly, never switch language
    if e in ("kokoro", "qwen"):
        if qwen_ready():
            return "qwen"
        return "kokoro" if e == "kokoro" and zh_local_opt_in() else None
    if missing_key(e):
        return None
    if e == "clone":
        try:
            clone_config()
        except RuntimeError:
            return None
    if e == "openai-compatible" and not server_config().get("base_url"):
        return None
    return e


def zh_narration_ok(engine="auto"):
    """True when a Chinese version may be narrated in Chinese (``zh_voice_engine`` found a voice for it)."""
    return zh_voice_engine(engine) is not None


def prefs():
    """The app's voice choices (Settings > Voice): the JSON file at env VSTUDIO_TTS_PREFS, {} when none."""
    f = os.environ.get(PREFS_ENV)
    if not f:
        return {}
    try:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def zh_voice(engine):
    """The Chinese voice of ``engine``: for qwen the app's choice (``prefs()["zh_voice"]``, one of QWEN_ZH_VOICES)
    first; then persona tts.<engine>_voice_zh, else ZH_VOICE; None = the engine's default."""
    if engine == "system":
        return prefs().get("system_voice") or ZH_VOICE["system"]
    if engine == "qwen":
        v = str(prefs().get("zh_voice") or "").lower()
        if v in QWEN_ZH_VOICES:
            return v
    v = (_tts_cfg() or {}).get(f"{engine}_voice_zh")
    return v or ZH_VOICE.get(engine)


def kokoro_model(model=None):
    """Kokoro model: ``model`` > env VSTUDIO_KOKORO_MODEL > persona ``tts.kokoro_model`` > DEFAULT_MODEL (HF repo)."""
    m = model or os.environ.get(KOKORO_MODEL_ENV) or _tts_cfg().get("kokoro_model") or DEFAULT_MODEL["kokoro"]
    m = str(m)
    return os.path.expanduser(m) if m.startswith("~") else m


def kokoro_voices(model=None):
    """Voice ids a local Kokoro folder has (sorted); None for a Hugging Face repo (any voice, fetched on use)."""
    d = kokoro_model(model)
    if not os.path.isdir(d):
        return None
    try:
        return sorted(f[:-len(".safetensors")] for f in os.listdir(os.path.join(d, "voices"))
                      if f.endswith(".safetensors"))
    except OSError:
        return []


def kokoro_lang(voice):
    """Kokoro's lang_code for a voice id ("zf_xiaobei" -> "z"); None when the id has no language prefix."""
    v = os.path.basename(str(voice or ""))
    return v[0] if len(v) > 3 and v[0] in KOKORO_LANGS and v[1] in "fm" and v[2] == "_" else None


def _voice(engine, voice):
    if voice:
        return voice
    if engine == "system":
        return zh_voice("system")
    try:
        from .config import persona
        v = (persona().get("tts") or {}).get(f"{engine}_voice")
    except Exception:
        v = None
    if not v and engine == "openai-compatible":
        v = server_config()["voice"]
    return v or DEFAULT_VOICE[engine]


def cache_key(text, engine, voice, speed, instructions, model):
    return hashlib.sha1(json.dumps([engine, model, voice, round(float(speed), 4), instructions or "", text],
                                   ensure_ascii=False).encode()).hexdigest()


def _speech_http(url, body, headers, dst, timeout=300):
    from . import ai_consent
    ai_consent.require(url, "speech")
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=dict(headers, **{
        "Content-Type": "application/json"}))
    with ai_consent.urlopen(req, timeout=timeout) as r, open(dst, "wb") as f:
        f.write(r.read())


def _openai(text, voice, speed, instructions, model, dst):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise MissingKey("openai", free=local_engine() is not None)
    body = {"model": model, "voice": voice, "input": text, "speed": speed, "response_format": "wav"}
    if instructions and not model.startswith("tts-1"):
        body["instructions"] = instructions
    _speech_http("https://api.openai.com/v1/audio/speech", body, {"Authorization": f"Bearer {key}"}, dst)


def _compatible(text, voice, speed, instructions, model, dst):
    sc = server_config()
    if not sc["base_url"]:
        raise RuntimeError("TTS engine openai-compatible needs VSTUDIO_TTS_BASE_URL (or persona tts.server.base_url)")
    key = os.environ.get(sc["api_key_env"]) if sc["api_key_env"] else None
    if sc["api_key_env"] and not key:
        raise RuntimeError(f"TTS engine openai-compatible needs {sc['api_key_env']}")
    body = {"model": model, "voice": voice, "input": text, "speed": speed, "response_format": "wav"}
    if instructions:
        body["instructions"] = instructions
    _speech_http(sc["base_url"].rstrip("/") + "/audio/speech", body,
                 {"Authorization": f"Bearer {key}"} if key else {}, dst)


def _elevenlabs(text, voice, speed, model, dst):
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise MissingKey("elevenlabs", free=local_engine() is not None)
    body = {"text": text, "model_id": model, "voice_settings": {"speed": max(0.7, min(1.2, float(speed)))}}
    _speech_http(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128", body,
                 {"xi-api-key": key, "Accept": "audio/mpeg"}, dst)


def _kokoro(text, voice, speed, model, dst, tmp):
    if not importlib.util.find_spec("mlx_audio"):
        raise RuntimeError("kokoro needs mlx-audio (pip install mlx-audio; Apple Silicon)")
    local = os.path.isdir(model)
    if not local and os.environ.get(MANAGED_ENV):
        raise VoiceNotDownloaded()
    lang = kokoro_lang(voice)
    vref = voice
    if local and not str(voice).endswith(".safetensors"):
        vref = os.path.join(model, "voices", f"{voice}.safetensors")
        if not os.path.isfile(vref):
            raise RuntimeError(f"Kokoro voice {voice!r} is not downloaded (this copy has: "
                               f"{', '.join(kokoro_voices(model) or []) or 'none'})")
    lib = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in (lib, os.environ.get("PYTHONPATH")) if p))
    if local:
        env["HF_HUB_OFFLINE"] = "1"                  # a local folder: never reach for the hub
    out = os.path.join(tmp, "kokoro.wav")
    r = subprocess.run([sys.executable, "-m", "vstudio.kokoro_synth", "--model", model, "--voice", vref,
                        "--speed", str(speed), "--out", out] + (["--lang", lang] if lang else []),
                       input=text, capture_output=True, text=True, env=env)
    tail = lambda: "\n".join(((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-15:])
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"kokoro failed (exit {r.returncode}):\n{tail()}")
    shutil.move(out, dst)


def _qwen(text, voice, model, dst, tmp, instructions=None):
    if not importlib.util.find_spec("mlx_audio"):
        raise RuntimeError("qwen needs mlx-audio (pip install mlx-audio; Apple Silicon)")
    local = os.path.isdir(model)
    if not local and os.environ.get(MANAGED_ENV):
        raise VoiceNotDownloaded(chinese=True)
    lib = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in (lib, os.environ.get("PYTHONPATH")) if p))
    if local:
        env["HF_HUB_OFFLINE"] = "1"                  # a local folder: never reach for the hub
    out = os.path.join(tmp, "qwen.wav")
    r = subprocess.run([sys.executable, "-m", "vstudio.qwen_synth", "--model", model, "--voice", str(voice),
                        "--out", out] + (["--instruct", instructions] if instructions else []),
                       input=text, capture_output=True, text=True, env=env)
    tail = lambda: "\n".join(((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-15:])
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"qwen failed (exit {r.returncode}):\n{tail()}")
    shutil.move(out, dst)


def clone_config(ref_wav=None, ref_text=None, model=None, language=None):
    """Resolve the clone engine's reference + model: arguments first, then persona ``tts.clone.*``.
    Returns dict(ref_wav, ref_text, model, language, ref_hash). Raises RuntimeError when the reference
    is missing."""
    try:
        from .config import persona
        pc = (persona().get("tts") or {}).get("clone") or {}
    except Exception:
        pc = {}
    ref_wav = ref_wav or pc.get("ref_wav")
    ref_text = ref_text if ref_text is not None else pc.get("ref_text")
    if not ref_wav or not os.path.exists(os.path.expanduser(str(ref_wav))):
        raise RuntimeError("clone engine needs a reference recording: pass ref_wav= or set persona "
                           f"tts.clone.ref_wav in persona.local.yaml (got {ref_wav!r})")
    if not ref_text:
        raise RuntimeError("clone engine needs ref_text (the exact transcript of ref_wav): pass ref_text= "
                           "or set persona tts.clone.ref_text")
    ref_wav = os.path.abspath(os.path.expanduser(str(ref_wav)))
    h = hashlib.sha1()
    with open(ref_wav, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    h.update(str(ref_text).encode())
    lang = language or pc.get("language")
    lang = LANG_NAMES.get(str(lang).lower(), lang) if lang else None
    return dict(ref_wav=ref_wav, ref_text=str(ref_text), model=model or pc.get("model") or DEFAULT_MODEL["clone"],
                language=lang, ref_hash=h.hexdigest()[:16])


def _guess_language(text):
    return "Chinese" if any("\u4e00" <= c <= "\u9fff" for c in text) else "English"


def _clone_model(model):
    """Load (once per process) a Qwen3-TTS model through mlx_audio."""
    if model not in _CLONE_MODELS:
        if not importlib.util.find_spec("mlx_audio"):
            raise RuntimeError("clone engine needs mlx-audio (pip install mlx-audio; Apple Silicon) and the "
                               f"model {model} (downloaded by Hugging Face on first use, several GB)")
        from mlx_audio.tts.utils import load_model
        _CLONE_MODELS[model] = load_model(model)
    return _CLONE_MODELS[model]


def _clone(text, cfg, dst, seed=None):
    import numpy as np
    import soundfile as sf
    m = _clone_model(cfg["model"])
    if seed is not None:
        try:
            import mlx.core as mx
            mx.random.seed(int(seed))
        except ImportError:
            pass
    res = list(m.generate(text=text, ref_audio=cfg["ref_wav"], ref_text=cfg["ref_text"],
                          language=cfg["language"] or _guess_language(text)))
    if not res:
        raise RuntimeError("clone engine produced no audio")
    a = np.concatenate([np.asarray(r.audio, dtype=np.float32).reshape(-1) for r in res])
    sf.write(dst, a, int(getattr(m, "sample_rate", 24000)))


def _edge(text, voice, speed, dst):
    from . import ai_consent
    if ai_consent.required():
        raise RuntimeError("Edge voices are unavailable in the Mac App Store edition. Choose a local voice or an API voice service.")
    rate = f"{int(round((speed - 1) * 100)):+d}%"
    if importlib.util.find_spec("edge_tts"):
        import edge_tts
        asyncio.run(edge_tts.Communicate(text, voice, rate=rate).save(dst))
    elif shutil.which("edge-tts"):
        subprocess.run(["edge-tts", "--voice", voice, f"--rate={rate}", "--text", text, "--write-media", dst],
                       check=True, capture_output=True)
    else:
        raise RuntimeError("edge engine needs edge-tts (pip install edge-tts)")


def synth(text, engine="openai", voice=None, speed=1.0, instructions=None, out=None, model=None, cache=True,
          ref_wav=None, ref_text=None, language=None, seed=None):
    """Synthesise ``text`` -> 48 kHz mono wav; returns the wav path (``out`` if given, else the cache file).

    Args: engine "openai" | "kokoro" | "qwen" | "system" | "edge" | "clone" | "openai-compatible" | "elevenlabs" | "auto"; voice
    (default persona tts.<engine>_voice); speed (1.0 = normal; openai 0.25-4, edge as +-% rate, qwen/system by ffmpeg atempo;
    ignored by clone); instructions = delivery direction (openai gpt-4o-*, qwen: a style line); model overrides DEFAULT_MODEL; cache=False forces a new take (still cached after).
    clone only: ref_wav / ref_text / language (default persona tts.clone.*), seed (reproducible take; part
    of the cache key).
    """
    engine = pick_engine(engine)
    if engine not in DEFAULT_VOICE:
        raise ValueError(f"unknown TTS engine {engine!r}")
    ccfg = None
    if engine == "clone":
        ccfg = clone_config(ref_wav, ref_text, model, language)
        model = ccfg["model"]
        voice = f"ref:{ccfg['ref_hash']}:{ccfg['language'] or 'auto'}:{seed if seed is not None else '-'}"
    else:
        voice = _voice(engine, voice)
        model = kokoro_model(model) if engine == "kokoro" else qwen_model(model) if engine == "qwen" else \
            model or (server_config()["model"] if engine == "openai-compatible" else None) or DEFAULT_MODEL[engine]
    mkey = f"{server_config()['base_url']}#{model}" if engine == "openai-compatible" else model
    if engine == "kokoro":
        from . import kokoro_lexicon
        if kokoro_lexicon.mentions(text):     # a line naming a curated name: its take follows the lexicon's version
            mkey = f"{mkey}#names{kokoro_lexicon.VERSION}"
    key = cache_key(text, engine, voice, speed, instructions, mkey)
    cpath = os.path.join(_cache_dir(), f"{key}.wav")
    if not (cache and os.path.exists(cpath)):
        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "raw" + (".mp3" if engine in ("edge", "elevenlabs") else ".wav"))
            if engine == "openai":
                _openai(text, voice, speed, instructions, model, raw)
            elif engine == "openai-compatible":
                _compatible(text, voice, speed, instructions, model, raw)
            elif engine == "elevenlabs":
                _elevenlabs(text, voice, speed, model, raw)
            elif engine == "kokoro":
                _kokoro(text, voice, speed, model, raw, tmp)
            elif engine == "qwen":
                _qwen(text, voice, model, raw, tmp, instructions)
            elif engine == "system":
                from .system_voice import synth as system_synth
                system_synth(text, voice, raw, tmp)
            elif engine == "clone":
                _clone(text, ccfg, raw, seed)
            else:
                _edge(text, voice, speed, raw)
            part = cpath + ".part.wav"
            tempo = ["-af", f"atempo={max(0.5, min(2.0, float(speed))):.4f}"] if engine in ("qwen", "system") and \
                abs(float(speed) - 1.0) > 1e-3 else []          # Qwen3-TTS has no speed of its own
            media.run(["ffmpeg", "-y", "-i", raw, *tempo, "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", part])
            os.replace(part, cpath)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        shutil.copyfile(cpath, out)
        return out
    return cpath


# where a line may be cut in two: after a sentence end, else after a clause mark, else between words
_SPLIT_AT = (re.compile(r"(?<=[。！？!?；;])\s*|(?<=[.…])\s+"), re.compile(r"(?<=[，、：,:—])\s*"), re.compile(r"\s+"))
GAP_S = 0.18                       # the pause between the two halves of a split take (about a sentence break)


def split_in_two(text):
    """``text`` -> (first, second) cut at the sentence end nearest its middle, else the nearest clause mark, else the
    nearest space, else (Chinese with no marks) the middle character; None when there is nothing to cut (a word)."""
    t = " ".join(str(text).split())
    for pat in _SPLIT_AT:
        cuts = [m.start() for m in pat.finditer(t) if 0 < m.start() < len(t)]
        cuts = [c for c in cuts if t[:c].strip(" ,，、") and t[c:].strip(" .。!?！？,，、")]
        if cuts:
            c = min(cuts, key=lambda c: abs(c - len(t) / 2))
            return t[:c].strip(), t[c:].strip()
    cjk = [i for i, ch in enumerate(t) if "\u4e00" <= ch <= "\u9fff"]
    if len(cjk) >= 2:
        c = cjk[len(cjk) // 2]
        return t[:c].strip(), t[c:].strip()
    return None


def concat_wavs(paths, out, gap=GAP_S):
    """Join 16-bit wavs of one format (synth's 48 kHz mono) with ``gap`` seconds of silence between them."""
    import wave
    frames, params = [], None
    for p in paths:
        with wave.open(p) as w:
            params = params or w.getparams()
            frames.append(w.readframes(w.getnframes()))
    silence = b"\0" * (int(params.framerate * gap) * params.sampwidth * params.nchannels)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with wave.open(out, "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        w.writeframes(silence.join(frames))
    return out


def synth_split(text, out, **kw):
    """``synth`` of ``text`` as two takes (``split_in_two``) joined into ``out``; ValueError when it cannot be cut."""
    halves = split_in_two(text)
    if not halves:
        raise ValueError(f"cannot split {text!r}")
    return concat_wavs([synth(h, **kw) for h in halves], out)
