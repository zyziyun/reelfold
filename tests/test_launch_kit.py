"""launch-kit recipe (vstudio.launch): release notes -> features, config validation, storyboard timing and camera,
HyperFrames project, post copy, schedule, first-pass format. Synthetic fixtures only (a generated test-pattern
"recording", made-up product); no render (that needs Node + HyperFrames)."""
import json
import os
import re
import subprocess
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from vstudio import platform as PF  # noqa: E402
from vstudio.launch import brand as B  # noqa: E402
from vstudio.launch import compose as CO  # noqa: E402
from vstudio.launch import config as C  # noqa: E402
from vstudio.launch import features as FE  # noqa: E402
from vstudio.launch import posts as PO  # noqa: E402
from vstudio.launch import schedule as SC  # noqa: E402
from vstudio.launch import story as S  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FONTS = os.path.join(ROOT, "apps", "site", "public", "fonts")
DISPLAY = os.path.join(FONTS, "newsreader-latin-opsz-normal.woff2")
TEXT = os.path.join(FONTS, "inter-latin-wght-normal.woff2")


# ------------------------------------------------------------------------------------------------ features
def test_conventional_commits_keep_user_facing_changes_only():
    fs = FE.from_commits(["feat(desk): add a week board for publishing", "fix(engine): keep the word a filler cut trims",
                          "chore: bump deps", "ci(repo): check commit subjects", "docs: typo",
                          "refactor!: drop the old api", "perf(render): cache stage renders", "not conventional"])
    kinds = [f["kind"] for f in fs]
    assert kinds == ["feat", "perf", "change", "fix"]           # feat first, chores / ci / docs gone
    assert fs[0]["title"] == "Add a week board for publishing" and fs[0]["scope"] == "desk"
    assert len({f["id"] for f in fs}) == len(fs)


def test_changelog_section_with_intro_bullets(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text("# Changelog\n\n## [Unreleased]\n\n### Added\n\n- **App**, MIT:\n  - Home composer: describe the job.\n"
                 "  - An inbox that shows only what needs you.\n- **Platforms**: 20 profiles\n  with safe zones.\n"
                 "  - not a feature, a detail\n\n### Fixed\n\n- Chat edits always answer.\n\n## [0.1.0]\n\n- Old thing\n",
                 encoding="utf-8")
    fs = FE.from_changelog(str(p))
    titles = [f["title"] for f in fs]
    assert titles == ["Home composer", "An inbox that shows only what needs you", "Platforms",
                      "Chat edits always answer"]
    assert fs[-1]["kind"] == "fix"
    assert [f["title"] for f in FE.from_changelog(str(p), "0.1.0")] == ["Old thing"]
    with pytest.raises(ValueError):
        FE.from_changelog(str(p), "9.9")


def test_git_range(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True,
                       env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                                GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com"))
    git("init", "-q")
    for msg in ("chore: init", "feat: first feature", "feat(ui): second feature"):
        git("commit", "-q", "--allow-empty", "-m", msg)
    git("tag", "v1")
    git("commit", "-q", "--allow-empty", "-m", "feat: third feature")
    assert [f["title"] for f in FE.from_git(str(tmp_path), "v1..HEAD")] == ["Third feature"]
    assert len(FE.from_git(str(tmp_path))) == 3
    with pytest.raises(ValueError):
        FE.from_git(str(tmp_path), "nope..HEAD")


def test_notes_and_slug():
    assert [f["title"] for f in FE.from_notes("Faster sync\nDark mode")] == ["Faster sync", "Dark mode"]
    assert len(FE.slug("a very long feature name that keeps going and going", 20)) <= 20


# ------------------------------------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def kitdir(tmp_path_factory):
    d = tmp_path_factory.mktemp("launch")
    cap = d / "capture"
    cap.mkdir()
    for sid in ("plan", "review"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=576x360:r=30:d=6",
                        "-pix_fmt", "yuv420p", str(cap / f"{sid}.mp4")], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.2", "-i", str(cap / f"{sid}.mp4"), "-frames:v",
                        "1", str(cap / f"{sid}.png")], check=True)
    shots = {"size": [288, 180], "scale": 2, "fps": 30, "shots": [
        {"id": "plan", "title": "Plan", "caption": "", "file": "plan.mp4", "still": "plan.png", "w": 576, "h": 360,
         "duration": 6.0, "focus": [{"t": 1.0, "x": 0.1, "y": 0.1, "w": 0.3, "h": 0.08, "kind": "type"},
                                     {"t": 4.2, "x": 0.7, "y": 0.8, "w": 0.15, "h": 0.06, "kind": "click"}]},
        {"id": "review", "title": "Review", "caption": "", "file": "review.mp4", "still": "review.png", "w": 576,
         "h": 360, "duration": 6.0, "focus": [{"t": 2.0, "x": 0.4, "y": 0.4, "w": 0.2, "h": 0.1, "kind": "click"}]}]}
    (cap / "shots.json").write_text(json.dumps(shots))
    cfg = {
        "out": "kit",
        "product": {"name": "Acme Notes", "name_zh": "速记", "version": "v1.4.0", "site": "https://acme.example",
                    "one_liner": {"en": "Notes that file themselves", "zh": "自己归档的笔记"}},
        "brand": {"colors": {"accent": "#2F6F9F", "marker": "#CFE0EE"}, "fonts": {"display": DISPLAY, "text": TEXT}},
        "languages": ["en", "zh"],
        "platforms": ["xiaohongshu", "x", "tiktok", "linkedin", "youtube-shorts"],
        "capture": {"shots": "capture/shots.json"},
        "features": [
            {"id": "plan", "kicker": {"en": "Plan", "zh": "方案"},
             "caption": {"en": "Describe it in 【one sentence】.", "zh": "【一句话】说清要什么"}},
            {"id": "review", "kicker": {"en": "Review", "zh": "审阅"},
             "caption": {"en": "Look only at what is 【flagged】.", "zh": "只看【标出来】的"}}],
        "end_card": {"cta": {"en": "Free for personal use", "zh": "个人免费"}},
        "post": {"en": {"hook": "Acme Notes 1.4: notes that file themselves.", "body": ["Write; it files."],
                        "tags": ["notes", "productivity"], "links": {"Site": "https://acme.example"}},
                 "zh": {"hook": "速记 1.4：笔记自己归档。", "body": ["随手写。"], "tags": ["效率工具"]}},
        "schedule": {"start": "2026-11-03"},
    }
    (d / "launch.config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True))
    return d


@pytest.fixture(scope="module")
def cfg(kitdir):
    return C.load(str(kitdir / "launch.config.yaml"))


@pytest.fixture(scope="module")
def shots(cfg):
    return C.load_shots(cfg)


def _has_cjk_fonts():
    from vstudio import config as VC
    try:
        VC.font("cjk-bold")
        VC.font("cjk-serif-bold")
        return True
    except Exception:                                    # noqa: BLE001 - fonts come from install.sh
        return False


# ------------------------------------------------------------------------------------------------ config
def test_config_paths_defaults_and_renders(cfg, kitdir):
    assert cfg["out"] == str(kitdir / "kit")
    assert cfg["capture"]["shots"] == str(kitdir / "capture" / "shots.json")
    assert C.renders(cfg, "demo") == [("en", "16:9"), ("en", "9:16"), ("en", "1:1"), ("zh", "16:9"), ("zh", "9:16")]
    assert C.renders(cfg, "clips") == [("en", "1:1"), ("en", "9:16"), ("zh", "9:16")]
    assert C.text({"en": "a", "zh": "b"}, "zh") == "b" and C.text({"en": "a"}, "zh") == "a"


def test_config_errors_are_collected(tmp_path):
    bad = {"product": {"name": "X"}, "languages": ["en", "fr"], "platforms": ["myspace"],
           "features": [{"id": "a", "caption": {"zh": "只有中文"}}, {"id": "a"}],
           "demo": {"shots": ["nope"], "renders": ["en:4:3"]}, "music": {"file": "bed.m4a"}}
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(bad, allow_unicode=True))
    with pytest.raises(C.ConfigError) as e:
        C.load(str(p))
    msg = str(e.value)
    for want in ("one_liner", "languages", "myspace", "unique id", "caption is required", "unknown feature",
                 "LANG:ASPECT", "music.license", "music.file not found"):
        assert want in msg, want


def test_example_config_is_valid_yaml_with_every_section():
    ex = os.path.join(ROOT, "workflows", "launch-kit", "examples", "launch.config.example.yaml")
    with open(ex, encoding="utf-8") as f:
        d = yaml.safe_load(f)
    for k in ("product", "brand", "languages", "platforms", "capture", "features", "pace", "motion", "make", "demo",
              "loop", "clips", "gallery", "post", "schedule"):
        assert k in d, k
    assert "release" not in d          # optional: the seeded example must not name a CHANGELOG.md she never gave
    assert C.validate(C._merge(C.DEFAULTS, d), check_files=False) == []


