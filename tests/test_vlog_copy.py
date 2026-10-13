"""Real post copy for the vlog / travel recipes (2026-10: her Seattle red-leaves vlog went out with only its title in
each platform's post.md): a hook / title, a 2-4 line body (a longer YouTube description), topic hashtags within each
platform's limits, the place from the DJI flight logs (offline, the city only), the music credit, each platform in
its language (her Chinese request -> 小红书 in Chinese; YouTube / TikTok per persona, English by default). The routed
AI writes it (a fake ``copy`` model here), the rules when there is none; both recorded as the ``copy`` decision she
can change, next to the ``framing`` decision (follow the subject / fill with blur)."""
import json
import os
import shutil
import subprocess

import pytest

from vstudio import places
from vstudio import postcopy as PC
from vstudio import publish
from vstudio.project import autopilot as AP
from vstudio.project.core import Project

ASK = "使用这些视频帮我剪辑成一个西雅图红叶的视频，配个音乐什么的，显得高级一点"
TITLE = "Seattle in Red — Autumn From Above"
SRT = """1
00:00:00,000 --> 00:00:00,033
<font size="28">FrameCnt: 1, DiffTime: 33ms
2026-10-10 18:55:57.457
[iso: 100] [shutter: 1/120.0] [fnum: 1.8] [ev: 0] [focal_len: 24.00] [latitude: 47.762948] [longitude: -122.182302] [rel_alt: 85.200 abs_alt: 105.1] </font>

2
00:00:00,033 --> 00:00:00,066
<font size="28">FrameCnt: 2, DiffTime: 33ms
2026-10-10 18:55:57.490
[iso: 100] [shutter: 1/120.0] [fnum: 1.8] [ev: 0] [focal_len: 24.00] [latitude: 47.762950] [longitude: -122.182300] [rel_alt: 85.400 abs_alt: 105.3] </font>
"""
CALLS = []


def fake_copy(task, system, prompt, schema=None, provider=None, **kw):
    """The routed ``copy`` model: hashtags in the body, too many tags, an em-dash - the checks must clean it up."""
    CALLS.append(dict(task=task, system=system, prompt=prompt, schema=schema))
    langs = schema["required"]
    out = {}
    if "en" in langs:
        out["en"] = dict(title="Seattle's red season — from the sky", hook="Every street in Seattle turned red this week.",
                         body="Maple rows and empty roads, seen from 80 metres up.\nSound on for the slow version. #fall",
                         description="A calm minute over Seattle's maple streets in October.\nFilmed with a drone.\n"
                                     "Which city should I fly next?",
                         tags=["#Seattle", "fall foliage", "autumn", "drone", "aerial", "PNW", "maple", "travel", "x"])
    if "zh" in langs:
        out["zh"] = dict(title="西雅图红叶季，从天上看", hook="这周西雅图的街道全红了。",
                         body="枫树和空无一人的路，在80米高空看。\n戴上耳机慢慢看。#红叶",
                         description="十月的西雅图红叶航拍。",
                         tags=["西雅图", "红叶", "航拍", "秋天", "旅行vlog", "无人机", "枫叶", "治愈", "风景"])
    return {"provider": "fake", "json": out}


def broken_copy(task, system, prompt, schema=None, provider=None, **kw):
    raise RuntimeError("claude: not logged in")


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_BATCH_BENCH", str(tmp_path / "bench.json"))
    monkeypatch.setenv("VSTUDIO_MUSIC_DIRS", "")
    monkeypatch.setenv("HOME", str(tmp_path / "userhome"))
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VSTUDIO_CLIENTS"):
        monkeypatch.delenv(k, raising=False)
    CALLS.clear()
    from vstudio import config
    config.persona.cache_clear()
    yield
    monkeypatch.undo()
    config.persona.cache_clear()


def ctx(**kw):
    return PC.context(**dict(dict(request=ASK, title=TITLE, place=dict(en="Seattle", zh="西雅图", date="2026-10-10",
                                                                    aerial=True),
                                  music=dict(title="Slow pad", credit=None), duration=59.5), **kw))


# --------------------------------------------------------------------------- the facts
def test_place_from_dji_logs_offline(tmp_path):
    v = tmp_path / "DJI_20261010185557_0672_D.MP4"
    v.write_bytes(b"")
    (tmp_path / "DJI_20261010185557_0672_D.SRT").write_text(SRT)
    p = places.from_footage([str(v)])
    assert p["en"] == "Seattle" and p["zh"] == "西雅图" and p["km"] < 30
    assert p["date"] == "2026-10-10" and p["aerial"] is True
    assert places.nearest(0.0, -150.0) is None                            # mid-ocean: no name, never coordinates
    assert places.from_footage([str(tmp_path / "nothing.mp4")]) is None


