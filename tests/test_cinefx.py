"""vstudio.cinefx: the cine vlog engine on synthetic media (lavfi clips, generated photos).

    python3 -m pytest tests/test_cinefx.py -q
"""
import os
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from vstudio import cinefx as C

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg needed")


def _clip(path, w, h, dur=2.0):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r=30:d={dur}",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", path], check=True)


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    root = tmp_path_factory.mktemp("cine") / "work"
    (root / "sdr").mkdir(parents=True)
    (root / "photos_full").mkdir()
    _clip(str(root / "sdr" / "tall.mp4"), 1080, 1920)
    _clip(str(root / "sdr" / "wide.mp4"), 1920, 1080)
    rng = np.random.default_rng(0)
    for name, size in (("p_tall", (1200, 1600)), ("p_wide", (1600, 1200)), ("p_sq", (1400, 1400))):
        a = rng.integers(0, 255, (size[1] // 8, size[0] // 8, 3), dtype=np.uint8)
        Image.fromarray(a).resize(size).save(root / "photos_full" / f"{name}.jpg")
    C.configure(str(root), None, beat=0.5, music_start=0.0)
    return root


def _ok(frame):
    assert frame.shape == (C.H, C.W, 3)
    assert np.isfinite(frame).all()


def test_beat_grid_and_sequence(proj):
    assert C.B(4) == pytest.approx(2.0)
    shots = C.sequence(1.0, [(1, lambda a, b: C.Photo(a, b, "p_tall")), (2, lambda a, b: C.Photo(a, b, "p_sq"))])
    assert [(s.t0, s.t1) for s in shots] == [(1.0, 1.5), (1.5, 2.5)]


@pytest.mark.parametrize("look", sorted(C.LOOKS))
def test_finish_keeps_shape_and_range(look):
    img = np.full((C.H, C.W, 3), 128, np.float32)
    img[900:1000, 500:600] = 255               # a highlight for the halation
    out = C.finish(img, 5, look)
    _ok(out)
    assert -20 < out.min() and out.max() < 300


def _shots():
    return [
        C.Clip(0, 1, "tall", 0.0, zoom=(1.0, 1.04)),
        C.Clip(0, 1, "tall", 0.0, ramp=[(0, 3.0), (1, 0.8)]),
        C.Photo(0, 1, "p_wide", z=(1.0, 1.06)),
        C.Opening(0, 4, ("wide", 0.0), ("tall", 0.0), "标题", "TITLE", "2026"),
        C.Triptych(0, 1.5, [("wide", 0.0, 0.5), ("wide", 0.5, 0.5), ("wide", 1.0, 0.5)], 0.2),
        C.Dual(0, 1.5, ("wide", 0.0), ("wide", 0.5), 0.2),
        C.Super8(0, 1.5, "tall", 0.0, 1.0, date="1 1 '26"),
        C.FilmStrip(0, 1.5, ["p_tall", "p_sq"], edge="400T"),
        C.Slides(0, 2, [("p_wide", "一"), ("p_tall", "二")]),
        C.Strip(0, 1.5, "wide", 0.0, reveal=0.5, close=0.5),
        C.Strip(0, 1.5, photo_name="p_wide"),
        C.Print(0, 2, "p_wide", settle=1.0, fade_from=1.5, label="place"),
        C.EndCard(0, 2, "片尾", "SUB"),
        C.DoubleExp(0, 1, ("tall", 0.0), ("tall", 0.5)),
    ]


@pytest.mark.parametrize("i", range(len(_shots())))
def test_every_shot_draws(proj, i):
    s = _shots()[i]
    s.open()
    try:
        for t in (0.0, (s.t1 - s.t0) / 2, s.t1 - s.t0 - 0.04):
            out = C.finish(s.draw(t, s.t0 + t), int(t * 30), s.look)
            _ok(out)
    finally:
        s.close()


def test_project_captions_overlays_and_dips(proj):
    vo = [("talk", 2.0, 4.0, 10.0, [(2.0, 3.0, "第一句"), (3.0, 4.0, "第二句")])]
    P = C.Project(lambda: [C.Photo(0, 12, "p_tall")], vo=vo, labels=[(1.0, "章节", "CHAPTER")],
                  hook=(0.1, 2.0, "钩子"), typewriter=(5.0, "typed line"), leak=6.0, dips=[8.0])
    assert P.caps == [(10.0, 11.15, "第一句"), (11.0, 12.15, "第二句")]
    base = np.full((C.H, C.W, 3), 90, np.float32)
    for gt in (0.5, 1.5, 5.5, 6.0, 8.0, 10.5):
        _ok(C.overlays(base.copy(), gt, P))
    dipped = C.dips(8.0, base.copy(), P)
    assert dipped.mean() < base.mean() * 0.5                 # a dip, never a white flash


def test_covers_same_canvas(proj, tmp_path):
    for img in (C.cover_negative("p_tall", "标题", "副标题", "EN", foot=("2026", "CITY")),
                C.cover_still("p_wide", "标题", "副标题", "EN", top="上", bottom="00:00"),
                C.cover_strip(["p_tall", "p_wide", "p_sq"], "标题", "副标题", "EN")):
        _ok(img)
    p = C.save_cover(C.cover_strip(["p_tall", "p_wide", "p_sq"], "标题"), str(tmp_path / "c.png"))
    assert Image.open(p).size == (C.W, C.H)


def test_burn_cover_keeps_duration_and_frames(proj, tmp_path):
    v = str(tmp_path / "v.mp4")
    _clip(v, 1080, 1920, dur=1.0)
    cover = C.save_cover(np.full((C.H, C.W, 3), 200, np.float32), str(tmp_path / "cover.png"))

    def frames(path):
        return int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                   "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", path],
                                  capture_output=True, text=True).stdout.strip())
    n = frames(v)
    C.burn_cover(v, cover, frames=3)
    assert frames(v) == n
    first = subprocess.run(["ffmpeg", "-v", "error", "-i", v, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt",
                            "rgb24", "-"], capture_output=True).stdout
    assert np.frombuffer(first, np.uint8).mean() == pytest.approx(200, abs=6)


