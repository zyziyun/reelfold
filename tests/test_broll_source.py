"""Inserted footage must not silently become black or frozen on decoder failure."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from vstudio import media, broll as BR


spec = importlib.util.spec_from_file_location(
    "broll_source_test", Path(__file__).parents[1] / "workflows/talkinghead/scripts/vertical/broll.py")
LEGACY = importlib.util.module_from_spec(spec)
spec.loader.exec_module(LEGACY)


@pytest.fixture
def clip(tmp_path):
    path = str(tmp_path / "insert.mp4")
    media.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=red:s=64x48:r=10:d=1",
               "-f", "lavfi", "-i", "color=blue:s=64x48:r=10:d=1",
               "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", path])
    return path


@pytest.mark.parametrize("after_good_frame", [False, True])
def test_decode_failure_is_not_black_or_a_cached_frame(clip, monkeypatch, after_good_frame):
    source = BR.Source(clip, loop=False)
    try:
        if after_good_frame:
            source.frame(0)
        # Keep the real metadata and first decode; fail only the requested next frame.
        class BrokenRead:
            def set(self, *args):
                return source_cap.set(*args)

            def read(self):
                return False, None

        source_cap = source.cap
        monkeypatch.setattr(source, "cap", BrokenRead())
        with pytest.raises(RuntimeError, match="B-roll.*decode.*insert.mp4"):
            source.frame(.5)
        assert source.last == (0 if after_good_frame else -1)
    finally:
        source_cap.release()


@pytest.mark.parametrize("module", [BR, LEGACY], ids=["shared", "legacy-config"])
def test_native_seek_loop_and_intentional_end_hold(clip, module):
    for loop in (False, True):
        source = module.Source(clip, loop=loop)
        try:
            red, blue = source.frame(.2).copy(), source.frame(1.2).copy()
            assert red[..., 0].mean() > 240 and red[..., 2].mean() < 10
            assert blue[..., 2].mean() > 240 and blue[..., 0].mean() < 10
            assert np.array_equal(source.frame(.2), red)  # seek backwards
            assert np.array_equal(source.frame(2.2), red if loop else blue)
            assert np.array_equal(source.frame(2.2), red if loop else blue)  # cache
        finally:
            source.cap.release()
