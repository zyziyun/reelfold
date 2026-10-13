"""RIFE frame interpolation (vstudio.rife), morph cuts (vstudio.morphcut) and RIFE slow motion: the decisions, the
wiring (cut.xfade_assemble morph joins, cleanup smooth, the talking-head default and the chat action) and, when the
rife-mlx weights are on this machine (VSTUDIO_RIFE_MODEL), the real network on synthetic frames."""
import json
import os
import shutil
import subprocess

import numpy as np
import pytest

from vstudio import cut, morphcut, rife
from vstudio import ffmpeg_filters as FF

needs_ff = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
needs_rife = pytest.mark.skipif(not rife.available(), reason="RIFE weights / MLX not available")


def _ramp_video(path, n=60, fps=30, w=320, h=180, jump_at=None, jump=0):
    """A grey gradient with a square that moves 1 px per frame (and ``jump`` px at frame ``jump_at``)."""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", path],
                         stdin=subprocess.PIPE)
    x0 = 40
    for i in range(n):
        if jump_at is not None and i == jump_at:
            x0 += jump
        img = np.tile(np.linspace(40, 200, w, dtype=np.uint8)[None, :, None], (h, 1, 3))
        x = x0 + i
        img[60:120, x:x + 60] = (230, 80, 60)
        p.stdin.write(img.tobytes())
    p.stdin.close()
    assert p.wait() == 0
    return path


# ------------------------------------------------------------------ decisions
def test_decide_morphs_only_small_moves_and_never_across_a_shot_change():
    assert morphcut.decide(dict(face=True, delta=0.02, bg=1.0))["action"] == "morph"
    small = morphcut.decide(dict(face=True, delta=0.0, bg=1.0), fps=30)
    big = morphcut.decide(dict(face=True, delta=0.06, bg=1.0), fps=30)
    assert small["frames"] == 3 and big["frames"] == 6           # 3-6 frames at 30 fps, more for a bigger move
    assert morphcut.decide(dict(face=True, delta=0.03, bg=1.0), fps=60)["frames"] >= 8   # scaled with the rate
    assert morphcut.decide(dict(face=True, delta=0.2, bg=1.0)) == dict(action="cut", frames=0, why="moved")
    assert morphcut.decide(dict(face=True, delta=0.01, bg=36.0))["why"] == "shot-change"
    assert morphcut.decide(dict(face=False, bg=0.5))["why"] == "no-face"


def test_joints_of_a_timemap():
    tm = cut.TimeMap.from_segments([(0, 2), (3, 5), (5, 6), (8, 9)])
    assert morphcut.joints_of(tm) == [2.0, 5.0]                  # 5 -> 5 is contiguous: no cut
    assert morphcut.joints_of(tm.to_list()) == [2.0, 5.0]


def test_yuv_round_trip_keeps_the_picture():
    rng = np.random.default_rng(1)
    img = (rng.random((36, 64, 3)) * 200 + 20).astype(np.uint8)
    img = img.repeat(2, 0).repeat(2, 1)                          # chroma-friendly (2x2 blocks)
    for m in ("bt709", "bt601"):
        back = morphcut.yuv_to_rgb(morphcut.rgb_to_yuv(img, m), 128, 72, m)
        assert np.abs(back.astype(int) - img.astype(int)).mean() < 3.0


def test_qc_refuses_a_flickering_bridge():
    a = np.full((64, 64, 3), 100, np.uint8)
    b = np.full((64, 64, 3), 110, np.uint8)
    good = [np.full((64, 64, 3), v, np.uint8) for v in (103, 105, 108)]
    assert morphcut._qc(a, b, good, [0.25, 0.5, 0.75])[0]
    flash = [np.full((64, 64, 3), 160, np.uint8)] * 3
    assert not morphcut._qc(a, b, flash, [0.25, 0.5, 0.75])[0]


def test_no_rife_leaves_the_video_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(rife, "available", lambda: False)
    src = tmp_path / "a.mp4"
    src.write_bytes(b"not really a video")
    rep = morphcut.smooth(str(src), str(tmp_path / "b.mp4"), [1.0, 2.0], log=None)
    assert rep["morphed"] == 0 and not rep["available"]
    assert [d["why"] for d in rep["joints"]] == ["no-rife", "no-rife"]
    assert (tmp_path / "b.mp4").read_bytes() == src.read_bytes()


