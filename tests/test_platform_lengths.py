"""Platform-specific lengths: every platform's habits live in references/platforms/<name>.md (front matter), persona
and Settings › Publishing override them; a goal video gets a length per platform (capped by its footage) and one cut
per length; the intake makes one item per cut (a long and a short render of one project); a short AI script is
extended (fake model); a beat short never ships under 20 s. Her DJI goal had every platform version at one length
(history 80-106 s, films 52-93 s, reels 13-28 s) and an AI script 80 s for 120."""
import json
import os
import shutil
import subprocess

import pytest

from vstudio import platform as P
from vstudio import platform_habits as H
from vstudio import topup as TU
from vstudio.intake import goal as G
from vstudio.intake import rules as R


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_LLM_PROVIDER", "none")
    monkeypatch.setenv("VSTUDIO_LLM_INTAKE_PROVIDER", "none")


# --------------------------------------------------------------------------- profiles
def test_every_platform_has_a_profile_file_with_sane_bands():
    for n in P.ORDER:
        assert os.path.isfile(H.path_of(n)), n
        h = H.habits(n)
        assert h["source"] == "file" and h["platform"] == n and h["form"] in ("long", "short")
        hard = P.PLATFORMS[n]["length"]
        for k in H.KINDS:
            b = H.band(n, k)
            assert b["min"] <= b["target"] <= b["max"], (n, k, b)
            assert hard.get("min", 0) <= b["min"] and b["max"] <= hard["max"], (n, k, b)
            if k == "reel" and hard["max"] >= 20:
                assert b["min"] >= 20, (n, b)
    assert H.form("youtube") == H.form("bilibili") == "long"
    assert {H.form(p) for p in ("youtube-shorts", "tiktok", "douyin", "xiaohongshu", "instagram", "linkedin")} == {"short"}
    assert H.band("youtube", "history")["chapters"] and not H.band("youtube-shorts", "history")["chapters"]
    assert H.band("youtube-shorts", "history")["max"] <= 180                # the Shorts hard limit holds


def test_persona_and_settings_override_a_platform(tmp_path, monkeypatch):
    from vstudio import config
    pf = tmp_path / "persona.yaml"
    pf.write_text("platforms:\n  xiaohongshu:\n    lengths:\n      film: [40, 100, 150]\n    chapters: {use: true}\n")
    monkeypatch.setenv("VSTUDIO_PERSONA", str(pf))
    config.persona.cache_clear()
    try:
        b = H.band("xiaohongshu", "film")
        assert (b["min"], b["target"], b["max"], b["source"]) == (40, 100, 150, "persona")
        H.set_limits("xiaohongshu", max_s=90)                                  # Settings › Publishing wins
        b = H.band("xiaohongshu", "film")
        assert b["max"] == 90 and b["target"] == 90 and b["source"] == "settings"
        assert json.load(open(H.settings_path()))["platforms"]["xiaohongshu"] == {"max_s": 90}
        H.set_limits("xiaohongshu", reset=True)
        assert H.band("xiaohongshu", "film")["target"] == 100
        with pytest.raises(ValueError):
            H.set_limits("youtube-shorts", max_s=600)                          # over the 3 min Shorts limit
        with pytest.raises(ValueError):
            H.set_limits("youtube", min_s=600, max_s=300)
        with pytest.raises(ValueError):
            H.set_limits("myspace", max_s=60)
    finally:
        monkeypatch.delenv("VSTUDIO_PERSONA")
        config.persona.cache_clear()


def test_a_broken_profile_file_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "DIR", str(tmp_path))
    (tmp_path / "youtube.md").write_text("---\nlengths: [oops\n---\n")
    b = H.band("youtube", "film")                       # the platform's own sweet spot, never a crash
    assert b["min"] <= b["target"] <= b["max"] and H.habits("snapchat")["source"] == "builtin"


