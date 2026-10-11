"""A vlog finished before the recipe had the vertical framing and post copy steps (her Seattle red-leaves project:
exports on a blurred fill, post.md with the title only, no framing / copy answer, no shots.json) is brought up to date
on the finished item (``python -m vstudio.project remake``): its current framing is read from the exports, switching
it re-makes only the vertical exports (the crossfades derived from the edit when the render wrote none), and the post
copy is written on demand with every platform's post.md - no other stage runs."""
import json
import os
import shutil
import sqlite3
import subprocess

import pytest

from vstudio import export as EX
from vstudio import media
from vstudio.project import autopilot as AP
from vstudio.project.core import Project
from vstudio.project.remake import RemakeEnv, RemakeError, remake
from vstudio.project.adapters import vlog as V

TITLE = "Seattle in Red — Autumn From Above"
ASK = "使用这些视频帮我剪辑成一个西雅图红叶的视频，配个音乐什么的，显得高级一点"
SRT = ("1\n00:00:00,000 --> 00:00:00,033\n<font size=\"28\">FrameCnt: 1\n2026-10-10 18:55:57.457\n[latitude: 47.762948] "
       "[longitude: -122.182302] [rel_alt: 85.200 abs_alt: 105.1] </font>\n")

needs_ff = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def fake_copy(task, system, prompt, schema=None, provider=None, **kw):
    """The routed ``copy`` model (a stand-in for Claude Code here)."""
    out = {}
    if "en" in schema["required"]:
        out["en"] = dict(title="Seattle's red season from the sky", hook="Every street in Seattle turned red this week.",
                         body="Maple rows and empty roads, seen from 80 metres up.\nSound on for the slow version.",
                         description="A calm minute over Seattle's maple streets in October.\nFilmed with a drone.",
                         tags=["Seattle", "fall foliage", "drone"])
    if "zh" in schema["required"]:
        out["zh"] = dict(title="西雅图红叶季，从天上看", hook="这周西雅图的街道全红了。", body="枫树和空无一人的路。\n戴上耳机慢慢看。",
                         description="十月的西雅图红叶航拍。", tags=["西雅图", "红叶", "航拍"])
    return {"provider": "fake", "json": out}


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_BATCH_BENCH", str(tmp_path / "bench.json"))
    monkeypatch.setenv("VSTUDIO_MUSIC_DIRS", "")
    monkeypatch.setenv("HOME", str(tmp_path / "userhome"))
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VSTUDIO_CLIENTS", "VSTUDIO_PERSONA"):
        monkeypatch.delenv(k, raising=False)
    from vstudio import config
    config.persona.cache_clear()
    yield
    monkeypatch.undo()
    config.persona.cache_clear()


def footage(d):
    """Two DJI-like landscape clips: a red disk crossing a textured ground (something to follow) + flight logs."""
    out = []
    for i in range(2):
        p = os.path.join(d, f"DJI_2026101018555{i}_000{i}_D.MP4")
        vf = (f"geq=r='40+30*random(1)':g='{90 + 20 * i}+30*random(1)':b='40+20*random(1)',"
              f"drawbox=x='40+t*90':y=150:w=40:h=40:color=red@1:t=fill")
        subprocess.run([media.ffmpeg_bin(), "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "color=c=black:size=480x270:rate=30:duration=4", "-vf", vf, "-c:v", "libx264", "-pix_fmt",
                        "yuv420p", p], check=True)
        with open(os.path.splitext(p)[0] + ".SRT", "w") as f:
            f.write(SRT)
        out.append(p)
    return out


def make_old(pdir, item="main"):
    """A project as the app made it before the framing / copy steps: no answers or overrides for them, no payloads,
    no stage rows, no shots.json, the exports on a blurred fill with the title as the whole post."""
    p = Project(pdir)
    for cid in ("framing", "copy"):
        p.data["answers"].pop(cid, None)
    for k in ("reframe", "copy_pick"):
        p.data["overrides"].get(item, {}).pop(k, None)
    p.data["auto"] = ["hook", "filler", "cover"]
    p.save()
    for cid in ("framing", "copy"):
        f = os.path.join(p.state_dir, "checkpoints", item, f"{cid}.json")
        if os.path.exists(f):
            os.remove(f)
    db = sqlite3.connect(os.path.join(p.state_dir, "batch.db"))
    db.execute("DELETE FROM stages WHERE stage IN ('copy', 'cp_framing', 'cp_copy')")
    db.commit()
    db.close()
    work = os.path.join(pdir, "items", item, "work")
    for f in os.listdir(work):
        if f.endswith(".shots.json"):
            os.remove(os.path.join(work, f))
    ex = os.path.join(pdir, "items", item, "exports")
    master = json.load(open(os.path.join(ex, "manifest.json")))["master"]
    for f in os.listdir(ex):
        os.remove(os.path.join(ex, f))
    EX.export(master, ["youtube", "tiktok"], ex, post=dict(title=TITLE), mode="pad-blur", preset="ultrafast")
    return ex


