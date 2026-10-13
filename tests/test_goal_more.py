"""A made group gets more videos (vstudio.intake.goal.extend_goal, `intake goal-more`): new plan cards over the same
survey, cut only from the clips no video of the group plays yet (read from each made cut's edit list), the model's
ideas checked, the rules when no model answers; and what a made cut plays (edl_shots / used_in_project)."""
import json
import os
import subprocess
import sys

import pytest

from vstudio.intake import goal as G


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_LLM_PROVIDER", "none")
    monkeypatch.setenv("VSTUDIO_LLM_INTAKE_PROVIDER", "none")


def story(sid, place, n, secs=30.0, start="2026-06-22 20:00:00"):
    return dict(id=sid, place=dict(en=place, zh=place + "中文", km=1.0), date=start[:10], start=start, end=start,
                time_of_day="evening", videos=n, photos=0, panoramas=0, seconds=secs * n, aerial=True, vertical=0,
                light=0.4, geo=None, clips=[f"/card/{sid}_{k}.MP4" for k in range(n)], clip_secs=[secs] * n,
                stills=[], panorama_dirs=[], thumbs=[], folder="DJI_001", short_clips=0, sheet=None)


def doc_of():
    st = [story("s1", "Seattle", 4), story("s2", "Kirkland", 3, start="2026-06-23 12:00:00"),
          story("s3", "Tacoma", 2, start="2026-06-24 09:00:00")]
    by = {s["id"]: s for s in st}
    vids = []
    for k, (sid, title) in enumerate((("s1", "The Needle After Dark"), ("s2", "Kirkland Noon")), 1):
        v = dict(id=f"v{k}", title=title, title_zh=title, kind="film", stories=[sid], brief="b", theme="t", why="w",
                 platforms=["youtube", "xiaohongshu"])
        vids.append(G._finish_video(v, by, ["youtube", "xiaohongshu"]))
    return dict(kind=G.KIND, version=1, id="g", prompt="做 12 条左右，最少 10 条", inputs=["/card"], ui_lang="en",
                platforms=["youtube", "xiaohongshu"], survey=dict(stories=st, totals={}, unused={}), videos=vids,
                count=dict(asked=12, min=10, max=14, planned=2), planner=dict(provider="none", fallback=True))


def test_rest_stories_leave_out_the_used_clips():
    d = doc_of()
    rest = {s["id"]: s for s in G.rest_stories(d, ["/card/s1_0.MP4", "/card/s1_1.MP4", "/card/s3_0.MP4",
                                                   "/card/s3_1.MP4"])}
    assert set(rest) == {"s1", "s2"}                               # s3: every clip is played already
    assert rest["s1"]["clips"] == ["/card/s1_2.MP4", "/card/s1_3.MP4"]
    assert rest["s1"]["videos"] == 2 and rest["s1"]["seconds"] == 60.0


def test_more_videos_by_the_rules_use_only_unused_clips():
    d = doc_of()
    used = ["/card/s1_0.MP4", "/card/s1_1.MP4", "/card/s1_2.MP4", "/card/s2_0.MP4"]
    d, ids, info = G.extend_goal(d, 3, used)
    assert info["fallback"] is True
    assert ids == ["v3", "v4", "v5"]                               # numbered after the group's videos
    new = [v for v in d["videos"] if v["id"] in ids]
    for v in new:
        assert v["extra"] == 1 and v["pick"] and not set(v["pick"]) & set(used)
        assert set(v["inputs"]) == set(v["pick"])                  # its request is cut from those clips only
        assert v["clips"] == len(v["pick"]) and v["request"].startswith('Title: "')
    by_story = {v["stories"][0]: v for v in new}
    assert by_story["s2"]["inputs"] == ["/card/s2_1.MP4", "/card/s2_2.MP4"]
    assert by_story["s1"]["inputs"] == ["/card/s1_3.MP4"] or "s1" not in by_story   # 30 s left: a story still
    assert d["count"]["planned"] == 5
    assert d["more"][-1]["added"] == ids and d["more"][-1]["asked"] == 3
    # a second round: numbered on, its own round, nothing the first round took
    d, ids2, _ = G.extend_goal(d, 2, used + [p for v in new for p in v["pick"]])
    assert all(v["extra"] == 2 for v in d["videos"] if v["id"] in ids2)
    assert not ids2 or int(ids2[0][1:]) > 5