# --------------------------------------------------------------------------- per-platform lengths
def test_lengths_differ_per_platform_and_group_into_cuts():
    plats = ["youtube", "bilibili", "xiaohongshu", "youtube-shorts", "tiktok"]
    L = H.lengths(plats, "history")
    assert L["youtube"] == L["bilibili"] >= 240 and L["xiaohongshu"] == L["youtube-shorts"] == L["tiktok"] <= 90
    cuts = H.cuts(plats, L, "history")
    assert [c["id"] for c in cuts] == ["long", "short"] and cuts[0]["chapters"] and not cuts[1]["chapters"]
    assert cuts[0]["platforms"] == ["youtube", "bilibili"] and cuts[1]["length_s"] == L["tiktok"]
    capped = H.lengths(plats, "history", footage_max=100)                       # the footage carries 100 s
    assert capped["youtube"] == 100 and capped["xiaohongshu"] <= 100
    assert H.lengths(["youtube", "xiaohongshu"], "film", asked=120) == {"youtube": 120, "xiaohongshu": 120}
    assert H.lengths(["youtube-shorts"], "film", asked=600) == {"youtube-shorts": 180}   # only hard limits clamp hers
    assert min(H.lengths(["tiktok", "xiaohongshu"], "reel", footage_max=13).values()) >= 20   # a reel: 20 s at least
    assert [c["id"] for c in H.cuts(["x"], {"x": 45})] == ["main"]
    assert H.fmt_len(90) == "90 s" and H.fmt_len(240) == "4 min" and H.fmt_len(330, "zh") == "5.5 分钟"


def _doc(seconds_per_clip=60.0, clips=8):
    st = dict(id="s1", videos=clips, photos=0, panoramas=0, seconds=seconds_per_clip * clips, aerial=True,
              clips=[f"/nowhere/DJI_{k:04d}.MP4" for k in range(clips)], clip_secs=[seconds_per_clip] * clips,
              place=dict(en="Seattle", zh="西雅图", km=1.0), stills=[])
    return st, {"s1": st}


def test_goal_video_gets_a_length_per_platform_and_its_cuts():
    st, by_id = _doc()
    v = G._finish_video(dict(title="Elliott Bay", kind="history", stories=["s1"], brief="the waterfront"), by_id,
                        ["youtube", "xiaohongshu", "bilibili"], lang="en")
    assert v["possible_s"] > 300 and v["possible"].startswith("about ") and "min possible" in v["possible"]
    assert v["lengths"]["youtube"] == v["lengths"]["bilibili"] > v["lengths"]["xiaohongshu"]
    assert [c["id"] for c in v["cuts"]] == ["long", "short"] and v["length_s"] == v["lengths"]["youtube"]
    assert f"Cuts: {v['lengths']['youtube']} s for YouTube and Bilibili (long cut, chapters); " \
           f"{v['lengths']['xiaohongshu']} s for Xiaohongshu (short cut)." in v["request"]
    assert v["request"].endswith("Export for YouTube, Xiaohongshu and Bilibili.")
    # the request's per-platform lengths come back out of its words (the intake reads them)
    assert R.cut_lengths(v["request"]) == v["lengths"]
    # thin footage caps every platform; a reel never under 20 s
    st2, by2 = _doc(seconds_per_clip=8.0, clips=2)
    thin = G._finish_video(dict(title="Pier", kind="film", stories=["s1"]), by2, ["youtube", "xiaohongshu"])
    assert thin["possible_s"] < 20 and max(thin["lengths"].values()) <= 20 and len(thin["cuts"]) == 1
    assert "Cuts:" not in thin["request"]
    reel = G._finish_video(dict(title="Jet ski", kind="reel", stories=["s1"]), by2, ["youtube", "tiktok"])
    assert reel["platforms"] == ["youtube-shorts", "tiktok"] and min(reel["lengths"].values()) >= 20
    zh = G._finish_video(dict(title="x", kind="film", stories=["s1"]), by_id, ["youtube"], lang="zh")
    assert zh["possible"].startswith("素材够做约")


def test_goal_footage_estimate_reads_analysed_moments(monkeypatch):
    from vstudio import shots as SH
    a = dict(shots=[dict(i=1, start=0, end=60, moments=[dict(i=k + 1, start=k * 12.0, end=k * 12.0 + 12, score=s,
                                                             best=[k * 12.0, k * 12.0 + 4]) for k, s in
                                                        enumerate([0.9, 0.8, 0.1, 0.7, 0.2])])])
    monkeypatch.setattr(SH, "cached", lambda p, backend="auto": a)
    st, by_id = _doc(seconds_per_clip=60.0, clips=1)
    assert G.footage_max([st], "film") == int(round(3 * 8.0 * 0.8))           # 3 usable moments x 8 s, little variety
    assert G.footage_max([st], "history") > G.footage_max([st], "film")         # a voice holds a shot longer


