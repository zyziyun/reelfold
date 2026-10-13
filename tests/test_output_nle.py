"""A clip's edit for editing programs (vstudio.project.nle): FCP7 XML for Premiere / Resolve, 剪映 / CapCut drafts
and OpenTimelineIO, each read back: pieces back to back on whole frames, the source parts the cuts kept, speed,
levels, linked sound, captions, media copied and relinked. Synthetic media only."""
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from test_output_edit import _iso, _pipeline, _work, synth, th  # noqa: F401  (fixtures)
from vstudio.project import nle as N
from vstudio.project import outputs as O

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def _edited(tmp_path, synth):  # noqa: F811
    w, oid = _work(tmp_path, synth)
    O.edit(w, oid, [dict(op="trim", start=0.3, snap=False), dict(op="cut", start=2.1, end=2.6, no_snap=True),
                    dict(op="speed", value=1.2), dict(op="caption_add", start=0.5, end=1.5, text="新的字幕"),
                    dict(op="effect_add", effect="music-bed", params=dict(file=synth["bgm"])),
                    dict(op="effect_add", effect="pop-words", start=1.0, params=dict(text="重点"))])
    return w, oid


def _segs(w, oid):
    s = O.show(w, oid)
    return s["timeline"]["segments"], s["state"]["speed"]


def test_rate_and_frames():
    assert N.rate_of(29.97) == dict(fps=30000 / 1001, timebase=30, ntsc=True)
    assert N.rate_of(25) == dict(fps=25.0, timebase=25, ntsc=False)
    assert N.norm_format("Premiere") == "xmeml" and N.norm_format("剪映") == "jianying"
    with pytest.raises(N.NleError):
        N.norm_format("imovie")
    assert N.url_path(N.path_url("/a b/c#d.mp4")) == "/a b/c#d.mp4"
    assert N.srt([dict(text="hi", start=1.5, end=2.25)]) == "1\n00:00:01,500 --> 00:00:02,250\nhi\n\n"


def test_xmeml_round_trip(tmp_path, synth):  # noqa: F811
    w, oid = _edited(tmp_path, synth)
    segs, speed = _segs(w, oid)
    r = N.export_output(w, oid, "premiere", out_dir=str(tmp_path / "x"), measure=True)
    assert r["format"] == "xmeml" and r["clips"] == len(segs) == 2
    assert any("pop-words" in n for n in r["notes"])
    root = ET.parse(r["main"]).getroot()
    seq = root.find("sequence")
    tb = int(seq.find("rate/timebase").text)
    vclips = seq.findall("media/video/track/clipitem")
    assert len(vclips) == 2
    # back to back on whole frames, from frame 0
    assert int(vclips[0].find("start").text) == 0
    assert int(vclips[0].find("end").text) == int(vclips[1].find("start").text)
    assert int(seq.find("duration").text) == int(vclips[-1].find("end").text)
    # the source part each piece plays (the trim and the cut) at 1.2x
    for c, (a, b) in zip(vclips, segs):
        assert abs(int(c.find("in").text) / tb - a) <= 1.5 / tb
        dur = int(c.find("end").text) - int(c.find("start").text)
        assert abs(dur / tb - (b - a) / speed) <= 1.5 / tb
        sp = [p for p in c.iter("parameter") if p.findtext("parameterid") == "speed"]
        assert sp and float(sp[0].findtext("value")) == pytest.approx(120)
    # the media is a real file; written once, referred to after
    files = [f for f in seq.iter("file") if f.find("pathurl") is not None]
    assert len({f.get("id") for f in files}) == len(files) == 2            # the clip + the music
    assert all(os.path.isfile(N.url_path(f.findtext("pathurl"))) for f in files)
    # sound: linked to its picture, a level, the music bed on its own track
    tracks = seq.findall("media/audio/track")
    assert len(tracks) == 2
    a0 = tracks[0].findall("clipitem")
    assert len(a0) == 2 and a0[0].find("link") is not None
    assert {lk.findtext("linkclipref") for lk in a0[0].findall("link")} == {vclips[0].get("id"), a0[0].get("id")}
    levels = [p for p in a0[0].iter("parameter") if p.findtext("parameterid") == "level"]
    assert levels and 0 < float(levels[0].findtext("value")) <= N.MAX_GAIN
    music = tracks[1].findall("clipitem")
    assert len(music) == 1 and float([p for p in music[0].iter("parameter")
                                      if p.findtext("parameterid") == "level"][0].findtext("value")) < 1
    # captions: an SRT beside it
    srt = [f for f in r["files"] if f.endswith(".srt")]
    assert srt and "新的字幕" in open(srt[0], encoding="utf-8").read()
    assert os.path.exists(os.path.join(r["dir"], "README.txt"))


