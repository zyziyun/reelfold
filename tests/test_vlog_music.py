"""The vlog recipe's music (0.2.7: her "Seattle red leaves" vlog asked for music, got none, and its export failed
with ``Missing: 'out.music.master'``): the export reads the music stage it now depends on, a vlog without music
exports its silent master, the music is picked from the license-free library (an autopilot decision she can
change; Ask me first offers three tracks + no music), a CC BY track puts its credit in the post copy, and a project
that failed the old way recovers on Try again. Tiny synthetic DJI-like clips (no audio stream), no network."""
import copy
import json
import os
import shutil
import subprocess

import pytest

from vstudio import media
from vstudio import music as MU
from vstudio.batch import recipes as RC
from vstudio.batch.store import Store
from vstudio.project import autopilot as AP
from vstudio.project import build as B
from vstudio.project import manifests as M
from vstudio.project import registry  # noqa: F401  (the real recipes registered before a test swaps one)
from vstudio.project.core import Project

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")

ASK = "使用这些视频帮我剪辑成一个西雅图红叶的视频，配个音乐什么的，显得高级一点"


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


def make(tmp_path, clips, prompt=ASK, name="p", music=None):
    inputs = dict(footage=list(clips))
    if music:
        inputs["music"] = [music]
    p = Project.create(str(tmp_path / name), recipe="vlog", inputs=inputs,
                       params=dict(platforms=["youtube"], preset="ultrafast"))
    p.data["prompt"] = prompt
    p.save()
    return p.dir


def run(pdir, **kw):
    evs = []
    out = Project(pdir).run(on_event=evs.append, **kw)
    return out, evs


def export_of(pdir):
    man = json.load(open(os.path.join(pdir, "items", "main", "exports", "manifest.json")))
    e = man["exports"][0]
    return os.path.join(pdir, "items", "main", "exports", e["file"]), e


def has_audio(path):
    return media.probe(path)["has_audio"]


# --------------------------------------------------------------------------- the library pick
def test_rank_fits_her_words_and_the_style():
    top = MU.rank(ASK + "\nSeattle in Red - Autumn From Above", style="calm", n=3)
    assert [t["mood"] for t in top] == ["story", "calm", "warm"]          # calm, premium, autumn: no drums
    assert "高级" in top[0]["why"] and "红叶" in top[0]["why"]
    assert MU.rank("卡点 vlog", style="fun")[0]["mood"] == "bright"
    assert MU.wants_none("不要音乐，安静一点") and not MU.wants_none(ASK)


def test_cc_by_tracks_carry_their_credit(tmp_path, monkeypatch):
    d = tmp_path / "music"
    d.mkdir()
    (d / "Dreamer_KevinMacLeod.mp3").write_bytes(b"x")                    # how fetch_music.sh names a download
    (d / "own.wav").write_bytes(b"x")
    (d / "cc0.wav").write_bytes(b"x")
    (d / "cc0.wav.json").write_text(json.dumps(dict(license="CC0", mood="story")))
    monkeypatch.setenv("VSTUDIO_MUSIC_DIRS", str(d))
    by = {os.path.basename(t["path"]): t for t in MU.tracks() if t["source"] == "file"}
    km = by["Dreamer_KevinMacLeod.mp3"]
    assert km["license"] == "CC BY 4.0" and km["credit"].startswith('Music: "Dreamer" by Kevin MacLeod')
    assert "creativecommons.org/licenses/by/4.0" in km["credit"]
    assert by["own.wav"]["credit"] is None and by["cc0.wav"]["credit"] is None
    assert MU.rank(ASK, style="calm")[0]["path"].endswith("cc0.wav")      # her own track of the best mood first


# --------------------------------------------------------------------------- end to end
def test_autopilot_picks_a_fitting_track_and_exports_with_audio(tmp_path, clips):
    pdir = make(tmp_path, clips)
    out, evs = run(pdir, autopilot=True)
    assert out["exit_code"] == 0, out
    started = [e["stage"] for e in evs if e["event"] == "stage-start"]
    assert started.index("cp_music") < started.index("music") < started.index("export")
    mp4, e = export_of(pdir)
    assert has_audio(mp4)
    assert abs(e["loudness"]["i"] - (-14.0)) <= 1.0                        # the platform's -14 LUFS
    assert abs(media.probe(mp4)["duration"] - e["duration"]) < 0.1
    dec = next(d for d in AP.decisions(Project(pdir)) if d["checkpoint"] == "music")
    assert dec["kind"] == "music-pick" and dec["by"] == "rules" and dec["reason_code"] == "music-fit"
    assert dec["params"]["title"] == MU.STYLES["story"]["en"] and "高级" in dec["reason"]
    log = [json.loads(x) for x in open(os.path.join(pdir, "state", "autopilot.jsonl"))]
    assert any(x["event"] == "decided" and x["checkpoint"] == "music" for x in log)
    pay = json.load(open(os.path.join(pdir, "state", "checkpoints", "main", "music.json")))
    assert [o["kind"] for o in pay["options"]] == ["track", "track", "track", "none"]
    # she changes it: takes the decision back, the Inbox asks with the three tracks, she picks "no music"
    r = AP.reopen(Project(pdir), "music", "main")
    assert r["ok"]
    out, _ = run(pdir)
    assert any(p["id"] == "music" for p in Project(pdir).pending())
    Project(pdir).answer("music", dict(pick=3), items=["main"])
    out, evs = run(pdir)
    assert out["exit_code"] == 0, out
    mp4, _ = export_of(pdir)
    assert not has_audio(mp4)                                              # her call: the silent master


