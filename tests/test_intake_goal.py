"""Goal mode in the engine (vstudio.intake.goal): a goal-style request -> a read-only survey of a DJI-like card
(stories by time + place + light, DJI .SRT GPS, panorama folders) -> a plan of several videos, each with its own
intake request; the plan card's edits rebuild the requests."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from vstudio.intake import goal as G

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

SEATTLE = (47.62050, -122.34930)
KIRKLAND = (47.68150, -122.20870)       # ~12 km from the first spot: another story


def _srt(path, stamp, lat, lon, n=3):
    blocks = []
    for k in range(n):
        blocks.append(f"{k + 1}\n00:00:0{k},000 --> 00:00:0{k},033\n<font size=\"28\">FrameCnt: {k + 1}\n"
                      f"{stamp}.{k:03d}\n[iso: 100] [latitude: {lat + k * 1e-4:.5f}] [longitude: {lon:.5f}] "
                      f"[rel_alt: 80.000 abs_alt: 120.0] </font>\n")
    with open(path, "w") as f:
        f.write("\n".join(blocks))


def _clip(path, color, secs=8):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=10:d={secs}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True)


@pytest.fixture(scope="module")
def card(tmp_path_factory):
    """A small DJI card: an evening by the Space Needle, a bright noon at Kirkland, the same spot after dark (light
    split), and a panorama tile folder."""
    root = tmp_path_factory.mktemp("card") / "DCIM"
    d = root / "DJI_001"
    d.mkdir(parents=True)
    shots = [("20260611200000", "0001", SEATTLE, "#c08040"), ("20260611200500", "0002", SEATTLE, "#b07038"),
             ("20260612120000", "0003", KIRKLAND, "#e0e0e0"), ("20260612121000", "0004", KIRKLAND, "#d8d8d8"),
             ("20260612124500", "0005", KIRKLAND, "#080808"), ("20260612125000", "0006", KIRKLAND, "#0a0a0a")]
    for ts, n, (lat, lon), color in shots:
        stem = d / f"DJI_{ts}_{n}_D"
        _clip(str(stem) + ".MP4", color)
        _srt(str(stem) + ".SRT", f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}", lat, lon)
    pano = root / "PANORAMA" / "001_0007"
    pano.mkdir(parents=True)
    from PIL import Image
    for k in range(3):
        Image.new("RGB", (64, 48), (90, 120, 200)).save(pano / f"PANO_{k + 1:04d}.JPG")
    return str(root)


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_LLM_PROVIDER", "none")
    monkeypatch.setenv("VSTUDIO_LLM_INTAKE_PROVIDER", "none")


def _listing(root):
    return sorted((os.path.relpath(os.path.join(dp, f), root), os.path.getsize(os.path.join(dp, f)))
                  for dp, _dn, fns in os.walk(root) for f in fns)


def test_goal_requests_are_recognised(card):
    hers = (f"在尝试帮我做多个dji航拍视频的剪辑吧，在{card}，可以先归纳一下，然后几个类似的做视频，可以尝试并行做多个视频，"
            "每个视频的主题可以不同")
    assert G.paths_in(hers) == [card]
    assert G.is_goal(hers)
    assert G.is_goal("Make several videos from this card, each with a different theme", [card])
    assert not G.is_goal("把这条视频剪成小红书竖屏", [card])                       # one request
    assert not G.is_goal("make several videos about AI")                          # nothing to survey
    assert G.wanted("做3个视频") == 3 and G.wanted("make five videos") == 5 and G.wanted("尽量多做几个") is None
    # her own words: about 12, at least 10, at most 15 (never cut to the old cap of 8)
    assert G.wanted_range("做 12 条左右成片，最少 10 条，最多 15 条。按 90–120 秒讲解") == dict(want=12, min=10, max=15)
    assert G.wanted_range("make 10-15 videos from my card") == dict(want=None, min=10, max=15)
    assert G.wanted_range("about 12 videos") == dict(want=12, min=10, max=14)
    assert G.wanted_range("做3个视频") == dict(want=3, min=3, max=3)


def test_survey_splits_stories_by_time_place_and_light(card):
    before = _listing(card)
    sc = G.scan([card])
    kinds = sorted(x["kind"] for x in sc["items"])
    assert kinds.count("video") == 6 and kinds.count("panorama") == 1 and "photo" not in kinds   # tiles: 1 panorama
    st = G.stories(sc, sheet_dir=os.path.join(os.environ["VSTUDIO_CACHE"], "sheets"))
    vids = [s for s in st if s["videos"]]
    assert [s["videos"] for s in vids] == [2, 2, 2]           # evening / noon / after dark (light split)
    assert vids[0]["place"]["en"] == "Seattle" and vids[0]["aerial"]
    assert vids[1]["light"] > 0.6 > 0.2 > vids[2]["light"]
    assert vids[0]["date"] == "2026-06-11" and vids[1]["date"] == "2026-06-12"
    assert any(s["panoramas"] == 1 for s in st)
    assert all(s.get("sheet") and os.path.exists(s["sheet"]) for s in vids)
    assert "GPS" in G.story_line(vids[0])
    assert _listing(card) == before                            # the card is never written to


def test_rule_plan_has_one_request_per_video(card):
    doc = G.make_goal(f"做多个视频 {card} youtube 小红书 B站", [], ui_lang="zh")
    assert doc["kind"] == G.KIND and doc["planner"]["fallback"]
    assert len(doc["videos"]) == 3
    for v in doc["videos"]:
        assert v["inputs"] and all(os.path.exists(p) for p in v["inputs"])
        assert v["platforms"] == ["youtube", "xiaohongshu", "bilibili"]
        assert "Chinese for Xiaohongshu and Bilibili, English for YouTube" in v["request"]
        assert v["request"].endswith("Export for YouTube, Xiaohongshu and Bilibili.")
        assert 15 <= v["length_s"] <= 180
    assert doc["goal"] == G.GOAL_LINE["zh"]
    assert doc["survey"]["totals"]["videos"] == 6


def test_model_plan_is_validated(card):
    seen = {}

    def call(system, body, images):
        seen.update(system=system, body=body, images=images)
        return dict(provider="test", json=dict(goal="Six DJI shorts", videos=[
            dict(title="Space Needle at dusk", title_zh="黄昏太空针", kind="history", stories=["s1"], length_s=500,
                 brief="the Space Needle, built for the 1962 World's Fair", theme="History", why="a landmark",
                 platforms=["youtube", "xiaohongshu"]),
            dict(title="Kirkland noon", kind="reel", stories=["s2", "s99"], length_s=30, brief="bright water",
                 platforms=["youtube"]),
            dict(title="Ghost", kind="film", stories=["s42"]),                       # no such story: left out
            dict(title="Pano", kind="photos", stories=["s4"]),                       # a panorama alone: not a video
            dict(title="Space needle at DUSK", kind="history", stories=["s1"])]))    # same story + angle: left out
    doc = G.make_goal("make several videos from my card", [card], call=call, ui_lang="en")
    assert not doc["planner"]["fallback"] and doc["goal"] == "Six DJI shorts"
    assert len(seen["images"]) >= 3 and "s1:" in seen["body"]
    h, r = doc["videos"]
    assert h["kind"] == "history" and "state only well-known, verifiable facts" in h["request"]
    assert "Narrate in Chinese for Xiaohongshu and in English for YouTube" in h["request"]
    assert h["length_s"] == 20                                 # never longer than the footage carries (16 s; floor 20)
    assert r["platforms"] == ["youtube-shorts"] and "Vertical first" in r["request"]
    assert r["stories"] == ["s2"]
    assert doc["survey"]["unused"] == dict(stories=["s3", "s4"], photos=0, panoramas=1)


def test_plan_card_edits_rebuild_the_requests(card):
    doc = G.make_goal(f"make several videos {card}", [], ui_lang="en")
    v1, v2, v3 = (v["id"] for v in doc["videos"])
    doc = G.edit_goal(doc, [{"op": "rename", "video": v1, "title": "Evening glow"},
                            {"op": "kind", "video": v1, "kind": "history"},
                            {"op": "merge", "videos": [v2, v3]},
                            {"op": "platforms", "platforms": ["youtube", "xiaohongshu"]}])
    a, b, c = doc["videos"]
    assert a["title"] == "Evening glow" and a["request"].startswith('Title: "Evening glow". Make a')
    assert "history explainer" in a["request"] and a["theme"] == G.THEME["history"]["en"]
    assert c["dropped"] and c["merged_into"] == b["id"] and len(b["inputs"]) == 4
    assert all("Export for YouTube and Xiaohongshu." in v["request"] for v in doc["videos"])
    with pytest.raises(ValueError):
        G.edit_goal(doc, [{"op": "kind", "video": v1, "kind": "opera"}])
    with pytest.raises(ValueError):
        G.edit_goal(doc, [{"op": "drop", "video": "v9"}])


def test_cli_goal(card, tmp_path):
    out = tmp_path / "goal.json"
    env = dict(os.environ, PYTHONPATH=os.path.join(os.path.dirname(__file__), "..", "lib"))
    r = subprocess.run([sys.executable, "-m", "vstudio.intake", "goal", "--prompt", f"make several videos {card}",
                        "--out", str(out), "--json", "--quiet"], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["videos"] and json.loads(out.read_text())["id"] == doc["id"]
    r = subprocess.run([sys.executable, "-m", "vstudio.intake", "goal-edit", "--goal", str(out), "--ops",
                        json.dumps([{"op": "drop", "video": "v1"}]), "--in-place", "--json"],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text())["videos"][0]["dropped"]
    r = subprocess.run([sys.executable, "-m", "vstudio.intake", "goal", "--prompt", "make several videos", "--json"],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 5 and json.loads(r.stdout)["code"] == "plan-empty"


def test_her_range_is_met_or_the_plan_says_why(card):
    """She asked for at least N: a rich story may carry two videos with their own angle, the stories no video uses
    are added (biggest first), and a plan still short of her minimum says so (``count.short``) with why."""
    seen = {}

    def call(system, body, images):
        seen["system"] = system
        return dict(provider="test", json=dict(goal="Drone set", videos=[
            dict(title="Golden hour on the bay", kind="film", stories=["s1"], brief="the light going"),
            dict(title="The bay after dark", kind="film", stories=["s1"], brief="the lit skyline"),   # own angle: kept
            dict(title="Jet ski", kind="reel", stories=["s2"], platforms=["youtube", "youtube-shorts", "xiaohongshu"])]))
    doc = G.make_goal(f"在 {card} 做 4 条左右成片，最少 3 条，最多 5 条", [], call=call, ui_lang="zh")
    assert "about 4; at least 3, at most 5" in seen["system"]
    titles = [v["title"] for v in doc["videos"]]
    assert titles[:3] == ["Golden hour on the bay", "The bay after dark", "Jet ski"]
    reel = doc["videos"][2]
    assert reel["platforms"] == ["youtube", "youtube-shorts", "xiaohongshu"]   # both named: both kept, never twice
    assert len(doc["videos"]) >= 3 and doc["count"]["min"] == 3 and doc["count"]["max"] == 5
    assert not doc["count"].get("short")
    # the stories no video uses fill up to her minimum
    doc = G.make_goal(f"在 {card} 做 3 条成片", [], call=lambda *a: dict(provider="test", json=dict(videos=[
        dict(title="Only one", kind="film", stories=["s1"])])), ui_lang="zh")
    assert len(doc["videos"]) == 3 and {s for v in doc["videos"] for s in v["stories"]} >= {"s1", "s2", "s3"}
    # more than the footage carries: the plan says it is short and why
    doc = G.make_goal(f"在 {card} 至少做 9 条视频", [], ui_lang="zh")
    assert doc["count"]["short"] and doc["count"]["min"] == 9 and doc["count"]["planned"] == len(doc["videos"]) < 9
    assert doc["count"]["photo_only"] >= 1


def test_the_platforms_she_names_win_over_the_composer_chip(card):
    """Her words name YouTube, 小红书 and B站: the composer's platform chip (TikTok, Instagram, X ...) never adds to
    them - each video, and so each language cut, is made for what she named."""
    doc = G.make_goal(f"做多个视频 {card}，发 YouTube、小红书和 B站", [], ui_lang="zh",
                      platforms=["youtube", "youtube-shorts", "tiktok", "instagram", "x", "xiaohongshu", "douyin"])
    assert doc["platforms"] == ["youtube", "xiaohongshu", "bilibili"]
    assert all(v["platforms"] == ["youtube", "xiaohongshu", "bilibili"] or v["kind"] == "reel" for v in doc["videos"])
    assert not any("tiktok" in v["platforms"] for v in doc["videos"])
