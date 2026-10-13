"""「Edit the collection」 (goals.py + goaledit.py): a made group of videos keeps being edited - her words routed to more
videos (new plan cards cut from the clips no video plays, Ask-me-first respected), one video's re-cut (its unused
candidates; only that video is made again; Undo brings its cut back) or one edit across every made video (each clip
through its own AI, per-video progress and Undo); the count she asked for and 「补够」."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import goals as GO  # noqa: E402
from desk_engine.common import BadRequest  # noqa: E402
from desk_engine.goaledit import intent, match_video, scope_of  # noqa: E402
from desk_engine.goals import Goals  # noqa: E402
from test_goals import FakeHistory, FakeIntake  # noqa: E402

VIDS = [dict(id="v1", title="The Needle After Dark", title_zh="夜色中的太空针塔"),
        dict(id="v2", title="Seattle's Working Waterfront", title_zh="西雅图的工作码头")]


class Words(unittest.TestCase):
    def test_her_words_are_routed(self):
        cases = {
            "再做 3 条": dict(kind="more", n=3), "再做一条关于渡轮的": dict(kind="more", n=1, about="渡轮"),
            "补够 12 条": dict(kind="more", to=12), "补够": dict(kind="more", n=4), "make 2 more videos": dict(kind="more", n=2),
            "another one about the ferry": dict(kind="more", n=1, about="the ferry"),
            "给 Needle After Dark 多加几个镜头": dict(kind="recut", video="v1", mode="add"),
            "换掉第 3 个镜头": dict(kind="recut", video=None, shot=3, mode="replace"),
            "给夜色中的太空针塔换掉第2个镜头": dict(kind="recut", video="v1", shot=2),
            "换一批镜头": dict(kind="recut", video=None, mode="swap"),
            "replace shot 4 in the waterfront video": dict(kind="recut", video="v2", shot=4),
            "全部加水印": dict(kind="fanout", scope={}), "全部换成更安静的音乐": dict(kind="fanout", scope={}),
            "所有 YouTube 版本加英文旁白": dict(kind="fanout", scope=dict(lang="en")),
            "小红书和B站的版本都加字幕": dict(kind="fanout", scope=dict(lang="zh")),
        }
        for words, want in cases.items():
            got = intent(words, VIDS, need=4)
            for k, v in want.items():
                self.assertEqual(got.get(k), v, f"{words}: {got}")
        self.assertEqual(intent("  ", VIDS)["kind"], "empty")
        self.assertEqual(match_video("第 2 条加几个镜头", VIDS), "v2")
        self.assertIsNone(match_video("the dark", VIDS))                # too little of a title
        self.assertEqual(scope_of("全部加英文旁白"), {})                   # the voice's language, not the versions


def story(sid, n, secs=30.0):
    return dict(id=sid, place=dict(en=f"Place {sid}", zh=f"地点{sid}"), date="2026-06-22",
                start="2026-06-22 20:00:00", end="2026-06-22 20:30:00", time_of_day="evening", videos=n, photos=0,
                panoramas=0, seconds=secs * n, aerial=True, vertical=0, light=0.4, geo=None,
                clips=[f"/card/{sid}_{k}.MP4" for k in range(n)], clip_secs=[secs] * n, stills=[], panorama_dirs=[],
                thumbs=[], folder="DJI_001", short_clips=0, sheet=None)


def plan_doc():
    from vstudio.intake import goal as G
    st = [story("s1", 4), story("s2", 3), story("s3", 3), story("s4", 2)]
    by = {s["id"]: s for s in st}
    vids = [G._finish_video(dict(id=f"v{k}", title=t, title_zh=z, kind="film", stories=[sid], brief="b", theme="t",
                                 why="w", platforms=["youtube", "xiaohongshu"]), by, ["youtube", "xiaohongshu"])
            for k, (sid, t, z) in enumerate((("s1", VIDS[0]["title"], VIDS[0]["title_zh"]),
                                             ("s2", VIDS[1]["title"], VIDS[1]["title_zh"])), 1)]
    return dict(kind=G.KIND, version=1, id="x", prompt="p", inputs=["/card"], ui_lang="en",
                platforms=["youtube", "xiaohongshu"], survey=dict(stories=st, totals={}, unused={}), videos=vids,
                planner=dict(provider="none", fallback=True))


def write_edl(d, srcs):
    p = os.path.join(d, "items", "a", "work")
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, "fun_vlog.edl.json"), "w") as f:
        json.dump(dict(shots=[dict(i=k, src=s, kind="video", src_in=1.0, src_out=3.0) for k, s in enumerate(srcs)]), f)


class FakeOutputs:
    """The clip editor as an edit across the group uses it (each clip's own AI, edit, render, undo / revert)."""

    def __init__(self):
        self.calls, self.steps = [], {}

    def clips(self, item):
        return dict(clips=[dict(id=f"{item}-c", files=[dict(path="/x.mp4")])])

    def ask(self, item, clip, prompt):
        self.calls.append(("ask", item, prompt))
        if "nothing" in prompt:
            return dict(proposals=[], summary="nothing to do")
        return dict(proposals=[dict(id="p1", op=dict(op="voiceover", text="hello"), describe="add a voice-over")],
                    summary="voice-over added", provider="test", turn="t1-abc")

    def edit(self, item, clip, ops, by="user", turn=None, note=None):
        self.calls.append(("edit", item, ops[0]["op"], by, turn))
        sid = f"s{len(self.steps.get(clip, [])) + 1}-aa"
        self.steps.setdefault(clip, []).append(sid)
        return dict(ok=True, step=dict(id=sid))

    def render(self, item, clip, quality="preview", targets="primary", with_ops=None):
        self.calls.append(("render", item, quality, targets))
        return dict(ok=True)

    def show(self, item, clip):
        return dict(steps=[dict(id=s) for s in self.steps.get(clip, [])])

    def undo(self, item, clip, steps=1, redo=False):
        self.calls.append(("undo", item))
        self.steps[clip].pop()

    def revert(self, item, clip, step):
        self.calls.append(("revert", item, step))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="goaledit-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.intake, self.history, self.outputs = FakeIntake(), FakeHistory(), FakeOutputs()
        self.states = {}
        p = mock.patch.object(GO, "project_state", side_effect=lambda d: self.states.get(d, ("running", {})))
        p.start()
        self.addCleanup(p.stop)
        self.env = mock.patch.dict(os.environ, {"VSTUDIO_CACHE": os.path.join(self.tmp, "cache"),
                                                "VSTUDIO_LLM_PROVIDER": "none", "VSTUDIO_LLM_INTAKE_PROVIDER": "none"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def made_goal(self, mode="ask", prompt="做 12 条左右，最少 10 条"):
        """A done group of two made videos, each an English + a Chinese project; v1's cut plays s1_0 and s1_1."""
        G = Goals(self.tmp, None, self.intake, self.history, ticker=False, outputs=self.outputs)
        gid = "abcdefabcdef"
        vids = []
        for k, v in enumerate(plan_doc()["videos"], 1):
            ps = []
            for lang, word in (("en", "English"), ("zh", "中文")):
                d = os.path.join(self.tmp, f"v{k}-{lang}")
                os.makedirs(d, exist_ok=True)
                self.states[d] = ("made", {})
                ps.append(dict(dir=d, name=f"{v['title']} ({word})", item=f"item{k}{lang}"))
            if k == 1:
                write_edl(ps[0]["dir"], ["/card/s1_0.MP4", "/card/s1_0.MP4", "/card/s1_1.MP4"])
            vids.append(dict(v, state="made", projects=ps, versions=[], finished=time.time(), progress=1.0))
        g = dict(id=gid, prompt=prompt, inputs=["/card"], platforms=None, lang="en", mode=mode, state="done",
                 created=time.time(), videos=vids, goal="Drone edits", count=None)
        os.makedirs(os.path.join(self.tmp, "goals"), exist_ok=True)
        with open(os.path.join(self.tmp, "goals", f"{gid}.json"), "w") as f:
            json.dump(g, f)
        with open(os.path.join(self.tmp, "goals", f"{gid}.plan.json"), "w") as f:
            json.dump(plan_doc(), f)
        G._load()
        return G, gid

    def until(self, fn, what):
        for _ in range(300):
            x = fn()
            if x:
                return x
            time.sleep(0.02)
        self.fail(what)


class MoreVideos(Base):
    def test_count_she_asked_for_and_fill(self):
        G, gid = self.made_goal()
        v = G.view(gid)
        self.assertEqual(v["count"]["asked"], 12)               # from her words: the goal kept no count
        self.assertEqual(v["count"]["min"], 10)
        self.assertEqual(v["fill"], dict(target=12, min=10, have=2, need=10))

    def test_more_on_ask_me_first_waits_on_new_plan_cards(self):
        G, gid = self.made_goal(mode="ask")
        r = G.say(gid, "再做 2 条")
        self.assertEqual(r["intent"]["kind"], "more")
        v = self.until(lambda: (lambda x: x if x["more"]["state"] == "ready" else None)(G.view(gid)), "more ready")
        new = [x for x in v["videos"] if x.get("proposed")]
        self.assertEqual([x["id"] for x in new], ["v3", "v4"])
        self.assertEqual(v["counts"]["total"], 2)                 # cards are not part of the group yet
        used = {"/card/s1_0.MP4", "/card/s1_1.MP4", "/card/s2_0.MP4", "/card/s2_1.MP4", "/card/s2_2.MP4"}
        for x in new:                                             # v1 by its cut, v2 by the clips it was given
            self.assertFalse(set(G.goals[gid]["videos"][int(x["id"][1:]) - 1]["inputs"]) & used)
        self.assertEqual(v["state"], "done")
        with self.assertRaises(BadRequest):
            G.more(gid, 2)                                         # the open cards first
        v = G.edit_more(gid, [{"op": "rename", "video": "v3", "title": "Night Harbour"}])
        self.assertEqual(v["videos"][2]["title"], "Night Harbour")
        with self.assertRaises(BadRequest):
            G.edit_more(gid, [{"op": "drop", "video": "v1"}])       # a made video is not a card
        v = G.more_act(gid, "approve")
        self.assertEqual(v["state"], "running")
        self.assertEqual(v["counts"]["total"], 4)
        self.assertEqual([x["state"] for x in v["videos"]], ["made", "made", "planning", "planning"])
        started = [c for c in self.intake.calls if c[0] == "start"]
        self.assertEqual(len(started), 2)
        self.assertIn('Title: "Night Harbour"', started[0][2])
        self.assertEqual(v["fill"]["have"], 4)

    def test_more_on_autopilot_is_made_at_once_and_discard(self):
        G, gid = self.made_goal(mode="autopilot")
        G.more(gid, to=3)                                          # 补够 3: one more
        v = self.until(lambda: (lambda x: x if x["state"] == "running" else None)(G.view(gid)), "made at once")
        self.assertEqual(v["counts"]["total"], 3)
        self.assertEqual(v["more"]["state"], "made")
        G2, gid2 = self.made_goal(mode="ask")
        G2.more(gid2, 1, about="Place s3")
        self.until(lambda: G2.view(gid2)["more"]["state"] == "ready", "ready")
        new = [x for x in G2.view(gid2)["videos"] if x.get("proposed")]
        self.assertEqual(new[0]["stories"], ["s3"])                # her "about" picks the story
        v = G2.more_act(gid2, "discard")
        self.assertEqual(len(v["videos"]), 2)
        self.assertEqual([x["id"] for x in G2.plan_doc(gid2)["videos"]], ["v1", "v2"])

    def test_the_planner_failing_says_so(self):
        G, gid = self.made_goal()
        G._extend = lambda *a: (_ for _ in ()).throw(RuntimeError("model timed out"))
        G.more(gid, 2)
        v = self.until(lambda: (lambda x: x if x["more"]["state"] == "failed" else None)(G.view(gid)), "failed")
        self.assertIn("timed out", v["more"]["error"])
        G.more(gid, 1)                                             # she can ask again


class Recut(Base):
    def test_candidates_and_a_shot_replaced_then_undone(self):
        G, gid = self.made_goal()
        c = G.candidates(gid, "v1")
        self.assertEqual([s["i"] for s in c["shots"]], [1, 2, 3])
        free = [x["path"] for x in c["free"]]
        self.assertNotIn("/card/s1_0.MP4", free)                    # its own shots
        self.assertNotIn("/card/s2_0.MP4", free)                    # v2's
        self.assertTrue(c["free"][0]["same"])
        with self.assertRaises(BadRequest):
            G.recut(gid, "v1", add=["/card/s2_0.MP4"])              # another video's clip
        old = [p["dir"] for p in G.goals[gid]["videos"][0]["projects"]]
        v = G.recut(gid, "v1", shots=[3])                           # 换掉第 3 个镜头: s1_1 out, a fresh clip in
        x = v["videos"][0]
        self.assertEqual(x["state"], "planning")
        self.assertEqual(x["recut"]["drop"], ["s1_1.MP4"])
        self.assertEqual(len(x["recut"]["add"]), 1)
        rid = x["intake"]
        req = self.intake.jobs[rid]
        self.assertNotIn("/card/s1_1.MP4", req["inputs"])
        self.assertIn("Re-cut of an earlier version", req["prompt"])
        self.assertEqual(v["videos"][1]["state"], "made")           # only this video is made again
        self.assertEqual(v["state"], "running")
        # made again
        d = os.path.join(self.tmp, "recut-en")
        os.makedirs(d)
        self.intake.applied(rid, d)
        self.states[d] = ("made", {})
        G.tick(gid)
        G.tick(gid)
        v = G.view(gid)
        self.assertEqual(v["videos"][0]["state"], "made")
        self.assertEqual(v["videos"][0]["recut"]["state"], "made")
        self.assertTrue(v["videos"][0]["can_undo_recut"])
        self.assertEqual(v["state"], "done")
        _reqs, dirs = G.owned()
        self.assertTrue(all(os.path.realpath(o) in dirs for o in old))   # the cut before stays the group's
        v = G.undo_recut(gid, "v1")
        self.assertEqual([p["dir"] for p in v["videos"][0]["projects"]], old)
        self.assertEqual(self.history.archived, [d])
        self.assertEqual(v["videos"][0]["recut"]["state"], "undone")

    def test_let_ai_pick_adds_its_own_stories_unused_clips(self):
        G, gid = self.made_goal()
        v = G.recut(gid, "v1", pick="ai")
        req = self.intake.jobs[v["videos"][0]["intake"]]
        self.assertIn("/card/s1_2.MP4", req["inputs"])
        self.assertIn("/card/s1_3.MP4", req["inputs"])
        with self.assertRaises(BadRequest):
            G.recut(gid, "v2")                                      # nothing picked, nothing dropped (and v2 made)


class AcrossTheGroup(Base):
    def test_autopilot_applies_each_clip_and_undo_is_per_video(self):
        G, gid = self.made_goal(mode="autopilot")
        r = G.say(gid, "所有 YouTube 版本加英文旁白")
        self.assertEqual(r["intent"], dict(kind="fanout", scope=dict(lang="en")))
        f = self.until(lambda: (lambda x: x if x["state"] == "done" else None)(G.view(gid)["fanouts"][-1]), "fanout")
        self.assertEqual([x["state"] for x in f["videos"]], ["done", "done"])
        self.assertEqual(f["counts"]["done"], 2)
        asked = sorted(c[1] for c in self.outputs.calls if c[0] == "ask")
        self.assertEqual(asked, ["item1en", "item2en"])            # only the English versions
        self.assertIn(("edit", "item1en", "voiceover", "ai", "t1-abc"), self.outputs.calls)
        self.assertIn(("render", "item1en", "final", "all"), self.outputs.calls)
        self.assertEqual(f["videos"][0]["rows"][0]["describe"], ["add a voice-over"])
        with self.assertRaises(BadRequest):
            G.fanout_act(gid, f["id"], "apply")                      # nothing waits
        G.fanout_act(gid, f["id"], "undo", video="v1")
        f = self.until(lambda: (lambda x: x if x["state"] == "done" else None)(G.view(gid)["fanouts"][-1]), "undo")
        self.assertEqual([x["state"] for x in f["videos"]], ["undone", "done"])
        self.assertIn(("undo", "item1en"), self.outputs.calls)

    def test_ask_me_first_waits_then_applies_and_nothing_is_said(self):
        G, gid = self.made_goal(mode="ask")
        G.fanout(gid, "全部加水印")
        f = self.until(lambda: (lambda x: x if x["state"] == "done" else None)(G.view(gid)["fanouts"][-1]), "fanout")
        self.assertEqual(f["counts"]["proposed"], 2)
        self.assertFalse([c for c in self.outputs.calls if c[0] == "edit"])
        G.fanout_act(gid, f["id"], "apply")
        f = self.until(lambda: (lambda x: x if x["state"] == "done" else None)(G.view(gid)["fanouts"][-1]), "apply")
        self.assertEqual([x["state"] for x in f["videos"]], ["done", "done"])
        self.assertEqual(len([c for c in self.outputs.calls if c[0] == "edit"]), 4)   # 2 videos x 2 versions
        G.fanout(gid, "nothing to change here")
        f = self.until(lambda: (lambda x: x if x["state"] == "done" else None)(G.view(gid)["fanouts"][-1]), "nothing")
        self.assertEqual(f["counts"]["nothing"], 2)


if __name__ == "__main__":
    unittest.main()