# ------------------------------------------------------------------------------------------------ story
def test_text_boxes_inside_every_platform_safe_area():
    for asp, plats in C.CANVAS_PLATFORMS.items():
        x0, y0, x1, y1 = S.LAYOUTS[asp]["text"]
        for pl in plats:
            p = PF.profile(pl, use_persona=False)
            assert (p.w, p.h) == C.ASPECTS[asp], pl
            sx0, sy0, sx1, sy1 = PF.safe_box(p)
            assert sx0 <= x0 and sy0 <= y0 and x1 <= sx1 and y1 <= sy1, (asp, pl)
            for kx0, ky0, kx1, ky1 in PF.keepouts(p):
                assert x1 <= kx0 or y1 <= ky0, (asp, pl, "text under the button column")


def test_demo_loop_clip_timing(cfg, shots):
    d = S.plan(cfg, shots, "demo", "en", "16:9")
    lays = [s["layout"] for s in d["scenes"]]
    assert lays[0] == "chapter" and lays[-1] == "end" and S.adjacent_ok(d["scenes"])    # opening card .. end card
    assert d["scenes"][0]["title"] == "Acme Notes" and "macro" in lays
    assert d["duration"] <= cfg["demo"]["max_seconds"]
    for a, b in zip(d["scenes"], d["scenes"][1:]):
        assert b["start"] == pytest.approx(a["start"] + a["dur"] - S.XF, abs=1e-3)   # transitions overlap
    lp = S.plan(cfg, shots, "loop", "en", "16:9")
    assert lp["duration"] == pytest.approx(cfg["loop"]["seconds"], abs=0.01) and lp["loop"]
    for asp in ("1:1", "9:16"):
        cl = S.plan(cfg, shots, "clip", "zh", asp, feature="review")
        assert cfg["clips"]["min_seconds"] - 0.01 <= cl["duration"] <= cfg["clips"]["max_seconds"]
        assert [s["layout"] for s in cl["scenes"]] == ["type", "full", "macro", "end"]
        assert cl["scenes"][0]["text"] == "只看【标出来】的" and S.text_share(cl) <= 0.4 + 1e-6


def test_demo_is_squeezed_to_max_seconds(cfg, shots):
    tight = dict(cfg, demo=dict(cfg["demo"], max_seconds=12), motion=dict(cfg["motion"], beat=False))
    d = S.plan(tight, shots, "demo", "en", "16:9")
    assert all(s["dur"] >= s["min"] - 1e-6 for s in d["scenes"])              # every layout keeps its floor
    assert d["duration"] <= 12 + 1e-6 or all(s["dur"] == pytest.approx(s["min"]) for s in d["scenes"]
                                               if s["layout"] in S.FOOTAGE)


def test_camera_punches_in_on_actions_and_stays_inside(cfg, shots):
    for asp in S.LAYOUTS:
        L = S.LAYOUTS[asp]
        keys = S.camera(L, shots["plan"], 0.0, 6.0, 7.0)
        assert keys[0]["t"] == 0 and len(keys) >= 3
        _, _, W, H = L["win"]
        fit = max(W / 576, H / 360)
        assert max(k["scale"] for k in keys) > keys[0]["scale"] or asp == "9:16"
        for k in keys:
            assert k["scale"] >= fit - 1e-4
            assert k["x"] <= 0.01 and k["y"] <= 0.01                         # never shows the window's background
            assert k["x"] + 576 * k["scale"] >= W - 0.5 and k["y"] + 360 * k["scale"] >= H - 0.5
        punch = next(k for k in keys[1:] if k["scale"] > keys[0]["scale"] * 1.05) if asp != "9:16" else keys[1]
        assert punch["t"] == pytest.approx(1.0 - S.LEAD, abs=0.01) or punch["t"] >= 0


def test_cuts_land_on_the_beats_of_the_music_bed(cfg, shots):
    from vstudio import music as MU
    d = S.plan(cfg, shots, "demo", "en", "16:9")
    period, phase = d["beat"]
    assert period == pytest.approx(60 / MU.STYLES["tech"]["bpm"])            # the built-in bed's exact tempo
    for s in d["scenes"][1:]:
        k = (s["start"] + d["xf"] / 2 - phase) / period
        assert k == pytest.approx(round(k), abs=0.01)                        # every hand-over centred on a beat
    assert all(s["dur"] >= s["min"] - 1e-6 for s in d["scenes"])
    assert S.plan(cfg, shots, "loop", "en", "16:9")["beat"] is None          # a loop is silent
    assert S.plan(dict(cfg, music=None), shots, "demo", "en", "16:9")["beat"] is None


def test_beat_detection_finds_the_tempo_of_a_bed(tmp_path):
    from vstudio import music as MU
    wav = MU.make("bright", 24.0, out=str(tmp_path / "bed.wav"))
    period, phase = MU.detect_beat(wav)
    assert period == pytest.approx(60 / MU.STYLES["bright"]["bpm"], rel=0.01)
    assert min(phase, period - phase) < 0.06                                 # the grid starts on the downbeat


def test_launch_camera_establishes_then_pushes_into_the_action(cfg, shots):
    for asp in S.LAYOUTS:
        L = S.LAYOUTS[asp]
        keys = S.push_camera(L, shots["plan"], 0.0, 6.0, 5.0)
        _, _, W, H = L["win"]
        fit = max(W / 576, H / 360)
        zlo, zhi = L["zoom"]
        assert keys[0]["t"] == 0 and keys[0]["scale"] < fit * 1.1           # establishing: the whole window
        push = keys[1]
        assert zlo * fit - 1e-3 <= push["scale"] <= zhi * fit * 1.06 and push["d"] <= 1.1
        for a, b in zip(keys[1:], keys[2:]):
            assert b["t"] >= a["t"] + a["d"] - 1e-3                          # moves never overlap: no jitter
        for k in keys:
            assert k["x"] <= 0.01 and k["y"] <= 0.01
            assert k["x"] + 576 * k["scale"] >= W - 0.5 and k["y"] + 360 * k["scale"] >= H - 0.5


def _long_film(cfg, **film):
    caps = ["Write it once.", "It files itself.", "Find anything in a second.", "Links show up on their own.",
            "Share a page with one click.", "Search that reads your mind.", "Works offline.", "Sync everywhere.",
            "Export to anything.", "Undo is forever."]
    feats = [dict(id=f"f{i}", shot="plan" if i % 2 == 0 else "review", caption=dict(en=c, zh=f"功能{i}，一句话。"),
                  seconds=4.0) for i, c in enumerate(caps)]
    feats[4]["shot"] = ["plan", "review"]                    # two moments of one feature
    feats[6]["chapter"] = dict(en="Everywhere", zh="随处可用")
    return dict(cfg, features=feats, film=dict(S.film_opts(cfg), **film),
                demo=dict(cfg["demo"], min_seconds=30, max_seconds=60))


@pytest.mark.parametrize("variety", ["calm", "balanced", "lively"])
def test_rhythm_planner_varies_layouts_and_caps_text(cfg, shots, variety):
    long_cfg = _long_film(cfg, variety=variety)
    for asp in S.LAYOUTS:
        for lang in ("en", "zh"):
            p = S.plan(long_cfg, shots, "demo", lang, asp)
            sc = p["scenes"]
            lays = [s["layout"] for s in sc]
            assert S.adjacent_ok(sc), lays                                   # never the same layout twice in a row
            assert S.text_share(p) <= 0.4 + 1e-6 and p["text_share"] <= 0.4 + 1e-6
            assert lays[0] == "chapter" and lays[-1] == "end"
            assert lays.count("chapter") == 2                                # the opening + the one chapter: feature
            assert {"full", "split", "type"} <= set(lays), lays
            if variety != "calm":
                assert "macro" in lays
            # every feature is on screen; a split carries a feature's two shots side by side
            shown = {u for s in sc if s["layout"] in S.FOOTAGE for u in s["units"]}
            assert shown == {f"f{i}" for i in range(10)}
            two = next(s for s in sc if s["layout"] == "split" and s["units"] == ["f4"])
            assert [q["shot"] for q in two["panes"]] == ["plan", "review"]
            # no headline over the shots: words in a footage scene are only a small lower third / label
            assert all(not s.get("text") or s["layout"] == "float" for s in sc if s["layout"] in S.FOOTAGE)
            for i, s in enumerate(sc):
                if s["layout"] == "macro":                                   # a detail: 2.5-4x the whole UI
                    q = s["panes"][0]
                    assert q["cont"] and sc[i - 1]["panes"][0]["shot"] == q["shot"]
                    _, _, W, H = q["box"]
                    contain = min(W / 576, H / 360)
                    fit = max(W / 576, H / 360)
                    for k in q["cam"]:
                        assert 2.5 * contain * 0.95 - 1e-3 <= k["scale"] <= max(4 * contain, fit * 1.35) * 1.03 + 1e-3
                    first = sc[i - 1]["panes"][0]["media"]["segs"]           # the take continues across the cut
                    if first and q["media"]["segs"]:
                        assert q["media"]["segs"][0][0] >= first[0][0]
    tight = S.plan(_long_film(cfg, variety=variety, text=0.2), shots, "demo", "en", "16:9")
    assert tight["text_share"] <= 0.2 + 1e-6 and tight["dropped"]            # lower thirds, then type beats go