@needs_ff
def test_find_cuts_sees_a_baked_in_jump(tmp_path):
    v = _ramp_video(str(tmp_path / "j.mp4"), jump_at=30, jump=40)
    assert morphcut.find_cuts(v) == [1.0]
    assert morphcut.find_cuts(_ramp_video(str(tmp_path / "s.mp4"))) == []


# ------------------------------------------------------------------ wiring
def test_xfade_assemble_morph_joins_are_hard_cuts_marked_for_the_bridge():
    asm = cut.xfade_assemble([(0, 2), (3, 5), (6, 8)], xfade=0.3, transition=["morph", "fade"], mute_pad=False)
    assert asm.xfades[1] == 0.0 and asm.xfades[2] == 0.3
    assert asm.morphs == [round(asm.offsets[1], 4)] and abs(asm.morphs[0] - 2.0) < 1e-6
    assert "concat=n=2:v=1:a=0[vx1]" in asm.graph and "xfade=transition=fade" in asm.graph


def test_render_assembly_bridges_morph_joins(monkeypatch, tmp_path):
    asm = cut.xfade_assemble([(0, 2), (3, 5)], xfade=0.0, transition="morph", mute_pad=False)
    calls = []
    monkeypatch.setattr(cut.media, "run", lambda cmd, **k: None)
    monkeypatch.setattr(morphcut, "smooth_inplace", lambda out, joints, **k: calls.append((out, joints)) or {})
    cut.render_assembly(asm, ["in.mp4"], str(tmp_path / "o.mp4"))
    assert calls == [(str(tmp_path / "o.mp4"), [2.0])]


def test_talking_head_smooths_jump_cuts_by_default_and_nothing_else_does():
    from vstudio import formats as F
    from vstudio.project import manifests as M
    assert F.get("talking-head")["smooth_cuts"] is True
    assert F.get("promo")["smooth_cuts"] is False and F.get("call-clips")["smooth_cuts"] is False
    assert M.param_defaults(M.get("talkinghead"))["smooth_cuts"] is True


def test_stage_keys_change_only_when_smoothing_is_on():
    from vstudio.batch import stages as ST
    from vstudio.batch import thfolder as TH
    k = ST._smooth_key(ST._keyp("cleanup_reply"))
    assert k(dict(params=dict(cleanup_reply="x")), {}) == dict(cleanup_reply="x")
    assert k(dict(params=dict(cleanup_reply="x", smooth_cuts=True)), {})["smooth_cuts"] is True
    k = TH._with_smooth(TH._keys("range"))
    assert k(dict(params=dict(range=None, smooth_cuts=False)), {}) == dict(range=None)


def test_vtrack_body_joints_carry_pass1_cuts_through_the_strict_keep():
    from vstudio.batch import thfolder as TH
    pass1 = dict(segs=[dict(clip=1, t0=0.0, t1=4.0, b0=0.0, b1=4.0), dict(clip=1, t0=5.0, t1=9.0, b0=4.0, b1=8.0),
                       dict(clip=1, t0=9.0, t1=12.0, b0=8.0, b1=11.0)])
    assert TH.body_joints(pass1) == [4.0]                         # 9 -> 9 is contiguous
    strict = dict(keep=[[0.0, 2.0], [3.0, 11.0]])                 # cut 2-3, pass-1 joint at 4 -> 3 in the output
    assert TH.body_joints(pass1, strict) == [2.0, 3.0]


def test_chat_action_smooth_the_jump_cuts():
    from vstudio.project import outfx as FX
    from vstudio.project import outputs as OUT
    for t in ("smooth the jump cuts", "平滑跳剪", "把跳剪平滑一下", "跳剪太生硬了", "add a morph cut"):
        assert OUT.wants_morph_cuts(t), t
        ops = OUT._rule_ops(t, 60.0, {})
        assert dict(op="effect_add", effect="morph-cuts", start=0) in ops, t
    for t in ("加个转场", "磨皮", "剪掉开头3秒"):
        assert not OUT.wants_morph_cuts(t), t
    assert FX.resolve("平滑跳剪") == "morph-cuts" and FX.resolve("smooth-cuts") == "morph-cuts"
    clean, _ = FX.validate("morph-cuts", {})
    assert clean["max_move"] == 0.06