# ------------------------------------------------------------------------------------------------ example + tools
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(REPO, "workflows", "vlog", "examples", "cine.example.py")


def test_example_timeline_is_gapless_and_on_beat():
    P = C.load(EXAMPLE)
    S = P.timeline()
    assert S[0].t0 == 0
    for a, b in zip(S, S[1:]):
        assert b.t0 == pytest.approx(a.t1), f"gap or overlap between {type(a).__name__} and {type(b).__name__}"
    for s in S:
        beats = (s.t1 - s.t0) / C.BEAT
        assert beats == pytest.approx(round(beats * 2) / 2, abs=1e-6), "every shot is a whole or half beat"
        assert beats >= 1 - 1e-6, "no half-beat cuts: they read as flicker"
    assert P.total == pytest.approx(S[-1].t1)
    assert all(0 <= t0 < t1 <= P.total for t0, t1, _ in P.caps)
    assert P.hook and P.hook[0] > 0, "the hook text starts after the burned-in cover frames"


def _tools():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "cine_tools", os.path.join(REPO, "workflows", "vlog", "scripts", "cine_tools.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_lag_detects_shift_and_sync():
    T = _tools()
    rng = np.random.default_rng(1)
    env = np.repeat(rng.random(400), 480).astype(np.float32)
    x = env * rng.normal(0, 1, env.size).astype(np.float32)
    assert T.lag_ms(x, x) == 0
    shifted = np.concatenate([np.zeros(4800, np.float32), x[:-4800]])   # 100 ms later
    assert abs(T.lag_ms(x, shifted) - 100) <= 2


def test_photo_full_keeps_resolution_and_rotation(tmp_path):
    T = _tools()
    src = tmp_path / "p.jpg"
    im = Image.new("RGB", (4000, 3000), (10, 20, 30))
    exif = im.getexif()
    exif[274] = 6                          # rotated 90: must come out portrait
    im.save(src, exif=exif)
    out = T.photo_full(str(src), str(tmp_path / "o.jpg"))
    assert Image.open(out).size == (3000, 4000)
