"""The shot plan steering every footage builder (vstudio.brain.steer): calm segments, beat-short shots, the photo
story's spec, the talking head's jump cuts / punch-ins / B-roll, her per-shot changes reaching the drafted edit, and
each builder's per-shot edit list (``*.edl.json``) the clip timeline reads."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from vstudio.brain import steer as S
from vstudio.brain import store as ST
from vstudio.brain import template as T
from vstudio.brain import treat as TR

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VSTUDIO_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)


def _tile(i, clip="a", t0=0.0, dur=12.0, **kw):
    base = dict(id=f"C{i}.S1", clip=f"/x/{clip}.mp4", file=f"{clip}.mp4", start=t0, end=t0 + dur,
                best=[t0 + 2, t0 + 6], t=t0 + 4, score=0.8, sharp=0.8, steady=0.85, exposure=0.8, jitter_px=0.3,
                pan_px_s=20.0, motion=3.0, bright=0.45, lab=[120.0, 128.0, 130.0], faces=0, subject_frac=0.5,
                subject_xy=[0.5, 0.5], src_fps=30.0, w=3840, h=2160, time_of_day="evening", city="Seattle")
    base.update(kw)
    return base


def _doc(tiles, template, **kw):
    return dict(template=dict(label="x"), plan=TR.plan(tiles, template, **kw))


CLIPS = {"a": "/x/a.mp4", "b": "/x/b.mp4", "c": "/x/c.mp4"}


# --------------------------------------------------------------------------- calm vlog
def test_calm_segments_carry_the_joins_slow_motion_and_stabilise():
    ts = [_tile(1, "a"), _tile(2, "b"), _tile(3, "c", bright=0.12, exposure=0.5, lab=[60.0, 128, 140],
                                              time_of_day="night", score=0.7, src_fps=60.0, motion=10.0,
                                              steady=0.3, jitter_px=2.0)]
    doc = _doc(ts, "travel-calm")
    segs = S.calm(doc, CLIPS)
    by = {s["brain"]: s for s in segs}
    assert [s["clip"] for s in segs] == ["a", "b", "c"]
    assert "xfade" not in by["C1.S1"]                                  # the opening has no join
    assert by["C2.S1"]["xfade"] == 0.0                                 # same light: a hard cut
    assert by["C3.S1"]["xfade"] == 0.8                                 # dusk -> night: the template's dissolve
    assert by["C3.S1"].get("stabilize") is True


def test_annotate_gives_the_ai_windows_the_plan_and_her_change_wins():
    ts = [_tile(1, "a", src_fps=60.0, motion=10.0), _tile(2, "b")]
    doc = _doc(ts, "travel-calm", rife=False)
    picks = [dict(clip="a", start=3.0, dur=6.0), dict(clip="b", start=1.0, dur=5.0, xfade=1.2)]
    out = S.annotate(picks, doc, CLIPS)
    assert out[0]["brain"] == "C1.S1" and out[1]["brain"] == "C2.S1"
    assert out[1]["xfade"] == 1.2                                      # the drafter's own join stays (rules' row)
    row = doc["plan"]["shots"][1]
    row.update(by="her", transition=dict(kind="cut", s=0.0))
    assert S.annotate(picks, doc, CLIPS)[1]["xfade"] == 0.0            # her "cut here" wins over the drafter


# --------------------------------------------------------------------------- beat short
def test_beat_short_shots_land_on_beats_with_one_ramp():
    ts = [_tile(k, c, motion=4.0 + k, steady=0.9) for k, c in enumerate("abc", 1)]
    doc = _doc(ts, "beat-short", beats=True)
    shots = S.fun(doc, CLIPS)
    assert all(s["beats"] in (1, 2, 4) for s in shots)
    ramps = [s for s in shots if s.get("ramp") == S.RAMP]
    assert len(ramps) == 1 and ramps[0]["beats"] == 4
    assert all(s["brain"] for s in shots)
    assert S.beats_of(0.5) == 1 and S.beats_of(1.2) == 2 and S.beats_of(2.6) == 4


def test_fun_ai_picks_get_the_ramp_and_slow_motion_where_planned():
    ts = [_tile(1, "a", motion=12.0, steady=0.95), _tile(2, "b", motion=2.0)]
    doc = _doc(ts, "beat-short", beats=True)
    out = S.annotate([dict(clip="a", start=4.0, beats=2), dict(clip="b", start=2.0, beats=1)], doc, CLIPS,
                     fun_style=True)
    assert out[0]["ramp"] == S.RAMP and out[0]["beats"] == 4 and "ramp" not in out[1]


# --------------------------------------------------------------------------- photo story
SPEC = '''TITLE_ZH = "西雅图"
SCRIPT = [
    (0, [("Seattle at dusk.", "黄昏的西雅图。")], [("va", 1, "still", dict(off=3.0, label="Space Needle · 太空针塔")), ("vb", 1, "still", dict(off=2.0))]),
    (1, [("Night falls.", "夜幕降临。")], [("vc", 1, "still", None)]),
]
'''


def test_photo_story_spec_follows_the_plan_and_stays_plain_data():
    from vstudio.project import drafts as DR
    ts = [_tile(1, "a"), _tile(2, "b"), _tile(3, "c", bright=0.12, exposure=0.5, lab=[60.0, 128, 140],
                                              time_of_day="night", score=0.7)]
    doc = _doc(ts, "documentary")
    by_id = {k: dict(path=v) for k, v in CLIPS.items()}
    line = S.photo_line(doc, by_id)
    assert "va off=" in line and "Stills worth cutting" in line
    out, notes = S.photo_fix(SPEC, doc, by_id)
    assert DR.data_module_ok(out) and notes
    assert 'tr=\'cut\'' in out.split("vb")[1].split(")")[0] or "tr='cut'" in out
    assert "dict(tr='fade'" in out or "tr='fade'" in out                # vc: dusk -> night dissolve
    assert "label_at=" in out.split('"vb"')[0]                         # the labelled shot gets its text-safe third
    assert "太空针塔" in out and "黄昏的西雅图" in out                    # the 中文 survives the byte columns


def test_photo_story_shot_in_and_out():
    from vstudio.brain import generate as GN
    by_id = {k: dict(path=v) for k, v in CLIPS.items()}
    new = S.photo_shot(SPEC, "/g/ai_g1.mp4", after_clip="a", by_id=by_id, brain="g1")
    assert new.index('"v/g/ai_g1.mp4"') > new.index('"va"') and new.index('"v/g/ai_g1.mp4"') < new.index('"vb"')
    first = S.photo_shot(SPEC, "/g/ai_g2.mp4")
    assert first.index('"v/g/ai_g2.mp4"') < first.index('"va"')
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "spec.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write(new)
    GN._unplace_spec(p, "/g/ai_g1.mp4")
    with open(p, encoding="utf-8") as f:
        assert f.read() == SPEC


# --------------------------------------------------------------------------- talking head
def test_talking_head_spans_say_morph_punch_or_cut():
    ts = [dict(_tile(1, "talk", 0, 20, faces=1, face_area=0.05, speech=1.0), id="C1.S1"),
          dict(_tile(2, "talk", 20, 15, faces=1, face_area=0.05, speech=1.0), id="C1.S2")]
    doc = _doc(ts, "th-refined", rife=False)
    spans = S.talk(doc, "/x/talk.mp4")
    assert [s["join"] for s in spans] == [None, "punch"]               # no RIFE: the jump cut gets a punch-in
    assert S.joint_policy(spans, 25.0, "cut") == "punch" and S.joint_policy(spans, 5.0, "morph") == "morph"
    doc = _doc(ts, "th-refined", rife=True)
    assert S.talk(doc, "/x/talk.mp4")[1]["join"] == "morph"
    doc["plan"]["shots"][1].update(by="her", punch_in="none", transition=dict(kind="cut", s=0))
    assert S.talk(doc, "/x/talk.mp4")[1]["join"] == "cut"


class _Ctx:
    def __init__(self, d, params):
        self.dir, self.params = d, params

    def path(self, *n):
        return os.path.join(self.dir, *n)

    def log(self, m):
        pass


def test_thfolder_joints_follow_the_plan_and_compose_gets_punch_and_broll(tmp_path, monkeypatch):
    from vstudio.batch import thfolder as TH
    pass1 = dict(segs=[dict(clip=1, t0=0.0, t1=5.0, b0=0.0, b1=5.0, sid=0),
                       dict(clip=1, t0=6.0, t1=10.0, b0=5.0, b1=9.0, sid=1),       # a jump cut at 5.0 (source 6.0)
                       dict(clip=1, t0=22.0, t1=30.0, b0=9.0, b1=17.0, sid=2)])    # and at 9.0 (source 22.0)
    TH.write_json(str(tmp_path / "segs.pass1.json"), pass1)
    TH.write_json(str(tmp_path / "segs.strict.json"), {})
    spans = [dict(a=0.0, b=20.0, join="morph", brain="C1.S1"), dict(a=20.0, b=35.0, join="punch", brain="C1.S2")]
    ctx = _Ctx(str(tmp_path), dict(smooth_cuts=False))
    plan = TH.joint_plan(ctx, spans)
    assert plan == {5.0: "morph", 9.0: "punch"}
    called = {}
    monkeypatch.setattr("vstudio.morphcut.smooth_inplace",
                        lambda v, J, **kw: called.update(J=J) or dict(morphed=len(J), available=True))
    assert TH.smooth_body(ctx, spans) == 1 and called["J"] == [5.0]
    assert json.load(open(tmp_path / "punch.json")) == [9.0]
    cl = dict(punch=str(tmp_path / "punch.json"), pass1=str(tmp_path / "segs.pass1.json"),
              strict=str(tmp_path / "segs.strict.json"))
    subs = [dict(sid=0, start=0.0), dict(sid=1, start=5.0), dict(sid=2, start=9.05)]
    take = tmp_path / "g.mp4"
    take.write_bytes(b"x")
    monkeypatch.setattr(TH, "brain_broll", lambda p: [dict(id="g1", file=str(take), t=24.0, seconds=5.0)])
    punch, broll = TH.brain_compose(cl, subs, {})
    assert punch == [2] and broll == [dict(t0=11.0, t1=16.0, src=str(take), mode="cut", loop=False)]
    cfg = TH.config_file(dict(_clip_id="c1"), {}, False, punch=punch, broll=broll)
    assert "PUNCH = [2]" in cfg and "BROLL = [{'t0': 11.0" in cfg
    TH.write_json(str(tmp_path / "timeline.json"), dict(BODY_START=2.0, BODY_SPEED=1.0, TOTAL=19.0))
    monkeypatch.setattr(TH, "brain_spans", lambda p: spans)
    edl = json.load(open(TH.write_edl(ctx, cl, dict(source="/x/talk.mp4"), "m.mp4", broll)))
    roles = [r["role"] for r in edl["shots"]]
    assert roles[0] == "hook" and roles.count("body") == 3 and "broll" in roles
    body = [r for r in edl["shots"] if r["role"] == "body"]
    assert body[1]["t0"] == 7.0 and body[1]["src_in"] == 6.0 and body[2]["brain"] == "C1.S2"


# --------------------------------------------------------------------------- her change -> the drafted edit
@pytest.fixture
def project(tmp_path, monkeypatch):
    from vstudio.project.core import Project
    clips = []
    for k in range(2):
        c = tmp_path / f"c{k}.mp4"
        c.write_bytes(b"x")
        clips.append(str(c))
    pr = Project.create(str(tmp_path / "proj"), recipe="vlog", inputs=dict(footage=clips))
    pr.data["prompt"] = "Make a 30-second calm film from these drone shots."
    pr.data["items"] = [dict(id="v1")]
    pr.save()
    an = dict(files=[dict(id=f"f{k}", path=c, kind="video", duration=40, speech=False, orientation="horizontal",
                          talking_head=False, multi_person=False, screen_share=False) for k, c in enumerate(clips)])
    ts = [_tile(1, "a", src_fps=60.0, motion=10.0), _tile(2, "b")]
    ts[0]["clip"], ts[1]["clip"] = clips[0], clips[1]
    monkeypatch.setattr(ST, "_signals", lambda project, paths, refresh=False, light=False:
                        (T.signals(an, project.data["prompt"]), []))
    monkeypatch.setattr(ST, "_tiles", lambda project, paths, refresh=False, echo=None: ts)
    return pr, clips


def test_her_shot_change_reaches_the_drafted_edit(project):
    from vstudio.project.core import Project
    pr, clips = project
    doc = ST.show(pr)
    work = os.path.join(pr.dir, "items", "v1", "work")
    os.makedirs(work)
    segs = S.calm(doc, {"a": clips[0], "b": clips[1]})
    with open(os.path.join(work, "edit.json"), "w") as f:
        json.dump(dict(clips={"a": clips[0], "b": clips[1]}, segments=segs), f)
    sid = segs[1]["brain"]
    r = ST.set_shot(Project(pr.dir), sid, transition="dissolve")
    assert r["edit"] and r["edit"][0]["changed"] == 1
    got = json.load(open(os.path.join(work, "edit.json")))["segments"]
    assert got[1]["xfade"] == 0.8
    row = next(r for r in ST.show(Project(pr.dir))["plan"]["shots"] if r["id"] == sid)
    assert row["why"][0]["code"] == "her-join" and "dissolve" in row["why"][0]["en"]     # her reason, not the rules'
    assert not any(w["code"] in ("cut", "match-cut") for w in row["why"])
    ST.set_shot(Project(pr.dir), sid, skip=True)
    assert [s["brain"] for s in json.load(open(os.path.join(work, "edit.json")))["segments"]] == [segs[0]["brain"]]


# --------------------------------------------------------------------------- the builders' edit lists
def _clip(path, src, secs):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}=size=320x180:rate=30", "-t", str(secs),
                    "-pix_fmt", "yuv420p", path], check=True)


@needs_ffmpeg
def test_build_vlog_joins_per_segment_and_writes_its_edit_list(tmp_path):
    for k, src in enumerate(("testsrc2", "mandelbrot", "testsrc")):
        _clip(str(tmp_path / f"c{k}.mp4"), src, 4)
    cfg = dict(src_dir=".", clips={"a": "c0.mp4", "b": "c1.mp4", "c": "c2.mp4"}, res=[320, 180], fps=30, xfade=0.8,
               fade_out=0.5, match_exposure=0, deflicker=False, qc={"flicker": "off"}, out="m.mp4",
               segments=[dict(clip="a", start=0, dur=3, brain="C1.S1"), dict(clip="b", start=0, dur=3, xfade=0,
                                                                              brain="C2.S1"),
                         dict(clip="c", start=0, dur=3, brain="C3.S1")])
    with open(tmp_path / "edit.json", "w") as f:
        json.dump(cfg, f)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "lib"))
    subprocess.run([sys.executable, os.path.join(ROOT, "workflows/vlog/scripts/build_vlog.py"),
                    str(tmp_path / "edit.json")], check=True, capture_output=True, env=env)
    edl = json.load(open(tmp_path / "m.edl.json"))
    assert edl["builder"] == "calm" and [s["join"] for s in edl["shots"]] == [None, "cut", "dissolve"]
    assert [s["brain"] for s in edl["shots"]] == ["C1.S1", "C2.S1", "C3.S1"]
    assert abs(edl["duration"] - (9 - 1 / 30 - 0.8)) < 0.05
    sh = json.load(open(tmp_path / "m.shots.json"))
    assert len(sh["transitions"]) == 1                                  # only the real dissolve
    assert edl["shots"][1]["t1"] == edl["shots"][2]["t0"]


def test_build_fun_and_photo_story_edit_lists(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "workflows/vlog/scripts"))
    import build_fun
    tl = [dict(t0=0.0, t1=1.1, src="/x/a.mp4", kind="video", role="hook", nb=2, src_span=(3.0, 4.1)),
          dict(t0=1.1, t1=3.3, src="/x/b.mp4", kind="video", role="body", nb=4, src_span=(2.0, 3.0), ramp=S.RAMP,
               brain="C2.S1", clip="b")]
    build_fun.write_edl(str(tmp_path / "r.edl.json"), tl, [dict(i=1, kind="cut")], 3.3)
    d = json.load(open(tmp_path / "r.edl.json"))
    assert d["shots"][1]["brain"] == "C2.S1" and d["shots"][1]["join"] == "cut" and d["shots"][1]["ramp"] == S.RAMP
    sys.path.insert(0, os.path.join(ROOT, "workflows/photo-story/scripts"))
    from photostory import render as PR

    class C:
        def find_video(self, n):
            return f"/x/{n}.mp4"

        def find_image(self, n):
            return f"/x/{n}.jpg"

    class Tl:
        total = 10.0
        shots = [dict(src="va", start=0.0, end=5.0, off=3.0, tr=None, trd=0, brain="C1.S1"),
                 dict(src="vb", start=5.0, end=10.0, off=2.0, tr="fade", trd=1.0, label="X", label_at="upper")]
    monkeypatch.setattr(PR, "parse_src", lambda C_, src: ("video", src[1:]))
    PR.write_edl(C(), Tl(), str(tmp_path / "story.mp4"))
    d = json.load(open(tmp_path / "story.edl.json"))
    assert [s["join"] for s in d["shots"]] == [None, "dissolve"] and d["shots"][1]["t0"] == 5.5
    assert d["shots"][0]["src_in"] == 3.0 and d["shots"][1]["label_at"] == "upper"
