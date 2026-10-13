"""Editing templates: one named way to cut a kind of video = a recipe + its params + the shot-treatment policy.

    from vstudio.brain import presets as P
    P.get("travel-calm")          # {id, recipe, params, labels, policy, goal_kind?}
    P.for_recipe("vlog")          # the templates a vlog project can be made with
    P.for_goal_kind("reel")       # the template a goal video of that kind is made with

A template never adds a gimmick: the policy is what ``brain.treat`` may use per shot (AESTHETICS.md P1-P9, A4-A9).
``policy`` keys:

    hold          (min, max) seconds a shot is held in the cut
    transitions   allowed joins, first = the default (cut | beat-cut | dissolve | match-cut | morph)
    dissolve_s    length of a dissolve
    speed         allowed speeds: normal | slowmo (RIFE when available, else 60p at 0.5x) | ramp
    ramps         at most this many speed ramps in the whole video (A7: a signature move stars once)
    punch_in      punch-ins allowed (talking heads: on emphasis / to hide a jump cut)
    reframe       follow the subject when the output aspect differs from the source
    text          on-screen text policy: none | sparse (2-5 lines, P6) | labels (place labels) | captions
    grade         look: cinema (P3: contrast 1.04, sat 1.04, exposure match) | talkinghead | neutral
    music         bed | beat | under-voice | none
"""

PRESETS = {}


def _add(id, recipe, en, zh, why_en, why_zh, params=None, goal_kind=None, **policy):
    base = dict(hold=(2.0, 6.0), transitions=("cut",), dissolve_s=0.8, speed=("normal",), ramps=0, punch_in=False,
                reframe=True, text="sparse", grade="cinema", music="bed")
    base.update(policy)
    PRESETS[id] = dict(id=id, recipe=recipe, params=dict(params or {}), labels=dict(en=en, zh=zh),
                       blurb=dict(en=why_en, zh=why_zh), goal_kind=goal_kind, policy=base)


# ---- footage films (drone / travel)
_add("travel-calm", "vlog", "Calm travel film", "旅行安静片",
     "music and a few short lines, long holds that follow the light", "配乐 + 几句短句，长镜头跟着光走",
     params=dict(style="calm"), goal_kind="film",
     hold=(7.0, 14.0), transitions=("dissolve", "cut", "match-cut"), speed=("normal", "slowmo"), text="sparse",
     music="bed")
_add("beat-short", "vlog", "Beat-cut short", "卡点短片",
     "fast cuts on the beat, one speed ramp at the peak", "卡点快剪，高潮处一次变速",
     params=dict(style="fun"), goal_kind="reel",
     hold=(0.8, 3.0), transitions=("beat-cut", "cut", "match-cut"), speed=("normal", "ramp", "slowmo"), ramps=1,
     text="sparse", music="beat")
_add("trip-vlog", "vlog", "Trip vlog", "旅行 vlog",
     "moments in time order with place and time captions", "按时间顺序，带地点和时间字幕",
     params=dict(style="calm"), goal_kind="vlog",
     hold=(3.0, 8.0), transitions=("cut", "dissolve", "match-cut"), speed=("normal", "slowmo"), text="labels",
     music="bed")
_add("history-explainer", "photo-story", "History explainer", "地方历史讲解",
     "a narrated story of the place over its best shots, with place labels", "旁白讲这个地方的故事，配地点标签",
     params=dict(mode="narration"), goal_kind="history",
     hold=(5.0, 12.0), transitions=("dissolve", "cut"), speed=("normal", "slowmo"), text="labels",
     music="under-voice")
_add("documentary", "photo-story", "Documentary", "纪录片",
     "an observational narrated film: wide to close, room to breathe", "观察式旁白纪录片：由远及近，留白",
     params=dict(mode="narration"),
     hold=(4.0, 10.0), transitions=("cut", "dissolve", "match-cut"), speed=("normal",), text="labels",
     music="under-voice")
_add("essay", "photo-story", "Reflective essay", "随笔短片",
     "a calm voice-over, soft music, slow cuts", "安静旁白、轻音乐、慢剪",
     params=dict(mode="narration"), goal_kind="essay",
     hold=(4.0, 9.0), transitions=("dissolve", "cut"), speed=("normal", "slowmo"), text="captions",
     music="under-voice")
