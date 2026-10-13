"""Her review of the DJI videos: "加中文的语音太难听了" (the built-in Mandarin voice sounds bad) and "youtube都应该英文版"
(YouTube must always be English). Policy at the source:
- YouTube / Shorts is always English: platform.lang_for, post copy (postcopy / publish), export captions, the photo
  story's subtitles / header / cover / post, the vlog drafter's on-screen words, the intake planner's split;
- a mood / scenery piece has no voice-over by default; a told (history / explainer) Chinese version is narrated in
  English with Chinese subtitles unless a good Chinese voice is set up; the built-in Chinese voice is opt-in;
- the local English voice says curated names from phonemes (Elliott was heard as "El Yacht")."""
import os
import sys

import pytest

from vstudio import export as EX
from vstudio import narration as N
from vstudio import platform as P
from vstudio import postcopy as PC
from vstudio import publish as PB
from vstudio import tts
from vstudio.subs import Cue

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _no_voice_env(monkeypatch):
    for k in ("OPENAI_API_KEY", "ELEVENLABS_API_KEY", "VSTUDIO_TTS_ENGINE", tts.ZH_LOCAL_ENV, "VSTUDIO_TTS_BASE_URL"):
        monkeypatch.delenv(k, raising=False)


def _persona(monkeypatch, text):
    from vstudio import config
    path = os.path.join(os.environ["VSTUDIO_HOME"], "persona.voice-test.yaml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    monkeypatch.setenv("VSTUDIO_PERSONA", path)
    monkeypatch.delenv("VSTUDIO_DEFAULT_PERSONA", raising=False)
    config.persona.cache_clear()
    return path


# ------------------------------------------------------------------------------------------- platform language
def test_platform_language_youtube_is_always_english():
    for n in ("youtube", "YouTube Shorts", "youtube-shorts:vertical", "yt", "shorts", "youtube-shorts-vertical"):
        assert P.lang_for(n) == "en" and P.lang_fixed(n), n
    for n in ("xiaohongshu", "小红书", "bilibili:vertical", "B站", "douyin", "xiaohongshu-full"):
        assert P.lang_for(n) == "zh" and not P.lang_fixed(n), n
    assert P.lang_for("tiktok") == "en" and not P.lang_fixed("tiktok") and P.lang_for("nope") is None
    assert P.split_by_lang(["bilibili", "xiaohongshu:vertical", "youtube-shorts", "youtube"]) == {
        "en": ["youtube", "youtube-shorts"], "zh": ["xiaohongshu:vertical", "bilibili"]}   # international first


def test_post_copy_language_youtube_ignores_persona(monkeypatch):
    _persona(monkeypatch, "publish:\n  copy_lang: {intl: zh, youtube: zh, youtube-shorts: zh}\n")
    try:
        assert PC.copy_lang("youtube", "帮我剪一个红叶视频") == "en"
        assert PC.copy_lang("youtube-shorts:vertical") == "en"
        assert PC.copy_lang("tiktok") == "zh" and PC.copy_lang("xiaohongshu") == "zh"   # the others follow her
    finally:
        from vstudio import config
        config.persona.cache_clear()


def test_localize_post_youtube_never_chinese():
    post = dict(en=dict(title="Golden Hour", body="Light on the bay."), zh=dict(title="黄金时刻", body="海湾的光。"),
                lang="zh", bilingual=True, per_platform=dict(youtube=dict(title="黄金时刻", lang="zh")))
    warned = []
    for pl in ("youtube", "youtube-shorts"):
        b = PB.localize_post(post, pl, lang="zh", bilingual=True, warn=warned.append)
        assert b["title"] == "Golden Hour" and b["lang"] == "en", pl
    assert PB.localize_post(post, "xiaohongshu", warn=warned.append)["lang"] == "en+zh"   # bilingual elsewhere
    assert not warned
    PB.localize_post(dict(title="黄金时刻"), "youtube", warn=warned.append)
    assert warned and "en-only" in warned[0]


def test_export_captions_english_only_on_youtube():
    yt, xhs = P.profile("youtube"), P.profile("xiaohongshu")
    cues = [Cue(0, 1, "金色落在水面", "Gold settles on the water."), Cue(1, 2, "Let the light take its time.", "让光慢慢走"),
            Cue(2, 3, "只有中文")]
    out, warn = EX.cues_for_platform(yt, cues)
    assert [(c.text, c.alt) for c in out] == [("Gold settles on the water.", ""), ("Let the light take its time.", ""),
                                              ("只有中文", "")]
    assert warn and "1 cue" in warn[0]
    zh, none = EX.cues_for_platform(xhs, cues, bilingual=False)    # one language per platform: 中文 on 小红书
    assert [(c.text, c.alt) for c in zh] == [("金色落在水面", ""), ("让光慢慢走", ""), ("只有中文", "")] and not none
    same, none = EX.cues_for_platform(xhs, cues, bilingual=True)
    assert [(c.text, c.alt) for c in same] == [(c.text, c.alt) for c in cues] and not none


# ------------------------------------------------------------------------------------------- the voice policy
def test_builtin_chinese_voice_is_opt_in(monkeypatch):
    monkeypatch.setattr(tts, "available_engine", lambda name="auto": "kokoro" if name in (None, "auto") else name)
    assert tts.zh_voice_engine() is None and not tts.zh_narration_ok()
    monkeypatch.setenv(tts.ZH_LOCAL_ENV, "1")
    assert tts.zh_voice_engine() == "kokoro"
    monkeypatch.delenv(tts.ZH_LOCAL_ENV)
    assert tts.zh_voice_engine("openai") is None                  # no key: not a voice we can use
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert tts.zh_voice_engine("openai") == "openai"
    assert tts.zh_voice_engine("clone") is None                   # no reference recording set up


def test_builtin_chinese_voice_opt_in_from_persona(monkeypatch):
    monkeypatch.setattr(tts, "available_engine", lambda name="auto": "kokoro")
    _persona(monkeypatch, "tts:\n  zh_local: true\n")
    try:
        assert tts.zh_local_opt_in() and tts.zh_voice_engine() == "kokoro"
        _persona(monkeypatch, "voice:\n  zh_local: true\n")
        assert tts.zh_local_opt_in()
    finally:
        from vstudio import config
        config.persona.cache_clear()


def test_request_says_voice_or_mood():
    assert N.wants_voice("no narration, just music") is False and N.wants_voice("不要旁白，纯音乐") is False
    assert N.wants_voice("with an English voice-over") is True and N.wants_voice("配旁白讲讲历史") is True
    assert N.wants_voice("a golden hour film") is None
    assert N.is_mood_piece("an autumn essay of the red leaves") and N.is_mood_piece("黄金时刻的海湾，治愈")
    assert not N.is_mood_piece("the history of the 1962 World's Fair at sunset")
    assert N.default_mode("photo-story", "autumn red-leaf essay with soft piano") == "music"
    assert N.default_mode("photo-story", "autumn essay with a calm voice-over") == "narration"
    assert N.default_mode("photo-story", "Seattle Center history, 90 s") == "narration"


def test_voice_plan_chinese_version(monkeypatch):
    monkeypatch.setattr(tts, "available_engine", lambda name="auto": "kokoro" if name in (None, "auto") else name)
    vp = N.voice_plan("zh")
    # the free Chinese voice is not on this computer (tests/conftest.py): English narration, and how to get it
    assert vp["narrate"] == "en" and vp["sub_lead"] == "zh" and "Settings > Voice" in N.note_text(vp["note"], "en")
    assert "中文配音" in N.note_text(vp["note"], "zh")
    assert N.voice_plan("en")["narrate"] == "en" and N.voice_plan("en")["note"] is None
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert N.voice_plan("zh", "openai") == dict(narrate="zh", sub_lead="zh", engine="openai", note=None)


# ------------------------------------------------------------------------------------------- photo story
def test_photo_story_version_language_follows_its_platforms():
    from vstudio.project.adapters.photostory import narration_is_chinese as zh
    ask = "做一条西雅图 1962 世博会的历史片，中文旁白"
    assert not zh(ask, "世博会 中文版", platforms=["youtube"])           # YouTube is English, whatever the name
    assert not zh(ask, platforms=["youtube-shorts", "xiaohongshu"])
    assert zh("make a history film", "Seattle", platforms=["xiaohongshu", "bilibili"])
    assert zh(ask, "Seattle")                                          # no platforms: as before


def test_photo_story_spec_voice_is_enforced():
    from vstudio.project.adapters import photostory as PS
    spec = 'TITLE_ZH = "红叶"\nTTS = dict(language="zh",\n           voice="x")\nSCRIPT = []\n'
    out = PS.enforce_voice(spec, dict(narrate="en", sub_lead="zh"), True)
    assert "TTS = dict(language='en', voice='x')" in out and "SUB_LEAD = 'zh'" in out and 'language="zh"' not in out
    music = PS.enforce_voice(spec, dict(narrate="en", sub_lead="zh"), True, music_mode=True)
    assert "MODE = 'music'" in music and "SUB_LEAD = 'zh'" in music
    assert PS.spec_language(_write(out)) == "en"


def _write(text):
    import tempfile
    fd, p = tempfile.mkstemp(suffix=".py")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return p


def _photostory():
    sys.path.insert(0, os.path.join(ROOT, "workflows/photo-story/scripts"))


def test_photo_story_youtube_render_is_english_only(tmp_path):
    _photostory()
    from photostory.ctx import Ctx, load_spec
    spec = tmp_path / "spec.py"
    spec.write_text('PLATFORM = "youtube"\nTITLE_ZH = "西雅图 1962"\nTITLE_EN = "Seattle 1962"\n'
                    'SECTIONS = ["开场"]\nSECTIONS_EN = ["Opening"]\nTTS = dict(language="zh")\nSCRIPT = []\n'
                    f'CACHE = {str(tmp_path / "cache")!r}\n')
    C = Ctx(load_spec(str(spec)))
    assert C.SUBS == "en" and not C.ZH_LEAD and C.EN_LEAD and C.HEAD_MAIN == "Seattle 1962" and C.HEAD_SUB == ""
    assert C.HEAD_SECTIONS == ["Opening"] and C.sub_pair("The Needle.", "太空针。") == ("The Needle.", "")
    assert C.shown("Pyramid · 金字塔构图") == "Pyramid" and C.shown("Draft 草稿") == "Draft"
    assert C.shown("示意图，非精确比例 · schematic, not to scale") == "schematic, not to scale"
    assert C.shown("画家的海岸") == ""             # nothing English to show: not shown on YouTube (P9)
    spec.write_text(spec.read_text().replace('"youtube"', '"xiaohongshu"').replace(
        'TTS = dict(language="zh")', 'TTS = dict(language="en")\nSUB_LEAD = "zh"'))
    C = Ctx(load_spec(str(spec)))
    assert C.SUBS == "zh" and C.ZH_LEAD and not C.EN_LEAD and C.HEAD_MAIN == "西雅图 1962"   # 中文 only on 小红书
    assert C.shown("Pyramid · 金字塔构图") == "金字塔构图"


def test_photo_story_youtube_cover_and_post_are_english():
    _photostory()
    from photostory import cover as PCV
    from photostory import export as PE

    class C:
        TITLE_ZH, TITLE_EN = "红叶落时", "When the Leaves Let Go"

    class Spec:
        COVER = dict(kicker="秋日随笔", title="红叶落时", subtitle="When the Leaves Let Go", tagline=("让", "秋天", "走"),
                     polaroids=[dict(src="a", caption="枫叶"), dict(src="b", caption="Maple")],
                     hero=dict(a="x", b="y"))
        TITLE_EN = "When the Leaves Let Go"
    cfg = PCV.english_cover(Spec, C)
    assert cfg["title"] == "When the Leaves Let Go" and "kicker" not in cfg and "tagline" not in cfg
    assert [p["caption"] for p in cfg["polaroids"]] == [None, "Maple"] and cfg["hero"]["labels"] == ("Draft", "Final")
    from photostory.subtitles import english_only
    assert english_only("PHOTOS · 张照片") == "PHOTOS" and english_only("张照片") == ""
    Spec.COVER = dict(Spec.COVER, title="When the Leaves Let Go")         # an English subtitle equal to the title
    assert PCV.english_cover(Spec, C)["subtitle"] == ""
    Spec.COVER_EN = dict(kicker="An autumn essay")
    assert PCV.english_cover(Spec, C)["kicker"] == "An autumn essay"
    zh = dict(title="红叶落时", intro="秋日随笔。", tags=["红叶"])
    post = PE.post_for(Spec, zh, "youtube")
    assert post["title"] == "When the Leaves Let Go" and post["intro"] == "" and post["tags"] == []


def test_photo_story_tts_skips_builtin_chinese_voice():
    src = open(os.path.join(ROOT, "workflows/photo-story/scripts/photostory/tts.py"), encoding="utf-8").read()
    assert "zh_local_opt_in()" in src and 'cfg["language"] = "en"' in src


# ------------------------------------------------------------------------------------------- vlog / explainer
def test_vlog_onscreen_words_language():
    from vstudio.project.adapters import vlog as V
    assert V.onscreen_lang(["youtube", "xiaohongshu"], "帮我剪个红叶视频") == "en"
    assert V.onscreen_lang(["xiaohongshu", "bilibili"], "make a golden hour film") == "zh"
    assert V.onscreen_lang(["tiktok"], "剪个视频") == "en" and V.onscreen_lang([], "剪一个视频") == "zh"
    assert "YouTube / YouTube Shorts is always English" in V.DRAFT_SYSTEM


def test_vlog_cover_gets_an_english_twin_for_youtube():
    from vstudio.project.adapters import common as CM
    assert CM.english_cover_text("Golden Hour · 黄金时刻 | Elliott Bay, Seattle") == "Golden Hour | Elliott Bay, Seattle"
    assert CM.english_cover_text("Jet Ski Summer | 华盛顿湖 · 夏日") == "Jet Ski Summer"
    assert CM.english_cover_text("红叶") == "" and CM._goes_to_youtube(["xiaohongshu", "youtube-shorts"])
    assert not CM._goes_to_youtube("xiaohongshu,bilibili")
    recipe = open(os.path.join(ROOT, "workflows/vlog/recipe.yaml"), encoding="utf-8").read()
    assert "youtube={cover.en}" in recipe and "youtube-shorts={cover.en_v916}" in recipe


def test_explainer_chinese_version_narrates_in_english_without_a_good_voice(monkeypatch):
    from vstudio.project.adapters import explainer as E
    monkeypatch.setattr(tts, "available_engine", lambda name="auto": "kokoro" if name in (None, "auto") else name)
    assert E.explainer_voice(dict(platforms=["bilibili"]), True)["narrate"] == "en"
    assert E.explainer_voice(dict(platforms=["youtube", "bilibili"]), True)["note"] is None   # English version
    monkeypatch.setenv(tts.ZH_LOCAL_ENV, "1")
    assert E.explainer_voice(dict(platforms=["bilibili"]), True)["narrate"] == "zh"
    rec = E._with_voice_note(dict(review=dict(lines=[])), N.voice_plan("zh", "openai")["note"] or tts.ZH_LOCAL_NOTE,
                             "en")
    assert "free Chinese voice" in rec["review"]["lines"][0]["params"]["label"]


# ------------------------------------------------------------------------------------------- intake planner
def _proj(recipe, platforms, name="Seattle 1962", mode=None):
    params = dict(platforms=list(platforms))
    if mode:
        params["mode"] = mode
    return dict(id="p1", recipe=recipe, name=name, params=params, param_sources={}, items=dict(method="single"),
                inputs={}, materials=[])


def test_planner_splits_youtube_from_chinese_platforms():
    from vstudio.intake import plan as PL
    ps, qs = PL.split_by_language([_proj("photo-story", ["xiaohongshu", "youtube", "bilibili"]),
                                   _proj("talkinghead", ["youtube", "douyin"], "Talk")],
                                  [dict(project=1, text="?")])
    assert [(p["id"], p["name"], p["params"]["platforms"]) for p in ps] == [
        ("p1", "Seattle 1962 (English)", ["youtube"]), ("p2", "Seattle 1962 (中文)", ["xiaohongshu", "bilibili"]),
        ("p3", "Talk", ["youtube", "douyin"])]
    assert qs[0]["project"] == 2 and ps[0]["param_sources"]["platforms"] == "language"
    one, _ = PL.split_by_language([_proj("vlog", ["xiaohongshu", "bilibili"])])
    assert len(one) == 1                                        # no YouTube: nothing to split


def test_planner_prompt_and_voice_note(monkeypatch):
    from vstudio.intake import plan as PL
    monkeypatch.setattr(tts, "available_engine", lambda name="auto": "kokoro" if name in (None, "auto") else name)
    system = PL.SYSTEM.format(phrases="")
    assert "YouTube and YouTube Shorts are ALWAYS English" in system and "robotic" in PL.zh_voice_line({})
    seen = {}
    monkeypatch.setattr(PL, "_prompt_doc", lambda *a, **k: "{}")
    PL._call_model("a history film", {}, dict(tts_engine="auto"), {},
                   call=lambda s, b: seen.update(system=s) or dict(json={}, model="m"))
    assert seen["system"].rstrip().endswith(PL.zh_voice_line({}))
    risk = PL.voice_risks([_proj("photo-story", ["xiaohongshu"])], "en")[0]
    assert risk.startswith("The free Chinese voice") and risk.info["code"] == "intake.risk.zh-voice"
    assert "约 3 GB" in PL.voice_risks([_proj("photo-story", ["xiaohongshu"])], "zh")[0]   # the desk offers the download
    assert PL.voice_risks([_proj("photo-story", ["xiaohongshu"], mode="music")], "en") == []
    assert PL.voice_risks([_proj("photo-story", ["youtube"])], "en") == []


def test_planner_mood_photo_story_has_no_voice():
    from vstudio.intake import plan as PL
    from vstudio.intake import rules as R
    from vstudio.project import manifests as M
    m = M.get("photo-story")
    for ask, mode in (("autumn red-leaf essay with soft piano for youtube", "music"),
                      ("Seattle Center history with narration", "narration"),
                      ("golden hour essay with an English voice-over", "narration"),
                      ("a history of the waterfront, no narration", "music")):
        params, sources = {}, {}
        PL._apply_intent(m, params, sources, R.parse_prompt(ask), {})
        assert params.get("mode", "narration") == mode, ask



def test_planner_language_version_keeps_its_own_platforms():
    from vstudio.intake import plan as PL
    ps, _ = PL.split_by_language([_proj("vlog", ["youtube", "xiaohongshu"], "Golden hour - English version"),
                                  _proj("vlog", ["youtube", "xiaohongshu"], "黄金时刻 中文版")])
    assert [p["params"]["platforms"] for p in ps] == [["youtube"], ["xiaohongshu"]]
    assert PL.name_lang("zh") == "zh" and PL.name_lang("Trip (EN)") == "en" and PL.name_lang("Trip") is None
