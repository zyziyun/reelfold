"""Beat This! backend plumbing (vstudio.beatthis / beats) and shot detection (vstudio.shots / transnet).

No network and no model weights needed: the network maths is checked against the reference implementation by hand
(see the commit), here we test the parts around it - checkpoint loading safety, peak picking, how beats.analyze uses
the network's beats / downbeats, the fallbacks, and the shot / moment / sheet pipeline on a synthetic clip with cuts.
Tests that need the real weights run only when VSTUDIO_BEAT_THIS / VSTUDIO_TRANSNETV2 point at them."""
import io
import json
import os
import pathlib
import pickle
import subprocess
import sys
import zipfile

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from vstudio import beats, beatthis, shots, transnet  # noqa: E402

SR = 22050


# ------------------------------------------------------------------ Beat This!
def test_mel_filters_and_log_mel_shape():
    fb = beatthis.mel_filters()
    assert fb.shape == (513, 128) and fb.min() >= 0 and (fb.max(0) > 0).all()
    x = np.sin(2 * np.pi * 440 * np.arange(SR * 2) / SR).astype(np.float32)
    s = beatthis.log_mel(x)
    assert s.shape == (1 + (len(x) + 1024 - 1024) // 441, 128)
    assert abs(s.mean(0).argmax() - np.argmax(fb[round(440 / (SR / 1024))])) <= 1     # energy in the 440 Hz band


def test_peaks_and_postprocess_snap_downbeats_to_beats():
    lg = np.full(500, -5.0, np.float32)
    for f in (50, 75, 100, 125, 150):
        lg[f] = 3.0
    lg[101] = 2.9                                                          # within +-3 frames: not a second peak
    dl = np.full(500, -5.0, np.float32)
    dl[51] = 1.0                                                           # one frame off the beat
    b, d = beatthis.postprocess(lg, dl)
    assert list(b) == [1.0, 1.5, 2.0, 2.5, 3.0] and list(d) == [1.0]


def _torch_zip(obj_pickle):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x/data.pkl", obj_pickle)
        z.writestr("x/data/0", np.arange(6, dtype="<f4").tobytes())
    return buf.getvalue()


class _Evil:
    def __reduce__(self):
        return (os.system, ("echo pwned",))


def test_checkpoint_loader_only_takes_tensors(tmp_path):
    p = tmp_path / "evil.ckpt"
    p.write_bytes(_torch_zip(pickle.dumps({"state_dict": _Evil()})))
    with pytest.raises(pickle.UnpicklingError):
        beatthis.load_checkpoint(str(p))


def test_checkpoint_loader_reads_a_torch_zip(tmp_path):
    torch = pytest.importorskip("torch")
    p = tmp_path / "w.ckpt"
    t = torch.arange(12, dtype=torch.float32).reshape(3, 4)
    torch.save({"hyper_parameters": {"a": 1}, "state_dict": {"w": t, "wt": t.t(), "s": t[1:, 2:]}}, str(p))
    ck = beatthis.load_checkpoint(str(p))
    assert ck["hyper_parameters"] == {"a": 1}
    assert np.array_equal(ck["state_dict"]["w"], t.numpy()) and np.array_equal(ck["state_dict"]["wt"], t.t().numpy())
    assert np.array_equal(ck["state_dict"]["s"], t[1:, 2:].numpy())


def _click(bpm, dur, meter=4):
    x = np.zeros(int(dur * SR), np.float32)
    per = 60 / bpm
    n = np.arange(int(dur / per))
    tk = np.arange(int(0.1 * SR)) / SR
    k = (np.sin(2 * np.pi * 60 * tk) * np.exp(-tk * 30)).astype(np.float32)
    for i in n:
        a = int(i * per * SR)
        x[a:a + len(k)] += k * (1.0 if i % meter == 0 else 0.5)
    return x, n * per


def test_analyze_uses_beat_this_downbeats_and_meter(monkeypatch):
    x, bt = _click(90, 20, meter=3)
    monkeypatch.setattr(beatthis, "available", lambda: True)
    # the network says: waltz, downbeat on the 2nd beat of the file
    monkeypatch.setattr(beatthis, "track", lambda x, sr: (bt.copy(), bt[1::3].copy()))
    b = beats.analyze(x, sr=SR)
    assert b.backend == "beat_this" and b.meter == 3 and abs(b.bpm - 90) < 0.5 and b.grid_ok
    assert b.tempo_check["downbeats"]["agree"] == 1.0
    assert np.allclose(b.downbeats[:3], bt[1::3][:3], atol=0.02)
    assert np.allclose(np.diff(b.cut_plan(3, 0.0, 20.0, "every-bar")), 3 * 60 / 90, atol=0.01)
    assert b.to_dict()["meter"] == 3


def test_analyze_thins_a_double_time_tail(monkeypatch):
    x, bt = _click(100, 30)
    tail = np.arange(bt[-1] + 0.3, 30, 0.3)                                 # the network doubles in an outro
    monkeypatch.setattr(beatthis, "available", lambda: True)
    monkeypatch.setattr(beatthis, "track", lambda x, sr: (np.concatenate([bt[bt < 24], np.arange(24, 30, 0.3)]),
                                                          bt[::4].copy()))
    b = beats.analyze(x, sr=SR)
    assert b.backend == "beat_this" and abs(b.bpm - 100) < 1.0 and b.grid_ok and len(tail)


def test_analyze_falls_back_and_says_why(monkeypatch):
    x, _ = _click(120, 10)
    monkeypatch.setattr(beatthis, "available", lambda: False)
    b = beats.analyze(x, sr=SR)
    assert b.backend in ("numpy", "librosa") and b.tempo_check["beat_this"] == "not downloaded" and b.meter == 4

    def boom(x, sr):
        raise ValueError("bad checkpoint")
    monkeypatch.setattr(beatthis, "available", lambda: True)
    monkeypatch.setattr(beatthis, "track", boom)
    b = beats.analyze(x, sr=SR)
    assert b.backend != "beat_this" and "bad checkpoint" in b.tempo_check["beat_this"]
    with pytest.raises(RuntimeError):
        beats.analyze(x, sr=SR, backend="beat_this")


@pytest.mark.skipif(not os.environ.get("VSTUDIO_BEAT_THIS"), reason="needs the Beat This! checkpoint")
def test_beat_this_real_checkpoint_on_a_built_in_bed(tmp_path):
    from vstudio import music
    y = music.generate("story", 30)
    b = beats.analyze(y.mean(1), sr=music.SR)
    assert b.backend == "beat_this" and abs(b.bpm - 64) < 1.0              # the DSP trackers say 128


# ------------------------------------------------------------------ shots
@pytest.fixture(scope="module")
def cut_clip(tmp_path_factory):
    """4 s testsrc2, 3 s solid red, then 14 s of a slowly zooming mandelbrot: two hard cuts, one long shot."""
    d = tmp_path_factory.mktemp("shots")
    p = str(d / "cuts.mp4")
    g = ("[0:v]trim=0:4,setpts=PTS-STARTPTS[a];[1:v]trim=0:3,setpts=PTS-STARTPTS[b];"
         "[2:v]trim=0:14,setpts=PTS-STARTPTS[c];[a][b][c]concat=n=3:v=1[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30",
                    "-f", "lavfi", "-i", "color=c=red:size=320x180:rate=30",
                    "-f", "lavfi", "-i", "mandelbrot=size=320x180:rate=30",
                    "-filter_complex", g, "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", p], check=True)
    return p


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    return tmp_path