def test_jianying_and_capcut_drafts_round_trip(tmp_path, synth):  # noqa: F811
    w, oid = _edited(tmp_path, synth)
    segs, speed = _segs(w, oid)
    for app in ("jianying", "capcut"):
        r = N.export_output(w, oid, app, out_dir=str(tmp_path / app), measure=False)
        folder = r["main"]
        info = json.load(open(os.path.join(folder, "draft_info.json"), encoding="utf-8"))
        meta = json.load(open(os.path.join(folder, "draft_meta_info.json"), encoding="utf-8"))
        assert json.load(open(os.path.join(folder, "draft_content.json"), encoding="utf-8")) == info
        assert info["platform"]["app_source"] == ("lv" if app == "jianying" else "cc")
        assert [t["type"] for t in info["tracks"]] == ["video", "audio", "text"]
        v = info["tracks"][0]["segments"]
        assert len(v) == len(segs)
        assert v[0]["target_timerange"]["start"] == 0
        assert v[0]["target_timerange"]["start"] + v[0]["target_timerange"]["duration"] == \
            v[1]["target_timerange"]["start"]                                       # one shared cut
        for s, (a, b) in zip(v, segs):
            assert s["speed"] == pytest.approx(speed)
            assert abs(s["source_timerange"]["start"] / 1e6 - a) < 0.05
            assert s["source_timerange"]["duration"] == pytest.approx(s["target_timerange"]["duration"] * speed, abs=2)
            assert s["volume"] == 1                                                  # its own sound, unmeasured
            mat = next(m for m in info["materials"]["videos"] if m["id"] == s["material_id"])
            assert os.path.isfile(mat["path"]) and mat["local_material_id"]
        assert len(info["materials"]["videos"]) == 1                                # one material, two clips
        assert info["tracks"][1]["segments"][0]["volume"] < 1                       # the music bed
        txt = json.loads(info["materials"]["texts"][0]["content"])
        assert txt["text"] == "新的字幕"
        lib = meta["draft_materials"][0]["value"]
        assert meta["draft_materials"][0]["type"] == 0 and {e["metetype"] for e in lib} == {"video", "music"}
        assert meta["draft_id"] == info["id"] and meta["draft_fold_path"] == folder


def test_otio_and_copy_relink(tmp_path, synth):  # noqa: F811
    w, oid = _edited(tmp_path, synth)
    segs, speed = _segs(w, oid)
    out = tmp_path / "o"
    r = N.export_output(w, oid, "otio", out_dir=str(out), media="copy", measure=False)
    doc = json.load(open(r["main"], encoding="utf-8"))
    assert doc["OTIO_SCHEMA"] == "Timeline.1"
    vtrack = doc["tracks"]["children"][0]
    assert vtrack["kind"] == "Video" and [c["OTIO_SCHEMA"] for c in vtrack["children"]] == ["Clip.1", "Clip.1"]
    assert vtrack["children"][0]["effects"][0]["time_scalar"] == pytest.approx(speed)
    assert doc["tracks"]["markers"][0]["name"] == "新的字幕"
    urls = [c["media_reference"]["target_url"] for c in vtrack["children"]]
    assert all(N.url_path(u).startswith(str(out / "media")) and os.path.isfile(N.url_path(u)) for u in urls)
    try:
        import opentimelineio as otio
    except ImportError:
        otio = None
    if otio is not None:
        t = otio.adapters.read_from_file(r["main"])
        assert len(t.video_tracks()[0]) == 2
    # the media moves: relink points every timeline at the new folder
    moved = tmp_path / "moved"
    shutil.move(str(out / "media"), str(moved))
    rl = N.relink(str(out), str(moved))
    assert rl["ok"] and rl["missing"] == [] and r["main"] in rl["files"]
    doc = json.load(open(r["main"], encoding="utf-8"))
    assert all(N.url_path(c["media_reference"]["target_url"]).startswith(str(moved))
               for c in doc["tracks"]["children"][0]["children"])
    # an xml export relinks the same way
    x = N.export_output(w, oid, "xmeml", out_dir=str(tmp_path / "x2"), media="copy", measure=False)
    shutil.move(str(tmp_path / "x2" / "media"), str(tmp_path / "moved2"))
    assert N.relink(str(tmp_path / "x2"), str(tmp_path / "moved2"))["ok"]
    seq = ET.parse(x["main"]).getroot()
    assert all(os.path.isfile(N.url_path(p.text)) for p in seq.iter("pathurl"))


def test_pipeline_output_uses_the_master_and_its_captions(th):  # noqa: F811
    oid, rec = _pipeline(th)
    O.edit(th, oid, [dict(op="caption_text", cue="0", text=rec["cues"][0]["text"])])
    rec2, doc = O._load(th, oid)
    tl = N.plan(rec2, doc, doc.state(), measure=False)
    assert tl["source"]["mode"] == "master" and tl["files"][0]["path"] == os.path.abspath(rec["master"])
    assert len(tl["cues"]) >= 1 and tl["cues"][0]["start"] >= 0
    assert not any("burned" in n for n in tl["notes"])


def test_cli_nle_all(tmp_path, synth):  # noqa: F811
    w, oid = _edited(tmp_path, synth)
    e = dict(os.environ)
    e["PYTHONPATH"] = os.pathsep.join([os.path.join(ROOT, "lib"), os.path.join(ROOT, "tests"), e.get("PYTHONPATH", "")])
    r = subprocess.run([sys.executable, "-m", "vstudio.project", "output", "nle", "--project", w, "--all",
                        "--format", "jianying", "--out", str(tmp_path / "all"), "--no-measure", "--json"],
                       capture_output=True, text=True, env=e)
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["ok"] and len(doc["outputs"]) == 1 and os.path.isdir(doc["outputs"][0]["main"])
    r = subprocess.run([sys.executable, "-m", "vstudio.project", "output", "nle", "--project", w, "--output", oid,
                        "--format", "imovie", "--json"], capture_output=True, text=True, env=e)
    assert r.returncode == 5 and json.loads(r.stdout)["code"] == "unknown-format"
