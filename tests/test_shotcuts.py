"""Shot cuts of an imported finished film (vstudio.shotmatch.detect_shots): a synthetic graded, compressed film with
hard cuts, crossfades and a dip to black is cut into all of its shots; a single moving take stays one shot.
Media made with ffmpeg (lavfi), nothing mocked."""
import shutil
import subprocess

import pytest

from vstudio import shotmatch as SM

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")

# six "aerial" shots: a textured picture under a slow drone-like push / drift, all under one grade (so the shots side
# by side are close in tone, as in a finished film)
_M = "mandelbrot=s=480x270:r=30:start_x={x}:start_y={y}:start_scale={s}:end_scale={e}:end_pts=400:inner=convergence"
SHOTS = [
    _M.format(x=-0.743643887, y=0.131825904, s=0.02, e=0.012),
    _M.format(x=-0.75, y=0.1, s=0.2, e=0.15),
    _M.format(x=-1.25066, y=0.02012, s=0.05, e=0.03),
    _M.format(x=0.285, y=0.01, s=0.1, e=0.07),
    _M.format(x=-0.1011, y=0.9563, s=0.04, e=0.03),
    _M.format(x=-1.768, y=0.001, s=0.03, e=0.02),
]
LEN = 4.0
# the transition into shot k+1: (xfade transition, seconds); a 1-frame fade is a hard cut
JOINS = [("fade", 1 / 30), ("fade", 0.8), ("fadeblack", 0.8), ("dissolve", 0.6), ("fade", 1 / 30)]


def _ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def film(tmp_path_factory):
    root = tmp_path_factory.mktemp("cuts")
    ins = []
    for src in SHOTS:
        ins += ["-f", "lavfi", "-t", str(LEN), "-i", f"{src},crop=320:180:x='80*t/{LEN}':y=45,format=yuv420p,setsar=1"]
    graph, prev, off, cuts = [], "0:v", 0.0, []
    for k, (tr, dur) in enumerate(JOINS):
        off += LEN - dur
        out = f"x{k}"
        graph.append(f"[{prev}][{k + 1}:v]xfade=transition={tr}:duration={dur:.4f}:offset={off:.4f}[{out}]")
        cuts.append(off + dur / 2)
        prev = out
    # a finished film's grade (low contrast, warm) and a heavy delivery compression
    graph.append(f"[{prev}]eq=contrast=0.65:saturation=0.8:brightness=0.03,format=yuv420p[g]")
    path = root / "film.mp4"
    _ff(*ins, "-filter_complex", ";".join(graph), "-map", "[g]", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "34", str(path))
    return dict(path=str(path), cuts=cuts)


def _shots(path):
    info = SM.probe(path)
    fw, fh = SM._fin_size(info["w"], info["h"])
    t, frames = SM._decode(path, fw, fh, fps=SM.FIN_FPS)
    return SM.detect_shots(t, frames, info["duration"])


def test_finished_film_with_crossfades_has_every_shot(film):
    shots = _shots(film["path"])
    assert len(shots) == len(SHOTS), shots
    for (a, _b), cut in zip(shots[1:], film["cuts"]):
        assert abs(a - cut) <= 0.45, (a, cut)


def test_one_moving_take_is_one_shot(tmp_path):
    # a slow pan + zoom over one picture (a drone move): change every frame, but no cut
    path = tmp_path / "take.mp4"
    _ff("-f", "lavfi", "-t", "10", "-i", "mandelbrot=s=640x360:r=30:start_scale=1.5:end_scale=0.6:end_pts=300",
        "-vf", "crop=320:180:x='160*(1+sin(t/3))':y='90*(1+cos(t/4))',eq=contrast=0.7,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", str(path))
    assert len(_shots(str(path))) == 1