def test_adaptive_shots_moments_and_sheet(cut_clip, cache):
    a = shots.analyze(cut_clip, backend="adaptive")
    assert a["backend"] == "adaptive" and abs(a["dur"] - 21.0) < 0.2
    starts = [s["start"] for s in a["shots"]]
    assert len(starts) == 3 and abs(starts[1] - 4.0) < 0.1 and abs(starts[2] - 7.0) < 0.1
    long = a["shots"][2]["moments"]
    assert len(long) >= 2 and all(m["end"] - m["start"] >= shots.MOMENT_MIN - 0.05 for m in long)
    for m in shots.moments(a):
        assert 0 <= m["score"] <= 1 and m["start"] <= m["best"][0] < m["best"][1] <= m["end"] + 1e-6
    assert len(a["secs"]) == 21 and {"t", "sharp", "motion", "bright"} <= set(a["secs"][0])
    assert "S3.1" in shots.line(a) and a["best"][0]["score"] >= a["best"][-1]["score"]
    out = shots.sheet(cut_clip, str(cache / "sheet.jpg"), a)
    assert os.path.getsize(out) > 0
    assert shots.analyze(cut_clip, backend="adaptive")["total_s"] == a["total_s"]           # cached


def test_flash_frames_are_found():
    luma = np.full(60, 100.0, np.float32)
    luma[30:32] = 200.0
    assert shots._flashes(luma, 30) == [30, 31]
    luma[40:50] = 200.0                                                   # a real exposure change: not a flash
    assert 45 not in shots._flashes(luma, 30)