def test_caption_modes(cfg, shots):
    none = S.plan(_long_film(cfg, captions="none"), shots, "demo", "en", "16:9")
    assert not any(s.get("text") or s.get("labels") for s in none["scenes"])
    assert {s["layout"] for s in none["scenes"]} & {"type"} == set()
    typ = S.plan(_long_film(cfg, captions="type"), shots, "demo", "en", "16:9")
    assert not any(s.get("text") or s.get("labels") for s in typ["scenes"] if s["layout"] in S.FOOTAGE)
    assert any(s["layout"] == "type" for s in typ["scenes"])
    low = S.plan(_long_film(cfg, captions="lower"), shots, "demo", "en", "16:9")
    assert not any(s["layout"] == "type" for s in low["scenes"])
    assert any(s.get("text") for s in low["scenes"] if s["layout"] == "float")
    pinned = _long_film(cfg)
    pinned["features"][1]["layout"] = "split"
    pinned["features"][2]["layout"] = "split"
    p = S.plan(pinned, shots, "demo", "en", "16:9")
    assert S.adjacent_ok(p["scenes"])                                        # a clash of pins is resolved too


def test_split_and_lower_third_stay_inside_the_text_box(cfg, shots):
    for asp, L in S.LAYOUTS.items():
        x0, y0, x1, y1 = L["text"]
        for box in L["split"]:
            if L["labels"] == "above":
                assert box[1] - int(L["label_px"] * 1.3) - 14 >= y0
            else:
                assert box[1] + box[3] + 24 + L["label_px"] * 1.3 <= y1
        fx, fy, fw, fh = L["float"]
        assert fy + fh + 30 + L["lt_px"] * 1.3 * L["lt_lines"] <= y1 + 40


def test_film_and_type_keys_are_checked(cfg):
    bad = dict(cfg, film=dict(variety="wild", text=0.9, captions="loud"), type=dict(scale=3, weight=950, heavy=600, titles="huge"))
    errs = " ".join(C.validate(bad, check_files=False))
    for want in ("film.variety", "film.text", "film.captions", "type.scale", "type.weight", "type.heavy", "type.titles"):
        assert want in errs, want


def test_missing_shot_is_a_clear_error(cfg, shots):
    with pytest.raises(C.ConfigError, match="run the capture step"):
        S.plan(dict(cfg, features=cfg["features"] + [{"id": "ghost", "caption": "x"}], demo=dict(cfg["demo"],
               shots=["ghost"])), shots, "demo", "en", "16:9")


# ------------------------------------------------------------------------------------------------ brand + compose
def test_fit_measures_the_font():
    px, lines = B.fit("Describe the batch in 【one sentence】.", DISPLAY, (56, 40), 1680, 1, "en", 560)
    assert px == 56 and lines == ["Describe the batch in 【one sentence】."]
    px, lines = B.fit("Describe the batch in one sentence and then much more text here", DISPLAY, (68, 48), 600, 3)
    assert len(lines) <= 3 and all(B.measure(ln, DISPLAY, px) <= 600 for ln in lines)
    with pytest.raises(ValueError, match="caption too long"):
        B.fit("word " * 60, DISPLAY, (56, 40), 600, 1)


def test_a_missing_engine_font_never_stops_a_build(monkeypatch):
    from vstudio import config as VC

    def gone(role):
        raise VC.MissingAsset(f"font '{role}' not found")
    monkeypatch.setattr(VC, "font", gone)
    files = B.font_files({"brand": {}}, "zh")
    assert set(files.values()) == {B.INTER} and os.path.exists(B.INTER)


def test_red_accent_is_flagged():
    assert B.is_reddish("#FF2442") and B.is_reddish("#D42A43")
    assert not B.is_reddish("#0E9484") and not B.is_reddish("#2F6F9F") and not B.is_reddish("#A84F2D")
    assert B.warnings({"brand": {"colors": {"accent": "#0A7266"}}}) == []
    w = B.warnings({"brand": {"colors": {"accent": "#FF2442", "ink": "#9A9A9A"}}})
    assert len(w) == 2 and "red" in w[0] and "contrast" in w[1]


def test_build_writes_a_lint_clean_shaped_project(cfg, shots, tmp_path):
    proj = str(tmp_path / "demo-en-16x9")
    CO.build(cfg, S.plan(cfg, shots, "demo", "en", "16:9"), proj, quiet=True)
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    assert 'data-composition-id="main"' in html and 'window.__timelines["main"] = tl' in html
    assert "transform: translate" not in html                       # GSAP owns the camera transform
    assert re.search(r'tl\.set\("#s1m0", \{x: [-\d.]+, y: [-\d.]+, scale: [\d.]+\}, 0\)', html)
    assert '<span class="w mk">one sentence</span>' in html                 # the lower third, its term in accent
    assert html.count("<video ") >= 3 and 'data-volume="0"' in html          # + the detail cut's continuation
    from html.parser import HTMLParser
    class MediaClock(HTMLParser):
        def __init__(self):
            super().__init__(); self.stack = []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "video" and "data-start" in attrs:
                assert not any("data-start" in a and "data-composition-id" not in a for _, a in self.stack)
            if tag not in ("img", "meta", "link", "br", "input", "hr", "source"):
                self.stack.append((tag, attrs))
        def handle_endtag(self, tag):
            for n in range(len(self.stack) - 1, -1, -1):
                if self.stack[n][0] == tag:
                    del self.stack[n:]; break
    MediaClock().feed(html)
    assert "PingFang SC" not in html
    assert 'data-layout="macro"' in html and 'class="lt"' in html and "box-shadow" in html
    assert "--lk-flat" in html and html.count('class="full field"') == 2       # gradient only behind the cards
    assert "#0E9484" not in html and "#2F6F9F" in html.upper()      # the brand accent, not someone else's
    cues = json.load(open(os.path.join(proj, "cues.json"), encoding="utf-8"))["cues"]
    # a 14 s film: the second lower third is taken out to keep words under 40 % of the runtime
    assert [c["text"] for c in cues] == ["Acme Notes", "Describe it in one sentence."]
    assert os.path.exists(os.path.join(proj, "assets", "fonts", os.path.basename(DISPLAY)))


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_build_accepts_explicitly_null_optional_product_text(cfg, shots, tmp_path, lang):
    import copy
    c = copy.deepcopy(cfg)
    c["product"].update(site=None, version=None)
    plan = S.plan(c, shots, "demo", lang, "16:9")
    proj = CO.build(c, plan, str(tmp_path / lang), quiet=True)
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    assert 'data-composition-id="main"' in html
    assert "None" not in html and "null" not in html
    cues = json.load(open(os.path.join(proj, "cues.json"), encoding="utf-8"))["cues"]
    assert cues and all(cue["text"] and "None" not in cue["text"] for cue in cues)
    assert c["product"]["site"] is None and c["product"]["version"] is None


def test_loop_has_a_tail_back_to_frame_zero(cfg, shots, tmp_path):
    proj = str(tmp_path / "loop")
    CO.build(cfg, S.plan(cfg, shots, "loop", "en", "16:9"), proj, quiet=True)
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    assert 'id="tail"' in html and "tail-first.jpg" in html
    assert 'tl.set("#s0", {opacity: 1}, 0)' in html and 'tl.set("#tailm"' in html


@pytest.mark.skipif(not _has_cjk_fonts(), reason="Noto SC fonts not installed (./install.sh)")
def test_zh_build_subsets_cjk(cfg, shots, tmp_path):
    proj = str(tmp_path / "clip-zh")
    CO.build(cfg, S.plan(cfg, shots, "clip", "zh", "9:16", feature="plan"), proj, quiet=True)
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    assert 'lang="zh-CN"' in html and "LK-zh-display" in html
    assert any(f.startswith("zh-display") for f in os.listdir(os.path.join(proj, "assets", "fonts")))


@pytest.mark.skipif(not _has_cjk_fonts(), reason="Noto SC fonts not installed (./install.sh)")
def test_chinese_headlines_break_after_punctuation():
    f = B.font_files({"brand": {}}, "zh")["display"]
    assert B.fit("说一句，拖一个文件夹。", f, (96, 64), 756, 3, "zh")[1] == ["说一句，", "拖一个文件夹。"]


