"""发布 board (publish redesign A): scheduleMany / removeMany + restore (unschedule with undo), updatePost (caption,
platform, on / off, stats, filled), per-post status + warnings (caption too long, no caption, slot clash),
fillWeek in the engine, and the one-sentence planner (parse + preview that never writes)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import outputs as OU  # noqa: E402
from desk_engine import schedule_text as ST  # noqa: E402
from desk_engine import works as WK  # noqa: E402
from desk_engine.calendar import Calendar, post_text, shorten_rules, text_limit  # noqa: E402
from desk_engine.common import BadRequest, Registry  # noqa: E402
from desk_engine.history import History  # noqa: E402
from test_v04 import make_fuye  # noqa: E402

A, B = "A_换圈子", "B_自媒体"
MON = "2026-10-05"   # a Monday


class Board(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.watch = os.path.join(self.root, "demos")
        self.d = make_fuye(self.watch)
        self.env = mock.patch.dict(os.environ, {"DESK_HISTORY_WATCH": self.watch,
                                                "VSTUDIO_HOME": os.path.join(self.root, "home")})
        self.env.start()
        data = os.path.join(self.root, "desk")
        self.h = History(data, Registry(data))
        self.o = OU.Outputs(data, self.h)
        self.item = next(r["id"] for r in self.h.list()["items"] if r["dir"] == self.d)
        WK.adopt(self.d)
        self.cal = Calendar(data, self.h, self.o)

    def tearDown(self):
        self.env.stop()

    def posts(self):
        return self.cal.list()["posts"]

    def test_explicit_video_is_per_post_and_must_exist(self):
        posts = self.cal.add_many([dict(item=self.item, clip=A, platform=p, at="2026-10-07T20:00") for p in ("youtube", "xiaohongshu")])["posts"]
        xhs = next(p for p in posts if p["platform"] == "xiaohongshu")
        file = self.o.clips(self.item)["clips"][0]["files"][0]["path"]
        self.cal.update(xhs["id"], {"video_path": file})
        self.assertEqual(next(p for p in self.posts() if p["id"] == xhs["id"])["video_path"], file)
        self.assertNotIn("video_path", next(p for p in self.posts() if p["platform"] == "youtube"))
        with self.assertRaises(BadRequest):
            self.cal.update(xhs["id"], {"video_path": "/not/a/clip.mp4"})
        self.cal.update(xhs["id"], {"video_path": None})
        self.assertNotIn("video_path", next(p for p in self.posts() if p["id"] == xhs["id"]))

    def test_account_selection_survives_restart_and_undo_and_platform_changes_clear_it(self):
        p = self.cal.add(dict(item=self.item, clip=A, platform="xiaohongshu", account="brand", at="2026-10-07T20:00"))
        pid = p["id"]
        self.assertEqual(Calendar(os.path.join(self.root, "desk"), self.h, self.o).list()["posts"][0]["account"], "brand")
        self.cal.update(pid, dict(state="filled"))
        self.cal.update(pid, dict(account="main"))
        self.assertEqual(self.posts()[0]["state"], "planned")
        removed = self.cal.remove_many([pid])["removed"]
        self.cal.restore(removed)
        self.assertEqual(self.posts()[0]["account"], "main")
        self.cal.update(pid, dict(platform="douyin"))
        self.assertNotIn("account", self.posts()[0])
        self.cal.update(pid, dict(account="brand"))
        self.cal.update(pid, dict(account=None))
        self.assertNotIn("account", self.posts()[0])
        for invalid in ("", "Upper", "../main", "x" * 33, 42):
            with self.assertRaises(BadRequest):
                self.cal.update(pid, dict(account=invalid))
        self.cal.update(pid, dict(account="main", state="posted"))
        with self.assertRaises(BadRequest):
            self.cal.update(pid, dict(account="brand"))

    def test_api_delivery_receipt_survives_restart_restore_and_blocks_local_remote_edits(self):
        p = self.cal.add(dict(item=self.item, clip=A, platform="youtube", at="2026-10-07T20:00"))
        result = dict(url="https://youtu.be/example", privacy="private", publishAt="2026-10-09T03:00:00Z",
                      lockedPrivate=False, warnings=["Cover unavailable"])
        self.cal.update(p["id"], dict(state="scheduled", via="api", url=result["url"], api_result=result))
        row = Calendar(os.path.join(self.root, "desk"), self.h, self.o).list()["posts"][0]
        self.assertEqual(row["state"], "scheduled")
        self.assertEqual(row["status"], "scheduled")
        self.assertEqual(row["api_result"], result)
        self.assertNotIn("posted_at", row)
        for patch in (dict(at="2026-10-10T20:00"), dict(account="brand"), dict(platform="xiaohongshu"),
                      dict(video_path="/different.mp4"), dict(caption="new caption"), dict(state="ready"), dict(enabled=False)):
            with self.assertRaises(BadRequest):
                self.cal.update(p["id"], patch)
        removed = self.cal.remove_many([p["id"]])["removed"]
        self.cal.restore(removed)
        self.assertEqual(self.posts()[0]["api_result"], result)
        public = {**result, "privacy": "public", "publishAt": None}
        self.cal.update(p["id"], dict(state="posted", via="api", api_result=public))
        self.assertIn("posted_at", self.posts()[0])

    def test_private_unknown_and_invalid_platform_receipts(self):
        for privacy in ("private", "unlisted", "unknown"):
            p = self.cal.add(dict(item=self.item, clip=A, platform="youtube", at="2026-10-07T20:00"))
            result = dict(url="https://youtu.be/example", privacy=privacy, publishAt=None,
                          lockedPrivate=False, warnings=[])
            with self.assertRaises(BadRequest):
                self.cal.update(p["id"], dict(state="posted", via="api", api_result=result))
            self.cal.update(p["id"], dict(state="uploaded", via="api", api_result=result))
            row = next(x for x in self.posts() if x["id"] == p["id"])
            self.assertEqual(row["state"], "uploaded")
            self.assertNotIn("posted_at", row)
            for bad in ({**result, "publishAt": "tomorrow"}, {**result, "url": "file:///secret"},
                        {**result, "warnings": "bad"}, {**result, "privacy": "guessed"}):
                with self.assertRaises(BadRequest):
                    self.cal.update(p["id"], dict(state="uploaded", via="api", api_result=bad))

    def test_schedule_many_is_one_step_and_decorated(self):
        r = self.cal.add_many([dict(item=self.item, clip=A, platform=p, at="2026-10-07T20:00") for p in ("xiaohongshu", "douyin", "x")])
        self.assertEqual(len(r["ids"]), 3)
        ps = self.posts()
        self.assertEqual({p["platform"] for p in ps}, {"xiaohongshu", "douyin", "x"})
        p = next(x for x in ps if x["platform"] == "xiaohongshu")
        self.assertEqual(p["status"], "draft")
        self.assertTrue(p["enabled"])
        self.assertNotIn("同一个行业待越久，思路越窄", p["caption"])       # 小红书 has a title field: not repeated
        self.assertEqual(p["title"], "同一个行业待越久，思路越窄")           # the AI's title is the clip's title
        self.assertIn("正文第一段", p["caption"])                          # the clip's post copy
        self.assertIn("#副业", p["caption"])
        x = next(x for x in ps if x["platform"] == "x")
        self.assertTrue(x["caption"].startswith("同一个行业待越久，思路越窄"))  # X has no title field: it leads
        self.assertFalse(p["caption_custom"])
        self.assertEqual(p["limit"], 1000)
        self.assertEqual(p["project"], "fuye")
        self.assertNotIn(A, [q["clip"] for q in self.cal.list()["queue"]])
        # all or nothing: one bad row -> nothing written
        with self.assertRaises(BadRequest):
            self.cal.add_many([dict(item=self.item, clip=B, platform="xiaohongshu", at="2026-10-08T20:00"),
                               dict(item=self.item, clip=B, platform="xiaohongshu", at="tomorrow")])
        self.assertEqual(len(self.posts()), 3)

    def test_unschedule_and_undo_restores_the_same_rows(self):
        ids = self.cal.add_many([dict(item=self.item, clip=A, platform=p, at="2026-10-07T20:00") for p in ("xiaohongshu", "x")])["ids"]
        self.cal.update(ids[1], dict(caption="my own X text"))
        files = sorted(os.listdir(os.path.join(self.d, "final")))
        gone = self.cal.remove_many(ids)["removed"]
        self.assertEqual(self.posts(), [])
        self.assertIn(A, [q["clip"] for q in self.cal.list()["queue"]])     # back in the queue
        self.assertEqual(sorted(os.listdir(os.path.join(self.d, "final"))), files)  # never deletes files
        self.cal.restore(gone)
        back = {p["id"]: p for p in self.posts()}
        self.assertEqual(set(back), set(ids))
        self.assertEqual(back[ids[1]]["caption"], "my own X text")
        self.assertTrue(back[ids[1]]["caption_custom"])
        self.cal.restore(gone)                                             # idempotent
        self.assertEqual(len(self.posts()), 2)

    def test_update_caption_platform_onoff_state_stats(self):
        pid = self.cal.add(dict(item=self.item, clip=A, platform="xiaohongshu", at="2026-10-07T20:00"))["id"]
        self.cal.update(pid, dict(caption="短文案"))
        self.assertEqual(self.posts()[0]["caption"], "短文案")
        self.cal.update(pid, dict(caption=None))                           # back to the clip's copy
        self.assertFalse(self.posts()[0]["caption_custom"])
        self.cal.update(pid, dict(platform="douyin"))
        self.assertEqual(self.posts()[0]["platform"], "douyin")
        self.cal.update(pid, dict(enabled=False))
        self.assertFalse(self.posts()[0]["enabled"])
        self.assertEqual(self.cal.confirm_week(MON)["ready"], 0)          # switched off: not confirmed
        self.cal.update(pid, dict(enabled=True))
        self.assertEqual(self.cal.confirm_week(MON)["ready"], 1)
        self.cal.update(pid, dict(state="filled"))
        self.assertEqual(self.posts()[0]["status"], "filled")
        self.cal.update(pid, dict(state="posted", stats=dict(views=1204, likes=96)))
        p = self.posts()[0]
        self.assertEqual((p["status"], p["stats"]["views"]), ("posted", 1204))
        for bad in (dict(state="published"), dict(enabled="no"), dict(platform="X!"), dict(stats=dict(views=-1)),
                    dict(caption=1)):
            with self.assertRaises(BadRequest):
                self.cal.update(pid, bad)

    def test_warnings_caption_too_long_no_caption_slot_clash(self):
        ids = self.cal.add_many([dict(item=self.item, clip=A, platform="x", at="2026-10-09T20:00"),
                                 dict(item=self.item, clip=B, platform="x", at="2026-10-09T20:00"),
                                 dict(item=self.item, clip=B, platform="xiaohongshu", at="2026-10-09T21:00")])["ids"]
        self.cal.update(ids[0], dict(caption="再小的博主也是博主" * 20))       # 180 CJK = 360 weighted on X
        self.cal.update(ids[2], dict(caption=""))
        ps = {p["id"]: p for p in self.posts()}
        kinds = lambda i: sorted(w["kind"] for w in ps[i]["warnings"])   # noqa: E731
        self.assertEqual(kinds(ids[0]), ["caption_too_long", "slot_clash"])
        w = next(w for w in ps[ids[0]]["warnings"] if w["kind"] == "caption_too_long")
        self.assertEqual((w["n"], w["max"]), (360, 280))                   # X weighs CJK as 2
        self.assertEqual(kinds(ids[1]), ["slot_clash"])
        self.assertEqual(kinds(ids[2]), ["no_caption"])
        self.cal.update(ids[1], dict(at="2026-10-09T21:30"))
        self.assertEqual(sorted(w["kind"] for w in next(p for p in self.posts() if p["id"] == ids[0])["warnings"]), ["caption_too_long"])

    def test_fill_week_one_undo(self):
        self.cal.add(dict(item=self.item, clip=A, platform="xiaohongshu", at="2026-10-06T12:00"))
        r = self.cal.fill_week(dict(start=MON, today=MON, platforms=["xiaohongshu", "douyin"],
                                    times=dict(xiaohongshu="20:00", douyin="12:30")))
        # the queue has one clip left (B): the first free day (Mon) gets it on both platforms
        self.assertEqual(len(r["ids"]), 2)
        ats = sorted((p["platform"], p["at"]) for p in r["posts"])
        self.assertEqual(ats, [("douyin", "2026-10-05T12:30"), ("xiaohongshu", "2026-10-05T20:00")])
        self.cal.remove_many(r["ids"])
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(self.cal.fill_week(dict(start=MON, today="2026-10-12", platforms=["x"]))["reason"], "no_free_days")
        with self.assertRaises(BadRequest):
            self.cal.fill_week(dict(start=MON, platforms=[]))

    def test_plan_preview_never_writes_and_moves_clashes(self):
        self.cal.add(dict(item=self.item, clip=A, platform="xiaohongshu", at="2026-10-07T20:00"))
        before = self.cal._rows()
        p = self.cal.plan(dict(text="每天晚上8点发一条小红书，周末不发", start=MON, today=MON, platforms=["douyin"],
                               times={}))
        self.assertTrue(p["ok"])
        self.assertEqual(self.cal._rows(), before)                         # preview only
        self.assertEqual(p["platforms"], ["xiaohongshu"])
        self.assertEqual(p["time"], "20:00")
        self.assertEqual(p["days"], [0, 1, 2, 3, 4])
        self.assertEqual(len(p["drafts"]), 1)                              # one clip left in the queue
        self.assertEqual(p["drafts"][0]["at"], "2026-10-06T20:00")         # from tomorrow (Tue)
        # selection: the same clip twice in a row lands on Tue and Wed; Wed 20:00 is taken -> 21:00
        sel = [dict(item=self.item, clip=B), dict(item=self.item, clip=A)]
        p = self.cal.plan(dict(text="every weekday at 8pm on RedNote", start=MON, today=MON, clips=sel))
        self.assertEqual([d["at"] for d in p["drafts"]], ["2026-10-06T20:00", "2026-10-07T21:00"])
        self.assertEqual(p["adjustments"], [dict(kind="moved", platform="xiaohongshu", frm="2026-10-07T20:00", to="2026-10-07T21:00")])
        self.assertTrue(p["from_selection"])
        applied = self.cal.add_many([{k: d[k] for k in ("item", "clip", "platform", "at")} for d in p["drafts"]])
        self.assertEqual(len(applied["ids"]), 2)
        nope = self.cal.plan(dict(text="hmm, whatever", start=MON, today=MON))
        self.assertEqual((nope["ok"], nope["reason"]), (False, "not_understood"))
        nxt = self.cal.plan(dict(text="下周每天中午12点发抖音", start=MON, today=MON, clips=sel))
        self.assertEqual(nxt["start"], "2026-10-12")
        self.assertEqual(nxt["drafts"][0]["at"], "2026-10-12T12:00")


class ScheduleClipsTest(Board):
    """All projects' bulk Schedule of hundreds of videos: a few batched requests (not one per project), the next free
    days one a day, a clip already scheduled left alone, all or none, one undo however many."""

    def test_next_free_days_one_a_day_skipping_taken_ones(self):
        self.cal.add_many([dict(item=self.item, clip=B, platform="x", at="2026-10-07T12:00")])     # the 7th is taken
        r = self.cal.schedule_clips(dict(today="2026-10-05", hour="19:00", clips=[
            dict(item=self.item, clip=A, platforms=["tiktok", "youtube", "tiktok"]),
            dict(item=self.item, clip=B, platforms=["x"])]))                                       # B: has a post
        self.assertEqual((r["clips"], r["skipped"], r["first"], r["last"]), (1, 1, "2026-10-06T19:00", "2026-10-06T19:00"))
        self.assertEqual(len(r["ids"]), 2)                          # one row per platform, a repeated one once
        mine = sorted((p["platform"], p["at"]) for p in self.posts() if p["clip"] == A)
        self.assertEqual(mine, [("tiktok", "2026-10-06T19:00"), ("youtube", "2026-10-06T19:00")])
        self.cal.remove_many(r["ids"])
        r = self.cal.schedule_clips(dict(today="2026-10-06", clips=[dict(item=self.item, clip=A, platforms=["x"])]))
        self.assertEqual(r["first"], "2026-10-08T19:00")             # the 7th has a post: the next free day

    def test_all_or_none_and_bounds(self):
        with self.assertRaises(BadRequest):                          # an unknown clip: nothing written
            self.cal.schedule_clips(dict(today="2026-10-05", clips=[dict(item=self.item, clip=A, platforms=["x"]),
                                                                    dict(item=self.item, clip="nope", platforms=["x"])]))
        self.assertEqual(self.posts(), [])
        for bad in (dict(today="2026-10-05", clips=[]), dict(today="soon", clips=[dict(item=self.item, clip=A, platforms=["x"])]),
                    dict(today="2026-10-05", clips=[dict(item=self.item, clip=A, platforms=[])]),
                    dict(today="2026-10-05", hour="7pm", clips=[dict(item=self.item, clip=A, platforms=["x"])])):
            with self.assertRaises(BadRequest):
                self.cal.schedule_clips(bad)

    def test_quiet_until_the_last_request_and_one_undo_for_hundreds(self):
        events = []
        self.cal.bus = mock.Mock(publish=lambda *a, **k: events.append(a[0]))
        self.cal.schedule_clips(dict(today="2026-10-05", quiet=True, clips=[dict(item=self.item, clip=A, platforms=["x"])]))
        self.assertEqual(events, [])
        r = self.cal.schedule_clips(dict(today="2026-10-05", clips=[dict(item=self.item, clip=B, platforms=["x"])]))
        self.assertEqual(events, ["calendar"])
        self.assertEqual(r["first"], "2026-10-07T19:00")
        # an undo of a bulk Schedule of hundreds of videos x platforms is one request (was capped at 200 rows)
        rows = [dict(id=f"{i:012x}", item=self.item, clip=A, platform="x", at="2026-11-01T19:00", state="planned") for i in range(900)]
        self.cal.restore(rows)
        self.assertEqual(len(self.cal.remove_many([x["id"] for x in rows])["removed"]), 900)


class TitleAndPostedTest(Board):
    def test_title_edit_per_row_limit_and_reset(self):
        r = self.cal.add_many([dict(item=self.item, clip=A, platform=p, at="2026-10-07T20:00") for p in ("xiaohongshu", "youtube")])
        xhs, yt = r["ids"]
        p = next(x for x in self.posts() if x["id"] == xhs)
        original = p["title"]
        self.assertEqual(p["title_limit"], 20)
        self.assertFalse(p["title_custom"])
        self.cal.update(xhs, dict(title="再小的博主，也是博主"))
        self.cal.update(yt, dict(platform_title="Even a small creator is a creator"))
        ps = {x["id"]: x for x in self.posts()}
        self.assertEqual(ps[xhs]["title"], "再小的博主，也是博主")
        self.assertEqual(ps[xhs]["title_length"], 10)
        self.assertTrue(ps[yt]["title_custom"])
        self.assertEqual(ps[yt]["platform_title"], "Even a small creator is a creator")
        self.assertEqual(ps[yt]["title"], "再小的博主，也是博主")  # one title per clip: every card follows
        self.assertEqual(ps[yt]["platform_title"], "Even a small creator is a creator")   # her own one still wins
        clip = next(c for c in self.o.clips(self.item)["clips"] if c["id"] == A)
        self.assertEqual((clip["title"], clip["title_custom"]), ("再小的博主，也是博主", True))   # the editor header
        self.assertEqual(ps[yt]["title_limit"], 100)
        # 小红书 counts CJK as 1, latin as 0.5: 21 CJK characters are over, 30 latin letters are not
        self.cal.update(xhs, dict(platform_title="一" * 21))
        self.assertIn("title_too_long", [w["kind"] for w in next(x for x in self.posts() if x["id"] == xhs)["warnings"]])
        self.cal.update(xhs, dict(platform_title="a" * 30))
        self.assertNotIn("title_too_long", [w["kind"] for w in next(x for x in self.posts() if x["id"] == xhs)["warnings"]])
        with self.assertRaises(BadRequest):
            self.cal.update(xhs, dict(title="two\nlines"))
        with self.assertRaises(BadRequest):
            self.cal.update(xhs, dict(title="   "))
        self.cal.update(yt, dict(platform_title=None))
        p = next(x for x in self.posts() if x["id"] == yt)
        self.assertNotIn("platform_title", p)
        self.assertFalse(p["title_custom"])
        self.cal.update(xhs, dict(title=None))
        self.assertEqual(next(x for x in self.posts() if x["id"] == xhs)["title"], original)
        self.assertFalse(next(c for c in self.o.clips(self.item)["clips"] if c["id"] == A)["title_custom"])

    def test_posts_only_skips_the_queue_scan(self):
        self.cal.add_many([dict(item=self.item, clip=A, platform="xiaohongshu", at="2026-10-07T20:00")])
        full, lean = self.cal.list(), self.cal.list(queue=False)
        self.assertTrue(full["queue"])
        self.assertEqual(lean["queue"], [])
        self.assertEqual([p["id"] for p in lean["posts"]], [p["id"] for p in full["posts"]])

    def test_posted_keeps_url_and_via_and_unposting_clears_them(self):
        pid = self.cal.add_many([dict(item=self.item, clip=A, platform="xiaohongshu", at="2026-10-07T20:00")])["ids"][0]
        self.cal.update(pid, dict(state="posted", url="https://www.xiaohongshu.com/explore/abc", via="assisted"))
        p = next(x for x in self.posts() if x["id"] == pid)
        self.assertEqual((p["state"], p["url"], p["via"]), ("posted", "https://www.xiaohongshu.com/explore/abc", "assisted"))
        self.assertTrue(p["posted_at"])
        with self.assertRaises(BadRequest):
            self.cal.update(pid, dict(url="javascript:alert(1)"))
        self.cal.update(pid, dict(state="ready"))
        p = next(x for x in self.posts() if x["id"] == pid)
        self.assertNotIn("url", p)
        self.assertNotIn("posted_at", p)


class ShortenTest(Board):
    def test_rules_make_it_fit_and_keep_tags(self):
        long = ("Small creators are still creators. I posted for 8 months to 300 followers before one video changed "
                "how I think about side projects. Here is what I wish I knew on day one, and why consistency beat "
                "talent every single time. Start before you feel ready, post the rough version, keep going.\n\n#creator #sidehustle")
        r = self.cal.shorten(dict(text=long, platform="x"))
        self.assertEqual(r["provider"], "rules")                          # mock engine: no model
        self.assertLessEqual(r["length"], 280)
        self.assertEqual(r["limit"], 280)
        self.assertTrue(r["text"].startswith("Small creators are still creators."))
        self.assertIn("#creator", r["text"])
        zh = "再小的博主也是博主。" * 40
        out = shorten_rules("x", zh, 280)
        self.assertLessEqual(text_limit("x", out)[0], 280)
        self.assertEqual(self.cal.shorten(dict(text="short", platform="x"))["text"], "short")
        with self.assertRaises(BadRequest):
            self.cal.shorten(dict(text="", platform="x"))


class ParseTest(unittest.TestCase):
    def test_sentences(self):
        cases = {
            "每天晚上8点发一条小红书，周末不发": ("20:00", [0, 1, 2, 3, 4], ["xiaohongshu"], 1),
            "工作日中午12点发抖音和X": ("12:00", [0, 1, 2, 3, 4], ["douyin", "x"], 1),
            "每周一三五 19:30 小红书": ("19:30", [0, 2, 4], ["xiaohongshu"], 1),
            "每天两条抖音，早上9点": ("09:00", list(range(7)), ["douyin"], 2),
            "post on TikTok every day at 6pm, no weekends": ("18:00", [0, 1, 2, 3, 4], ["tiktok"], 1),
            "Instagram on Mondays and Thursdays at 7:15 pm": ("19:15", [0, 3], ["instagram"], 1),
            "tous les soirs à 20h sur Instagram, pas le week-end": ("20:00", [0, 1, 2, 3, 4], ["instagram"], 1),
            "YouTube Shorts weekends only at 10:00": ("10:00", [5, 6], ["youtube-shorts"], 1),
            "晚上八点半发视频号": ("20:30", None, ["wechat-channels"], 1),
        }
        for text, (tm, days, pfs, n) in cases.items():
            r = ST.parse(text)
            self.assertTrue(r["understood"], text)
            self.assertEqual((r["time"], r["days"], r["platforms"], r["per_day"]), (tm, days, pfs, n), text)
        self.assertFalse(ST.parse("hello there")["understood"])
        self.assertTrue(ST.parse("下周每天发")["next_week"])

    def test_post_text_and_limits(self):
        self.assertEqual(post_text(dict(title="标题", body="正文", tags=["a", "b"])), "标题\n\n正文\n\n#a #b")
        self.assertEqual(post_text(dict(title="标题", body="正文 #a", tags=["a"])), "标题\n\n正文 #a")
        self.assertEqual(post_text(None), "")
        # a platform with a title field gets the title there, not again as the text's first line; X leads with it
        self.assertEqual(post_text(dict(title="标题", body="正文", tags=["a"]), "youtube"), "正文\n\n#a")
        self.assertEqual(post_text(dict(title="标题", body="正文", tags=["a"]), "xiaohongshu:vertical"), "正文\n\n#a")
        self.assertEqual(post_text(dict(title="标题", body="正文", tags=["a"]), "x"), "标题\n\n正文\n\n#a")
        self.assertEqual(post_text(dict(title="标题", body="", tags=["a"]), "youtube"), "标题\n\n#a")   # no body: never empty
        n, lim = text_limit("x", "中文ab")
        self.assertEqual((n, lim), (6, 280))
        self.assertEqual(text_limit("xiaohongshu:vertical", "abc")[1], 1000)


if __name__ == "__main__":
    unittest.main()