def test_ask_me_first_offers_three_tracks_and_no_music(tmp_path, clips):
    pdir = make(tmp_path, clips)
    out, _ = run(pdir, autopilot=False, auto=["edit", "cover", "publish"])
    pend = Project(pdir).pending()
    if any(x["id"] == "edit" for x in pend):              # the starter edit list waits for her (author, never auto)
        Project(pdir).answer("edit", dict(done=True), items=["main"])
        out, _ = run(pdir, auto=["cover", "publish"])
        pend = Project(pdir).pending()
    mp = next(x for x in pend if x["id"] == "music")
    assert mp["kind"] == "music-pick" and len([o for o in mp["options"] if o["kind"] == "track"]) == 3
    assert mp["default"] == dict(pick=0) and mp["options"][0]["checked"] and mp["options"][0]["labels"]["zh"]
    assert all(os.path.exists(o["path"]) for o in mp["options"] if o["kind"] == "track")   # each one to listen to
    Project(pdir).answer("music", dict(pick=1), items=["main"])
    out, _ = run(pdir, auto=["cover", "publish"])
    assert out["exit_code"] == 0, out
    assert has_audio(export_of(pdir)[0])
    st = Store(os.path.join(pdir, "state"))
    try:
        assert st.stage_rows("main")["music"]["out"]["title"] == mp["options"][1]["title"]
    finally:
        st.close()


def test_no_music_asked_exports_the_silent_master(tmp_path, clips):
    pdir = make(tmp_path, clips, prompt="剪一个安静的红叶视频，不要音乐")
    out, _ = run(pdir, autopilot=True)
    assert out["exit_code"] == 0, out
    assert not has_audio(export_of(pdir)[0])
    dec = next(d for d in AP.decisions(Project(pdir)) if d["checkpoint"] == "music")
    assert dec["reason_code"] == "music-none" and dec["reason"] == "you asked for no music"


def test_her_own_track_skips_the_pick(tmp_path, clips):
    bed = MU.make("warm", 12.0, out=str(tmp_path / "mine.wav"))
    pdir = make(tmp_path, clips, music=bed)
    out, _ = run(pdir, autopilot=True)
    assert out["exit_code"] == 0, out
    assert has_audio(export_of(pdir)[0])
    assert not any(d["checkpoint"] == "music" for d in AP.decisions(Project(pdir)))


def test_a_cc_by_pick_credits_the_track_in_the_post_copy(tmp_path, clips, monkeypatch):
    d = tmp_path / "music"
    d.mkdir()
    MU.make("story", 10.0, out=str(d / "Dreamer_KevinMacLeod.wav"))
    (d / "Dreamer_KevinMacLeod.wav.json").write_text(json.dumps(dict(mood="story")))   # labelled, licence by name
    monkeypatch.setenv("VSTUDIO_MUSIC_DIRS", str(d))
    pdir = make(tmp_path, clips)
    out, _ = run(pdir, autopilot=True)
    assert out["exit_code"] == 0, out
    mp4, e = export_of(pdir)
    assert has_audio(mp4) and e.get("post")
    post = open(os.path.join(os.path.dirname(mp4), e["post"]), encoding="utf-8").read()
    assert 'Music: "Dreamer" by Kevin MacLeod' in post and "CC BY 4.0" in post


# --------------------------------------------------------------------------- her project: Try again recovers
def _old_vlog():
    """The 0.2.7 vlog recipe: no music pick, export depending on cover_frames only (it read out.music through it)."""
    m = copy.deepcopy(M.get("vlog"))
    m["checkpoints"] = [c for c in m["checkpoints"] if c["id"] != "music"]
    for s in m["stages"]:
        if s["id"] == "music":
            s["keys"] = ["platforms"]
        if s["id"] == "export":
            s["deps"] = ["cover_frames"]
            s["run"]["argv"] = [a for a in s["run"]["argv"] if not (isinstance(a, dict) and a["if"] == "out.music.post")]
    return m


def test_the_old_recipe_shape_is_rejected():
    assert any("reads stage 'music'" in e for e in M.validate(_old_vlog(), deep=False))


def test_a_project_that_failed_at_export_recovers_on_try_again(tmp_path, clips, monkeypatch):
    old = _old_vlog()
    allm = dict(M.all_manifests(), vlog=old)
    name = B.recipe_name(M.get("vlog"), None)
    old_recipe = B.build(old, None)
    with monkeypatch.context() as mp:
        mp.setattr(M, "_cached", lambda: allm)
        mp.setitem(RC.REGISTRY, name, old_recipe)
        pdir = make(tmp_path, clips)
        out, evs = run(pdir, autopilot=True)
        fails = [e for e in evs if e["event"] == "stage-fail"]
        assert fails and fails[0]["stage"] == "export" and "out.music.master" in fails[0]["error"]
        st = Store(os.path.join(pdir, "state"))
        try:
            assert st.stage_rows("main")["music"]["out"]["skipped"] is True     # done, the bare master
        finally:
            st.close()
    assert RC.REGISTRY[name] is not old_recipe and any(c["id"] == "music" for c in M.get("vlog")["checkpoints"])
    out, evs = run(pdir)                                                   # Try again (autopilot kept on)
    assert out["exit_code"] == 0, out
    started = [e["stage"] for e in evs if e["event"] == "stage-start"]
    assert "render" not in started and "probe" not in started              # the 4K render is kept
    assert {"cp_music", "music", "export"} <= set(started)
    assert has_audio(export_of(pdir)[0])
    assert any(d["checkpoint"] == "music" for d in AP.decisions(Project(pdir)))
