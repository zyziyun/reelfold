"""Cover engine 2.0: monolingual titles, saliency / keep-out placement, small-size legibility, the YouTube A/B pack,
frame ranking, the torch-free model plumbing (ptload, ESRGAN, aesthetic MLP, BiRefNet fallback) and the pins."""
import json
import os
import subprocess
import zipfile

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _has_fonts():
    from vstudio import config as VC
    try:
        VC.font("cjk-bold")
        VC.font("cjk-serif-bold")
        return True
    except Exception:  # noqa: BLE001
        return False


def _scene(path, w=1920, h=1080):
    """A sky-over-water frame with a bright subject on the left third."""
    im = Image.new("RGB", (w, h), (70, 110, 150))
    d = ImageDraw.Draw(im)
    d.rectangle((0, int(h * 0.55), w, h), fill=(30, 60, 80))
    d.ellipse((int(w * 0.15), int(h * 0.35), int(w * 0.33), int(h * 0.7)), fill=(240, 200, 60))
    im.save(path, quality=95)
    return path


# ------------------------------------------------------------------ text
def test_mono_text_and_title_parts():
    from vstudio import cover_engine as CE
    t = "Golden Hour · 黄金时刻 | Elliott Bay, Seattle"
    assert CE.mono_text(t, "en") == "Golden Hour | Elliott Bay, Seattle"
    assert CE.mono_text(t, "zh") == "黄金时刻"
    assert CE.title_parts("Golden Hour | Elliott Bay, Seattle", "en") == ("Golden Hour", "Elliott Bay, Seattle")
    title, kick = CE.title_parts("Seattle World's Fair 1962: The Space Needle & Pacific Science Center", "en")
    assert title == "Seattle World's Fair 1962" and kick.startswith("The Space Needle")
    assert CE.title_parts("航拍西雅图：埃利奥特湾工作海滨两分钟简史", "zh")[0] == "航拍西雅图"


@pytest.mark.skipif(not _has_fonts(), reason="fonts from install.sh")
def test_wrap_is_balanced_and_never_orphans_a_character():
    from vstudio import cover_engine as CE
    from vstudio.draw import load_font
    f = load_font("cjk-bold", 100)
    lines = CE._wrap("华盛顿东部公路旅行", f, 600, "zh")
    assert lines and len(lines) == 2 and all(len(x) >= 2 for x in lines)
    if CE._zh_words("华盛顿东部") != list("华盛顿东部"):                    # jieba here: a word boundary
        assert lines == ["华盛顿东部", "公路旅行"]                            # not 华盛顿东 / 部公路旅行
    en = CE._wrap("Eastern Washington Road Trip", f, 1200, "en")
    assert en and len(en) == 2 and abs(len(en[0]) - len(en[1])) < 10


# ------------------------------------------------------------------ geometry
def test_platform_specs_have_language_and_keepouts():
    from vstudio import cover_engine as CE
    yt = CE.spec_for("youtube")
    assert yt["size"] == (1280, 720) and yt["lang"] == "en"
    x0, y0, x1, y1 = yt["keepouts"][0]
    assert x0 > 1000 and y0 > 600 and x1 == 1280 and y1 == 720           # the duration badge
    assert CE.spec_for("bilibili")["lang"] == "zh" and CE.spec_for("xiaohongshu")["lang"] == "zh"
    assert CE.spec_for("bilibili")["keepouts"][0][1] > 600               # the play-count band


def test_place_avoids_the_subject_and_the_keepouts():
    from vstudio import cover_engine as CE
    occ = np.zeros((720, 1280), np.float32)
    occ[:, :640] = 1.0                                                   # the subject fills the left half
    L = dict(w=400, h=160)
    cost, x, y, align = CE.place(occ, L, (40, 40, 1240, 680), [(1100, 600, 1280, 720)])
    assert x >= 640 and cost < 0.5
    assert not (x < 1280 and x + 400 > 1100 and y < 720 and y + 160 > 600)


def test_legibility_rejects_small_or_low_contrast_type():
    from vstudio import cover_engine as CE
    img = Image.new("RGB", (1280, 720), (20, 20, 24))
    glyphs = Image.new("L", (1280, 720), 0)
    ImageDraw.Draw(glyphs).rectangle((100, 100, 700, 220), fill=255)
    big = Image.composite(Image.new("RGB", img.size, (250, 247, 240)), img, glyphs)
    assert CE.legibility(big, glyphs, title_size=150)["ok"]
    assert not CE.legibility(big, glyphs, title_size=40)["ok"]              # 40 px type is ~2 % at 168x94
    grey = Image.composite(Image.new("RGB", img.size, (40, 40, 44)), img, glyphs)
    assert not CE.legibility(grey, glyphs, title_size=150)["ok"]            # no contrast