def test_language_per_platform(monkeypatch):
    assert PC.copy_lang("xiaohongshu", ASK) == "zh"
    assert PC.copy_lang("douyin", "make a Seattle fall video") == "zh"   # 抖音's audience reads Chinese
    assert PC.copy_lang("youtube", ASK) == "en" and PC.copy_lang("tiktok", ASK) == "en"
    p = os_persona(monkeypatch, "publish:\n  copy_lang: {intl: zh, youtube: en}\n")
    assert p and PC.copy_lang("tiktok", ASK) == "zh" and PC.copy_lang("youtube", ASK) == "en"


def os_persona(monkeypatch, text):
    from vstudio import config
    path = os.path.join(os.environ["VSTUDIO_HOME"], "persona.test.yaml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    monkeypatch.setenv("VSTUDIO_PERSONA", path)
    config.persona.cache_clear()
    return path


# --------------------------------------------------------------------------- the rules draft
def test_rules_draft_is_real_copy_in_each_language():
    d = PC.rules_draft(ctx(music=dict(title="Autumn", credit="Music: “Autumn” by A. Artist (CC BY 4.0)")),
                       ["youtube", "tiktok", "xiaohongshu:full"])
    per = d["per_platform"]
    assert d["source"] == "rules" and set(per) == {"youtube", "tiktok", "xiaohongshu"}
    for pl, c in per.items():
        lines = [x for x in c["body"].split("\n") if x.strip()]
        assert 2 <= len(lines) <= 6 and c["title"] and c["tags"]
        assert len(c["tags"]) <= PC.tag_limit(pl)
        assert "CC BY" in c["body"]                                       # the credit the license asks for
        assert "—" not in c["title"] + c["body"]                          # persona voice rule (em-dash)
    assert per["xiaohongshu"]["lang"] == "zh" and "西雅图" in per["xiaohongshu"]["body"]
    assert "红叶" in per["xiaohongshu"]["tags"] and "西雅图" in per["xiaohongshu"]["tags"]
    assert per["tiktok"]["lang"] == "en" and "Seattle" in per["tiktok"]["body"]
    assert per["tiktok"]["title"].startswith("Seattle in Red")             # her title, on the platforms in its language
    assert len(per["youtube"]["body"]) > len(per["tiktok"]["body"])       # a description, not a caption
    assert publish.check_title(per["xiaohongshu"]["title"], "xiaohongshu")[0]


def test_post_md_per_platform_from_the_draft(tmp_path):
    post = PC.post_json(PC.rules_draft(ctx(), ["youtube", "tiktok", "xiaohongshu:full"]))
    post = dict(post, title=TITLE)                                        # export --title: the flat title loses
    yt, _c = publish.platform_post(post, "youtube", warn=None)
    xhs, c = publish.platform_post(post, "xiaohongshu", warn=None)
    assert c["lang"] == "zh" and "#西雅图" in xhs and xhs.count("#") <= 10
    assert "#Seattle" in yt and yt.split("\n")[0].startswith("Seattle in Red")
    assert len([x for x in yt.split("\n") if x.strip()]) >= 4              # title + body lines + tags, not the title only


# --------------------------------------------------------------------------- the AI draft
def test_ai_draft_is_checked_against_each_platform():
    d = PC.draft(ctx(), ["youtube", "tiktok", "xiaohongshu:full", "x"], complete=fake_copy)
    assert d["source"] == "llm:fake" and CALLS and set(CALLS[0]["schema"]["required"]) == {"en", "zh"}
    assert "Seattle" in CALLS[0]["prompt"] and "drone" in CALLS[0]["prompt"] and "47.7" not in CALLS[0]["prompt"]
    per = d["per_platform"]
    assert per["tiktok"]["title"].startswith("Seattle in Red")             # her title wins in its language
    assert "#" not in per["tiktok"]["body"] and "#" not in per["xiaohongshu"]["body"]
    assert per["tiktok"]["body"].startswith("Every street")               # the hook leads the caption
    assert per["youtube"]["body"].startswith("A calm minute")              # the description on YouTube
    assert per["xiaohongshu"]["title"] == "西雅图红叶季，从天上看"
    for pl, c in per.items():
        assert 0 < len(c["tags"]) <= PC.tag_limit(pl)
        assert all(not t.startswith("#") and " " not in t for t in c["tags"] if c["lang"] == "en")
    assert len(per["x"]["tags"]) <= 2 and len(per["youtube"]["tags"]) <= 3 and len(per["xiaohongshu"]["tags"]) <= 10


def test_ai_failure_falls_back_to_the_rules_and_says_so():
    d = PC.draft(ctx(), ["tiktok", "xiaohongshu:full"], complete=broken_copy)
    assert d["source"] == "rules" and "not logged in" in d["error"]
    assert any("could not write it" in n for n in d["notes"])
    assert d["per_platform"]["xiaohongshu"]["body"]


# --------------------------------------------------------------------------- the recipe: decisions she can change
needs_ff = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture(scope="module")
def dji(tmp_path_factory):
    d = tmp_path_factory.mktemp("dji")
    out = []
    for i in range(2):
        p = str(d / f"DJI_2026101018555{i}_000{i}_D.MP4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc=size=320x180:rate=30:duration=4", "-vf", f"hue=h={i * 60}", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", p], check=True)
        with open(os.path.splitext(p)[0] + ".SRT", "w") as f:
            f.write(SRT)
        out.append(p)
    return out


@needs_ff
def test_vlog_autopilot_records_framing_and_copy_and_she_can_change_them(tmp_path, dji):
    p = Project.create(str(tmp_path / "p"), recipe="vlog", inputs=dict(footage=list(dji)),
                       params=dict(platforms=["tiktok", "xiaohongshu:full", "youtube"], preset="ultrafast",
                                   title=TITLE),
                       spec=dict(copy=dict(call="test_vlog_copy:fake_copy")))
    p.data["prompt"] = ASK
    p.save()
    out = Project(p.dir).run(autopilot=True)
    assert out["exit_code"] == 0, out
    decs = {d["checkpoint"]: d for d in AP.decisions(Project(p.dir))}
    fr, cp = decs["framing"], decs["copy"]
    assert fr["kind"] == "reframe-pick" and fr["reason_code"] == "reframe-follow" and fr["params"]["choice"] == "follow"
    assert cp["kind"] == "copy-pick" and cp["reason_code"] == "copy-ai" and cp["params"]["provider"] == "fake"
    ex = os.path.join(p.dir, "items", "main", "exports")
    man = json.load(open(os.path.join(ex, "manifest.json")))
    by = {e["platform"]: e for e in man["exports"]}
    assert by["tiktok"]["reframe"]["mode_used"] in ("subject", "pad-blur") and by["tiktok"]["reframe"].get("shots")
    assert by["youtube"]["reframe"]["mode_used"] == "scale"
    tk = open(os.path.join(ex, by["tiktok"]["post"]), encoding="utf-8").read()
    xhs = open(os.path.join(ex, by["xiaohongshu"]["post"]), encoding="utf-8").read()
    assert "Every street in Seattle" in tk and "#Seattle" in tk                 # body + hashtags, not the title only
    assert "这周西雅图的街道全红了" in xhs and "#西雅图" in xhs and by["xiaohongshu"]["post_lang"] == "zh"
    assert by["tiktok"]["post_lang"] == "en"
    # she changes the framing: the whole frame on a blurred fill -> the vertical versions are made again
    Project(p.dir).answer("framing", dict(pick=1), items=["main"])
    out = Project(p.dir).run()
    assert out["exit_code"] == 0, out
    man = json.load(open(os.path.join(ex, "manifest.json")))
    assert {e["platform"]: e for e in man["exports"]}["tiktok"]["reframe"]["mode_used"] == "pad-blur"
    ch = {c["checkpoint"]: c for c in AP.choices(Project(p.dir))}
    assert ch["framing"]["choice"] == "blur" and ch["framing"]["by"] == "her"           # still a setting she sees
    assert ch["framing"]["options"] == ["follow", "blur"] and ch["copy"]["choice"] == "ai"
    assert "framing" not in {d["checkpoint"] for d in AP.decisions(Project(p.dir))}     # hers, not the engine's
    # and the copy: the one written from the facts
    Project(p.dir).answer("copy", dict(pick=1), items=["main"])
    out = Project(p.dir).run()
    assert out["exit_code"] == 0, out
    tk = open(os.path.join(ex, "tiktok-vertical.post.md"), encoding="utf-8").read()
    assert "Every street" not in tk and "Seattle" in tk and "#" in tk


def test_a_mixed_chinese_title_stays_off_the_english_post():
    assert PC.title_lang("Elliott Bay 黄金时刻") == "zh" and PC.title_lang("Golden Hour") == "en"