_add("photo-story", "photo-story", "Photo story", "照片故事",
     "slow moves over each still, a music bed, a few lines", "每张照片慢慢推移，配乐和几句话",
     params=dict(mode="music"), goal_kind="photos",
     hold=(3.0, 6.0), transitions=("dissolve", "cut"), speed=("normal",), text="sparse", music="bed")
# ---- speech
_add("th-refined", "talkinghead", "Refined talking head", "口播精剪",
     "strict filler cuts, 1.1x, hard cuts; jump cuts smoothed, a punch-in only on emphasis",
     "严格去口癖、1.1 倍速、硬切；跳切做平滑，只在重点处推近",
     params=dict(edit_style="refined", cleanup_profile="tight", speed=1.1),
     hold=(1.5, 30.0), transitions=("cut", "morph"), speed=("normal",), punch_in=True, text="captions",
     grade="talkinghead", music="none")
_add("lecture-shorts", "longform-to-short", "Lecture to shorts", "长视频切片",
     "self-contained clips of the strongest ideas, vertical", "按完整观点切成竖屏短片",
     hold=(1.5, 30.0), transitions=("cut", "morph"), speed=("normal",), punch_in=True, text="captions",
     grade="talkinghead", music="none")
_add("conversation-clips", "call-clips", "Conversation clips", "对话切片",
     "question-and-answer clips, speakers framed, faces masked when asked", "一问一答切片，按说话人取景",
     hold=(1.5, 30.0), transitions=("cut",), speed=("normal",), punch_in=False, text="captions",
     grade="talkinghead", music="none")
# ---- made from words / product
_add("concept-explainer", "explainer", "Concept explainer", "概念讲解",
     "3Blue1Brown-style drawn visuals over a narrated script", "3b1b 风格的讲解动画配旁白",
     hold=(2.0, 12.0), transitions=("cut", "dissolve"), speed=("normal",), reframe=False, text="captions",
     grade="neutral", music="under-voice")
_add("product-promo", "promo-recut", "Product promo", "产品宣传片",
     "the talk recut with screenshots, highlights and one freeze", "口播重剪，配截图、高亮和一次定格",
     hold=(1.0, 8.0), transitions=("cut", "match-cut"), speed=("normal",), punch_in=True, text="captions",
     grade="talkinghead", music="under-voice")
_add("launch-film", "launch-kit", "Launch film", "产品发布片",
     "a product demo with a feature list, GIFs and stills", "产品演示 + 功能列表 + 动图",
     hold=(1.0, 6.0), transitions=("cut", "match-cut"), speed=("normal",), reframe=False, text="captions",
     grade="neutral", music="bed")
_add("ai-short", "ai-video", "AI short drama", "AI 短剧",
     "an AI-generated short from a script, budget locked first", "按剧本生成 AI 短剧，先锁预算",
     hold=(1.5, 6.0), transitions=("cut",), speed=("normal",), text="captions", grade="neutral", music="bed")

GOAL_KINDS = ("history", "film", "reel", "vlog", "essay", "photos")


def get(pid):
    return PRESETS[pid]


def ids():
    return list(PRESETS)


def for_recipe(recipe):
    return [p for p in PRESETS.values() if p["recipe"] == recipe]


def default_for_recipe(recipe):
    """The template a project of ``recipe`` falls back to (the first registered), or None."""
    rows = for_recipe(recipe)
    return rows[0] if rows else None


def for_goal_kind(kind):
    for p in PRESETS.values():
        if p.get("goal_kind") == kind:
            return p
    return PRESETS["travel-calm"]


def label(pid, lang="en"):
    p = PRESETS.get(pid)
    if not p:
        return pid
    return p["labels"].get(lang) or p["labels"]["en"]


def card(pid, lang="en"):
    """The plain-language card of a template (no engine words)."""
    p = PRESETS[pid]
    return dict(id=pid, recipe=p["recipe"], label=label(pid, lang), blurb=p["blurb"].get(lang) or p["blurb"]["en"])
