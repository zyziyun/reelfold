"""Shot-to-shot colour match + film looks (vstudio.colormatch), ghosting dissolves (vstudio.dissolve) and the small
re-make slips (doubled punctuation, labels in the version's language) - premium item 2 / 6, 2026-10-12."""
import os
import pathlib
import subprocess
import sys
import types

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "workflows" / "photo-story" / "scripts"))

from vstudio import colormatch as CM  # noqa: E402
from vstudio import dissolve as DS  # noqa: E402


def _scene(tint=(0, 0, 0), bright=0.0, seed=0, h=72, w=128):
    """A textured RGB frame (0-1) with a colour cast."""
    r = np.random.default_rng(seed)
    base = np.clip(r.normal(0.45, 0.16, (h, w, 1)) + np.linspace(-0.1, 0.1, w)[None, :, None], 0.05, 0.95)
    rgb = np.repeat(base, 3, axis=2) * np.array([1.0, 0.95, 0.9]) + np.asarray(tint) + bright
    return np.clip(rgb, 0, 1)


# ------------------------------------------------------------------------------------------------ the transfer
def test_mkl_maps_one_covariance_onto_the_other():
    a = np.array([[0.02, 0.004], [0.004, 0.01]])
    b = np.array([[0.008, -0.002], [-0.002, 0.015]])
    t = CM.mkl(a, b)
    assert np.allclose(t @ a @ t.T, b, atol=1e-9)
    assert np.allclose(t, t.T)                                    # the least-moving (symmetric) solution


def test_transfer_pulls_a_warm_shot_toward_the_reference_but_keeps_its_light():
    warm, cool = _scene((0.05, 0.0, -0.05), seed=1), _scene((-0.03, 0.0, 0.04), seed=2)
    sw, sc = CM.stats(warm), CM.stats(cool)
    before = CM.chroma_jump(sw, sc)
    after = CM.chroma_jump(CM.stats(np.clip(CM.transfer(sw, sc, 0.6)(warm), 0, 1)), sc)
    assert before > 8 and after < before * 0.6                   # the colour step at the cut gets much smaller
    full = CM.transfer(sw, sc, 1.0)(warm)
    assert CM.chroma_jump(CM.stats(np.clip(full, 0, 1)), sw) <= CM.CHROMA_CAP * 255 + 1.5   # ... never past the cap
    night, day = _scene(bright=-0.3, seed=3), _scene(bright=0.25, seed=4)
    moved = CM.transfer(CM.stats(night), CM.stats(day), 1.0)(night)
    assert abs(CM.stats(np.clip(moved, 0, 1))["mean"][0] - CM.stats(night)["mean"][0]) <= CM.LUMA_CAP + 0.01
    assert np.allclose(CM.transfer(sw, sc, 0.0)(warm), warm)     # strength 0 = untouched


def test_reference_is_the_medoid_or_the_one_asked_for():
    st = {k: CM.stats(_scene((d, 0, -d), seed=k)) for k, d in enumerate((-0.04, 0.0, 0.01, 0.06))}
    assert CM.reference(st) in (1, 2)
    assert CM.reference(st, prefer=3) == 3
    assert CM.reference({}) is None


# ------------------------------------------------------------------------------------------------ looks + LUTs
def test_six_film_looks_are_gentle_at_35_percent():
    assert len(CM.LOOKS) == 6 and set(CM.LOOK_LABELS) == set(CM.LOOKS)
    ident = CM.identity(17)
    for name in CM.LOOKS:
        t = CM.bake(CM.look(name), n=17)
        assert t.shape == (17, 17, 17, 3) and t.min() >= 0 and t.max() <= 1
        dev = np.abs(t - ident)
        assert 0.003 < dev.mean() < (0.1 if name == "mono-silver" else 0.03), name   # barely there
        if name != "mono-silver":                                # (black and white at 35 % still greys pure red)
            assert dev.max() < 0.15, name
    mono = CM.bake(CM.look("mono-silver", 1.0), n=9)
    assert np.abs(mono[..., 0] - mono[..., 2]).max() < 0.03      # black and white (a faint silver tone)
    assert CM.look_name("Kodak") == "kodak-2383-soft" and CM.look_name("黑白") == "mono-silver"
    assert CM.look_name("none") is None and CM.look_name(None) is None
    with pytest.raises(ValueError):
        CM.look_name("teal-orange")