@pytest.mark.skipif(not _has_fonts(), reason="fonts from install.sh")
def test_make_covers_youtube_ab_pack_and_monolingual_platforms(tmp_path, monkeypatch):
    from vstudio import cover_engine as CE
    from vstudio import matte as M
    monkeypatch.setattr(M, "birefnet_path", lambda: None)                 # no model downloads in tests
    src = _scene(str(tmp_path / "f.jpg"))
    res = CE.make_covers(src, "Golden Hour · 黄金时刻 | Elliott Bay, Seattle", ["youtube", "bilibili", "xiaohongshu"],
                         str(tmp_path / "out"), log=lambda m: None)
    yt = res["youtube"]
    assert Image.open(yt["file"]).size == (1280, 720) and yt["lang"] == "en" and yt["title"] == "Golden Hour"
    assert len(yt["variants"]) == 3 and {v["variant"] for v in yt["variants"]} == {"scene", "subject", "text"}
    assert yt["variants"][0]["file"].endswith(".ab1.jpg") and yt["ok"]
    assert all(os.path.getsize(v["file"]) <= 2_000_000 for v in yt["variants"])
    assert Image.open(res["bilibili"]["file"]).size == (1146, 717) and res["bilibili"]["title"] == "黄金时刻"
    assert Image.open(res["xiaohongshu"]["file"]).size == (1080, 1440) and not res["xiaohongshu"]["variants"]
    a = np.asarray(Image.open(yt["file"]).convert("L")).astype(int)
    assert a[650:, 1120:].std() < 25                                      # nothing drawn under the duration badge
    assert json.load(open(tmp_path / "out" / "cover.covers.json"))["youtube"]["variant"] == yt["variant"]
    assert "Test & Compare" in CE.ab_note(res)


@pytest.mark.skipif(not _has_fonts(), reason="fonts from install.sh")
def test_text_cover_defaults_to_the_designed_engine(tmp_path, monkeypatch):
    from vstudio import matte as M
    from vstudio.batch import edits as ED
    monkeypatch.setattr(M, "birefnet_path", lambda: None)
    monkeypatch.setattr(ED, "cover_style", lambda: "designed")
    src = _scene(str(tmp_path / "f.jpg"), 1080, 1920)
    out = ED._text_cover(src, "Eastern Washington | 华盛顿东部", str(tmp_path / "c.jpg"))
    assert Image.open(out).size == (1080, 1920)


# ------------------------------------------------------------------ frame ranking
def test_score_frames_ranks_without_faces(tmp_path):
    v = str(tmp_path / "v.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=10:duration=4",
                    "-f", "lavfi", "-i", "color=c=black:size=640x360:rate=10:duration=2", "-filter_complex",
                    "[0:v][1:v]concat=n=2:v=1[o]", "-map", "[o]", "-pix_fmt", "yuv420p", v], check=True)
    from vstudio.cover import score_frames
    picks = score_frames(v, top_n=3, step=5, min_gap=0.5, aesthetic=False, log=lambda m: None)
    assert picks and all(p["image"] is not None for p in picks)
    assert picks[0]["t"] < 4.0                                            # never the black tail
    assert {"sharp", "exposure", "subject", "face"} <= set(picks[0]["parts"])
    assert [p["score"] for p in picks] == sorted((p["score"] for p in picks), reverse=True)
    assert all(not (0.2 <= p["t"] <= 1.3) for p in score_frames(v, top_n=6, step=2, min_gap=0.1, aesthetic=False,
                                                              avoid=[[0.5, 1.0]], log=lambda m: None))


# ------------------------------------------------------------------ models without torch
def test_ptload_reads_a_torch_zip_and_refuses_other_globals(tmp_path):
    torch = pytest.importorskip("torch")
    from vstudio.ptload import load_state_dict
    p = str(tmp_path / "w.pth")
    sd = {"params": {"a.weight": torch.arange(12, dtype=torch.float32).reshape(3, 4).t(), "a.bias": torch.ones(2)}}
    torch.save(sd, p)
    out = load_state_dict(p)["params"]
    assert np.array_equal(out["a.weight"], sd["params"]["a.weight"].numpy()) and out["a.bias"].tolist() == [1, 1]
    bad = str(tmp_path / "bad.pth")
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("archive/data.pkl", b"cos\nsystem\n(S'echo hi'\ntR.")
    with pytest.raises(Exception, match="refusing"):
        load_state_dict(bad)


