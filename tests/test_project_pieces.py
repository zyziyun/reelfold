"""The making, piece by piece (Project.pieces) and what each item made (outputs.item_files) - the sources the desk's
project page reads (2026-10-11, her finished Seattle vlog read "Not started" with an empty tile, and she wanted to see
the graded segments, contact sheets and cover options while it is made). Generic over recipes: each stage's ``wip``
files (while it runs and after) and its ``preview`` once done, in recipe order, plus a waiting checkpoint's previews.
Tiny synthetic DJI-like clips (no audio stream), no AI, no network."""
import json
import os
import shutil
import subprocess
import time

import pytest

from vstudio.batch.store import Store
from vstudio.project import manifests as M
from vstudio.project import outputs as O
from vstudio.project.core import Project

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_BATCH_BENCH", str(tmp_path / "bench.json"))
    monkeypatch.setenv("VSTUDIO_MUSIC_DIRS", "")
    monkeypatch.setenv("HOME", str(tmp_path / "userhome"))
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VSTUDIO_CLIENTS"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("dji")
    out = []
    for i in range(3):
        p = str(d / f"DJI_000{i}_D.MP4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=size=320x180:rate=30:duration=4", "-vf", f"hue=h={i * 40}", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", p], check=True)
        out.append(p)
    return out


def make(tmp_path, clips, name="p"):
    p = Project.create(str(tmp_path / name), recipe="vlog", inputs=dict(footage=list(clips)),
                       params=dict(platforms=["youtube", "tiktok"], preset="ultrafast", title="Red leaves"))
    p.data["prompt"] = "a calm red leaves film with music"
    p.save()
    return p.dir


def test_the_vlog_recipe_declares_its_pieces_and_validates():
    m = M.reload()["vlog"]                                       # every recipe validated against the schema
    assert not M.validate(m)
    st = {s["id"]: s for s in m["stages"]}
    assert st["render"]["wip"]["kind"] == "videos" and st["render"]["wip"]["path"].endswith("seg_*.mp4")
    assert st["render"]["wip"]["label"] == {"zh": "调色片段", "en": "Graded segment", "fr": "Plan étalonné"}
    assert st["cover_frames"]["preview"]["label"]["en"] == "Cover options"


def test_a_finished_vlog_its_files_and_its_pieces(tmp_path, clips):
    pdir = make(tmp_path, clips)
    out = Project(pdir).run(autopilot=True)
    assert out["exit_code"] == 0, out
    # what it made: the export manifest under items/main/exports (not the batch layout), with the frame facts
    files = O.item_files(pdir)
    assert list(files) == ["main"] and files["main"]["state"] == "done"
    got = {(f["platform"], f["orientation"]): f for f in files["main"]["files"]}
    assert set(got) == {("youtube", "horizontal"), ("tiktok", "vertical")}
    yt = got[("youtube", "horizontal")]
    assert (yt["w"], yt["h"]) == (1920, 1080) and yt["duration"] > 1 and yt["safe_box"]
    assert os.path.isfile(yt["cover"]) and os.path.isfile(yt["post"])
    assert {os.path.realpath(f["file"]) for f in files["main"]["files"]} == \
        {os.path.realpath(x["file"]) for x in O.list_outputs(pdir)["outputs"]}
    # how it was made, in recipe order
    doc = Project(pdir).pieces()
    (it,) = doc["items"]
    ps = it["pieces"]
    order = []
    for p in ps:
        if p["stage"] not in order:
            order.append(p["stage"])
    assert order == ["probe", "sheets", "render", "music", "cover_frames", "copy"]
    segs = [p for p in ps if p["stage"] == "render" and p["kind"] == "videos"]
    assert [os.path.basename(p["path"]) for p in segs] == [f"seg_{i:02d}.mp4" for i in range(len(segs))]
    assert all(p["of"] == len(segs) and p["state"] == "done" for p in segs)
    master = [p for p in ps if p["stage"] == "render" and p["kind"] == "video"]
    assert len(master) == 1 and master[0]["label"]["en"] == "Master, no music yet"
    assert len({p["path"] for p in ps}) == len(ps)                  # each file once


def test_a_running_stage_shows_only_this_runs_files(tmp_path, clips):
    pdir = make(tmp_path, clips)
    assert Project(pdir).run(autopilot=True)["exit_code"] == 0
    segdir = os.path.join(pdir, "items", "main", "work", "clips")
    segs = sorted(os.listdir(segdir))
    # the render runs again: its row says running since now; one segment is rewritten, the others are last run's
    st = Store(os.path.join(pdir, "state"))
    try:
        st.set_stage("main", "render", state="running", started=time.time())
    finally:
        st.close()
    old = time.time() - 600
    for s in segs:
        os.utime(os.path.join(segdir, s), (old, old))
    os.utime(os.path.join(segdir, segs[0]), None)
    ps = Project(pdir).pieces()["items"][0]["pieces"]
    running = [p for p in ps if p["stage"] == "render"]
    assert [(os.path.basename(p["path"]), p["state"], p["n"], p["of"]) for p in running] == [(segs[0], "running", 1, 1)]
    assert not [p for p in ps if p["stage"] == "render" and p["kind"] == "video"]   # no master preview while it runs


def test_a_waiting_checkpoint_shows_its_previews(tmp_path, clips):
    pdir = make(tmp_path, clips)
    others = ["music", "framing", "copy", "publish"]
    Project(pdir).run(autopilot=False, auto=[*others, "cover"])                 # the starter cut waits for her
    Project(pdir).answer("edit", dict(done=True), items=["main"])
    out = Project(pdir).run(auto=others)                                         # then it parks at the cover pick
    assert [(x["item"], x["id"]) for x in out["pending"]] == [("main", "cover")]
    ps = Project(pdir).pieces()["items"][0]["pieces"]
    waiting = [p for p in ps if p["state"] == "waiting"]
    assert waiting and all(p["checkpoint"] == "cover" and os.path.isfile(p["path"]) for p in waiting)
    assert ps.index(waiting[0]) > max(i for i, p in enumerate(ps) if p["state"] == "done")
    json.dumps(ps)                                                     # what the desk serves as is