def test_caption_html_words_and_marker():
    h = CO.caption_html(["Look at 【what matters】 now"])
    assert h.count('class="w"') == 3 and '<span class="w mk">what matters</span>' in h
    assert CO.caption_html(["只看【标出来】的"]).count('class="w"') == 3


# ------------------------------------------------------------------------------------------------ copy + schedule
def test_posts_per_platform_and_language(cfg, tmp_path):
    res = PO.make_all(cfg, str(tmp_path / "copy"))
    assert list(res["launch"]) == PF.ordered(cfg["platforms"])
    assert list(res["launch"])[-1] == "xiaohongshu"                  # international first, Chinese after
    x = PF.profile("x", use_persona=False)
    for lang in ("en", "zh"):
        assert PF.text_len(x, res["launch"]["x"][lang]["text"]) <= 280
    assert "速记" in res["launch"]["xiaohongshu"]["zh"]["text"]
    assert "Describe it in one sentence." in res["clips"]["plan"]["x"]["en"]["text"]
    page = open(tmp_path / "copy" / "COPY.md", encoding="utf-8").read()
    assert "Nothing here has been posted" in page and page.index("### X") < page.index("### 小红书")
    assert (tmp_path / "copy" / "clips" / "review" / "tiktok.en.md").exists()
    from vstudio import publish as PB
    t = res["clips"]["review"]["xiaohongshu"]["zh"]["title"]
    assert t and PB.check_title(t, "xiaohongshu")[0]                       # "Name｜caption" too long -> caption
    assert "https://" not in res["launch"]["tiktok"]["en"]["text"]           # no dead links where they can't click
    assert "https://acme.example" in res["launch"]["x"]["en"]["text"]
    c2 = dict(cfg, post=dict(cfg["post"], en=dict(cfg["post"]["en"], by_platform={"x": {"hook": "Short X hook.", "body": []}})))
    r2 = PO.make_all(c2, str(tmp_path / "copy2"))
    assert r2["launch"]["x"]["en"]["text"].startswith("Short X hook.")
    assert not r2["launch"]["linkedin"]["en"]["text"].startswith("Short X hook.")


def test_posts_without_a_post_block_fail_loudly_without_a_model(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(PO.PB, "generate_copy", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="no model routed"):
        PO.make_all(dict(cfg, post=None), str(tmp_path / "copy"))


def test_schedule_picks_canvas_and_language(cfg):
    have = {("en", "16:9"): "d-en-169.mp4", ("en", "9:16"): "d-en-916.mp4", ("zh", "9:16"): "d-zh-916.mp4"}
    clips = {f: {("en", "1:1"): f"{f}-en-11.mp4", ("en", "9:16"): f"{f}-en-916.mp4", ("zh", "9:16"): f"{f}-zh.mp4"}
             for f in ("plan", "review")}
    rows = SC.propose(cfg, dict(demo=have, clips=clips))
    day0 = [r for r in rows if r["kind"] == "demo"]
    assert {r["at"][:10] for r in day0} == {"2026-11-03"}
    by = {r["platform"]: r for r in day0}
    assert by["x"]["video"] == "d-en-169.mp4" and by["tiktok"]["video"] == "d-en-916.mp4"
    assert by["xiaohongshu"]["video"] == "d-zh-916.mp4" and by["xiaohongshu"]["lang"] == "zh"
    assert [r["platform"] for r in day0][-1] == "xiaohongshu"
    clip_x = [r for r in rows if r["kind"] == "clip" and r["platform"] == "x"]
    assert [r["video"] for r in clip_x] == ["plan-en-11.mp4", "review-en-11.mp4"]
    assert clip_x[0]["at"][:10] == "2026-11-04"
    assert not [r for r in SC.propose(dict(cfg, platforms=["youtube", "x"]), dict(demo=have, clips=clips))
                if r["kind"] == "clip" and r["platform"] == "youtube"]


def test_schedule_apply_adds_planned_posts_only_for_known_accounts(cfg):
    from vstudio.project import pubcal
    pubcal.add_account("acme-x", "x", times=["09:00"])
    rows = SC.propose(cfg, dict(demo={("en", "16:9"): "d.mp4", ("en", "9:16"): "v.mp4"}))
    res = SC.apply(rows, {"x": "acme-x"})
    assert len(res["added"]) == 1 and res["added"][0]["state"] == "planned"
    assert {r["platform"] for r in res["skipped"]} == {r["platform"] for r in rows} - {"x"}


# ------------------------------------------------------------------------------------------------ format / recipe
def test_launch_format_allows_a_silent_render(tmp_path):
    from vstudio import firstpass as FP
    from vstudio import formats as F
    v = str(tmp_path / "silent.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0xF6F3EE:s=1920x1080:r=30:d=2",
                    "-pix_fmt", "yuv420p", v], check=True)
    f = F.get("launch", persona_formats={})
    assert f["audio"] == "optional" and f["workflow"] == "launch-kit"
    res = FP.run(v, fmt="launch", platform="x", media_checks=False)
    audio = next(i for i in res["items"] if i["id"] == "audio")
    assert audio["ok"] is None and audio["severity"] == "info"
    res = FP.run(v, fmt="talking-head", platform="x", media_checks=False)
    assert next(i for i in res["items"] if i["id"] == "audio")["ok"] is False


def test_recipe_manifest_is_registered():
    from vstudio.project import manifests as M
    m = M.reload()["launch-kit"]
    assert M.validate(m) == []
    assert [s["id"] for s in m["stages"]] == ["prepare", "features", "capture", "render", "stills", "copy", "schedule",
                                              "check"]
    assert {c["id"] for c in m["checkpoints"]} == {"config", "publish"}
    assert m["outputs"]["platforms"][0] == "x"


def test_cli_features_draft(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("## [1.0.0]\n\n### Added\n\n- Dark mode\n- Sync\n", encoding="utf-8")
    (tmp_path / "launch.config.yaml").write_text("release: {changelog: CHANGELOG.md}\n", encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "workflows", "launch-kit", "scripts", "launch_kit.py"),
                        "features", str(tmp_path / "launch.config.yaml")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    d = yaml.safe_load(r.stdout)
    assert [f["id"] for f in d["features"]] == ["dark-mode", "sync"]


def test_intake_routes_a_launch_request(tmp_path):
    from vstudio.intake import inventory as I
    from vstudio.intake import plan as PL
    (tmp_path / "CHANGELOG.md").write_text("## [1.0.0]\n\n- Dark mode\n", encoding="utf-8")
    from PIL import Image
    Image.new("RGB", (1440, 900), "#F6F3EE").save(tmp_path / "screen.png")
    a = I.analyze([str(tmp_path / "CHANGELOG.md"), str(tmp_path / "screen.png")])
    plan = PL.make_plan("Make a launch video for my app from this changelog", analysis=a, asr="off", provider="none")
    p = plan["projects"][0]
    assert p["recipe"] == "launch-kit"
    assert p["inputs"]["notes"].endswith("CHANGELOG.md") and p["inputs"]["shots"][0].endswith("screen.png")


def test_kit_jobs_names_and_outputs(cfg):
    from vstudio.launch import kit as K
    js = K.jobs(cfg)
    names = [j[0] for j in js]
    assert names[:5] == ["demo-en-16x9", "demo-en-9x16", "demo-en-1x1", "demo-zh-16x9", "demo-zh-9x16"]
    assert "loop-en" in names and "plan-zh-9x16" in names and "review-en-1x1" in names
    assert all(j[5].startswith(cfg["out"]) for j in js)
    assert [j[0] for j in K.jobs(cfg, only=["review"])] == ["review-en-1x1", "review-en-9x16", "review-zh-9x16"]


@pytest.mark.skipif(not __import__("vstudio.render", fromlist=["x"]).find_chromes(), reason="no Chrome")
def test_stills_exact_sizes(cfg, shots, tmp_path):
    from PIL import Image
    from vstudio.launch import stills as ST
    c = dict(cfg, gallery=dict(cfg["gallery"], facts=[{"value": "3", "label": "features"}], langs=["en"]))
    made = ST.make_all(c, shots, str(tmp_path / "stills"))
    names = [os.path.basename(m) for m in made]
    assert names == ["ph-gallery-1-hero.png", "ph-gallery-2-plan.png", "ph-gallery-3-review.png", "og-1200x630.png"]
    for m in made:
        with Image.open(m) as im:
            assert im.size == (ST.OG if "og-" in m else ST.PH)


def test_english_request_gets_an_english_plan_summary(tmp_path):
    from vstudio.intake import plan as PL
    from vstudio.intake import rules as R
    assert "xiaohongshu" in R.parse_prompt("clips for TikTok and Xiaohongshu")["platforms"]
    plan = dict(prompt="Cut this talk into clips for TikTok and Xiaohongshu", estimate=dict(wall_min=12),
                projects=[dict(recipe="talkinghead", recipe_label="口播精剪", items=dict(method="per-file", count=1), inputs={},
                               params=dict(platforms=["xiaohongshu:full", "tiktok"]),
                               checkpoints=[dict(id="publish", label="审片发布", needs_you=True)])])
    s = PL.template_summary(plan)
    assert s.startswith("I'll make 1 project") and "Review and publish" in s
    assert s.index("TikTok") < s.index("Xiaohongshu")                 # international first
    assert not any("一" <= c <= "鿿" for c in s)
    plan["prompt"] = "剪成小红书切片"
    assert PL.template_summary(plan).startswith("我会做")


def test_speed_ramp_on_idle_stretches(tmp_path):
    from vstudio.launch import timing as TM
    v = str(tmp_path / "wait.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x200:r=30:d=2",
                    "-f", "lavfi", "-i", "color=c=0xF4F0E8:s=320x200:r=30:d=3", "-f", "lavfi", "-i",
                    "testsrc2=s=320x200:r=30:d=2", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1[v]", "-map", "[v]",
                    "-pix_fmt", "yuv420p", v], check=True)
    shot = dict(id="w", kind="video", file=v, duration=7.0)
    spans = TM.idle_spans(shot)
    assert len(spans) == 1 and spans[0][0] == pytest.approx(2.0, abs=0.1) and spans[0][1] == pytest.approx(5.0, abs=0.1)
    assert os.path.exists(v + ".idle.json") and TM.idle_spans(shot) == spans          # cached
    segs = TM.segments(0.0, 7.0, spans)
    assert [r for _, _, r in segs] == [1.0, TM.IDLE_RATE, 1.0]
    assert TM.length(segs) == pytest.approx(7.0 - (3.0 - TM.KEEP) * (1 - 1 / TM.IDLE_RATE), abs=0.15)
    f = TM.fit(segs, 3.0)
    assert TM.length(f) == pytest.approx(3.0, abs=1e-3) and TM.fit(segs, 60) == segs   # never slows down
    assert TM.to_scene(segs, 0.0) == 0 and TM.to_scene(segs, 7.0) == pytest.approx(TM.length(segs))
    assert TM.to_scene(segs, 6.0) == pytest.approx(TM.length(segs) - 1.0, abs=0.01)    # after the ramp: real time
    end = TM.segments(0.0, 9.0, [(2.0, 4.0), (6.0, 9.0)])                               # ends frozen on the result
    assert end[-1] == (4.0, 6.0 + TM.END_HOLD, 1.0)
    held = TM.fit([(0.0, 8.0, 1.0), (8.0, 9.8, 1.0)], 6.0)
    assert held[-1] == (8.0, 9.8, 1.0) and TM.length(held) == pytest.approx(6.0, abs=1e-3)   # the result keeps its pace


