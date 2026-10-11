"""The desk's bundled ffmpeg is LGPL (no eq / hqdn3d / boxblur / smartblur / zscale): the engine's graphs, the
translation of old "eq=..." grade strings and the guard over every emitted filter.

0.2.6: a vlog render stopped at "No such filter: 'eq'" in the app."""
import os
import pathlib
import shutil
import subprocess
import sys

import numpy as np
import pytest

from vstudio import ffmpeg_filters as F

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_ffmpeg_filters as GUARD  # noqa: E402

BUNDLED = GUARD.read_list(GUARD.BUNDLED)


def _ffmpeg_with(*names):
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    have = GUARD.ffmpeg_filters(ff)
    return ff if all(n in have for n in names) else None


def _frame(ff, src, pre, vf):
    r = subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", src, "-vf", f"{pre},{vf},format=rgb24",
                        "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True)
    assert r.returncode == 0, r.stderr.decode()
    return np.frombuffer(r.stdout, np.uint8).astype(np.int16)


GRADES = [dict(brightness=0.05, contrast=1.12, saturation=1.18, gamma=1.04),        # vlog default (her 0.2.6 failure)
          dict(brightness=-0.06, contrast=1.08, saturation=1.05, gamma=0.96),       # talking-head / promo default
          dict(contrast=1.22, brightness=-0.07, saturation=1.3),                    # photo-story VEQ_FILTER
          dict(contrast=1.06, brightness=0.015, saturation=1.07, gamma=1.02),       # vertical polish grade
          dict(brightness=-0.08), dict(saturation=0.88), dict(saturation=0.0),
          dict(gamma=1.1, gamma_r=1.2, gamma_b=0.9, gamma_weight=0.5)]


# ------------------------------------------------------------------ the grade looks like eq
@pytest.mark.parametrize("src", ["testsrc2=s=320x180:d=1",
                                 "gradients=s=320x180:d=1:c0=red:c1=blue:c2=yellow:c3=green:n=4:seed=7"])
@pytest.mark.parametrize("pre", ["format=yuv420p", "format=yuv420p10le", "format=yuv444p"])
def test_lgpl_grade_renders_like_eq(src, pre):
    """Old eq graph vs the new LGPL graph on the same frame: mean abs diff per RGB channel <= 0.25, max <= 2 (it is
    bit-exact on the ffmpeg builds tried: brew 9.0, the bundled 8.1.2)."""
    ff = _ffmpeg_with("eq", "lutyuv")
    if not ff:
        pytest.skip("needs an ffmpeg with eq (a GPL build) to compare against")
    for g in GRADES:
        old = _frame(ff, src, pre, "eq=" + ":".join(f"{k}={v}" for k, v in g.items()))
        new = _frame(ff, src, pre, F.grade(**g))
        d = np.abs(old - new)
        assert d.mean() <= 0.25 and d.max() <= 2, (g, float(d.mean()), int(d.max()))


def test_lgpl_grade_runs_on_the_bundled_build():
    """VSTUDIO_TEST_LGPL_FFMPEG=<runtime>/ffmpeg/bin/ffmpeg: the graphs run there and match eq (from a GPL ffmpeg)."""
    lg = os.environ.get("VSTUDIO_TEST_LGPL_FFMPEG")
    if not lg:
        pytest.skip("set VSTUDIO_TEST_LGPL_FFMPEG to the bundled ffmpeg")
    assert "eq" not in GUARD.ffmpeg_filters(lg)
    ff = _ffmpeg_with("eq")
    for g in GRADES:
        new = _frame(lg, "testsrc2=s=320x180:d=1", "format=yuv420p", F.grade(**g))
        if ff:
            old = _frame(ff, "testsrc2=s=320x180:d=1", "format=yuv420p", "eq=" + ":".join(f"{k}={v}" for k, v in g.items()))
            assert np.abs(old - new).mean() <= 0.25
    for g in (F.DEFAULT_TH_GRADE, F.box_blur(30, 3), F.lgpl_graph("smartblur=1.5:-0.35")):
        _frame(lg, "testsrc2=s=320x180:d=1", "format=yuv420p", g)


def test_grade_graph_shape():
    assert F.grade() == "null"
    g = F.grade(brightness=0.05, contrast=1.12, saturation=1.18, gamma=1.04)
    assert F.filter_names(g) == ["format", "lutyuv"] and "eq" not in F.filter_names(g)
    assert set(F.filter_names(g)) <= BUNDLED
    assert F.filter_names(F.box_blur(30, 3)) == ["gblur"] and abs(float(F.box_blur(30, 3).split("=")[-1]) - 30.5) < 0.1
    assert F.filter_names(F.denoise(0.3)) == ["bilateral"]