def test_transnet_scenes_like_upstream():
    p = np.zeros(20)
    p[[5, 6, 12]] = 0.9
    assert transnet.scenes(p) == [(0, 5), (7, 12), (13, 19)]
    assert transnet.scenes(np.ones(4)) == [(0, 3)]


@pytest.mark.skipif(not os.environ.get("VSTUDIO_TRANSNETV2"), reason="needs the TransNet V2 weights")
def test_transnet_real_weights_find_the_cuts(cut_clip, cache):
    a = shots.analyze(cut_clip, backend="transnetv2")
    starts = [s["start"] for s in a["shots"]]
    assert a["backend"] == "transnetv2" and any(abs(s - 4.0) < 0.1 for s in starts)
    assert any(abs(s - 7.0) < 0.1 for s in starts)


def test_footage_context_sends_shot_tiles(cut_clip, cache):
    from vstudio import footage
    text, images, facts = footage.context([cut_clip], str(cache / "s"), ids=["c"])
    assert len(images) == 1 and "moments (id start-end" in text and facts[0]["moments"]
    assert facts[0]["moments"][0]["id"].startswith("S1")


def test_reel_scorer_reads_the_shots_decode(cut_clip, cache):
    import importlib.util
    spec = importlib.util.spec_from_file_location("sc", ROOT / "workflows/vlog/scripts/funvlog/score.py")
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    r = sc.clip_scores(cut_clip, cache_dir=str(cache / "sc"), faces=False)
    assert len(r["secs"]) == 21 and all(0 <= s["score"] <= 1 for s in r["secs"])
    st, v = sc.pick_window(r, 3.0)
    assert 0 <= st <= 18 and v > 0
    assert json.load(open(next((cache / "sc").glob("scores_*.json"))))["secs"] == r["secs"]


def test_aesthetic_model_joins_the_moment_score_when_present(cut_clip, cache, monkeypatch):
    from vstudio import aesthetic
    base = {(m["shot"], m["moment"]): m["score"] for m in shots.moments(shots.analyze(cut_clip, backend="adaptive"))}
    monkeypatch.setattr(shots, "_aesthetic_ok", lambda: True)
    monkeypatch.setattr(aesthetic, "score", lambda imgs: [7.0] * len(imgs))
    a = shots.analyze(cut_clip, backend="adaptive")
    for m in shots.moments(a):
        assert m["aesthetic"] == 7.0 and m["score"] == round(0.85 * base[(m["shot"], m["moment"])] + 0.15, 3)
    assert a["best"][0]["score"] == max(m["score"] for m in shots.moments(a))
