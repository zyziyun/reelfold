"""Typography kit: the kit font roles (config.FONTS / FONT_ENV), theme type-scale tokens and pairs, 避头尾 line
breaking (subs.kinsoku_violations / balanced_wrap) and the on-screen text lint (vstudio.textlint, firstpass)."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))

from vstudio import config, subs, textlint, theme  # noqa: E402


# ------------------------------------------------------------------------------------------------ fonts
@pytest.fixture
def font_dir(tmp_path, monkeypatch):
    d = tmp_path / "fonts"
    d.mkdir()
    monkeypatch.setattr(config, "FONT_DIR", str(d))
    monkeypatch.setattr(config, "persona", lambda: {})
    monkeypatch.delenv("VSTUDIO_FONT_DISPLAY_ZH", raising=False)
    return d


def test_kit_roles_exist_and_are_ofl_files():
    for role in ("display-zh", "zh-humanist", "display-latin", "serif-display"):
        assert config.FONTS[role]
    assert config.FONTS["display-latin"] == config.FONTS["serif-display"] == ["InstrumentSerif-Regular.ttf"]
    assert config.FONTS["zh-humanist"] == ["LXGWWenKai-Regular.ttf"]
    assert config.FONTS["display-zh"][0] == "SmileySans-Oblique.otf"


def test_display_zh_env_first_then_font_dir(font_dir, tmp_path, monkeypatch):
    (font_dir / "SmileySans-Oblique.otf").write_bytes(b"x")
    assert config.font("display-zh") == str(font_dir / "SmileySans-Oblique.otf")
    unpacked = tmp_path / "asset" / "SmileySans-Oblique.otf"
    unpacked.parent.mkdir()
    unpacked.write_bytes(b"x")
    monkeypatch.setenv("VSTUDIO_FONT_DISPLAY_ZH", str(unpacked))
    assert config.font("display-zh") == str(unpacked)
    monkeypatch.setenv("VSTUDIO_FONT_DISPLAY_ZH", str(tmp_path / "gone.otf"))   # stale env -> FONT_DIR
    assert config.font("display-zh") == str(font_dir / "SmileySans-Oblique.otf")


def test_missing_kit_font_raises_and_pair_font_falls_back(font_dir):
    for role in ("display-zh", "zh-humanist", "serif-display"):
        with pytest.raises(config.MissingAsset):
            config.font(role)
    (font_dir / "NotoSansSC-Bold.otf").write_bytes(b"x")
    (font_dir / "LXGWWenKai-Regular.ttf").write_bytes(b"x")
    assert theme.pair_font("display", "xhs-pop").endswith("NotoSansSC-Bold.otf")      # 得意黑 missing -> Noto Bold
    assert theme.pair_font("display", "soft").endswith("LXGWWenKai-Regular.ttf")       # installed kit face
    with pytest.raises(config.MissingAsset):
        theme.pair_font("text", "cinema")                                              # Noto Regular missing: no fallback


def test_desk_manifest_pins_the_kit_fonts():
    man = json.load(open(os.path.join(ROOT, "apps", "desk", "packaging", "assets.json"), encoding="utf-8"))
    groups = {g["id"]: g for g in man["groups"]}
    core = {f["dest"]: f for f in groups["core"]["files"]}
    assert core["fonts/LXGWWenKai-Regular.ttf"]["sha256"] == "39ad71264b588165b469e35e6afb162a378dacd1f95348160240ba9038ac3009"
    assert core["fonts/InstrumentSerif-Regular.ttf"]["size"] == 70012
    # the heavy Chinese titles: Noto Sans SC Black, pinned like the other Noto files
    black = core["fonts/NotoSansSC-Black.otf"]
    assert black["sha256"] == "ccb496022356b7dd14d117538a472ae40feff8f6e8f3fe8bffc5616785d2f3f9" and "/f8d1575" in black["url"]
    sm = groups["font-smiley"]
    assert sm["required"] and sm["extract"] and sm["env"] == {"VSTUDIO_FONT_DISPLAY_ZH": "SmileySans-Oblique.otf"}
    assert sm["files"][0]["sha256"] == "299c0be6c960ae37361762eca76f7d0cd516615435bb96c0d4b98a1e70178a07"
    assert config.FONT_ENV["display-zh"] in sm["env"]
    for g in (groups["core"], sm):
        assert "OFL" in g["licence"] and "GPL" not in g["licence"]


# ------------------------------------------------------------------------------------------------ type scale
def test_type_scale_vertical_and_horizontal_share_the_short_side():
    v = theme.type_scale(1080, 1920, "editorial")
    h = theme.type_scale(1920, 1080, "editorial")
    assert v["unit"] == h["unit"] == 1080
    assert (v["title"]["size"], v["subtitle"]["size"], v["label"]["size"], v["caption"]["size"]) == (80, 48, 28, 58)
    assert v["title"]["size"] == h["title"]["size"]
    assert h["title"]["max_chars_zh"] == theme.TITLE_MAX_ZH == 12 and v["title"]["max_words_en"] == 6
    assert v["title"]["max_chars_zh"] == 10                                    # 78 % of 1080 at 80 px, 0.02 em
    assert v["caption"]["max_chars_zh"] == 14                                  # = the vertical platform caption limit
    assert h["caption"]["max_chars_zh"] == theme.CAPTION_CAP_ZH and h["caption"]["max_chars_en"] == theme.CAPTION_CAP_EN
    assert v["label"]["tracking"] == theme.PRESETS["editorial"]["label_track"]
    for role in ("title", "subtitle", "label", "caption"):
        assert 1.1 <= v[role]["line_height"] <= 1.4
        assert v[role]["max_chars_en"] > v[role]["max_chars_zh"]


def test_type_scale_cinema_is_smaller_and_wider_and_scales_with_canvas():
    c, e = theme.type_scale(1080, 1920, "cinema"), theme.type_scale(1080, 1920, "editorial")
    assert c["title"]["size"] < e["title"]["size"] and c["title"]["tracking"] > e["title"]["tracking"]
    assert c["label"]["tracking"] == 0.22                                       # P5: 0.14-0.22 em on small labels
    assert c["fonts"] == dict(display="cjk-serif", display_latin="serif-display", text="cjk", quote="cjk-serif")
    k = theme.type_scale(3840, 2160, "cinema")
    assert k["caption"]["size"] == pytest.approx(2 * c["caption"]["size"], abs=1)


def test_pairs_cover_every_theme_and_name_real_roles():
    for name in theme.names(all_=True):
        pair = theme.PAIRS[name]
        assert set(pair) == {"display", "display_latin", "text", "quote"}
        assert all(r in config.FONTS for r in pair.values())
    assert theme.describe(theme.resolve("cinema"))["fonts"]["display_latin"] == "serif-display"
    assert all("fonts" in c for c in theme.catalogue())


# ------------------------------------------------------------------------------------------------ 避头尾
@pytest.mark.parametrize("text", [
    "他说：“这个东西真的很好用，你一定要试试看了。”",
    "我们今天来聊一聊这个问题吧好不好呢。",
    "《三体》这本书——真的，值得一读……你看过吗？",
    "约翰·史密斯和玛丽·安在纽约（一个很大的城市）里生活了很多年～",
    "价格是（含税）一百块，对吧！",
])
@pytest.mark.parametrize("width", [5, 6, 7, 8, 10])
def test_balanced_wrap_never_breaks_kinsoku(text, width):
    lines = subs.balanced_wrap(text, width)
    assert subs.kinsoku_violations(lines) == [], lines


def test_kinsoku_sets_cover_full_and_half_width():
    for c in "，。、！？；：”’）》」』】…—·~,.!?;:)":
        assert c in subs.NO_LINE_START, c
    for c in "“‘（《「『【([":
        assert c in subs.NO_LINE_END, c


def test_kinsoku_violations_kinds():
    v = subs.kinsoku_violations(["我们今天", "，来聊", "一"])
    assert [(x["line"], x["kind"]) for x in v] == [(1, "start"), (2, "orphan")]
    assert subs.kinsoku_violations(["他说“", "好的"])[0]["kind"] == "end"
    assert subs.kinsoku_violations(["说完", "了。"])[0]["kind"] == "orphan"          # punctuation does not count
    assert subs.kinsoku_violations(["……然后", "我们走了"]) == []                       # a lead-in ellipsis is fine
    assert subs.kinsoku_violations(["一"]) == []                                       # one line is not an orphan
    assert subs.kinsoku_violations(["Hello", "A"]) == []                              # latin is not CJK orphaning


def test_wrap_keeps_a_name_with_its_middle_dot():
    assert all(not ln.endswith("·") for ln in subs.balanced_wrap("约翰·史密斯和玛丽·安在纽约——一个很大的城市里生活了很多年", 10))


# ------------------------------------------------------------------------------------------------ text lint
def _by_id(items):
    return {i["id"]: i for i in items}


def test_lint_clean_captions_pass():
    it = _by_id(textlint.lint(["今天聊聊剪辑", "我们用Claude Code做视频"], platform="xiaohongshu:full"))
    assert set(it) == {"type-length", "type-kinsoku", "type-emoji", "type-punct", "type-lang"}
    assert all(i["ok"] and i["severity"] == "warn" for i in it.values())
    for i in it.values():
        assert set(i) == {"id", "ok", "severity", "value", "zh", "en", "fix_zh", "fix_en"}


def test_lint_caption_length_uses_platform_limits():
    long = "我觉得这个东西真的非常非常不错而且还很便宜哦你一定要去试一试看看到底怎么样再告诉我"
    it = _by_id(textlint.lint([{"text": long, "start": 3.2}], platform="xiaohongshu:full"))
    assert it["type-length"]["ok"] is False and it["type-length"]["value"][0].startswith("#1 (3.2s)")
    assert _by_id(textlint.lint(["今天\n聊聊剪辑的三个小技巧和一个大大的坑真的"], platform="douyin"))["type-length"]["ok"] is False


def test_lint_title_words():
    ok = _by_id(textlint.lint(["京都的第一天"], platform="xiaohongshu", kind="title"))
    assert ok["type-length"]["ok"]
    bad = _by_id(textlint.lint(["这是一个特别特别长的标题\n第二行也写得太长太长了真的"], platform="xiaohongshu", kind="title"))
    assert bad["type-length"]["ok"] is False
    v = _by_id(textlint.lint(["One two three four five six seven\nok"], platform="youtube-shorts", kind="title"))
    assert v["type-length"]["ok"] is False                                         # 7 words on a vertical canvas
    h = _by_id(textlint.lint(["One two three four five six seven\nok"], platform="youtube", kind="title"))
    assert h["type-length"]["ok"]                                                  # horizontal allows 8


def test_lint_kinsoku_on_manual_breaks():
    it = _by_id(textlint.lint(["这个东西真的很好用\n，你一定要试试"], platform="xiaohongshu"))
    assert it["type-kinsoku"]["ok"] is False


def test_lint_emoji_and_doubled_punctuation():
    it = _by_id(textlint.lint(["做视频🎬", "真的很好用。。", "wait,, what", "等等……", "and then..."], platform="xiaohongshu"))
    assert it["type-emoji"]["value"] == ["#1 做视频🎬"]
    assert it["type-punct"]["value"] == ["#2 真的很好用。。", "#3 wait,, what"]


def test_lint_area_styles_and_stacking():
    it = _by_id(textlint.lint(["Kyoto"], platform="youtube", boxes=[(0, 0, 1920, 400)]))
    assert it["type-area"]["ok"] is False and it["type-area"]["value"] == pytest.approx(0.37, abs=0.01)
    assert _by_id(textlint.lint([], frame_size=(1080, 1920), boxes=[(100, 100, 980, 300)]))["type-area"]["ok"]
    two = [dict(font="serif-display", size=80), dict(font="cjk", size=44)]
    assert _by_id(textlint.lint([], styles=two))["type-styles"]["ok"]
    three = two + [dict(font="cjk-bold", size=60, stroke=0.08, shadow=True, color="#FF2442")]
    it = _by_id(textlint.lint([], styles=three))
    assert it["type-styles"]["ok"] is False and it["type-stacked"]["ok"] is False
    quiet = [dict(font="cjk", size=58, stroke=0.05, shadow=True, color="#FFFFFF")]  # white over video: 2 treatments
    assert _by_id(textlint.lint([], styles=quiet))["type-stacked"]["ok"]


def test_lint_language_per_platform():
    yt = _by_id(textlint.lint(["Day one in Kyoto", "京都的第一天"], platform="youtube"))
    assert yt["type-lang"]["value"] == ["#2 京都的第一天"]
    xhs = _by_id(textlint.lint(["我们用Claude Code做视频", "iPhone 17 Pro 开箱", "this is really useful"],
                               platform="xiaohongshu"))
    assert xhs["type-lang"]["value"] == ["#3 this is really useful"]
    bilingual = _by_id(textlint.lint(["京都的第一天\nday one in kyoto"], platform="bilibili"))
    assert bilingual["type-lang"]["ok"]
    assert "type-lang" not in _by_id(textlint.lint(["随便写"], platform="tiktok"))  # not a one-language platform


def test_firstpass_check_text_lints_cues():
    from vstudio import firstpass as FP
    from vstudio import platform as PL
    cues = FP.load_cues([dict(start=1.0, end=2.0, text="真的很【好用】。。"), dict(start=2.0, end=3.0, text="hello there friends")])
    it = _by_id(FP.check_text(cues, PL.profile("xiaohongshu", "full")))
    assert it["type-punct"]["value"] == ["#1 (1.0s) 真的很好用。。"]
    assert it["type-lang"]["ok"] is False
    assert all(i["severity"] == "warn" for i in it.values())
