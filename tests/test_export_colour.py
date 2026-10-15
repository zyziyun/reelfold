"""Compare decoded pixels, not an RGB decoder that ignores H.264 matrix metadata.

Both plain scaling and the real caption compositor must preserve SDR source colours.
These fixtures test matrix/range handling; they do not validate HDR display appearance.
"""
import json
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from vstudio import export, media, platform

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def rgb_frame(path):
    info = media.probe(str(path))
    raw = subprocess.check_output([media.ffmpeg_bin(), "-v", "error", "-i", str(path), "-frames:v", "1",
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    return np.frombuffer(raw, np.uint8).reshape(info["display_h"], info["display_w"], 3)


def patch_colours(rgb):
    h, w = rgb.shape[:2]
    return np.array([np.median(rgb[round(h * .12):round(h * .32),
                                   round(w * (i + .2) / 6):round(w * (i + .8) / 6)], axis=(0, 1))
                     for i in range(6)])


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    folder = tmp_path_factory.mktemp("colour-sources")
    image = Image.new("RGB", (640, 360))
    for i, colour in enumerate([(235, 30, 30), (30, 220, 30), (30, 30, 230), (128, 128, 128), (28, 28, 28), (230, 230, 230)]):
        image.paste(colour, (round(640 * i / 6), 0, round(640 * (i + 1) / 6), 360))
    png = folder / "patches.png"; image.save(png)
    paths = {}
    for kind, matrix, range_ in [("untagged", "bt601", "tv"), ("601", "bt601", "tv"),
                                  ("709", "bt709", "tv"), ("full709", "bt709", "pc")]:
        path = folder / f"{kind}.mp4"
        tags = [] if kind == "untagged" else ["-colorspace", "bt709" if matrix == "bt709" else "smpte170m",
                                             "-color_range", range_]
        filters = [] if kind == "untagged" else ["-vf", f"scale=out_color_matrix={matrix}:out_range={range_}"]
        subprocess.run([media.ffmpeg_bin(), "-v", "error", "-y", "-loop", "1", "-i", str(png), "-t", "1", "-r", "10",
                        *filters, "-c:v", "libx264", "-preset", "ultrafast",
                        "-crf", "14", "-pix_fmt", "yuv420p", *tags, str(path)], check=True)
        streams = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)]))
        stream = streams["streams"][0]
        assert stream.get("color_space") == (None if kind == "untagged" else "bt709" if matrix == "bt709" else "smpte170m")
        assert stream.get("color_range") == (None if kind == "untagged" else range_)
        paths[kind] = path
    return paths


@pytest.mark.parametrize("kind", ["untagged", "601", "709", "full709"])
@pytest.mark.parametrize("captioned", [False, True], ids=["scale-only", "caption-compositor"])
def test_source_and_export_agree_through_colour_aware_decoder(tmp_path, sources, kind, captioned):
    source = sources[kind]
    cues = tmp_path / "cues.json"
    cues.write_text(json.dumps(dict(cues=[dict(start=0, end=1, text="Colour check")])))
    prof = platform.profile("youtube", "horizontal", overrides=dict(w=960, h=540))
    result = export.export_one(str(source), prof, str(tmp_path), captions=captioned,
                               cues=str(cues), watermark=False, encoder="libx264", preset="ultrafast")
    before = patch_colours(rgb_frame(source))
    after = patch_colours(rgb_frame(tmp_path / result["file"]))
    # Small codec/chroma rounding is expected; a 601/709 relabel shifts saturated channels by >15.
    assert np.max(np.abs(before - after)) <= 6, (kind, captioned, before.tolist(), after.tolist())