def test_cube_round_trip_and_lut3d_matches_numpy(tmp_path):
    src = CM.stats(_scene((0.05, 0, -0.04), seed=5))
    ref = CM.stats(_scene((-0.02, 0, 0.03), seed=6))
    table = CM.shot_lut(src, ref, "kodak-2383-soft")
    assert not CM.is_identity(table) and CM.is_identity(CM.shot_lut(None, None, None))
    cube = CM.write_cube(table, str(tmp_path / "luts dir, with comma"))
    assert CM.write_cube(table, str(tmp_path / "luts dir, with comma")) == cube        # content-addressed, once
    assert np.allclose(CM.read_cube(cube), table, atol=1e-5)
    img = (np.clip(_scene((0.05, 0, -0.04), seed=7, h=36, w=64), 0, 1) * 255).astype(np.uint8)
    png = tmp_path / "in.png"
    from PIL import Image
    Image.fromarray(img).save(png)
    from vstudio import media
    r = subprocess.run([media.ffmpeg_bin(), "-v", "error", "-i", str(png), "-vf", CM.lut3d_filter(cube) +
                        ",format=rgb24", "-f", "rawvideo", "-"], capture_output=True)
    assert r.returncode == 0, r.stderr
    out = np.frombuffer(r.stdout, np.uint8).reshape(36, 64, 3).astype(float)
    want = CM.apply(table, img.astype(float))
    assert np.abs(out - want).mean() < 2.0                       # ffmpeg's tetrahedral ~ our trilinear


def test_lut3d_filter_quotes_paths_for_the_filtergraph():
    f = CM.lut3d_filter("/tmp/a b,c/x.cube")
    want = os.path.abspath("/tmp/a b,c/x.cube").replace("\\", "/").replace(":", "\\:")  # D\:/tmp/... on Windows
    assert f == f"lut3d=file='{want}':interp=tetrahedral"
    if os.name != "nt":
        assert CM.lut3d_filter("/tmp/C:/x.cube").startswith("lut3d=file='/tmp/C\\:/x.cube'")
    with pytest.raises(ValueError):
        CM.lut3d_filter("/tmp/it's.cube")


def test_photostory_grade_plan_gives_each_shot_one_lut(tmp_path, monkeypatch):
    from photostory import grade, shots as SH
    clips = {}
    for i, tint in enumerate(((0.06, 0, -0.05), (-0.03, 0, 0.05), (0.0, 0.0, 0.0))):
        p = tmp_path / f"c{i}.mp4"
        r, g, b = (int(np.clip(110 + 255 * x, 0, 255)) for x in tint)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"color=c=0x{r:02x}{g:02x}{b:02x}:s=160x90:d=2,noise=alls=40:allf=t",
                        "-pix_fmt", "yuv420p", str(p)], check=True)
        clips[f"c{i}"] = str(p)
    monkeypatch.setattr(grade, "prep_video", lambda C, sh, name: clips[name])
    monkeypatch.setattr(grade, "parse_src", lambda C, src: ("video", src) if src.startswith("c") else ("img", src))
    C = types.SimpleNamespace(COLOR_MATCH=0.6, COLOR_REF=None, GRADE_LOOK="cinema-neutral", GRADE_LOOK_STRENGTH=0.35,
                              cache_dir=str(tmp_path / "cache"))
    T = types.SimpleNamespace(shots=[dict(src=s, start=2.0 * k, end=2.0 * k + 2, tail=0.8)
                                     for k, s in enumerate(["c0", "c1", "c2", "photo"])])
    rep = grade.plan(C, T)
    assert rep["ref"] == 2 and rep["look"] == "cinema-neutral"
    assert all(os.path.exists(T.shots[k]["_lut"]) for k in range(3))
    assert T.shots[3]["_lut_table"].shape[-1] == 3               # photos get the look in numpy
    out = SH.graded(C, clips["c0"], T.shots[0]["_lut"])
    st0, st2 = (CM.stats(CM.sample(p, 0, 2)) for p in (out, clips["c2"]))
    assert CM.chroma_jump(st0, st2) < CM.chroma_jump(CM.stats(CM.sample(clips["c0"], 0, 2)), st2)
    C.COLOR_MATCH, C.GRADE_LOOK = 0.0, None
    assert grade.plan(C, types.SimpleNamespace(shots=[dict(src="c0")])) == dict(ref=None, look=None, shots=[])


