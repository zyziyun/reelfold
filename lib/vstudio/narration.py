"""Who speaks a version, in which language - the one policy every recipe (photo-story, vlog, explainer) and the intake
planner follow.

1. A beautiful-footage film (a calm vlog, a mood / essay photo story: "autumn essay", golden hour, scenery) has NO
   voice-over by default: music and a few refined on-screen lines. Only when the request asks for a voice
   (narration / voice-over / 旁白 / 配音 / 解说) does it get one.
2. A history / explainer piece is narrated. Its YouTube version is English (vstudio.platform.lang_for: YouTube is
   always English). Its Chinese version (小红书 / B站 / 抖音) is narrated in Chinese only when a good Chinese voice is
   set up (vstudio.tts.zh_voice_engine: the free Chinese voice Qwen3-TTS once downloaded, OpenAI with its key, a
   cloned voice, a persona voice, a TTS server); else it is narrated in English with the Chinese subtitles leading.
   Kokoro's Mandarin voice is opt-in (persona ``tts.zh_local: true``): it sounds robotic.

    from vstudio import narration as N
    N.is_mood_piece("an autumn essay of the red leaves")     -> True
    N.wants_voice("no narration, just music")               -> False   (None: the request does not say)
    N.default_mode("photo-story", request)                   -> "music" | "narration"
    N.voice_plan("zh", engine="auto")   -> {"narrate": "en", "sub_lead": "zh", "note": {...}}   (no good zh voice)
"""
import re

from . import tts

# a request that asks for a voice / for none (English and Chinese)
_NO_VOICE = re.compile(
    r"\b(no|without|skip)\s+(narration|narrator|voice[- ]?over|voice|vo)\b|\bmusic[- ]only\b|\bjust (the )?music\b|"
    r"\bno talking\b|纯音乐|只要音乐|不要旁白|不要配音|不配音|无旁白|不用旁白|不要解说|音乐卡点", re.I)
_VOICE = re.compile(r"\bnarrat\w*|\bvoice[- ]?overs?\b|\bvoiceover\b|\bnarrator\b|\btell (the|its) story\b|"
                    r"旁白|配音|解说|讲解|口播|念出来", re.I)
# beautiful footage / a mood piece
_MOOD = re.compile(
    r"\bessay\b|\bmood\b|\bpoetic\b|\bpoem\b|\bcinematic\b|\bscenery\b|\bscenic\b|\blandscape\b|\bgolden hour\b|"
    r"\bsunset\b|\bsunrise\b|\bblue hour\b|\bautumn\b|\bfall colou?rs?\b|\bred leaves\b|\bcalm\b|\bserene\b|"
    r"\baesthetic\b|\bbeautiful\b|\bambient\b|\brelax\w*|\bvibe\b|"
    r"散文|随笔|诗意|氛围|意境|治愈|风景|空镜|美景|日落|黄金时刻|秋天|红叶|唯美|文艺|舒缓|安静|慢节奏", re.I)
# a piece that is told: history, an explainer, a guide
_TOLD = re.compile(
    r"\bhistor\w*|\bexplain\w*|\bexplainer\b|\bdocumentar\w*|\bthe story of\b|\bhow (it|they) (was|were) built\b|"
    r"\bfacts?\b|\bguide\b|\btutorial\b|\bwhy\b|\bworld'?s fair\b|"
    r"历史|讲解|科普|来历|由来|介绍|纪录|故事|讲讲|攻略|教程", re.I)


def wants_voice(request):
    """True: the request asks for a voice; False: it asks for none; None: it does not say."""
    t = str(request or "")
    if _NO_VOICE.search(t):
        return False
    if _VOICE.search(t):
        return True
    return None


def is_mood_piece(request):
    """A beautiful-footage / mood piece (an essay, golden hour, scenery) that is not a told story (history,
    explainer)."""
    t = str(request or "")
    return bool(_MOOD.search(t)) and not _TOLD.search(t)


def default_mode(recipe, request):
    """A photo story's mode by default: "music" (no voice: music + on-screen lines) for a mood piece or a request
    that asks for no voice, "narration" for a told story or a request that asks for a voice."""
    w = wants_voice(request)
    if w is not None:
        return "narration" if w else "music"
    if recipe in ("photo-story",) and is_mood_piece(request):
        return "music"
    return "narration"


def voice_plan(version_lang, engine="auto"):
    """How a narrated version is voiced -> {narrate: locale, sub_lead: locale, engine, note, voice?}.
    Preserve an explicit locale for narration and captions. Non-English local plans include
    a matching voice when the backend requires one; unsupported local languages fail explicitly.
    This policy does not translate scripts or infer a language from the destination platform.
    An English version: English voice, English leads. A Chinese version: Chinese voice when a good one
    is set up (``tts.zh_voice_engine``), else English narration with the Chinese subtitles leading and ``note`` (en /
    zh plain words for the plan card, the inbox, the drafter's summary) saying why and how to turn the local Chinese
    voice on."""
    locale = str(version_lang or "en").strip().replace("_", "-").lower()
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", locale):
        raise ValueError(f"Expected a language code or locale, got {version_lang!r}")
    base = locale.split("-")[0]
    if base != "zh":
        selected = tts.available_engine(engine)
        plan = dict(narrate=locale, sub_lead=locale, engine=selected, note=None)
        if base != "en":
            if selected == "system":
                from .system_voice import voice_for
                plan["voice"] = voice_for(locale, preferred=tts.prefs().get("system_voice"))
            elif selected == "kokoro":
                from .voicecast import cast
                choice = cast(locale, selected, complete=False)
                if not choice:
                    raise ValueError(f"No available {selected} voice for {locale}")
                plan["voice"] = choice["speaker"]
            elif selected in ("qwen", "clone"):
                from .qwen_synth import language_for
                language_for("", locale)  # reuse the backend's supported-language contract
        return plan
    good = tts.zh_voice_engine(engine)
    if good:
        return dict(narrate="zh", sub_lead="zh", engine=good, note=None)
    return dict(narrate="en", sub_lead="zh", engine=tts.available_engine(engine), note=dict(tts.ZH_LOCAL_NOTE))


def note_text(note, lang="en"):
    """A voice_plan note in the reader's language (en / zh; others read English)."""
    if not note:
        return ""
    return note.get(lang) or note.get("en") or ""
