"""Importing finished videos made elsewhere (vstudio.project.imports) + shot matching to their footage
(vstudio.shotmatch) + the second-pass tools on them (shot swaps, language versions, post copy). Synthetic media made
with ffmpeg: three "camera" clips and a finished cut of them (graded, a title bar, a caption box) in two platform
versions with covers and a post.md. No network, no model: translation, voice and ASR are hooks."""
import json
import os
import shutil
import subprocess

import numpy as np
import pytest

from vstudio import shotmatch as SM
from vstudio.project import imports as IM
from vstudio.project import outputs as O
from vstudio.project import outrender as R

HAS_FFMPEG = bool(shutil.which("ffmpeg"))
pytestmark = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")

SOURCES = {  # name -> lavfi source (each 8 s, distinct, moving)
    "DJI_0001.MP4": "mandelbrot=s=320x180:r=30",
    "DJI_0002.MP4": "mandelbrot=s=320x180:r=30:start_x=-1.25066:start_y=0.02012:start_scale=0.05:end_scale=0.00005:end_pts=180",
    "DJI_0003.MP4": "life=s=320x180:r=30:seed=7:ratio=0.3:mold=8:life_color=#30d0ff:death_color=#402010",
}
CUT = [("DJI_0001.MP4", 1.0), ("DJI_0002.MP4", 2.0), ("DJI_0003.MP4", 0.5)]   # (source, in point), 2 s each
WORDS = [dict(w=w, t=round(0.3 + i * 0.5, 3), te=round(0.6 + i * 0.5, 3)) for i, w in enumerate(
    "Seattle on the water . tonight we fly toward the city lights .".split())]