# ------------------------------------------------------------------------------------------------ ghosting joins
def _landmark(dx=0, scale=1.0, seed=11):
    """A night skyline-like frame (lights + a tower) with the tower moved by dx px / scaled."""
    import cv2
    rng = np.random.default_rng(seed)
    big = np.zeros((540, 960), np.uint8)
    for _ in range(500):
        x, y = rng.integers(0, 960), rng.integers(200, 540)
        cv2.circle(big, (int(x), int(y)), int(rng.integers(1, 4)), int(rng.integers(120, 255)), -1)
    cv2.rectangle(big, (460, 60), (500, 400), 200, -1)
    cv2.ellipse(big, (480, 120), (90, 22), 0, 0, 360, 230, -1)
    M = np.float32([[scale, 0, (1 - scale) * 480 + dx], [0, scale, (1 - scale) * 270]])
    return cv2.warpAffine(big, M, (960, 540))


def test_same_subject_moved_is_a_ghost_risk_a_new_scene_is_not():
    a = _landmark()
    moved = DS.ghost_risk(a, _landmark(dx=170))
    assert moved["risk"] and moved["shift"] > DS.SHIFT_CUT and DS.choose(moved, 0.8) == ("cut", 0.0)
    near = DS.ghost_risk(a, _landmark(dx=55))
    assert near["risk"] and DS.choose(near, 0.8) == ("fade", DS.SHORT_TRD)
    still = DS.ghost_risk(a, _landmark(dx=2))
    assert not still["risk"] and DS.choose(still, 0.8) == ("fade", 0.8)          # one continuous move: keep it
    other = DS.ghost_risk(a, _landmark(seed=99, dx=300))
    assert DS.choose(other, 0.8)[1] in (0.8, DS.SHORT_TRD, 0.0)
    assert not DS.ghost_risk(a, np.zeros_like(a))["risk"]                         # nothing in common
    assert DS.choose(moved, 0.8, tr="cut") == ("cut", 0.8) and DS.choose(moved, 0.25) == ("fade", 0.25)


def test_photostory_joins_plan_turns_a_ghosting_dissolve_into_a_cut(monkeypatch):
    from photostory import dissolves
    frames = {("a", 3.4): _landmark(), ("b", 0.4): _landmark(dx=170), ("b", 3.4): _landmark(dx=171),
              ("c", 0.4): _landmark(seed=5)}
    monkeypatch.setattr(dissolves, "prep_video", lambda C, sh, name: name)
    monkeypatch.setattr(dissolves, "parse_src", lambda C, src: ("video", src))
    monkeypatch.setattr(dissolves, "frame_at", lambda clip, t: np.dstack([frames[(clip, round(t, 1))]] * 3))
    shots = [dict(src="a", start=0.0, end=3.0, tr=None, trd=0, tail=0.8),
             dict(src="b", start=3.0, end=6.0, tr="fade", trd=0.8, tail=0.8),
             dict(src="c", start=6.0, end=9.0, tr="fade", trd=0.8, tail=99)]
    ch = dissolves.plan(types.SimpleNamespace(spec=types.SimpleNamespace()), types.SimpleNamespace(shots=shots))
    assert [c["k"] for c in ch] == [1] and shots[1]["tr"] == "cut" and shots[0]["tail"] == 0.0
    assert shots[2]["tr"] == "fade" and shots[2]["trd"] == 0.8