def test_ramped_shot_becomes_back_to_back_clips(cfg, shots, tmp_path):
    sh = {k: dict(v, idle=[(2.0, 4.5)]) for k, v in shots.items()}
    plan = S.plan(cfg, sh, "clip", "en", "1:1", feature="plan")
    sc = next(s for s in plan["scenes"] if s["layout"] == "full")
    k = plan["scenes"].index(sc)
    segs = sc["panes"][0]["media"]["segs"]
    assert len(segs) >= 2 and segs[1][2] > segs[0][2]
    proj = str(tmp_path / "ramp")
    CO.build(cfg, plan, proj, quiet=True)
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    starts = [float(x) for x in re.findall(rf'<video id="s{k}v0\d" [^>]*data-start="([\d.]+)"', html)]
    durs = [float(x) for x in re.findall(rf'<video id="s{k}v0\d" [^>]*data-duration="([\d.]+)"', html)]
    assert len(starts) >= 2 and all(abs(starts[j] + durs[j] - starts[j + 1]) < 0.002 for j in range(len(starts) - 1))


def test_music_bed_from_the_shared_library(cfg, shots, tmp_path):
    assert cfg["music"]["mood"] == "tech" and "MIT" in cfg["music"]["license"]       # default: a built-in bed
    assert C.music_spec("none") is None and C.music_spec(False) is None
    assert C.music_spec("calm") == {"mood": "calm", "license": "built-in bed generated by Reelfold (MIT)"}
    with pytest.raises(C.ConfigError):
        C.music_spec({"mood": "polka"})
    proj = str(tmp_path / "music")
    CO.build(cfg, S.plan(cfg, shots, "clip", "en", "1:1", feature="plan"), proj, quiet=True)
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    assert '<audio src="assets/audio/music.m4a"' in html
    from vstudio import media
    assert media.probe(os.path.join(proj, "assets", "audio", "music.m4a"))["duration"] > 9
    proj2 = str(tmp_path / "silent")
    CO.build(dict(cfg, music=None), S.plan(cfg, shots, "clip", "en", "1:1", feature="plan"), proj2, quiet=True)
    assert "<audio" not in open(os.path.join(proj2, "index.html"), encoding="utf-8").read()


# ------------------------------------------------------------------------------------------------ her clips + a brief
BRIEF = """# Quill Notes 2.0 — launch promo brief

**What:** a short promo for **Quill Notes 2.0**, the notes app that files itself. Dark space, one teal accent.

| # | Take (`raw/`) | Use | On screen (EN) | 中文 |
|---|---|---|---|---|
| 1 | `01-home.mp4` | 0:00–0:04 · Home lands | Quill Notes 2.0 | Quill Notes 2.0 |
| 2 | `02-tag.mp4` + `03-out.mp4` | 0:04–0:09 · tags, then the result | Tags itself. | 自己打标签。 |
| 3 | end card | 0:09–0:12 · logo | Quill Notes — free for Mac. quillnotes.app | 速记 Quill Notes —— 免费的 Mac 应用。quillnotes.app |
"""
REQUEST = ("Make a 12-second premium launch promo for Quill Notes 2.0 from the clips in this folder, following "
           "BRIEF.md: open on Home with no hook, tight cuts at 1.1× with fast smooth animated transitions, the "
           "built-in tech music bed, and export 16:9, 9:16 and 1:1 in English and Chinese.")


def _moving_clip(path, d=6):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x202020:s=640x400:r=30:d={d}",
                    "-f", "lavfi", "-i", f"color=c=white:s=40x40:r=30:d={d}", "-filter_complex",
                    "[0][1]overlay=x='40+mod(t*60\\,300)':y=150", "-pix_fmt", "yuv420p", str(path)], check=True)


@pytest.fixture(scope="module")
def clipdir(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    raw = d / "raw"
    raw.mkdir()
    for n in ("01-home", "02-tag", "03-out"):
        _moving_clip(raw / f"{n}.mp4")
    (d / "BRIEF.md").write_text(BRIEF, encoding="utf-8")
    return d


def test_brief_shot_table_becomes_features(clipdir):
    got = FE.from_brief(BRIEF, [str(p) for p in (clipdir / "raw").iterdir()])
    assert [f["id"] for f in got["features"]] == ["01-home", "02-tag"]
    assert got["features"][1]["shots"] == ["02-tag.mp4", "03-out.mp4"]
    assert got["features"][1]["caption"] == {"en": "Tags itself.", "zh": "自己打标签。"}
    assert got["features"][0]["seconds"] == 4.0 and got["features"][1]["seconds"] == 5.0
    assert got["end"]["zh"].startswith("速记")
    assert FE.from_brief("no table here", []) == {"features": [], "end": None}


def test_features_step_without_a_changelog_drafts_from_the_brief(clipdir, tmp_path):
    """Dogfood 2026-10-11: the seeded example named a CHANGELOG.md she never gave -> FileNotFoundError traceback."""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "BRIEF.md").write_text(BRIEF, encoding="utf-8")
    (tmp_path / "launch.config.yaml").write_text("release: {changelog: CHANGELOG.md}\n", encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "workflows", "launch-kit", "scripts", "launch_kit.py"),
                        "features", str(tmp_path / "launch.config.yaml")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr and "CHANGELOG.md is not in the project" in r.stderr
    d = yaml.safe_load(r.stdout)
    assert [f["id"] for f in d["features"]] == ["01-home", "02-tag"]
    assert d["features"][1]["shot"] == ["02-tag", "03-out"]


def test_a_failing_step_is_one_plain_line_with_a_code(tmp_path):
    from vstudio import proctail
    (tmp_path / "launch.config.yaml").write_text("languages: [en]\n", encoding="utf-8")
    script = os.path.join(ROOT, "workflows", "launch-kit", "scripts", "launch_kit.py")
    for step in ("capture", "build", "render"):
        r = subprocess.run([sys.executable, script, step, str(tmp_path / "launch.config.yaml")], capture_output=True,
                           text=True)
        assert r.returncode == 2, (step, r.stderr)
        assert "Traceback" not in r.stderr and r.stderr.startswith("launch-kit config:"), r.stderr
        assert "product.name is required" in r.stderr
        assert proctail.tool_failure(f"RuntimeError: launch_kit.py exit 2:\n{r.stderr}") == dict(
            code="stage-launch-config", params=dict(fix="ask-fix-config"))
    r = subprocess.run([sys.executable, script, "features", str(tmp_path / "nope.yaml")], capture_output=True, text=True)
    assert r.returncode == 2 and "Traceback" not in r.stderr and "nope.yaml is not there" in r.stderr