def _ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def footage(tmp_path_factory):
    root = tmp_path_factory.mktemp("imp")
    raw = root / "raw"
    raw.mkdir()
    for name, src in SOURCES.items():
        _ff("-f", "lavfi", "-i", f"{src},format=yuv420p", "-t", "8", "-c:v", "libx264", "-preset", "ultrafast",
            "-g", "15", str(raw / name))
    out = root / "out" / "01-night-flight"
    out.mkdir(parents=True)
    ins, parts = [], []
    for k, (name, t) in enumerate(CUT):
        ins += ["-ss", str(t), "-t", "2", "-i", str(raw / name)]
        parts.append(f"[{k}:v]setpts=PTS-STARTPTS,fps=30,format=yuv420p[v{k}]")
    graph = ";".join(parts) + ";" + "".join(f"[v{k}]" for k in range(len(CUT))) + \
        f"concat=n={len(CUT)}:v=1:a=0,eq=brightness=0.06:saturation=1.3[c]"
    master = root / "master.mp4"
    _ff(*ins, "-filter_complex", graph, "-map", "[c]", "-c:v", "libx264", "-preset", "ultrafast", str(master))
    tone = "sine=frequency=330:sample_rate=48000"
    # youtube: 16:9 with a title bar and a caption box burned in; xiaohongshu: a 9:16 crop of it
    _ff("-i", str(master), "-f", "lavfi", "-t", "6", "-i", tone, "-vf",
        "scale=640:360,drawbox=x=0:y=0:w=iw:h=40:color=0x202020:t=fill,"
        "drawbox=x=120:y=300:w=400:h=30:color=white@0.9:t=fill", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-shortest", str(out / "youtube.mp4"))
    _ff("-i", str(master), "-f", "lavfi", "-t", "6", "-i", tone, "-vf", "crop=101:180:30:0,scale=360:640",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(out / "xiaohongshu.mp4"))
    from PIL import Image
    Image.new("RGB", (64, 36), (200, 120, 40)).save(out / "youtube.cover.jpg")
    (out / "post.md").write_text("# Post copy\n\n## youtube\n\nNight flight over Seattle\n\nA short flight at dusk.\n\n"
                                 "#seattle #drone\n\n## xiaohongshu\n\n夜航西雅图\n\n黄昏的一次飞行。\n\n#西雅图 #航拍\n",
                                 encoding="utf-8")
    return dict(root=root, raw=raw, out=out)


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VSTUDIO_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("VSTUDIO_LLM_PROVIDER", "none")
    monkeypatch.setattr(O, "TRANSCRIBE", lambda path, language=None: [dict(x) for x in WORDS])


def _sha(p):
    import hashlib
    return hashlib.sha1(open(p, "rb").read()).hexdigest()


def test_classify_finished_vs_footage(footage):
    r = IM.classify([str(footage["out"]), str(footage["raw"])])
    assert r["verdict"] == "mixed"
    assert r["counts"]["finished"] == 2 and r["counts"]["raw"] == 3
    [c] = r["clips"]
    assert c["key"] == "01-night-flight" and c["title"] == "Night flight over Seattle"
    assert [v["platform"] for v in c["versions"]] == ["youtube", "xiaohongshu"]     # international first
    yt = c["versions"][0]
    assert yt["aspect"] == "16:9" and yt["cover"].endswith("youtube.cover.jpg")
    assert yt["post"]["tags"] == ["seattle", "drone"]
    assert c["versions"][1]["post"]["title"] == "夜航西雅图"
    raw = {f["path"]: f for f in r["files"] if f["role"] == "raw"}
    assert all("camera-name" in f["why"] for f in raw.values())


def test_video_role_reasons(tmp_path):
    # a CapCut export dropped on its own: finished; a phone clip: footage
    assert IM.video_role(str(tmp_path / "My trip_CapCut export.mp4"), dict(w=1080, h=1920, has_audio=True))[0] == \
        "finished"
    assert IM.video_role(str(tmp_path / "IMG_4521.MOV"), dict(w=3840, h=2160, has_audio=True,
                                                               tags="com.apple.quicktime.make=Apple"))[0] == "raw"
    assert IM.platform_of("ep3_douyin_9x16.mp4") == ("douyin", "vertical")
    assert IM._key_of("ep3_douyin_9x16") == "ep3"


def test_import_copies_never_touches_originals(footage):
    before = {p: (_sha(p), os.stat(p).st_mtime_ns) for p in
              [str(footage["out"] / "youtube.mp4"), str(footage["out"] / "post.md")]}
    r = IM.import_([str(footage["out"])], sources=[str(footage["raw"])])
    d = r["dir"]
    assert d.startswith(os.path.join(os.environ["VSTUDIO_HOME"], "projects", "import-"))
    [c] = r["clips"]
    assert len(c["sources"]) == 3
    yt = os.path.join(d, c["versions"][0]["file"])
    assert os.path.isfile(yt) and not os.path.samefile(yt, footage["out"] / "youtube.mp4")
    assert _sha(yt) == before[str(footage["out"] / "youtube.mp4")][0]
    assert os.path.isfile(os.path.join(d, c["versions"][0]["cover"]))
    for p, (h, mt) in before.items():
        assert _sha(p) == h and os.stat(p).st_mtime_ns == mt
    assert not os.path.exists(footage["out"] / ".vstudio")              # nothing written next to the originals
    rec = json.load(open(os.path.join(d, ".vstudio", "work.json")))
    assert rec["imported"]["clips"] == 1 and rec["outputs"][0].endswith("youtube.mp4")
    reg = json.load(open(os.path.join(os.environ["VSTUDIO_HOME"], "projects.json")))
    assert any(os.path.realpath(x["dir"]) == os.path.realpath(d) and x["kind"] == "work" for x in reg)
    with pytest.raises(IM.ImportError_) as e:
        IM.import_([str(footage["raw"])])
    assert e.value.info["code"] == "no-finished-video"


def test_shot_match_finds_each_shot(footage):
    m = SM.match(str(footage["out"] / "youtube.mp4"), sorted(str(p) for p in footage["raw"].iterdir()))
    assert [round(s["start"]) for s in m["shots"]] == [0, 2, 4]
    for s, (name, t) in zip(m["shots"], CUT):
        x = s["match"]
        assert x and os.path.basename(x["source"]) == name, s
        assert abs(x["t"] - t) < 0.35, (s, t)
        assert x["score"] > 0.6
    assert m["coverage"] == 1.0
    v = SM.match(str(footage["out"] / "xiaohongshu.mp4"), sorted(str(p) for p in footage["raw"].iterdir()))
    for s, (name, _t) in zip(v["shots"], CUT):
        assert s["match"] and os.path.basename(s["match"]["source"]) == name
        assert abs(s["match"]["box"][0] - 30 / 320) < 0.08                 # where the vertical crop sat
    alts = SM.alternatives(m, 0)
    assert alts and alts[0]["source"].endswith("DJI_0001.MP4") and alts[0]["t"] >= 3.0


def _imported(footage):
    r = IM.import_([str(footage["out"])], sources=[str(footage["raw"])])
    IM.match_shots(r["dir"])
    return r["dir"], r["clips"][0]["versions"][0]["file"]


def test_editor_on_an_import_swaps_a_shot(footage):
    d, oid = _imported(footage)
    sh = O.show(d, oid)
    assert sh["caps"]["imported"] and sh["caps"]["shot_swap"] and sh["caps"]["shots"] == 3
    assert sh["output"]["platform"] == "youtube:horizontal"
    assert len(sh["imported"]["shots"]) == 3 and sh["imported"]["sources"]
    r = O.edit(d, oid, [{"op": "shot_swap", "shot": 1}])
    assert r["values"][0]["why"] == "same-source-after" and r["values"][0]["source"] == "DJI_0002.MP4"
    assert r["state"]["shots"]["1"]["t"] >= 4.0
    out = R.render(d, oid, quality="preview")["targets"][0]
    assert [s["stage"] for s in out["stages"]][0] == "splice"
    assert abs(out["duration"] - 6.0) < 0.15
    from vstudio import media
    assert media.probe(out["file"])["has_audio"]
    # the title bar of the finished video stays over the new take; the picture under it is the new take
    _t, fr = SM._decode(out["file"], 64, 36, start=3.0, frames=1, color=True)
    _t, orig = SM._decode(os.path.join(d, oid), 64, 36, start=3.0, frames=1, color=True)
    assert np.abs(fr[0][:3].astype(int) - orig[0][:3].astype(int)).mean() < 12
    assert np.abs(fr[0][10:28].astype(int) - orig[0][10:28].astype(int)).mean() > 8
    O.edit(d, oid, [{"op": "shot_swap", "shot": 1, "restore": True}])
    assert O.show(d, oid)["state"]["shots"] == {}
    with pytest.raises(O.OutputError) as e:
        O.edit(d, oid, [{"op": "shot_swap", "shot": 9}])
    assert e.value.info["code"] == "bad-param"


def test_language_version_revoices_and_recaptions(footage, monkeypatch, tmp_path):
    d, oid = _imported(footage)
    calls = []

    def translate(system, prompt):
        rows = [ln.split(". ", 1) for ln in prompt.splitlines() if ". " in ln]
        calls.append(len(rows))
        return dict(lines=[dict(n=int(k), t=f"中文{k}") for k, _ in rows]), dict(provider="fake")
    monkeypatch.setattr(O, "TRANSLATE", translate)
    said = []

    def voice(text, lang, out):
        from vstudio import audio
        said.append((text, lang))
        t = np.arange(int(48000 * 0.6)) / 48000
        audio.write_wav(out, np.stack([0.2 * np.sin(2 * np.pi * 500 * t)] * 2, 1).astype(np.float32), 48000)
        return out
    monkeypatch.setattr(R, "VOICE", voice)
    r = O.edit(d, oid, [{"op": "export_add", "target": "xiaohongshu", "lang": "zh"}])
    ex = r["state"]["exports"][0]
    assert ex["lang"] == "zh" and ex["src_lang"] == "en" and calls
    assert [x[3] for x in ex["lines"]] == ["中文1", "中文2"]
    assert r["step"]["describe"][0]["code"] == "op-export-lang"
    out = R.render(d, oid, quality="preview", targets=["xiaohongshu:vertical"])["targets"][0]
    assert [s["stage"] for s in out["stages"]][:1] == ["canvas"]
    assert said == [("中文1", "zh"), ("中文2", "zh")]
    from vstudio import media
    info = media.probe(out["file"])
    assert (info["w"], info["h"]) == (1080, 1440) and abs(out["duration"] - 6.0) < 0.2
    p = R.plan(*O._load(d, oid), O._load(d, oid)[1].state(),
               R.targets_of(O._load(d, oid)[0], O._load(d, oid)[1].state(), ["xiaohongshu:vertical"])[0], "preview")
    assert p["canvas"]["op"] == "sources"          # rebuilt from the footage: no burned English in it
    assert any(c[2] == "中文1" for c in p["final"]["visual"]["captions"])


def test_language_version_without_model_is_refused(footage):
    d, oid = _imported(footage)
    with pytest.raises(O.OutputError) as e:
        O.edit(d, oid, [{"op": "export_add", "target": "youtube", "lang": "fr"}])
    assert e.value.info["code"] == "needs-model"


def test_rewrite_copy_keeps_the_original(footage):
    r = IM.import_([str(footage["out"])])
    d, cid = r["dir"], r["clips"][0]["id"]

    def complete(task, system, user, **kw):
        return dict(json={"en": dict(title="Dusk over Seattle", body="One flight.", tags=["seattle"]),
                          "zh": dict(title="黄昏西雅图", body="一次飞行。", tags=["西雅图"])}, provider="fake")
    out = IM.rewrite_copy(d, cid, transcript="Seattle on the water", complete=complete)
    assert out["posts"]["youtube"]["title"] == "Dusk over Seattle"
    assert out["posts"]["xiaohongshu"]["title"] == "黄昏西雅图"
    m = IM.manifest(d)
    v = m["clips"][0]["versions"][0]
    assert v["post_original"]["title"] == "Night flight over Seattle" and v["post"]["title"] == "Dusk over Seattle"
    assert "Dusk over Seattle" in open(os.path.join(d, os.path.dirname(v["file"]), "youtube.post.md")).read()


def test_cli_check_and_import(footage, tmp_path):
    env = dict(os.environ, PYTHONPATH=os.path.join(os.path.dirname(__file__), "..", "lib"))
    run = lambda *a: subprocess.run(["python3", "-m", "vstudio.project", *a, "--json"], capture_output=True,  # noqa
                                    text=True, env=env, check=True)
    chk = json.loads(run("import", str(footage["out"]), "--sources", str(footage["raw"]), "--check").stdout)
    assert chk["verdict"] == "mixed" and chk["counts"]["clips"] == 1
    imp = json.loads(run("import", str(footage["out"]), "--title", "Night flight").stdout)
    assert imp["title"] == "Night flight" and imp["first"]["clip"] == "01-night-flight"


def test_music_swap_drops_the_old_soundtrack(footage):
    """music-bed replace on a finished video with no speech: the old mix (a 330 Hz tone here) is gone, the new bed
    plays; a second bed without replace keeps it under."""
    d, oid = _imported(footage)
    from vstudio import audio

    def tone(path):
        x = audio.decode_audio(path, sr=48000, channels=1)[:, 0][48000:48000 * 4]
        f = np.abs(np.fft.rfft(x))
        hz = np.fft.rfftfreq(len(x), 1 / 48000)
        band = (hz > 320) & (hz < 340)
        return f[band].sum() / f.sum()
    O.edit(d, oid, [{"op": "effect_add", "effect": "music-bed", "start": 0, "params": {"mood": "calm"}}])
    under = R.render(d, oid, quality="preview")["targets"][0]["file"]
    t_under = tone(under)
    assert t_under > 0.05                                       # added under: the old tone is still there
    sh = O.show(d, oid)
    fx = next(e for e in sh["effects"] if e["effect"] == "music-bed")
    O.edit(d, oid, [{"op": "effect_update", "id": fx["id"], "params": {"replace": True}}])
    swapped = R.render(d, oid, quality="preview")["targets"][0]["file"]
    assert tone(swapped) < t_under * 0.5, (tone(swapped), t_under)   # swapped: only the new bed


def test_footage_pairs_by_folder_even_through_links(footage, tmp_path):
    """Two exported clips (01-, 02-) and their footage as folders of links into a card: each clip gets the footage
    of its own folder (the number they share), stored as the real files; the group is named above out/."""
    root = tmp_path / "trip"
    for k, (name, src) in enumerate((("01-night", "DJI_0001.MP4"), ("02-day", "DJI_0002.MP4"))):
        o = root / "out" / f"0{k + 1}-cut"
        o.mkdir(parents=True)
        shutil.copy(footage["out"] / "youtube.mp4", o / "youtube.mp4")
        f = root / name
        f.mkdir()
        os.symlink(footage["raw"] / src, f / src)
    r = IM.import_([str(root)])
    assert r["title"] == "trip"
    by = {c["id"]: c["sources"] for c in r["clips"]}
    assert by["01-cut"] == [os.path.realpath(footage["raw"] / "DJI_0001.MP4")]
    assert by["02-cut"] == [os.path.realpath(footage["raw"] / "DJI_0002.MP4")]