def test_desk_proposes_smoothing_the_jump_cuts():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "desk", "engine"))
    from desk_engine import outputs as DO
    assert DO._wants_morph("平滑一下跳剪") and DO._wants_morph("smooth out the jump cuts")
    assert "morph-cuts" in DO.EFFECT_BY_ID and DO.ALIASES["平滑跳剪"] == "morph-cuts"


# ------------------------------------------------------------------ slow motion
def test_retime_slow_motion_falls_back_to_minterpolate():
    assert "minterpolate=fps=30" in FF.retime(29.97, 0.5, 30)
    assert FF.retime(59.94, 0.5, 30) == "setpts=PTS/0.5,fps=30"   # every 60p frame: no in-betweens needed
    assert rife.needs_interp(29.97, 0.5, 30) and rife.needs_interp(59.94, 0.25, 30)
    assert not rife.needs_interp(59.94, 0.5, 30) and not rife.needs_interp(30, 1.0, 30)


def test_slow_frames_positions(monkeypatch):
    seen = []

    def fake(a, b, ts, scale=None):
        seen.append([round(t, 3) for t in ts])
        return [np.full_like(a, int(a[0, 0, 0] + t * (int(b[0, 0, 0]) - int(a[0, 0, 0])))) for t in ts]
    monkeypatch.setattr(rife, "interpolate", fake)
    frames = [np.full((4, 4, 3), 10 * i, np.uint8) for i in range(4)]
    out = list(rife.slow_frames(frames, 0.25))
    assert [int(f[0, 0, 0]) for f in out] == [int(10 * k * 0.25) for k in range(13)]
    assert seen[0] == [0.25, 0.5, 0.75]
    assert len(list(rife._exactly(iter(out), 15))) == 15 and len(list(rife._exactly(iter(out), 5))) == 5


# ------------------------------------------------------------------ the real network (weights present)
@needs_rife
def test_rife_midpoint_lands_between_the_frames():
    a = np.zeros((128, 192, 3), np.uint8)
    b = np.zeros((128, 192, 3), np.uint8)
    a[40:80, 40:80] = 255
    b[40:80, 60:100] = 255                                       # the square moved 20 px
    mid = rife.interpolate(a, b, [0.5])[0]
    cols = np.where(mid[60, :, 0] > 128)[0]
    assert abs(cols.min() - 50) <= 3 and abs(cols.max() - 89) <= 3   # at 10 px, not a double exposure


@needs_rife
@needs_ff
def test_smooth_morphs_a_small_move_and_keeps_length(tmp_path, monkeypatch):
    v = _ramp_video(str(tmp_path / "j.mp4"), jump_at=30, jump=6)
    monkeypatch.setattr(morphcut, "measure", lambda a, b: dict(face=True, delta=0.02, bg=1.0))
    rep = morphcut.smooth(v, str(tmp_path / "m.mp4"), [1.0], report=str(tmp_path / "r.json"), log=None)
    assert rep["morphed"] == 1 and json.load(open(tmp_path / "r.json"))["joints"][0]["action"] == "morph"
    from vstudio import media
    assert abs(media.probe(str(tmp_path / "m.mp4"))["duration"] - media.probe(v)["duration"]) < 0.04
    assert morphcut.find_cuts(str(tmp_path / "m.mp4")) == []      # the jump is gone


@needs_rife
@needs_ff
def test_rife_slowmo_writes_the_planned_length(tmp_path):
    v = _ramp_video(str(tmp_path / "s.mp4"), n=15)
    out = rife.slowmo(v, str(tmp_path / "slow.mp4"), 0.0, None, speed=0.5, fps=30)
    from vstudio import media
    assert abs(media.probe(out)["duration"] - 1.0) < 0.05
