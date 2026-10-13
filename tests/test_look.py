"""The look of an HTML-rendered video (vstudio.look): frames drawn twice in two shuffled orders and compared, fonts
that did not load, text cut off / in the caption band, sounds that are missing, the contact sheet, the scene mapping
for the explainer's repair round, and the first-pass items. The HyperFrames CLI is a fake here (``look.RUN``)."""
import json
import os
import re
import shutil

import numpy as np
import pytest
from PIL import Image

from vstudio import firstpass as FP
from vstudio import look as LK

HAS_FFMPEG = bool(shutil.which("ffmpeg"))


def _png(path, color, noise=False, size=(192, 108)):
    a = np.zeros((size[1], size[0], 3), np.uint8)
    a[:] = (17, 17, 17)
    a[20:60, 20:60] = color
    if noise:                                  # anti-aliasing: a few pixels off by a little
        a[30, 30:34] = np.clip(a[30, 30:34].astype(int) + 9, 0, 255)
    Image.fromarray(a).save(path)
    return str(path)


def _project(tmp_path, audio=None, body=""):
    d = tmp_path / "proj"
    d.mkdir(parents=True)
    au = f'<audio id="vo" class="clip" src="{audio}" data-start="0" data-duration="4"></audio>' if audio else ""
    (d / "index.html").write_text(
        '<!doctype html><html><head><style>@font-face{font-family:"Brand";src:url("assets/fonts/brand.woff2")}'
        '#t{font-family:"Brand",sans-serif}</style></head><body><div id="root" data-composition-id="main" '
        f'data-start="0" data-width="1920" data-height="1080" data-duration="4">{au}{body}</div></body></html>')
    return d


def _fake_cli(colors, fonts_failed=(), check=None, calls=None):
    """snapshot: writes frame-NN-at-Ts.png in the order asked, colour by (pass, t); check: prints ``check``."""
    passes = []

    def run(args, cwd, timeout):
        if calls is not None:
            calls.append(list(args))
        if args[0] == "snapshot":
            passes.append(1)
            n = len(passes)
            ts = [float(x) for x in args[args.index("--at") + 1].split(",")]
            out = args[args.index("-o") + 1]
            os.makedirs(out, exist_ok=True)
            for k, t in enumerate(ts):
                _png(os.path.join(out, f"frame-{k:02d}-at-{t:g}s.png"), colors(n, t), noise=n == 2)
            msg = f"Fonts FAILED: {', '.join(f + ' (normal normal)' for f in fonts_failed)}\n" if fonts_failed else ""
            return 0, msg + f"{len(ts)} snapshots saved", ""
        if args[0] == "check":
            return 0, json.dumps(check or dict(ok=True, lint={}, runtime={}, layout={})), ""
        return 1, "", "unknown"
    return run


CHECK = dict(ok=False, browserSkipped=False, lint=dict(findings=[]),
             runtime=dict(findings=[
                 dict(code="http_error", severity="error", message="404 loading assets/fonts/brand.woff2",
                      url="http://127.0.0.1:1/assets/fonts/brand.woff2", sourceFile="index.html", time=0),
                 dict(code="script_error", severity="error", message="script error: f02 x is not defined",
                      sourceFile="compositions/f02.html", time=2.5)]),
             layout=dict(findings=[
                 dict(code="text_box_overflow", severity="error", selector="#t", text="A very long headline",
                      message="Text extends outside its nearest visual/container box.", times=[0.5, 1.5],
                      sourceFile="compositions/f01.html", fixHint="widen the container"),
                 dict(code="canvas_overflow", severity="warning", selector="#t", text="A very long headline",
                      message="Text extends outside the composition canvas.", times=[0.5, 1.5],
                      sourceFile="compositions/f01.html"),
                 dict(code="canvas_overflow", severity="warning", selector="#fly", text="on its way in",
                      message="Text extends outside the composition canvas.", times=[3.0]),
                 dict(code="caption_zone_collision", severity="warning", selector="#low", text="low label",
                      message="overlaps the reserved caption band", times=[3.2], sourceFile="compositions/f02.html")]))