def _clip_cfg(clipdir, tmp_path, **over):
    raw = clipdir / "raw"
    cfg = {"out": str(tmp_path / "kit"),
           "product": {"name": "Quill Notes", "version": "v2.0", "one_liner": {"en": "Free for Mac", "zh": "免费"}},
           "brand": {"theme": "night", "colors": {"accent": "#4FBFAE"}}, "languages": ["en", "zh"],
           "capture": {"clips": [str(raw / "01-home.mp4"), str(raw / "02-tag.mp4"), str(raw / "03-out.mp4")]},
           "features": [{"id": "home", "shot": "01-home", "caption": {"en": "Quill Notes 2.0", "zh": "速记 2.0"},
                         "seconds": 4},
                        {"id": "tag", "shot": ["02-tag", "03-out"], "caption": {"en": "Tags itself.",
                                                                                 "zh": "自己打标签。"}, "seconds": 5}],
           "pace": 1.1, "motion": {"transition": "mix", "seconds": 0.3},
           "demo": {"title_card": False, "min_seconds": 8, "max_seconds": 20,
                    "renders": ["en:16:9", "en:9:16", "en:1:1", "zh:16:9", "zh:9:16", "zh:1:1"]},
           "make": ["demo"], "music": "tech"}
    cfg.update(over)
    p = tmp_path / "launch.config.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return C.load(str(p))


def test_supplied_clips_plan_a_premium_cut(clipdir, tmp_path):
    from vstudio.launch import kit as K
    cfg = _clip_cfg(clipdir, tmp_path)
    sh = C.load_shots(cfg)
    assert set(sh) == {"01-home", "02-tag", "03-out"}
    s0 = sh["01-home"]
    assert (s0["w"], s0["h"]) == (640, 400) and s0["focus"] and s0["auto_focus"]
    assert os.path.exists(s0["still"]) and str(tmp_path / "kit" / "capture") in s0["still"]
    assert not (clipdir / "raw" / "01-home.mp4.idle.json").exists()       # caches never land next to her files
    p = S.plan(cfg, sh, "demo", "en", "9:16")
    lays = [s["layout"] for s in p["scenes"]]
    assert lays == ["full", "chapter", "split", "end"]          # cold open on Home, the name, both takes side by side
    assert p["transition"] == "mix" and p["xf"] == 0.3
    a, ch, b = p["scenes"][:3]
    assert ch["title"] == "Quill Notes" and ch["version"] == "2.0"   # her first line was the name: it is the card
    assert a["panes"][0]["media"]["at"] == 0.0 and a["text"] == ""   # the opening take lands as recorded, no words
    beat = p["beat"][0]                                              # cuts snap to the bed's beats
    for s in p["scenes"][1:]:
        k = (s["start"] + p["xf"] / 2 - p["beat"][1]) / beat
        assert k == pytest.approx(round(k), abs=0.01)
    assert [q["shot"] for q in b["panes"]] == ["02-tag", "03-out"]
    assert all(seg[2] >= 1.1 for s in (a, b) for q in s["panes"] for seg in q["media"]["segs"])
    cam = a["panes"][0]["cam"]
    assert len(cam) >= 2 and cam[1]["scale"] > cam[0]["scale"]       # the full-bleed shot pushes in
    assert S.text_share(p) <= 0.4 + 1e-6 and p["dropped"] == [["lower", "tag"]]   # a 12 s film: the cards are enough
    assert [x["text"] for x in S.caption_cues(p)] == ["Quill Notes"]
    names = [j[0] for j in K.jobs(cfg)]
    assert names == ["demo-en-16x9", "demo-en-9x16", "demo-en-1x1", "demo-zh-16x9", "demo-zh-9x16", "demo-zh-1x1"]
    proj = CO.build(cfg, S.plan(cfg, sh, "demo", "zh", "16:9"), str(tmp_path / "b"), quiet=True)
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    assert 'tl.fromTo("#s1", {opacity: 0, filter: "blur(8px)"}' in html            # into the card: a blur dissolve
    assert 'tl.fromTo("#s2", {opacity: 0, scale: 1.06, filter: "blur(12px)"}' in html   # out of it: a zoom-through
    assert 'data-layout="split"' in html and 'id="s2w1"' in html                    # two windows
    assert "#000" not in html.split("<style>")[1].split("#root")[1][:200]         # a light field, not black
    assert 'src="assets/audio/music.m4a"' in html


def test_bad_motion_and_make_are_config_errors(clipdir, tmp_path):
    with pytest.raises(C.ConfigError, match="motion.transition"):
        _clip_cfg(clipdir, tmp_path, motion={"transition": "wipe"})
    with pytest.raises(C.ConfigError, match="make:"):
        _clip_cfg(clipdir, tmp_path, make=["poster"])


def _ctx(tmp_path, clipdir, request=REQUEST, langs=("en", "zh")):
    from vstudio.project import drafts as DR
    pdir = tmp_path / "proj"
    item = pdir / "items" / "main"
    (item / "inputs").mkdir(parents=True)
    shots = sorted(str(p) for p in (clipdir / "raw").iterdir() if p.suffix == ".mp4")
    for s in shots + [str(clipdir / "BRIEF.md")]:
        os.symlink(s, item / "inputs" / os.path.basename(s))
    (pdir / "project.yaml").write_text(yaml.safe_dump({"prompt": request, "autopilot": {"lang": "en"}}),
                                       encoding="utf-8")
    params = {"_inputs": {"notes": str(clipdir / "BRIEF.md"), "shots": shots}, "languages": list(langs),
              "_item_dir": str(item)}
    return DR.Ctx(str(pdir), "main", params, "launch-kit"), item


def test_engine_drafts_the_config_from_her_clips_brief_and_request(clipdir, tmp_path):
    from vstudio.project import drafts as DR
    from vstudio.project import manifests as M
    m = M.reload()["launch-kit"]
    cp = next(c for c in m["checkpoints"] if c["id"] == "config")
    assert "features" in cp["blocks"]                    # features reads her config, never the seeded example
    ctx, item = _ctx(tmp_path, clipdir)
    path = str(item / "launch.config.yaml")
    tpl = os.path.join(ROOT, cp["author"]["template"])
    rec = DR.ensure(ctx, cp, path, tpl, complete=lambda *a, **k: pytest.fail("no AI needed for a shot table"))
    assert rec["by"] == "rules" and DR.state(path, tpl, cp, "launch-kit") == "drafted"
    raw = yaml.safe_load(open(path, encoding="utf-8"))
    assert "release" not in raw
    assert raw["capture"]["clips"] == ["inputs/01-home.mp4", "inputs/02-tag.mp4", "inputs/03-out.mp4"]
    assert raw["pace"] == 1.1 and raw["motion"]["transition"] == "mix" and raw["make"] == ["demo"]
    assert raw["demo"]["title_card"] is False and raw["music"] == "tech"
    assert raw["demo"]["renders"] == ["en:16:9", "en:9:16", "en:1:1", "zh:16:9", "zh:9:16", "zh:1:1"]
    assert raw["brand"] == {"theme": "night", "colors": {"accent": "#4FBFAE"}}
    assert raw["product"] == {"name": "Quill Notes", "version": "v2.0", "site": "https://quillnotes.app",
                              "name_zh": "速记", "one_liner": {"en": "Free for Mac.", "zh": "免费的 Mac 应用。"},
                              "description": {"en": "Quill Notes is the notes app that files itself."}}
    assert raw["end_card"] == {"cta": {"en": "Free for Mac.", "zh": "免费的 Mac 应用。"}}
    assert raw["features"][1] == {"id": "02-tag", "shot": ["02-tag", "03-out"],
                                  "caption": {"en": "Tags itself.", "zh": "自己打标签。"}, "seconds": 5.0}
    assert "&id" not in open(path, encoding="utf-8").read()       # no YAML anchors in a file she may edit
    cfg = C.load(path)                                             # valid as drafted
    assert C.renders(cfg, "demo")[-1] == ("zh", "1:1")