# ------------------------------------------------------------------ old strings keep working
def test_translates_old_eq_strings():
    assert F.lgpl_graph("eq=brightness=-0.06:contrast=1.08:saturation=1.05:gamma=0.96") == \
        F.grade(brightness=-0.06, contrast=1.08, saturation=1.05, gamma=0.96)
    assert F.lgpl_graph("eq=1.06:0.015") == F.grade(contrast=1.06, brightness=0.015)            # positional
    assert F.lgpl_graph("eq=saturation='1.18'") == F.grade(saturation=1.18)                      # quoted
    assert F.lgpl_graph({"brightness": 0.04}) == F.grade(brightness=0.04)                        # dict form
    assert F.lgpl_graph(None) == "" and F.lgpl_graph("") == ""
    g, done = F.lgpl("[0:v]scale=1280:-2,eq@x=gamma=1.1[v];[v]boxblur=3:1,smartblur=1.5:-0.35[o]")
    assert done == ["eq", "boxblur", "smartblur"] and g.startswith("[0:v]scale=1280:-2,format=") and g.endswith("[o]")
    assert not set(F.filter_names(g)) & F.GPL_ONLY
    th, _ = F.lgpl("hqdn3d=1.2:1.2:3:3,eq=contrast=1.06:brightness=0.015:saturation=1.07:gamma=1.02,"
                   "colorbalance=rs=-0.02:bs=0.015:rm=-0.01,cas=0.45")
    assert th == F.DEFAULT_TH_GRADE
    # an expression / per-frame eq has no fixed lookup table: left alone (the guard keeps the code from emitting one)
    assert F.lgpl("eq=brightness=0.1*t:eval=frame")[1] == []
    assert F.lgpl("eq=gamma=1.1", available={"eq"}) == ("eq=gamma=1.1", [])                  # this ffmpeg has it


def test_user_grade_strings_are_translated_where_they_are_used(monkeypatch):
    from vstudio import h264, media
    monkeypatch.setattr(media, "_filters", lambda b: frozenset(BUNDLED))
    cmd = ["/x/ffmpeg", "-i", "a.mp4", "-vf", "scale=640:-2,eq=saturation=1.18", "b.mp4"]
    assert h264._lgpl_filters(cmd)[4] == "scale=640:-2," + F.grade(saturation=1.18)       # the subprocess hook
    assert media._portable_cmd(cmd)[4] == "scale=640:-2," + F.grade(saturation=1.18)      # media.run
    assert h264._lgpl_filters(["/x/ffmpeg", "-filters"]) == ["/x/ffmpeg", "-filters"]


def test_vlog_graphs_have_no_gpl_filter():
    sys.path.insert(0, str(ROOT / "workflows" / "vlog" / "scripts"))
    import build_vlog as V
    monkey = V.vlog_persona
    V.vlog_persona = lambda: {}
    try:
        cfg = dict(res=[1920, 1080], fit="blur")
        g = V.grade_chain(cfg, 0.0) + ";" + V.fit_chain(cfg)
    finally:
        V.vlog_persona = monkey
    names = set(F.filter_names(g))
    assert "lutyuv" in names and not names & F.GPL_ONLY and names <= BUNDLED


# ------------------------------------------------------------------ the guard
def test_guard_every_emitted_filter_is_in_the_bundled_build():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_ffmpeg_filters.py")], capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    used = GUARD.read_list(GUARD.ENGINE)
    assert {"lutyuv", "gblur", "scale", "xfade"} <= used and not used & F.GPL_ONLY
    assert used <= BUNDLED


def test_guard_catches_a_gpl_filter(tmp_path, monkeypatch):
    lib = tmp_path / "lib" / "vstudio"
    lib.mkdir(parents=True)
    (lib / "bad.py").write_text('W = 1\nvf = f"scale={W}:-2,eq=brightness=0.05,unsharp=5:5:0.5"\n'
                                'blur = "[bg]boxblur=30:3[b]"\nnote = "the eq of it, phase, signature"\n'
                                'opts = dict(eq=0.5)\n')
    monkeypatch.setattr(GUARD, "ROOT", tmp_path)
    uses = GUARD.static_uses(GUARD.read_list(GUARD.BUNDLED) | set(F.GPL_ONLY))
    assert {n for n in uses if n in F.GPL_ONLY} == {"eq", "boxblur"}        # prose and kwargs are not graphs
    assert uses["eq"] == [("lib/vstudio/bad.py", 2)]


def test_guard_checks_a_binary(tmp_path):
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("no ffmpeg")
    have = GUARD.ffmpeg_filters(ff)
    assert GUARD.check_binary(ff) == (0 if GUARD.read_list(GUARD.ENGINE) <= have else 1)


def test_polish_grade_returns_a_single_frame():
    """The talking-head cover grades ONE raw frame through stdin: a temporal denoise (atadenoise) never returns it on
    ffmpeg 6.1 (Ubuntu 24.04, CI) and the cover hung until the stall watchdog."""
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("no ffmpeg")
    r = subprocess.run([ff, "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "64x64", "-i", "-", "-vf",
                        F.DEFAULT_TH_GRADE, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], input=bytes(64 * 64 * 3),
                       capture_output=True, timeout=60)
    assert r.returncode == 0 and len(r.stdout) == 64 * 64 * 3
