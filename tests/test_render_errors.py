"""How a failed render is worded: an ffmpeg error the app caused (no such filter / unknown encoder) is a bug to report,
only a real open / read error is "a file couldn't be read" (named, with its drive when that is not connected).

0.2.6: "No such filter: 'eq'" on the bundled LGPL ffmpeg was shown as "One of the files couldn't be read"."""
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

from vstudio import proctail

ROOT = pathlib.Path(__file__).resolve().parents[1]


NOFILTER = ("[AVFilterGraph @ 0x600] No such filter: 'eq'\nError opening output file /x/clips/seg_00.mp4.\n"
            "Error opening output files: Filter not found")


def test_classification():
    assert proctail.tool_failure(NOFILTER) == dict(code="app-bug", params={})
    assert proctail.tool_failure("[vost#0:0 @ 0x1] Unknown encoder 'libx264'") == dict(code="app-bug", params={})
    assert proctail.cause(NOFILTER) == "[AVFilterGraph @ 0x600] No such filter: 'eq'"
    gone = "[in#0 @ 0x1] Error opening input: No such file or directory\nError opening input file " \
           "/Volumes/ReelfoldTestNoSuchDrive/DCIM/DJI_0079.MP4."
    assert proctail.tool_failure(gone) == dict(code="media-unmounted",
                                               params=dict(file="DJI_0079.MP4", volume="ReelfoldTestNoSuchDrive"))
    bad = "[mov,mp4 @ 0x1] moov atom not found\n/tmp/footage/clip.mp4: Invalid data found when processing input"
    assert proctail.tool_failure(bad) == dict(code="media-unreadable", params=dict(file="clip.mp4"))
    # a script's own missing file is not her footage; a missing ffmpeg is the tool
    assert proctail.tool_failure("FileNotFoundError: [Errno 2] No such file or directory: 'work/edit.json'") is None
    assert proctail.tool_failure("FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'")["code"] == \
        "tool-ffmpeg"


def test_stage_error_keeps_the_cause_past_a_long_traceback(tmp_path):
    """build.Env.run: the reason line survives a long command line / traceback after it."""
    from vstudio.project import build
    script = tmp_path / "boom.py"
    script.write_text("import sys\nsys.stderr.write(\"[AVFilterGraph @ 0x1] No such filter: 'eq'\\n\")\n"
                      "raise RuntimeError('x' * 3000)\n")
    env = build.Env.__new__(build.Env)
    env.dir = env.item_dir = str(tmp_path)
    with pytest.raises(RuntimeError) as e:
        env.run([sys.executable, str(script)])
    assert "No such filter: 'eq'" in str(e.value)
    assert proctail.tool_failure(str(e.value))["code"] == "app-bug"


def test_vlog_render_error_names_the_step_and_the_reason(tmp_path):
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("no ffmpeg")
    sys.path.insert(0, str(ROOT / "workflows" / "vlog" / "scripts"))
    import build_vlog as V
    with pytest.raises(V.RenderError) as e:
        V.run_ffmpeg(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                      "testsrc2=s=64x64:d=0.1", "-vf", "nosuchfilterzz=1", str(tmp_path / "o.mp4")],
                     "segment 00 (DJI_0079.MP4)")
    head = str(e.value).splitlines()[0]
    assert head.startswith("segment 00 (DJI_0079.MP4): ") and "nosuchfilterzz" in head.lower()
    assert proctail.tool_failure(str(e.value))["code"] == "app-bug"


def test_vlog_script_exits_with_the_reason_last(tmp_path):
    """The whole build_vlog.py run (as the desk runs it): the last stderr line is the reason, the exit is not 0."""
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("no ffmpeg")
    clip = tmp_path / "missing.MP4"
    edit = dict(src_dir=".", clips={"a": clip.name}, res=[320, 180], fps=30, hdr=False, xfade=0.2, fade_out=0.2,
                out="vlog_master.mp4", segments=[dict(clip="a", start=0, dur=1)])
    (tmp_path / "edit.json").write_text(json.dumps(edit))
    env = dict(os.environ, PYTHONPATH=str(ROOT / "lib"))
    r = subprocess.run([sys.executable, str(ROOT / "workflows" / "vlog" / "scripts" / "build_vlog.py"),
                        str(tmp_path / "edit.json")], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode != 0
    last = [ln for ln in r.stderr.splitlines() if ln.strip()][-1]
    assert last.startswith("!! render failed - ")
    got = proctail.tool_failure(r.stderr)
    assert got and got["code"] in ("media-unreadable", "media-unmounted") and got["params"].get("file") == clip.name


def test_media_run_feeds_stdin_once_across_the_stall_poll():
    """media._exec polls every 5 s; a run fed through stdin that takes longer must not re-send its input (CI: the
    talking-head cover grades a raw frame through stdin)."""
    from vstudio import media
    if not shutil.which("ffmpeg"):
        pytest.skip("no ffmpeg")
    frame = bytes(16 * 16 * 3)
    # one frame looped for ~5.7 s of real time (realtime filter): longer than one 5 s poll
    r = media.run(["ffmpeg", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "16x16", "-i", "-", "-vf",
                   "loop=loop=170:size=1,setpts=N/30/TB,realtime", "-f", "null", "-"], input=frame, capture=True)
    assert r.returncode == 0


def test_render_refuses_low_disk_space_before_starting_a_child(tmp_path, monkeypatch):
    from vstudio.project import build
    from collections import namedtuple
    env = build.Env.__new__(build.Env)
    env.dir = env.item_dir = str(tmp_path)
    env.entry = dict(id="render", resource="cpu-render")
    usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(build.shutil, "disk_usage", lambda _: usage(10 * 1024**3, 9 * 1024**3, 1024**3))
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: pytest.fail("render child must not start"))
    with pytest.raises(RuntimeError, match="No space left for rendering"):
        env.run([sys.executable, "render.py"])