def test_an_older_apps_seeded_example_is_never_her_answer(tmp_path):
    """Her project was seeded by 0.2.7's example (not byte-identical to today's template): still the example."""
    from vstudio.project import drafts as DR
    from vstudio.project import manifests as M
    cp = next(c for c in M.reload()["launch-kit"]["checkpoints"] if c["id"] == "config")
    old = tmp_path / "launch.config.yaml"
    old.write_text("product:\n  name: Acme Notes\n  site: https://acme.example\nrelease:\n  changelog: CHANGELOG.md\n",
                   encoding="utf-8")
    assert DR.state(str(old), os.path.join(ROOT, cp["author"]["template"]), cp, "launch-kit") == "template"


def test_ai_draft_naming_a_missing_changelog_drops_it(tmp_path):
    from vstudio.project.adapters import launchkit as LK
    p = tmp_path / "launch.config.yaml"
    p.write_text("product: {name: X}\nrelease: {changelog: CHANGELOG.md, version: 1.0}\n", encoding="utf-8")
    assert LK.drop_missing_release(str(p)) is True
    assert "release" not in yaml.safe_load(p.read_text(encoding="utf-8"))
    (tmp_path / "CHANGELOG.md").write_text("## [1.0]\n- x\n", encoding="utf-8")
    p.write_text("release: {changelog: CHANGELOG.md}\n", encoding="utf-8")
    assert LK.drop_missing_release(str(p)) is False


def _arc_film(cfg):
    c = _long_film(cfg, arc="launch", text=0.5)
    c["product"] = dict(cfg["product"], tagline=dict(en="The notes app that files itself", zh="自己归档的笔记"),
                        promise=dict(en="Write once, find anything.", zh="写一次，随处找到。"),
                        badges=dict(en=["Free", "Open source"], zh=["免费", "开源"]))
    c["features"][6] = dict(c["features"][6], chips="platforms")
    c["motion"] = dict(cfg["motion"], transition="mix")
    return c


def test_launch_arc_brand_card_reel_and_chapter_chips(cfg, shots):
    c = _arc_film(cfg)
    for asp in S.LAYOUTS:
        for lang in ("en", "zh"):
            p = S.plan(c, shots, "demo", lang, asp)
            sc = p["scenes"]
            lays = [s["layout"] for s in sc]
            assert p["arc"] == "launch" and S.adjacent_ok(sc), lays
            assert lays[0] == "brand" and lays[1] == "reel" and lays[-1] == "end", lays
            assert sc[0]["kicker"] and sc[0]["badges"] == (["免费", "开源"] if lang == "zh" else ["Free", "Open source"])
            reel = sc[1]
            assert 2 <= len(reel["panes"]) <= S.REEL_MAX and reel["text"]
            period, phase = p["beat"]
            for k, p0 in enumerate(reel["panes"]):           # every cut after the first lands on a beat
                assert p0["box"] == list(p["layout"]["reel"]["view"]) and p0["play"] > 0
                if k:
                    t = reel["start"] + p0["at"]
                    assert abs(((t - phase) / period) - round((t - phase) / period)) < 0.02
            chap = next(s for s in sc if s["layout"] == "chapter")
            red = "小红书" if lang == "zh" else "RedNote"            # the config's platforms, international first
            assert set(chap["chips"]) == {"YouTube Shorts", "TikTok", "X", "LinkedIn", red} and chap["chips"][-1] == red
    assert S.plan(_long_film(cfg), shots, "demo", "en", "16:9")["arc"] == "plain"


def test_reel_uses_same_feature_alternative_to_avoid_a_dark_pulse(tmp_path):
    from PIL import Image
    shots = {}
    for sid, luma in [("before", 235), ("ui", 230), ("result", 20), ("after", 238)]:
        still = tmp_path / f"{sid}.png"
        Image.new("RGB", (100, 60), (luma,) * 3).save(still)
        shots[sid] = dict(still=str(still))
    cfg = dict(features=[dict(id="a", shot="before"), dict(id="b", shot=["ui", "result"]), dict(id="c", shot="after")])
    panes = [dict(fid="a", sid="before"), dict(fid="b", sid="result"), dict(fid="c", sid="after")]
    S._reel_sources(cfg, panes, shots)
    assert [(p["fid"], p["sid"], p["k"]) for p in panes] == [("a", "before", 0), ("b", "ui", 0), ("c", "after", 0)]
    # With similarly exposed neighbours, the intended result stays selected,
    # and its per-shot trim uses its actual index rather than the first trim.
    for sid in ("before", "after"):
        Image.new("RGB", (100, 60), (25,) * 3).save(shots[sid]["still"])
    panes[1]["sid"] = "result"
    S._reel_sources(cfg, panes, shots)
    assert panes[1]["sid"] == "result" and panes[1]["k"] == 1


def test_reel_shows_a_normal_speed_result_window(cfg, shots):
    plan = S.plan(_arc_film(cfg), shots, "demo", "en", "16:9")
    reel = next(s for s in plan["scenes"] if s["layout"] == "reel")
    for pane in reel["panes"]:
        assert pane["media"]["segs"]
        assert all(rate <= 1.0 for _, _, rate in pane["media"]["segs"])
        assert sum((b - a) / rate for a, b, rate in pane["media"]["segs"]) <= pane["play"] + .002


def test_new_macro_context_dissolves_but_a_continuation_stays_a_punch_in():
    plan = dict(transition="mix", scenes=[dict(layout="float", panes=[{}]), dict(layout="macro", panes=[{}])])
    assert CO.transition_of(plan, 1) == "crossfade"
    plan["scenes"][1]["panes"][0]["cont"] = True
    assert CO.transition_of(plan, 1) == "cut"
    plan["scenes"] = [dict(layout="macro", panes=[{}]), dict(layout="float", panes=[{}])]
    assert CO.transition_of(plan, 1) == "crossfade"


def test_launch_arc_builds_slam_tilt_log_camera_and_foley(cfg, shots, tmp_path):
    c = _arc_film(cfg)
    p = S.plan(c, shots, "demo", "en", "16:9")
    proj = str(tmp_path / "arc")
    CO.build(c, p, proj, quiet=True)
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    assert 'class="badge"' in html and 'class="chip"' in html and 'class="playhead"' in html
    assert 'ease: "back.out(2.2)"' in html                          # the headline slam
    assert "rotationY" in html and "transformPerspective" in html     # real UI in perspective
    assert "const lkCam" in html and 'lkCam("#s' in html             # log-space camera moves
    assert "scale: 2.9" in html                                      # the zoom-through into a card
    assert os.path.exists(os.path.join(proj, "assets", "audio", "sfx.wav")) and 'id="sfx"' in html
    cues = json.load(open(os.path.join(proj, "cues.json"), encoding="utf-8"))["cues"]
    assert any("The notes app that files itself" in q["text"] for q in cues)
    assert any("RedNote" in q["text"] for q in cues)
    plain = S.plan(_long_film(cfg), shots, "demo", "en", "16:9")
    CO.build(_long_film(cfg), plain, str(tmp_path / "plain"), quiet=True)
    ph = open(os.path.join(str(tmp_path / "plain"), "index.html"), encoding="utf-8").read()
    assert "rotationY" not in ph and 'id="sfx"' not in ph and "scale: 2.9" not in ph


def test_film_arc_is_validated(cfg):
    bad = dict(cfg, film=dict(cfg["film"], arc="epic"))
    assert any("film.arc" in e for e in C.validate(bad, check_files=False))


# ------------------------------------------------------------------------------------------------ the set, blocks
def _set_cfg(cfg, **film):
    c = _arc_film(cfg)
    c["films"] = [
        dict(id="hero", title="Hero", shots=[f["id"] for f in c["features"]], renders=["en:16:9", "zh:9:16"],
             film=dict(blocks=["waterfall", "lift", "reel"], text=0.3, **film), brand=dict(backdrop="cream"),
             type=dict(titles="heavy"), demo=dict(title_card=False)),
        dict(id="short", shots=["f1", "f3"], renders=["en:9:16"], demo=dict(min_seconds=12, max_seconds=22),
             film=dict(blocks=["hook"], cold_open=False, chapters=False, hook=dict(en="Hundreds of videos. One run.",
                                                                   zh="几百条视频，一次跑完。")))]
    c["make"] = ["films"]
    return c


def test_film_set_merges_each_film_and_names_its_jobs(cfg):
    from vstudio.launch import kit as K
    c = _set_cfg(cfg)
    assert C.validate(c, check_files=False) == []
    hero, short = C.film_cfg(c, "hero"), C.film_cfg(c, "short")
    assert hero["brand"]["backdrop"] == "cream" and hero["brand"]["colors"] == c["brand"]["colors"]   # deep merge
    assert hero["film"]["blocks"] == ["waterfall", "lift", "reel"] and hero["film"]["arc"] == "launch"
    assert short["demo"]["shots"] == ["f1", "f3"] and short["demo"]["max_seconds"] == 22
    assert C.films(c) == [("hero", [("en", "16:9"), ("zh", "9:16")]), ("short", [("en", "9:16")])]
    names = [j[0] for j in K.jobs(c)]
    assert names == ["hero-en-16x9", "hero-zh-9x16", "short-en-9x16"]
    assert all(j[1] == "film" and "/films/" in j[5] for j in K.jobs(c))
    assert [j[0] for j in K.jobs(c, ["short"])] == ["short-en-9x16"]
    bad = dict(c, films=[dict(id="x", shots=["nope"], renders=["fr:16:9"], film=dict(blocks=["fireworks", "hook"]),
                              colour="red"), dict(id="x")])
    errs = " | ".join(C.validate(bad, check_files=False))
    for want in ("unique id", "unknown feature 'nope'", "language 'fr'", "film.blocks", "film.hook", "unknown key"):
        assert want in errs, (want, errs)
    assert any("make: films" in e for e in C.validate(dict(c, films=[]), check_files=False))