def test_plan_card_edits_lengths_per_platform():
    st, by_id = _doc()
    v = G._finish_video(dict(id="v1", title="Bay", kind="film", stories=["s1"]), by_id,
                        ["youtube", "xiaohongshu", "bilibili"])
    doc = dict(kind=G.KIND, survey=dict(stories=[st]), videos=[v], platforms=["youtube", "xiaohongshu", "bilibili"],
               ui_lang="en")
    doc = G.edit_goal(doc, [{"op": "length", "video": "v1", "platform": "bilibili", "length_s": 600}])
    v = doc["videos"][0]
    assert v["lengths"]["bilibili"] == 600 and v["lengths"]["youtube"] < 600 and len(v["cuts"]) == 3
    assert v["lengths_own"] == {"bilibili": 600} and "600 s for Bilibili" in v["request"]
    short = next(c["id"] for c in doc["videos"][0]["cuts"] if "xiaohongshu" in c["platforms"])
    doc = G.edit_goal(doc, [{"op": "length", "video": "v1", "cut": short, "length_s": 75}])
    assert doc["videos"][0]["lengths"]["xiaohongshu"] == 75
    doc = G.edit_goal(doc, [{"op": "kind", "video": "v1", "kind": "history"}])    # her numbers survive a kind change
    assert doc["videos"][0]["lengths"]["bilibili"] == 600
    doc = G.edit_goal(doc, [{"op": "platforms", "platforms": ["youtube", "xiaohongshu"]}])
    assert "bilibili" not in doc["videos"][0]["lengths_own"]
    doc = G.edit_goal(doc, [{"op": "length", "video": "v1", "length_s": 90}])    # no platform: every platform
    assert set(doc["videos"][0]["lengths"].values()) == {90} and len(doc["videos"][0]["cuts"]) == 1
    with pytest.raises(ValueError):
        G.edit_goal(doc, [{"op": "length", "video": "v1", "platform": "tiktok", "length_s": 60}])
    with pytest.raises(ValueError):
        G.edit_goal(doc, [{"op": "length", "video": "v1", "length_s": 5}])


def test_cut_lengths_in_her_own_words():
    assert R.cut_lengths("YouTube 5 min，小红书 60 秒，B站：8分钟") == {"youtube": 300, "xiaohongshu": 60, "bilibili": 480}
    assert R.cut_lengths("做一个 60 秒的视频发小红书") == {}
    assert R.parse_prompt("Cuts: 30 s for YouTube Shorts (short cut); 240 s for YouTube (long cut).")[
        "platform_lengths"] == {"youtube-shorts": 30, "youtube": 240}


# --------------------------------------------------------------------------- one story -> a long and a short cut
@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    if not shutil.which("ffmpeg"):
        pytest.skip("needs ffmpeg")
    p = str(tmp_path_factory.mktemp("clips") / "DJI_20260611200000_0001_D.MP4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", p], check=True)
    return p


def test_one_project_renders_a_long_and_a_short_cut(clip, tmp_path):
    from vstudio.intake import apply as AP
    from vstudio.intake import plan as PL
    from vstudio.project.core import Project
    prompt = ("Make a 300-second cinematic film from these drafted shots. Cuts: 300 s for Bilibili (long cut, "
              "chapters); 60 s for Xiaohongshu (short cut). Export for Xiaohongshu and Bilibili.")
    plan = PL.make_plan(prompt, [clip], recipe="vlog", asr="off")
    (p,) = [x for x in plan["projects"] if x["recipe"] == "vlog"]
    rows = p["items"]["rows"]
    assert [r["id"] for r in rows] == ["long", "short"]
    assert rows[0]["params"] == dict(platforms=[x for x in p["params"]["platforms"] if x.startswith("bilibili")],
                                     length_s=300, cut="long")
    assert rows[1]["params"]["length_s"] == 60 and rows[1]["params"]["platforms"][0].startswith("xiaohongshu")
    assert p["outputs"]["videos"] == 2
    res = AP.apply_plan(plan, str(tmp_path / "out"))
    pr = Project(res["projects"][0]["dir"])
    jobs = {r["id"]: r for r in pr.jobs_rows()}
    assert set(jobs) == {"long", "short"}                   # one project, two renders - each its own length
    assert jobs["long"]["length_s"] == 300 and jobs["short"]["length_s"] == 60
    assert jobs["long"]["cut"] == "long" and jobs["short"]["platforms"][0].startswith("xiaohongshu")
    # each cut's drafter is told which cut it writes
    assert "LONG cut" in H.cut_note(jobs["long"]) and "SHORT cut" in H.cut_note(jobs["short"])
    assert H.cut_note(dict(cut="main")) == ""