def test_times_shuffle_and_compare(tmp_path):
    ts = LK.sample_times(4, 4)
    assert ts == [0.5, 1.5, 2.5, 3.5]
    assert LK.shuffled(ts, 1) == LK.shuffled(ts, 1) and sorted(LK.shuffled(ts, 2)) == ts
    a = _png(tmp_path / "a.png", (230, 50, 50))
    b = _png(tmp_path / "b.png", (230, 50, 50), noise=True)
    c = _png(tmp_path / "c.png", (50, 230, 50))
    assert LK.block_diff(a, b) <= LK.SAME_LIMIT < LK.block_diff(a, c)
    assert LK.compare({1.0: a, 2.0: a}, {1.0: b, 2.0: c}) == [2.0]


def test_look_finds_what_goes_wrong_in_a_browser(tmp_path, monkeypatch):
    d = _project(tmp_path, audio="assets/vo.wav")
    calls = []
    # the frame at 1.5 s depends on what was drawn before it: another colour on the second pass
    colors = lambda n, t: (50, 230, 50) if (n == 2 and abs(t - 1.5) < 1e-6) else (230, 50, 50)  # noqa: E731
    monkeypatch.setattr(LK, "RUN", _fake_cli(colors, fonts_failed=["Brand"], check=CHECK, calls=calls))
    r = LK.look(str(d), count=4, caption_band=0.82)
    snaps = [c for c in calls if c[0] == "snapshot"]
    orders = [c[c.index("--at") + 1] for c in snaps]
    assert len(snaps) == 2 and orders[0] != orders[1] and sorted(orders[0].split(",")) == sorted(orders[1].split(","))
    chk = next(c for c in calls if c[0] == "check")
    assert "--caption-zone" in chk and "y0=0.820" in chk[chk.index("--caption-zone") + 1]
    codes = [f["code"] for f in r["findings"]]
    assert codes.count("look-nondeterministic") == 1
    assert any(f["code"] == "look-nondeterministic" and f["t"] == 1.5 for f in r["errors"])
    assert codes.count("look-font-failed") == 1                       # the browser's, not its 404 again
    assert codes.count("look-text-clipped") == 1                      # one per element; text on its way in is not
    assert "look-safe-area" in codes and "look-script-error" in codes
    assert any(f["code"] == "look-audio-missing" and "assets/vo.wav" in f["message"] for f in r["findings"])
    assert r["ok"] is False and all(f["fix"] for f in r["findings"])
    assert os.path.isfile(r["sheet"]) and Image.open(r["sheet"]).size[0] > 0
    assert len(r["frames"]) == 4
    # every frame the same picture: a page that does not move
    monkeypatch.setattr(LK, "RUN", _fake_cli(lambda n, t: (230, 50, 50)))
    r = LK.look(str(_project(tmp_path / "s")), count=3)
    assert [f["code"] for f in r["findings"]] == ["look-static"] and r["ok"]
    assert any("same picture" in p for p in r["passed"])


def test_no_node_skips_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(LK, "RUN", lambda args, cwd, timeout: (None, "", "no node"))
    r = LK.look(str(_project(tmp_path)), count=2)
    assert r["ok"] and r["frames"] == {} and len(r["skipped"]) == 2 and r["sheet"] is None


def test_lint_errors_block_the_browser_pass():
    f = LK.from_check(dict(lint=dict(findings=[dict(code="audio_src_not_found", severity="error",
                                                    message="<audio> references a missing file")]),
                           browserSkipped=True))
    assert [x["code"] for x in f] == ["look-audio-missing"]