def test_blocks_open_the_film_and_text_counts_after_the_wordmark(cfg, shots):
    c = _set_cfg(cfg)
    for asp in S.LAYOUTS:
        p = S.plan(C.film_cfg(c, "hero"), shots, "demo", "en", asp)
        lays = [s["layout"] for s in p["scenes"]]
        assert lays[:4] == ["full", "waterfall", "lift", "reel"] and lays[-1] == "end", lays
        assert S.adjacent_ok(p["scenes"]) and p["text_share"] <= 0.3 + 1e-6
        wf = p["scenes"][1]
        span = next(x for x in S.text_spans(p["scenes"], p["xf"]) if x[0] >= wf["start"])
        assert abs(span[0] - (wf["start"] + S.WATERFALL_TEXT)) < 1e-6         # no words while the tiles pour
        lift = p["scenes"][2]
        assert lift["words"] == ["Create", "Edit", "Publish"] and lift["platforms"][:2] == ["youtube", "tiktok"]
    pz = S.plan(C.film_cfg(c, "hero"), shots, "demo", "zh", "9:16")
    assert pz["scenes"][2]["words"] == ["做", "剪", "发"]
    ps = S.plan(C.film_cfg(c, "short"), shots, "demo", "en", "9:16")
    assert "chapter" not in [s["layout"] for s in ps["scenes"]]                 # a short has no chapter cards
    assert [s["layout"] for s in ps["scenes"]][0] == "hook" and ps["scenes"][0]["text"] == "Hundreds of videos. One run."
    assert 12 <= ps["duration"] <= 22
    assert any("Hundreds of videos" in q["text"] for q in S.caption_cues(ps))
    plain = S.plan(_arc_film(cfg), shots, "demo", "en", "16:9")              # default blocks: brand + reel, as before
    assert [s["layout"] for s in plain["scenes"]][:2] == ["brand", "reel"]


def test_mosaic_tiles_sit_on_the_letters():
    from vstudio.launch import blocks as BL
    from PIL import Image
    cells, (cw, ch), word = BL.mosaic("Reelfold", B.INTER, 880, (1920, 1080), (200, 380, 1520, 320), target=360)
    assert 220 <= len(cells) <= 520 and abs(cw / ch - 16 / 9) < 0.01
    assert 190 <= word["x"] and word["x"] + word["w"] <= 1730 and word["px"] > 250
    a = word["img"].split()[3].resize((int(word["w"]), int(word["h"])), Image.BILINEAR)
    on = sum(1 for cx, cy in cells if a.getpixel((min(a.width - 1, int(cx - word["x"])),
                                                   min(a.height - 1, int(cy - word["y"])))) > 60)
    assert on / len(cells) > 0.8                               # tiles land on the solid wordmark's pixels
    xs = [x for x, _ in cells]
    assert min(xs) > 180 and max(xs) < 1760


def test_blocks_build_waterfall_lift_hook_on_a_cream_stage(cfg, shots, tmp_path):
    c = _set_cfg(cfg)
    hero = C.film_cfg(c, "hero")
    proj = str(tmp_path / "hero")
    CO.build(hero, S.plan(hero, shots, "demo", "en", "16:9"), proj, quiet=True)
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    assert html.count('class="tile"') > 150 and "assets/thumbs/t000-" in html
    assert 'src="assets/brand/wordmark-1920x1080.png"' in html
    assert os.path.exists(os.path.join(proj, "assets", "brand", "wordmark-1920x1080.png"))
    assert 'class="pmark"' in html and html.count('class="pm"') == 9 and ">Publish<" in html
    assert 'font-family: "LK-zh-heavy"' in html   # Chinese platform marks have a staged face in the English film
    assert "PingFang SC" not in html
    assert "font-weight: 880" in html and "--lk-flat:#F2ECE3" in html                 # heavy type, cream stage
    assert 'class="center chap heavy"' in html                                       # heavy chapter titles
    assert 'ease: "power2.in"' in html and "yPercent: 115" in html
    # the stage is never an empty backdrop: the thumbnails and the platform marks start moving in with the scene
    for lay, part in (("waterfall", "t"), ("lift", "p")):
        sid, st = re.search(r'id="(s\d+)" data-start="([\d.]+)"[^>]*data-layout="%s"' % lay, html).groups()
        first = min(float(x) for x in re.findall(r'tl\.fromTo\("#%s%s\d+", [^;]*, ([\d.]+)\);' % (sid, part), html))
        assert first - float(st) <= 0.1, (lay, st, first)
    short = C.film_cfg(c, "short")
    sp = str(tmp_path / "short")
    CO.build(short, S.plan(short, shots, "demo", "en", "9:16"), sp, quiet=True)
    sh = open(os.path.join(sp, "index.html"), encoding="utf-8").read()
    assert 'class="type heavy"' in sh and 'scale: 1.5' in sh
    two = C.film_cfg(dict(c, films=[dict(c["films"][1], film=dict(c["films"][1]["film"],
                                                                     hook=dict(en="Open source.\nOn your Mac.")))]),
                     "short")
    tp = str(tmp_path / "two")
    CO.build(two, S.plan(two, shots, "demo", "en", "9:16"), tp, quiet=True)
    th = open(os.path.join(tp, "index.html"), encoding="utf-8").read()
    assert th.count('<span class="ln">') >= 2 and ">source.<" in th                 # her line breaks are kept


def test_review_page_and_contact_sheet(cfg, kitdir, tmp_path):
    from vstudio.launch import kit as K
    c = dict(_set_cfg(cfg), out=str(tmp_path))
    os.makedirs(tmp_path / "films")
    v = str(tmp_path / "films" / "short-en-9x16.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=30:d=3", "-pix_fmt",
                    "yuv420p", v], check=True)
    K.sheet(v, v[:-4] + ".sheet.jpg")
    from PIL import Image
    with Image.open(v[:-4] + ".sheet.jpg") as im:
        assert im.width > 1000
    page = open(K.review_page(c), encoding="utf-8").read()
    assert "films/short-en-9x16.mp4" in page and "short-en-9x16.sheet.jpg" in page and "not rendered yet" in page


def test_imported_bare_media_uses_exact_inputs_link_and_preserves_explicit_paths(tmp_path):
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    (inputs / 'demo.mp4').write_bytes(b'video')
    (inputs / 'screen.png').write_bytes(b'image')
    assert C._input_abs(str(tmp_path), 'demo.mp4') == str(inputs / 'demo.mp4')
    assert C._input_abs(str(tmp_path), 'screen.png') == str(inputs / 'screen.png')
    assert C._input_abs(str(tmp_path), 'missing.mp4') == str(tmp_path / 'missing.mp4')
    assert C._input_abs(str(tmp_path), 'other/demo.mp4') == str(tmp_path / 'other/demo.mp4')
    assert C._input_abs(str(tmp_path), '/external/demo.mp4') == '/external/demo.mp4'
    # A file next to the config wins; do not silently replace it with the imported take.
    (tmp_path / 'demo.mp4').write_bytes(b'another video')
    assert C._input_abs(str(tmp_path), 'demo.mp4') == str(tmp_path / 'demo.mp4')


def test_config_load_resolves_old_bare_imports_without_rewriting_file(tmp_path):
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    (inputs / 'demo.mp4').write_bytes(b'video')
    (inputs / 'screen.png').write_bytes(b'image')
    p = tmp_path / 'launch.config.yaml'
    raw = dict(product=dict(name='Example', one_liner=dict(en='Real recordings')),
               languages=['en'], capture=dict(clips=[dict(id='take',file='demo.mp4')],
               images=[dict(id='screen',file='screen.png')]),
               features=[dict(id='demo',shot='take',caption=dict(en='Create a video'))])
    p.write_text(yaml.safe_dump(raw))
    before=p.read_bytes()
    cfg=C.load(str(p))
    assert cfg['capture']['clips'][0]['file'] == str(inputs/'demo.mp4')
    assert cfg['capture']['images'][0]['file'] == str(inputs/'screen.png')
    assert p.read_bytes() == before