def test_a_single_length_sets_the_project_length(clip):
    from vstudio.intake import plan as PL
    plan = PL.make_plan("Make a film. Cuts: 45 s for TikTok (short cut). Export for TikTok.", [clip], recipe="vlog",
                        asr="off")
    (p,) = plan["projects"]
    assert p["params"]["length_s"] == 45 and not p["items"].get("rows")


# --------------------------------------------------------------------------- script top-up (fake model)
SHORT_SPEC = '''TITLE_EN = "Elliott Bay"
SCRIPT = [
    (1, [("Pier 86 sits on the north shore of the bay.", "86号码头位于海湾北岸。")], [("vCLIP", 1, "still", dict(off=2))]),
]
COVER = dict(title="Elliott Bay", hero=dict(src="cover_a"))
'''


def _long_spec(units):
    rows = ",\n".join(f'    ({k + 1}, [("The waterfront grew around the piers and the rail line along the shore, '
                      f'part {k + 1}.", "海滨沿着码头和铁路成长。")], [("vCLIP", 1, "still", dict(off={k}))])'
                      for k in range(units))
    return f'TITLE_EN = "Elliott Bay"\nSCRIPT = [\n{rows},\n]\nCOVER = dict(title="Elliott Bay", hero=dict(src="cover_a"))\n'


def _ps_ctx(tmp_path, request):
    from vstudio.project import drafts as DR
    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    (proj / "project.yaml").write_text(f"name: Elliott Bay\nprompt: {request}\n")
    ctx = DR.Ctx(str(proj), "en", dict(_inputs={}, platforms=["youtube"], length_s=60), "photo-story")
    os.makedirs(os.path.join(ctx.item_dir, "work", "frames"))
    for n in ("cover_a", "vCLIP"):
        with open(os.path.join(ctx.item_dir, "work", "frames", f"{n}.jpg"), "wb") as f:
            f.write(b"jpg")
    return ctx


def test_short_ai_script_is_extended_with_facts_checked(tmp_path, monkeypatch):
    from vstudio import factguard as FG
    from vstudio.project.adapters import photostory as PS
    monkeypatch.setattr(PS, "add_respellings", lambda text, complete: text)
    ctx = _ps_ctx(tmp_path, "a history of the Elliott Bay waterfront, narrated in English")
    calls = []

    def complete(task, system, body, **kw):
        calls.append(body)
        if system is FG.SYSTEM:
            return dict(json=dict(claims=[]), provider="claude-code", model="t")
        if "EXTEND it" in body:
            return dict(json=dict(content=_long_spec(9), summary="longer"), provider="claude-code", model="t")
        return dict(json=dict(content=SHORT_SPEC, summary="A short history."), provider="claude-code", model="t")
    path = os.path.join(ctx.item_dir, "work", "spec.py")
    rec = PS.draft_spec(ctx, dict(id="story", author={}), path, complete=complete)
    L = rec["length"]
    assert L["target_s"] == 60 and L["first_s"] < 10 and L["final_s"] >= 51 and L["rounds"] == 1 and not L["short"]
    assert "part 9" in open(path, encoding="utf-8").read() and "script extended" in rec["review"]["summary"][
        "params"]["text"]
    assert sum("EXTEND it" in b for b in calls) == 1 and "verifiable" in next(b for b in calls if "EXTEND it" in b)
    assert any(FG.SYSTEM is not None and "Elliott" in b for b in calls)