def test_upscale_falls_back_to_lanczos_without_weights(monkeypatch, tmp_path):
    from vstudio import upscale as U
    monkeypatch.setenv("VSTUDIO_ESRGAN_WEIGHTS", str(tmp_path / "none.pth"))
    monkeypatch.setattr(U, "weights_path", lambda: None)
    out, how = U.upscale_to(Image.new("RGB", (320, 180), (10, 20, 30)), (1280, 720))
    assert how == "lanczos" and out.size == (1280, 720)
    assert U.upscale_to(Image.new("RGB", (1920, 1080)), (1280, 720))[1] == "none"


def test_esrgan_mlx_matches_torch_on_random_weights():
    pytest.importorskip("torch")
    pytest.importorskip("mlx.core")
    from vstudio import upscale as U
    rng = np.random.default_rng(0)
    sd = {"body.0.weight": rng.normal(0, .1, (8, 3, 3, 3)).astype(np.float32), "body.0.bias": np.zeros(8, np.float32),
          "body.1.weight": np.full(8, .2, np.float32),
          "body.2.weight": rng.normal(0, .1, (48, 8, 3, 3)).astype(np.float32), "body.2.bias": np.zeros(48, np.float32)}
    x = rng.random((10, 12, 3)).astype(np.float32)
    assert np.abs(U._run_mlx(x, sd, 2) - U._run_torch(x, sd, 2)).max() < 2e-3


def test_aesthetic_head_is_a_linear_stack_and_absent_without_files(monkeypatch, tmp_path):
    from vstudio import aesthetic as A
    mats = [(np.eye(2, dtype=np.float32) * 2, np.ones(2, np.float32)), (np.ones((1, 2), np.float32), np.zeros(1))]
    assert A.mlp(np.array([[1.0, 2.0]], np.float32), mats).tolist() == [8.0]
    monkeypatch.setenv("VSTUDIO_AESTHETIC_MODEL", str(tmp_path))
    monkeypatch.setattr("vstudio.config.MODEL_DIR", str(tmp_path))
    assert A.files() is None and not A.available()


def test_matte_falls_back_and_says_so(monkeypatch):
    from vstudio import matte as M
    monkeypatch.setattr(M, "birefnet_alpha", lambda bgr: (_ for _ in ()).throw(FileNotFoundError("not downloaded")))
    monkeypatch.setattr(M, "mediapipe_alpha", lambda bgr: np.ones(bgr.shape[:2], np.float32))
    said = []
    _, a, used = M.matte(np.zeros((8, 8, 3), np.uint8), log=said.append)
    assert used == "mediapipe" and a.shape == (8, 8) and "birefnet" in said[0]
    monkeypatch.setattr(M, "mediapipe_alpha", lambda bgr: (_ for _ in ()).throw(RuntimeError("no model")))
    with pytest.raises(RuntimeError, match="no matte engine"):
        M.matte(np.zeros((8, 8, 3), np.uint8))


# ------------------------------------------------------------------ export + pins
def test_export_writes_the_ab_pack_and_its_note(tmp_path):
    from vstudio import export as X
    from vstudio import platform as P
    srcs = []
    for k in range(3):
        p = str(tmp_path / f"v{k}.jpg")
        Image.new("RGB", (1280, 720), (k * 60, 40, 40)).save(p)
        srcs.append(p)
    names = X.write_cover_ab(P.profile("youtube"), srcs, str(tmp_path), "youtube-horizontal")
    assert names == [f"youtube-horizontal.cover.ab{k}.jpg" for k in (1, 2, 3)]
    assert all(Image.open(tmp_path / n).size == (1280, 720) for n in names)
    assert "Test & Compare" in X.cover_ab_note(names)
    assert X.parse_covers(["youtube=" + ",".join(srcs)])[1]["youtube"].count(",") == 2


def test_cli_pins_match_the_app_manifest():
    from vstudio import assets as AS
    man = json.load(open(os.path.join(ROOT, "apps", "desk", "packaging", "assets.json"), encoding="utf-8"))
    groups = {g["id"]: g for g in man["groups"]}
    for gid, g in AS.GROUPS.items():
        app = groups[gid]
        assert sorted((f["sha256"], f["size"]) for f in app["files"]) == sorted((f["sha256"], f["size"]) for f in g["files"])
        assert list(app["env"]) == [g["env"]]
        assert not any(w in app["licence"] for w in ("GPL", "non-commercial", "CC BY-NC"))