# ------------------------------------------------------------------------------------------------ text slips
def test_doubled_punctuation_is_tidied():
    from vstudio.subs import tidy_punct
    assert tidy_punct("然后，叶子一片一片，，松开手。") == "然后，叶子一片一片，松开手。"
    assert tidy_punct("一片，**，松开手**") == "一片，**松开手**"
    assert tidy_punct("好了，。") == "好了。" and tidy_punct("a,, b") == "a, b"
    assert tidy_punct("Wait...") == "Wait..." and tidy_punct("真的？！") == "真的？！"
    from photostory.timeline import Timeline
    C = types.SimpleNamespace(cinema=True, SECTIONS=["A"], spec=types.SimpleNamespace(
        PACING={}, SCRIPT=[(0, [("Then, they let go.", "然后，叶子一片，，松开手。")], [("v1", 1, "still", {})])]))
    T = Timeline(C, {0: dict(dur=4.0, path=None, chunks=[dict(start=0, end=4)])})
    assert T.subs[0]["zh"] == "然后，叶子一片，松开手。"


def test_labels_follow_the_version_language(tmp_path, capsys):
    from photostory.ctx import Ctx, load_spec
    spec = tmp_path / "spec.py"
    spec.write_text('TITLE_ZH = "夜"\nTITLE_EN = "Night"\nSECTIONS = ["序"]\nSCRIPT = []\nSUB_LEAD = "zh"\n'
                    'LABELS_ZH = {"Pacific Science Center": "太平洋科学中心"}\n')
    sp = load_spec(str(spec))
    sp.PLATFORM = "xiaohongshu:vertical"
    C = Ctx(sp)
    assert C.shown("Space Needle · 太空针塔") == "太空针塔"
    assert C.shown("Pacific Science Center") == "太平洋科学中心"          # the spec's own table
    assert C.shown("Seattle") == "西雅图"                                  # the gazetteer
    assert C.shown("Space Needle") == ""                                   # never English on the Chinese version
    assert "no Chinese part" in capsys.readouterr().out
    sp = load_spec(str(spec))
    sp.PLATFORM = "youtube"
    C = Ctx(sp)
    assert C.shown("太空针塔") == "" and C.shown("西雅图") == "Seattle" and C.shown("Space Needle") == "Space Needle"


def test_drafted_labels_get_the_missing_language(monkeypatch):
    from vstudio.project.adapters import photostory as PS
    text = ('SCRIPT = [\n    (0, [("The tower.", "塔。")], [\n        ("vA", 1, "still", dict(off=1.0, label="Space Needle")),'
            '\n        ("vB", 1, "still", dict(label="International Fountain · 国际喷泉")),\n    ]),\n]\n'
            'NOTE = "Space Needle"\n')
    asked = {}

    def fake(role, system, body, **kw):
        asked["body"] = body
        return dict(json=dict(labels={"Space Needle": "太空针塔"}), provider="fake")
    out = PS.label_language(text, True, fake)
    assert "label='Space Needle · 太空针塔'" in out and 'NOTE = "Space Needle"' in out
    assert "International Fountain" not in asked["body"]                   # already bilingual: not asked
    from vstudio.project import drafts as DR
    assert DR.data_module_ok(out)
    assert PS.label_language(text, True, lambda *a, **k: dict(provider="none")) == text
    assert PS.label_language(text, False, fake) == text                    # English version: English is there