@pytest.fixture
def old(tmp_path):
    clips = footage(str(tmp_path))
    p = Project.create(str(tmp_path / "p"), recipe="vlog", inputs=dict(footage=clips),
                       params=dict(platforms=["youtube", "tiktok"], preset="ultrafast", title=TITLE),
                       spec=dict(copy=dict(call="test_vlog_remake:fake_copy")))
    p.data["prompt"] = ASK
    p.save()
    out = Project(p.dir).run(autopilot=True)
    assert out["exit_code"] == 0, out
    real = os.path.join(p.dir, "items", "main", "work", "vlog_master.shots.json")
    shots = json.load(open(real))["transitions"]                     # what build_vlog wrote (to compare with)
    ex = make_old(p.dir)
    return p.dir, ex, shots


def entry(ex, platform):
    return next(e for e in json.load(open(os.path.join(ex, "manifest.json")))["exports"] if e["platform"] == platform)


@needs_ff
def test_old_vlog_is_brought_up_to_date(old):
    pdir, ex, shots = old
    # what it has now, read from its exports: the setting shows (blur), the copy can be written (never was)
    ch = {c["checkpoint"]: c for c in AP.choices(Project(pdir))}
    assert ch["framing"]["choice"] == "blur" and ch["framing"]["by"] == "before"
    assert ch["framing"]["options"] == ["follow", "blur"] and ch["framing"]["pick"] == 1
    assert ch["copy"]["choice"] is None and ch["copy"]["by"] == "before"
    assert open(os.path.join(ex, "tiktok-vertical.post.md"), encoding="utf-8").read().strip() == TITLE
    yt = os.path.join(ex, "youtube-horizontal.mp4")
    yt_t = os.path.getmtime(yt)

    # the post copy, on demand: every platform's post.md has a body and hashtags, no video made again
    r = remake(Project(pdir), "main", {"copy": None})
    assert r["done"][0]["source"] == "llm:fake"
    for pf, tag in (("tiktok", "#Seattle"), ("youtube", "#Seattle")):
        e = entry(ex, pf)
        txt = open(os.path.join(ex, e["post"]), encoding="utf-8").read()
        assert len([x for x in txt.split("\n") if x.strip()]) >= 3 and tag in txt, txt
        assert e["post_lang"] == "en" and e["post_warnings"] is not None
    assert "Every street in Seattle" in open(os.path.join(ex, "tiktok-vertical.post.md"), encoding="utf-8").read()
    assert os.path.getmtime(yt) == yt_t
    ch = {c["checkpoint"]: c for c in AP.choices(Project(pdir))}
    assert ch["copy"]["choice"] == "ai" and ch["copy"]["by"] == "her"

    # follow the subject: only the vertical export is made again (cropped, the crossfades derived from the edit)
    r = remake(Project(pdir), "main", {"framing": "follow"})
    assert r["done"][0]["targets"] == ["tiktok:vertical"]
    tk = entry(ex, "tiktok")
    assert tk["reframe"]["mode"] == "subject" and tk["reframe"]["mode_used"] == "subject"
    plan = json.load(open(os.path.join(ex, tk["reframe"]["plan"])))
    assert plan["rects"] and any(r_ and r_[2] < plan["src_w"] for r_ in plan["rects"])     # a real crop
    assert os.path.getmtime(yt) == yt_t and entry(ex, "youtube")["reframe"]["mode_used"] == "scale"
    derived = json.load(open(r["done"][0]["shots"]))
    assert derived["derived"] == "edit.json"
    assert [[round(a, 1), round(b, 1)] for a, b in derived["transitions"]] == \
        [[round(a, 1), round(b, 1)] for a, b in shots]
    assert "Every street in Seattle" in open(os.path.join(ex, "tiktok-vertical.post.md"), encoding="utf-8").read()
    p = Project(pdir)
    assert p.data["overrides"]["main"]["reframe"] == "follow" and not p.data["answers"]["framing"]["main"].get("auto")
    ch = {c["checkpoint"]: c for c in AP.choices(p)}
    assert ch["framing"]["choice"] == "follow" and ch["framing"]["by"] == "her"

    # and back to the blurred fill
    remake(Project(pdir), "main", {"framing": "blur"})
    assert entry(ex, "tiktok")["reframe"]["mode_used"] == "pad-blur"


@needs_ff
def test_shots_from_the_edit_without_the_rendered_segments(old):
    pdir, _ex, shots = old
    work = os.path.join(pdir, "items", "main", "work")
    shutil.rmtree(os.path.join(work, "clips"), ignore_errors=True)
    env = RemakeEnv(Project(pdir), "main", "music")
    path = V.master_shots(env)
    got = json.load(open(path))["transitions"]
    assert len(got) == len(shots) and all(abs(a - c) < 0.05 and abs(b - d) < 0.05 for (a, b), (c, d) in zip(got, shots))


def test_remake_refuses_what_it_cannot_do(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"")
    p = Project.create(str(tmp_path / "p"), recipe="vlog", inputs=dict(footage=[str(tmp_path / "a.mp4")]),
                       params=dict(platforms=["tiktok"]))
    with pytest.raises(RemakeError):
        remake(Project(p.dir), "main", {"music": None})              # not a setting a finished clip can remake
    with pytest.raises(RemakeError):
        remake(Project(p.dir), "nope", {"framing": "follow"})
    with pytest.raises(RemakeError, match="not made yet|no exports"):
        remake(Project(p.dir), "main", {"framing": "follow"})
    assert AP.choices(Project(p.dir)) == []                            # nothing made: no setting to show