def test_a_script_that_stays_short_says_so(tmp_path, monkeypatch):
    from vstudio.project.adapters import photostory as PS
    monkeypatch.setattr(PS, "add_respellings", lambda text, complete: text)
    ctx = _ps_ctx(tmp_path, "a history of the Elliott Bay waterfront, narrated in English")
    n = []

    def complete(task, system, body, **kw):
        n.append(1)
        return dict(json=dict(content=SHORT_SPEC, summary="short", claims=[]), provider="claude-code", model="t")
    rec = PS.draft_spec(ctx, dict(id="story", author={}), os.path.join(ctx.item_dir, "work", "spec.py"),
                        complete=complete)
    assert rec["length"]["rounds"] == 2 and rec["length"]["short"]          # two rounds, then it says so
    assert "still short" in rec["review"]["summary"]["params"]["text"]
    assert TU.note(rec["length"], "zh").startswith("脚本仍偏短")


def test_topup_loop_keeps_the_longest_and_stops_on_failure():
    seen = []
    best, rec = TU.extend("a", 100, measure=len, redraft=lambda t, e, k: seen.append(k) or ("a" * 40 if k == 1 else None))
    assert best == "a" * 40 and rec["rounds"] == 2 and rec["short"] and seen == [1, 2]
    best, rec = TU.extend("a" * 90, 100, measure=len, redraft=lambda *a: "never")
    assert best == "a" * 90 and rec["rounds"] == 0 and not rec["short"]        # within 15 %: left alone
    assert TU.extend("", 100, measure=len, redraft=lambda *a: "x") == ("", None)


def test_explainer_length_comes_from_the_cut():
    from vstudio.project.adapters import explainer as EX
    assert EX.target_minutes(dict(length_s=300), "a 2 min explainer") == 5.0
    assert EX.target_minutes({}, "a 2 min explainer") == 2.0


# --------------------------------------------------------------------------- beat shorts: 20 s at least
def test_reel_minimum_and_padding():
    from vstudio.project.adapters import vlog as V
    assert V.reel_min_s(["tiktok", "youtube-shorts"]) == 20 and V.reel_min_s(["x"]) == 20
    shots = [dict(clip="a", start=1.0, beats=2, place="Bay"), dict(clip="b", start=4.0, beats=1)]
    out = V.pad_shots(shots, 6, {"a": dict(dur=12.0), "b": dict(dur=12.0, moments=[dict(best=[8.0, 12.0], score=.9)])})
    assert out[:2] == shots and sum(s.get("beats", 2) for s in out) - 3 >= 6       # more moments, hers unchanged
    assert dict(clip="b", start=8.0, beats=2) in out                               # the clip's best unused moment
    tiny = V.pad_shots([dict(clip="a", start=0.0, beats=1)], 3, {"a": dict(dur=1.0)})
    assert tiny == [dict(clip="a", start=0.0, beats=4)]                             # nowhere new: longer holds


def test_a_reel_rendered_too_short_is_recut(tmp_path, monkeypatch):
    from vstudio.project.adapters import vlog as V
    edit = tmp_path / "edit.json"
    edit.write_text(json.dumps(dict(style="fun", src_dir=".", clips={"a": "a.mp4"}, shots=[dict(clip="a", start=1.0,
                                                                                                    beats=2)])))
    (tmp_path / "a.mp4").write_bytes(b"x")
    lens = iter([13.0, 12.0, 24.0])
    renders = []
    monkeypatch.setattr(V, "_duration", lambda p: next(lens))
    monkeypatch.setattr(V, "_render_once", lambda env, path, cfg, plats: renders.append(len(cfg["shots"])) or dict(
        master=str(tmp_path / "fun_vlog.mp4")))
    res = V._reel_minimum(None, str(edit), dict(master=str(tmp_path / "fun_vlog.mp4")), ["tiktok"])
    assert renders and renders[0] > 1 and res["recut"]["first_s"] == 13.0 and res["recut"]["final_s"] == 24.0
    assert "short" not in res and len(json.load(open(edit))["shots"]) > 1
