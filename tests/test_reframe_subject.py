"""Smart vertical reframe ("Follow the subject", reframe mode ``subject``) on SYNTHETIC footage: a moving subject
stays in the crop with a smooth camera, a static shot holds still, a hard cut and a crossfade are shot changes, two
subjects too far apart / a featureless panorama fall back to the blurred fill for that shot only, the plan is
deterministic, the render keeps the subject in the frame, and the export / vlog recipe use it by default."""
import json
import os
import shutil
import subprocess

import numpy as np
import pytest

from vstudio import export as X
from vstudio import media
from vstudio import platform as P
from vstudio import reframe as R
from vstudio import saliency as S

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")

W, H, FPS = 640, 360, 30


def _write(path, frames, fps=FPS):
    h, w = frames[0].shape[:2]
    p = subprocess.Popen([media.ffmpeg_bin(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s",
                          f"{w}x{h}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                          "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(np.ascontiguousarray(f).tobytes())
    p.stdin.close()
    assert p.wait() == 0
    return str(path)


def _ground(seed=0, w=W, h=H, tint=(60, 110, 60)):
    """A textured, low-contrast landscape (grass / foliage-like noise): nothing stands out."""
    import cv2
    rng = np.random.default_rng(seed)
    g = cv2.GaussianBlur((rng.random((h, w, 3)) * 50).astype(np.float32), (0, 0), 2.5)
    return np.clip(g + np.array(tint, np.float32), 0, 255).astype(np.uint8)


def _disk(img, x, y, r=26, color=(40, 40, 230)):
    import cv2
    cv2.circle(img, (int(x), int(y)), r, color, -1)
    return img


def _xs(n, x0, x1):
    return [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("reframe")
    base = _ground(0)
    n = 150
    out = {}
    out["moving"] = _write(d / "moving.mp4", [_disk(base.copy(), x, 200) for x in _xs(n, 70, 570)])
    out["static"] = _write(d / "static.mp4", [_disk(base.copy(), 470, 160) for _ in range(90)])
    out["two"] = _write(d / "two.mp4", [_disk(_disk(base.copy(), 90, 180), 550, 170, color=(220, 70, 30))
                                        for _ in range(90)])
    other = _ground(5, tint=(200, 190, 210))
    out["cut"] = _write(d / "cut.mp4", [_disk((base if i < 45 else other).copy(), 100 if i < 45 else 540, 180)
                                        for i in range(90)])
    pano = _ground(7, w=1440, h=360)
    out["pano"] = _write(d / "pano.mp4", [pano.copy() for _ in range(60)])
    return out


def plan(src, tw=180, th=320, **kw):
    """9:16 from 16:9; no face model, no person model (synthetic footage has neither)."""
    return R.plan(src, tw, th, mode="subject", detector=lambda fr: [], analyzer=S.Analyzer(person=False), **kw)


def centre(r):
    return r[0] + r[2] / 2


def test_moving_subject_stays_in_the_crop_with_a_smooth_camera(clips):
    pl = plan(clips["moving"])
    assert pl["mode_used"] == "subject" and [s["kind"] for s in pl["shots"]] == ["follow"]
    xs = [x for x in _xs(150, 70, 570)]
    inside = [r[0] + 10 <= x <= r[0] + r[2] - 10 for r, x in zip(pl["rects"], xs)]
    assert sum(inside) / len(inside) >= 0.95                              # the subject is in the frame
    assert centre(pl["rects"][-1]) - centre(pl["rects"][0]) > 250         # the camera went with it
    st = pl["stats"]
    assert st["max_speed"] <= R.SUBJECT["max_speed"] * 1.03              # crop widths / s: never a whip
    assert st["mean_abs_accel"] < 1.0                                     # eased, no jitter
    v = np.diff([r[0] for r in pl["rects"]])
    assert np.all(v >= -0.5)                                              # never hunts back and forth


def test_static_shot_holds_still_where_the_subject_is(clips):
    pl = plan(clips["static"])
    assert [s["kind"] for s in pl["shots"]] == ["hold"]
    assert len({tuple(r) for r in pl["rects"]}) == 1                      # not one pixel of drift
    r = pl["rects"][0]
    assert r[0] < 470 < r[0] + r[2]


def test_hard_cut_resets_the_camera_and_crossfades_ease(clips):
    pl = plan(clips["cut"])
    assert pl["cuts"] == [45] and len(pl["shots"]) == 2
    a, b = pl["rects"][44], pl["rects"][45]
    assert a[0] < 100 < a[0] + a[2] and b[0] < 540 < b[0] + b[2]          # a cut, not a pan across the frame
    # the same picture as a crossfade window: eased from one framing to the next inside it, no jump
    pl2 = plan(clips["moving"], transitions=[[2.0, 2.6]])
    assert pl2["transitions"] == [[60, 78]] and len(pl2["shots"]) == 2
    x = [r[0] for r in pl2["rects"][58:81]]
    assert max(abs(np.diff(x))) < 0.25 * pl2["crop_w"]


def test_two_subjects_far_apart_and_a_flat_panorama_are_shown_whole(clips, tmp_path):
    pl = plan(clips["two"])
    assert pl["mode_used"] == "pad-blur" and pl["shots"][0]["kind"] == "pad-blur"
    assert "too far apart" in pl["fallback_reason"]
    pano = plan(clips["pano"])                                          # 4:1, nothing stands out: a crop keeps 14 %
    assert pano["mode_used"] == "pad-blur" and "panorama" in pano["fallback_reason"]
    # clean fun reels (shot_pad=False): no shot on a blurred pad - the strongest interest is cropped instead
    assert plan(clips["two"], shot_pad=False)["shots"][0]["kind"] != "pad-blur"
    # only that shot: a moving-subject shot after it still follows (mixed plan -> null rects for the wide shot)
    frames = [_disk(_disk(_ground(0), 90, 180), 550, 170, color=(220, 70, 30)) for _ in range(45)]
    other = _ground(5, tint=(200, 190, 210))
    frames += [_disk(other.copy(), x, 180) for x in _xs(60, 200, 400)]
    mixed = R.plan(None, 180, 320, mode="subject", frames=frames, fps=30, detector=lambda fr: [],
                   analyzer=S.Analyzer(person=False))
    assert [s["kind"] for s in mixed["shots"]] == ["pad-blur", "follow"]
    assert mixed["rects"][0] is None and mixed["rects"][-1] is not None
    out = R.render(None, str(tmp_path / "mixed.mp4"), mixed, frames=frames)
    assert media.probe(out)["w"] == 180


def test_plan_is_deterministic(clips):
    a, b = plan(clips["moving"]), plan(clips["moving"])
    assert a["rects"] == b["rects"] and a["shots"] == b["shots"]


def test_render_keeps_the_subject_and_prescales(clips, tmp_path):
    import cv2
    pl = plan(clips["moving"], tw=90, th=160)                              # 0.47x: ffmpeg scales first
    pre, (w, h), vf = R.prescaled(pl, pl["src_w"], pl["src_h"])
    assert vf.startswith("scale=") and h == 160 and pre["rects"][0][3] == pytest.approx(160)
    out = R.render(clips["moving"], str(tmp_path / "v.mp4"), pl)
    cap = cv2.VideoCapture(out)
    reds = []
    for i in range(150):
        ok, fr = cap.read()
        if not ok:
            break
        if i % 15 == 0:
            m = (fr[..., 2] > 150) & (fr[..., 1] < 100) & (fr[..., 0] < 100)
            reds.append(m.sum())
    cap.release()
    assert len(reds) == 10 and min(reds) > 50                              # the red subject is on screen throughout


def test_safe_box_and_caption_band_place_the_subject(clips):
    prof = P.profile("tiktok", "vertical")
    pl = R.plan(clips["static"], prof.w, prof.h, mode="subject", detector=lambda fr: [],
                analyzer=S.Analyzer(person=False), safe=P.safe_box(prof), caption=P.caption_box(prof))
    r = pl["rects"][0]
    s = prof.w / r[2]
    x_t = (470 - r[0]) * s                                                 # where the subject lands on the canvas
    x0, _y0, x1, _y1 = P.safe_box(prof)
    assert x0 < x_t < x1 and abs(x_t - (x0 + x1) / 2) < 0.12 * prof.w     # mid safe box, clear of the button column


def test_export_follows_by_default_for_follow_mode_and_reports_shots(clips, tmp_path):
    shots = tmp_path / "m.shots.json"
    shots.write_text(json.dumps({"transitions": [[2.0, 2.6]]}))
    out = tmp_path / "ex"
    man = X.export(clips["moving"], ["tiktok", "youtube"], str(out), mode="follow", preset="ultrafast",
                   transitions=X.load_shots(str(shots)))
    by = {e["platform"]: e for e in man["exports"]}
    assert by["tiktok"]["reframe"]["mode_used"] == "subject"
    assert by["tiktok"]["reframe"]["shots"] == {"follow": 2}
    assert by["youtube"]["reframe"]["mode_used"] == "scale"               # same aspect: a plain scale
    pl = json.load(open(out / "tiktok-vertical.crop.json"))
    assert pl["transitions"] == [[60, 78]]
    blur = X.export(clips["moving"], ["tiktok"], str(tmp_path / "eb"), mode="blur", preset="ultrafast")
    assert blur["exports"][0]["reframe"]["mode_used"] == "pad-blur"


def test_map_box_through_a_mixed_plan():
    pl = dict(target=[100, 200], src_w=400, src_h=200, mode_used="subject", rects=[None, [100, 0, 112.5, 200]])
    assert X.map_box(pl, (0, 0, 400, 200), 0) == pytest.approx((0, 75, 100, 125))     # shown whole
    assert X.map_box(pl, (100, 0, 10, 10), 1)[0] == pytest.approx(0)


def test_face_mode_can_fall_back_to_the_subject(clips):
    pl = R.plan(clips["moving"], 180, 320, mode="face", fallback="subject", detector=lambda fr: [],
                analyzer=S.Analyzer(person=False))
    assert pl["mode_used"] == "subject" and "face hit rate" in pl["fallback_reason"]


def test_saliency_cues():
    import cv2
    base = _ground(3)
    an = S.Analyzer(person=False)
    m = an(_disk(base.copy(), 500, 180))["map"]
    col = m.sum(0)
    assert abs(int(np.argmax(cv2.GaussianBlur(col.reshape(1, -1), (0, 0), 2).ravel())) / len(col) - 500 / W) < 0.06
    # motion that is not the camera's: a disk moving while the whole frame pans
    an.reset()
    big = _ground(4, w=W + 80)
    f1 = _disk(big[:, 0:W].copy(), 200, 180)
    an(f1)
    f2 = _disk(big[:, 8:W + 8].copy(), 240, 180)
    r = an(f2)
    assert r["motion"] > 0.6 and r["gm"][0] < 0                            # the pan is global, the disk is its own


def test_vlog_recipe_exports_follow_by_default():
    from vstudio.project import manifests as M
    m = M.get("vlog")
    assert m["params"]["properties"]["reframe"]["default"] == "follow"
    ex = next(s for s in m["stages"] if s["id"] == "export")
    assert "{reframe}" in ex["run"]["argv"] and "pad-blur" not in json.dumps(ex["run"]["argv"])
    assert {"framing", "copy"} <= {c["id"] for c in m["checkpoints"]}


def test_face_mode_falling_back_to_subject_takes_subject_options(clips):
    """A subject option (shot_pad) given to a face-mode plan that falls back to the subject (DJI fun reel crash)."""
    pl = R.plan(clips["two"], 180, 320, mode="face", fallback="subject", detector=lambda fr: [],
                analyzer=S.Analyzer(person=False), shot_pad=False)
    assert all(s["kind"] != "pad-blur" for s in pl.get("shots") or [])