def test_font_problems_static(tmp_path):
    (tmp_path / "assets" / "fonts").mkdir(parents=True)
    (tmp_path / "assets" / "fonts" / "ok.woff2").write_bytes(b"x")
    html = ('<template><style>@font-face{font-family:"Ok";src:url("assets/fonts/ok.woff2")}'
            '@font-face{font-family:"Gone";src:url("assets/fonts/gone.woff2")}'
            '@font-face{font-family:"Later";src:url("assets/fonts/scene-cjk-w7.woff2")}'
            '.a{font-family:"Ok",sans-serif}.b{font-family:"Made Up Sans",serif}.c{font-family:var(--f)}'
            '.d{font-family:-apple-system,sans-serif}</style></template>')
    p = LK.font_problems(html, str(tmp_path), will_exist=["assets/fonts/scene-cjk-w7.woff2"])
    msgs = " | ".join(x["message"] for x in p)
    assert "gone.woff2" in msgs and "made up sans" in msgs and len(p) == 2
    assert all(x["code"] == "look-font-failed" for x in p)
    assert [x["severity"] for x in p] == ["error", "warning"]          # a missing file / a fallback face


def test_look_scenes_maps_findings_to_scenes(tmp_path, monkeypatch):
    sd = tmp_path / "compositions"
    sd.mkdir()
    for sid in ("f01", "f02"):
        (sd / f"{sid}.html").write_text(f'<template><div data-composition-id="{sid}">'
                                        '<style>.x{font-family:"Brand"}</style></div></template>')
    colors = lambda n, t: (50, 230, 50) if (n == 2 and t > 2) else (230, 50, 50)  # noqa: E731
    monkeypatch.setattr(LK, "RUN", _fake_cli(colors, fonts_failed=["Brand"], check=CHECK))
    out = LK.look_scenes(str(sd), [("f01", 2.0), ("f02", 2.0)], 1920, 1080)
    assert set(out) == {"f01", "f02"}
    assert any("look-text-clipped" in x for x in out["f01"])
    assert any("look-nondeterministic" in x for x in out["f02"]) and any("look-safe-area" in x for x in out["f02"])
    assert any("look-script-error" in x for x in out["f02"])
    assert all(sum("look-font-failed" in x for x in v) == 1 for v in out.values())   # once per scene
    assert all(re.search(r"Fix: ", x) for v in out.values() for x in v)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_audio_checks(tmp_path):
    import subprocess
    d = tmp_path / "p"
    (d / "assets").mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1",
                    str(d / "assets" / "quiet.wav")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=1", str(d / "assets" / "vo.wav")],
                   check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-c:v", "libx264",
                    str(tmp_path / "nosound.mp4")], check=True)
    (d / "index.html").write_text('<audio id="a" src="assets/vo.wav"></audio><audio id="b" src="assets/quiet.wav">'
                                  '</audio><audio id="c" src="assets/none.wav"></audio>')
    f = LK.check_audio(str(d), video=str(tmp_path / "nosound.mp4"))
    msgs = [x["message"] for x in f]
    assert any("none.wav" in m for m in msgs) and any("quiet.wav is silent" in m for m in msgs)
    assert any("no audio track" in m for m in msgs) and not any(m.startswith("assets/vo.wav") for m in msgs)


def test_firstpass_items_from_a_look(tmp_path, monkeypatch):
    monkeypatch.setattr(LK, "RUN", _fake_cli(lambda n, t: (230, 50, 50) if n == 1 or t < 1 else (50, 230, 50),
                                             check=CHECK))
    res = LK.look(str(_project(tmp_path)), count=3)
    items = {i["id"]: i for i in FP.check_look(res)}
    assert items["look-nondeterministic"]["ok"] is False and items["look-nondeterministic"]["severity"] == "red"
    assert items["look-text-clipped"]["ok"] is False and items["look-safe-area"]["severity"] == "warn"
    assert items["look-sheet"]["value"] == res["sheet"] and items["look-sheet"]["severity"] == "info"
    assert "same time draws the same picture" in FP.report(dict(video="v.mp4", platform="x",
                                                                items=list(items.values()), ok=False), "en")
    # a clean look: passed items only
    monkeypatch.setattr(LK, "RUN", _fake_cli(lambda n, t: (230, 50, 50 + int(t * 50))))
    clean = FP.check_look(LK.look(str(_project(tmp_path / "c")), count=3))
    assert all(i["ok"] in (True, None) for i in clean) and any(i["id"] == "look-nondeterministic" for i in clean)