def test_nothing_left_says_so():
    d = doc_of()
    every = [p for s in d["survey"]["stories"] for p in s["clips"]]
    d, ids, info = G.extend_goal(d, 2, every)
    assert ids == [] and info["fallback"] and "no footage left" in info["reason"]
    assert d["more"][-1]["left"] == 0


def test_the_models_ideas_are_checked_and_titles_never_repeat():
    d = doc_of()
    seen = {}

    def call(system, body, imgs):
        seen.update(system=system, body=body)
        return dict(provider="test", model="m", json=dict(videos=[
            dict(title="The Needle After Dark", kind="film", stories=["s1"], brief="again"),      # a repeat: out
            dict(title="Tacoma Morning", title_zh="塔科马早晨", kind="reel", stories=["s3"], brief="b", theme="t", why="w"),
            dict(title="Nowhere", kind="film", stories=["s9"], brief="b")]))                       # no such story
    d, ids, info = G.extend_goal(d, 2, ["/card/s1_0.MP4"], about="Tacoma", call=call)
    assert info["fallback"] is False and info["provider"] == "test"
    assert [v["title"] for v in d["videos"] if v["id"] in ids] == ["Tacoma Morning"]
    assert "exactly 2" in seen["system"]
    assert "The Needle After Dark" in seen["body"] and "about: Tacoma" in seen["body"]
    assert "/card/s1_0.MP4" not in json.dumps(seen["body"])       # the model sees the clips that are left


def test_plan_card_edits_keep_the_pick():
    d = doc_of()
    d, ids, _ = G.extend_goal(d, 2, ["/card/s1_0.MP4", "/card/s2_0.MP4"])
    a, b = ids[:2]
    d = G.edit_goal(d, [{"op": "rename", "video": a, "title": "Waterfront, again"}, {"op": "merge", "videos": [a, b]}])
    va = next(v for v in d["videos"] if v["id"] == a)
    assert va["title"] == "Waterfront, again"
    assert "/card/s1_0.MP4" not in va["inputs"] and "/card/s2_0.MP4" not in va["inputs"]
    assert len(va["inputs"]) == 5                                   # both picks joined


def write_edl(d, item, shots, sub="work", name="fun_vlog.edl.json"):
    p = os.path.join(d, "items", item, sub)
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, name), "w") as f:
        json.dump(dict(version=1, builder="vlog", duration=9.0, shots=shots), f)


def test_what_a_made_cut_plays(tmp_path):
    d = str(tmp_path / "proj")
    write_edl(d, "a", [dict(i=0, src="/card/s1_0.MP4", kind="video", src_in=1.0, src_out=3.5),
                       dict(i=1, src="/card/s1_0.MP4", kind="video", src_in=4.0, src_out=6.0),
                       dict(i=2, src="/card/title.png", kind="still"),
                       dict(i=3, src="/card/s1_2.MP4", kind="video", src_in=0.5, src_out=2.0)])
    shots = G.edl_shots(d)
    assert [(s["i"], s["name"]) for s in shots] == [(1, "s1_0.MP4"), (2, "s1_0.MP4"), (3, "s1_2.MP4")]
    used = G.used_in_project(d)
    assert used == {"/card/s1_0.MP4": [[1.0, 3.5], [4.0, 6.0]], "/card/s1_2.MP4": [[0.5, 2.0]]}
    assert G.used_in_project(str(tmp_path / "none")) == {} and G.edl_shots(str(tmp_path / "none")) == []


def test_cli_goal_more(tmp_path):
    gp, up = tmp_path / "goal.json", tmp_path / "used.json"
    gp.write_text(json.dumps(doc_of()))
    up.write_text(json.dumps(["/card/s1_0.MP4"]))
    env = dict(os.environ, PYTHONPATH=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
    r = subprocess.run([sys.executable, "-m", "vstudio.intake", "goal-more", "--goal", str(gp), "--n", "1", "--used",
                        str(up), "--in-place", "--json"], capture_output=True, text=True, env=env, check=True)
    out = json.loads(r.stdout)
    assert out["ok"] and len(out["added"]) == 1
    saved = json.loads(gp.read_text())
    assert any(v["id"] == out["added"][0] and v.get("extra") == 1 for v in saved["videos"])
