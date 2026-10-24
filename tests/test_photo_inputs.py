"""Supplied-photo story planning uses the same real sources as the renderer."""
import os

import pytest
from PIL import Image

from vstudio.project import drafts as DR
from vstudio.project.adapters import photo_inputs as PI, photostory as PS


def test_photo_sheets_have_unique_ids_and_leave_sources_unchanged(tmp_path):
    photos = []
    for name, colour in (("a/商品.png", "red"), ("b/商品.png", "blue")):
        path = tmp_path / name
        path.parent.mkdir()
        Image.new("RGB", (180, 240), colour).save(path)
        photos.append(str(path))
    original = [open(p, "rb").read() for p in photos]
    work = tmp_path / "work"
    text, sheets, ids = PI.context(photos, str(work))
    assert ids == {"p0001", "p0002"} and len(sheets) == 1
    assert "商品.png" in text and "180x240" in text
    assert Image.open(work / "source_photos/p0001.png").getpixel((90, 120)) == (255, 0, 0)
    assert Image.open(work / "source_photos/p0002.png").getpixel((90, 120)) == (0, 0, 255)
    assert [open(p, "rb").read() for p in photos] == original


@pytest.mark.parametrize("caption_style", [None, "plain"])
def test_photo_only_draft_sees_inputs_and_binds_valid_sources(tmp_path, monkeypatch, caption_style):
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    photo = tmp_path / "cup.png"
    Image.new("RGB", (600, 800), (20, 100, 80)).save(photo)
    ctx = DR.Ctx(str(tmp_path), "main", dict(_inputs=dict(photos=[str(photo)]),
                 _item_dir=str(tmp_path / "item"), mode="music", platforms=["youtube"]), "photo-story")
    ctx.request_text = "Create a 6-second product ad for this cup, no voice-over"
    path = str(tmp_path / "item/work/spec.py")
    seen = {}
    def complete(task, system, body, **kw):
        seen.update(body=body, **kw)
        return dict(provider="test", model="fixture", json=dict(content=(
            (f'LAYOUT = dict(caption_style={caption_style!r})\n' if caption_style else '') +
            'TITLE_EN = "A daily cup"\nMEDIA = dict(images="wrong-directory")\n'
            'MUSIC = dict(length=6)\nCOVER = dict(hero=dict(src="p0001"))\n'
            'SCRIPT = [(0, [("A daily cup.", "日常水杯。")], [("p0001", 1, "still", None)])]\n'), summary="Product shown"))
    rec = PS.draft_spec(ctx, dict(id="story", author={}), path, complete=complete)
    assert rec and rec["photos"] == 1
    assert len(seen["images"]) == 1 and os.path.isfile(seen["images"][0])
    assert "p0001: cup.png" in seen["body"] and "Do not invent price" in seen["body"]
    media = PS._spec_value(open(path).read(), "MEDIA")
    assert media["images"][0] == "source_photos"
    assert os.path.isfile(os.path.join(os.path.dirname(path), media["images"][0], "p0001.png"))
    assert DR.data_module_ok(open(path).read())
    result = open(path).read()
    assert PS._spec_value(result, "GRADE_LOOK") is None
    assert PS._spec_value(result, "CHAPTER_CARD") == 0
    assert PS._spec_value(result, "TITLE_CARD") is False
    assert PS._spec_value(result, "PRESERVE_COLOUR") is True
    assert PS._spec_value(result, "LAYOUT")["caption_y"] == 0.12
    assert PS._spec_value(result, "LAYOUT")["caption_style"] == (caption_style or "label")


def test_unknown_photo_is_not_silently_replaced(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    photo = tmp_path / "real.png"
    Image.new("RGB", (120, 160)).save(photo)
    ctx = DR.Ctx(str(tmp_path), "main", dict(_inputs=dict(photos=[str(photo)]),
                 _item_dir=str(tmp_path / "item"), mode="music"), "photo-story")
    ctx.request_text = "product ad, no voice"
    with pytest.raises(ValueError, match="unknown photo source.*imaginary"):
        PS.draft_spec(ctx, dict(id="story", author={}), str(tmp_path / "item/work/spec.py"), complete=lambda *a, **k:
                      dict(provider="test", json=dict(content='SCRIPT = [(0, [("Cup", "杯子")], [("imaginary", 1, "still", None)])]')))


@pytest.mark.parametrize("script", [
    'SCRIPT = [dict(duration=4, cues=[("Cup", "杯子")], shots=[("p0001", 1, "still", None)])]',
    'SCRIPT = [(0, [("Cup",)], [("p0001", 1, "still", None)])]',
    'SCRIPT = [(0, [], [("p0001", -1, "still", None)])]',
    'SCRIPT = [(0, [], [("p0001", 1, "still", None)])]\nCTA = dict(text="Not rendered")',
])
def test_valid_python_is_not_enough_for_a_renderable_story(script):
    assert DR.data_module_ok(script)
    assert PS.spec_error(script)


def test_contain_photo_preserves_all_corners_on_each_canvas():
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'workflows/photo-story/scripts'))
    from photostory.shots import ImageShot
    im = Image.new("RGB", (300, 180), (240, 235, 225))
    colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255)]
    for box, colour in zip([(0, 0, 30, 30), (270, 0, 300, 30), (0, 150, 30, 180), (270, 150, 300, 180)], colours):
        im.paste(colour, box)
    for w, h in ((320, 180), (180, 320), (180, 240)):
        ctx = SimpleNamespace(BOX_W=w, BOX_H=h, open_img=lambda _: im.copy())
        shot = ImageShot(ctx, dict(start=0, end=3, tail=0, motion="in", fit="contain"), "p0001")
        for t in (0, 1, 2.9):
            frame = shot.frame(t)
            assert frame.shape == (h, w, 3)
            for colour in colours:
                assert np.any(np.all(np.abs(frame - np.array(colour)) < 8, axis=2))


def test_valid_python_with_wrong_timeline_is_repaired_before_render(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    photo = tmp_path / "cup.png"
    Image.new("RGB", (120, 160), "white").save(photo)
    ctx = DR.Ctx(str(tmp_path), "main", dict(_inputs=dict(photos=[str(photo)]),
                 _item_dir=str(tmp_path / "item"), mode="music"), "photo-story")
    ctx.request_text = "A 6-second product film from this illustration, no voice-over"
    bad = 'SCRIPT = [dict(duration=6, shots=[("p0001", 1, "still", None)])]'
    good = 'SCRIPT = [(0, [("A cup", "杯子")], [("p0001", 1, "still", None)])]\nMUSIC = dict(length=6)'
    calls = []
    def complete(*args, **kw):
        calls.append(args[2])
        return dict(provider="test", json=dict(content=bad if len(calls) == 1 else good))
    dest = str(tmp_path / "item/work/spec.py")
    assert PS.draft_spec(ctx, dict(id="story", author={}), dest, complete=complete)
    assert len(calls) == 2 and "three-part tuple" in calls[1]
    assert PS.spec_error(open(dest).read()) is None


def test_macos_heic_preview_preserves_the_original(tmp_path):
    import shutil
    import subprocess
    import sys
    if sys.platform != "darwin" or not shutil.which("sips"):
        pytest.skip("macOS HEIC conversion")
    src = tmp_path / "fixture.png"
    Image.new("RGB", (180, 240), (40, 110, 80)).save(src)
    heic = tmp_path / "fixture.heic"
    subprocess.run(["sips", "-s", "format", "heic", str(src), "--out", str(heic)], check=True, capture_output=True)
    original = heic.read_bytes()
    text, sheets, ids = PI.context([str(heic)], str(tmp_path / "work"))
    assert ids == {"p0001"} and "180x240" in text and sheets
    assert heic.read_bytes() == original
    assert PI.caption_ink([str(heic)], str(tmp_path / "work")) is not None


@pytest.mark.parametrize("subtitle", [None, "Stock footage / editing study"])
def test_product_cover_preserves_whole_source_and_its_colours(tmp_path, monkeypatch, subtitle):
    import importlib.util
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import numpy as np
    monkeypatch.setenv("VSTUDIO_DEFAULT_PERSONA", "1")
    from vstudio import config
    fonts = os.path.expanduser("~/.cache/video-studio/fonts")
    if not os.path.isfile(os.path.join(fonts, "NotoSansSC-Regular.otf")):
        pytest.skip("requires installed OFL font fixtures")
    monkeypatch.setattr(config, "FONT_DIR", fonts)
    scripts = Path(__file__).resolve().parents[1] / "workflows/photo-story/scripts"
    sys.path.insert(0, str(scripts))
    module = importlib.util.spec_from_file_location("photo_cover_test", scripts / "photostory/cover.py")
    cover = importlib.util.module_from_spec(module)
    module.loader.exec_module(cover)
    src = tmp_path / "source.png"
    im = Image.new("RGB", (300, 180), (230, 230, 220))
    colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255)]
    for box, colour in zip([(0, 0, 30, 30), (270, 0, 300, 30), (0, 150, 30, 180), (270, 150, 300, 180)], colours):
        im.paste(colour, box)
    im.save(src)
    ctx = SimpleNamespace(_readable=lambda p: p, find_image=lambda _: str(src),
                          TITLE_EN="A real product", TITLE_ZH="", SUBS="en")
    from PIL import ImageDraw
    drawn = []
    original_text = ImageDraw.ImageDraw.text
    def text_spy(self, xy, text, *args, **kwargs):
        drawn.append((xy, text))
        return original_text(self, xy, text, *args, **kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", text_spy)
    for w, h in ((480, 270), (270, 480), (360, 480)):
        out = tmp_path / f"cover-{w}-{h}.png"
        cover.product_cover(SimpleNamespace(), ctx, dict(hero=dict(src="source"), subtitle=subtitle), w, h, str(out))
        frame = np.asarray(Image.open(out)).astype(int)
        assert frame.shape == (h, w, 3)
        for colour in colours:
            assert np.any(np.all(np.abs(frame - colour) < 3, axis=2))

    if subtitle:
        assert any(subtitle == text for _, text in drawn)


@pytest.mark.parametrize("prompt,heading", [
    ("Write a comedy skit about a coffee machine", "PAYOFF"),
    ("企业宣传片，展示真实工厂", "EVIDENCE"),
    ("Write a product ad for this cup", "DEMONSTRATION"),
])
def test_non_teaching_scripts_receive_their_own_structure(tmp_path, monkeypatch, prompt, heading):
    from vstudio.project.adapters import preproduction as PP
    ctx = DR.Ctx(str(tmp_path), "main", dict(_inputs=dict(topic=prompt)), "preproduction")
    ctx.request_text = prompt
    seen = {}
    def generic(ctx, cp, path, **kw):
        seen.update(cp=cp, **kw)
        return dict(by="test")
    monkeypatch.setattr(DR, "generic", generic)
    assert PP.draft_script(ctx, dict(id="lock"), str(tmp_path / "SCRIPT.md"))
    assert f"## {heading}" in seen["template_text"]
    assert "## INSIGHT" not in seen["template_text"]
    assert "shot/action" in seen["cp"]["author"]["format"]


def test_company_process_defaults_do_not_inherit_scenic_chapters(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    image = tmp_path / "factory.png"; Image.new("RGB", (640, 360), (50, 80, 100)).save(image)
    ctx = DR.Ctx(str(tmp_path), "main", dict(_inputs=dict(photos=[str(image)]),
                 _item_dir=str(tmp_path / "item"), mode="music", platforms=["youtube"]), "photo-story")
    ctx.request_text = "Create a corporate film from the supplied factory view; no voice-over"
    path = str(tmp_path / "item/work/spec.py")
    def model(*a, **kw):
        return dict(provider="test", json=dict(content=(
            'TITLE_EN="Process"\nSCRIPT=[(0,[("The equipment", "设备")],[("p0001",1,"still",None)])]\n'
            'MEDIA=dict(images="frames")\nCOVER=dict(hero=dict(src="p0001"))\n')))
    PS.draft_spec(ctx, dict(id="story", author={}), path, complete=model)
    text = open(path).read()
    assert PS._spec_value(text, "TITLE_CARD") is False
    assert PS._spec_value(text, "CHAPTER_CARD") == 0
    assert PS._spec_value(text, "PRESERVE_COLOUR") is True
    assert PS._spec_value(text, "LAYOUT")["caption_style"] == "label"
    assert PS._spec_value(text, "PACING")["end_fade"] == 0.4


@pytest.mark.parametrize("platform,en,zh", [("youtube", "Manual loading", "人工装载"),
    ("tiktok", "A longer process label that needs a second line", ""),
    ("xiaohongshu:vertical", "", "逐一确认设备与物料的位置")])
def test_process_labels_render_inside_safe_width_on_each_canvas(tmp_path, monkeypatch, platform, en, zh):
    import sys, types
    import numpy as np
    root = os.path.dirname(os.path.dirname(__file__))
    sys.path.insert(0, os.path.join(root, "workflows", "photo-story", "scripts"))
    from photostory.ctx import Ctx
    from photostory.subtitles import make_sub
    from vstudio import config
    fonts = os.path.expanduser("~/.cache/video-studio/fonts")
    if not os.path.isfile(os.path.join(fonts, "NotoSansSC-Bold.otf")):
        pytest.skip("requires installed OFL font fixtures")
    monkeypatch.setattr(config, "FONT_DIR", fonts)
    monkeypatch.setenv("VSTUDIO_DEFAULT_PERSONA", "1")
    spec = types.SimpleNamespace(__file__=str(tmp_path / "spec.py"), PLATFORM=platform,
        TITLE_EN="Process", SECTIONS=["Process"], SCRIPT=[],
        LAYOUT=dict(caption_style="label", caption_y=0.68, sub=0.18))
    c = Ctx(spec)
    a = make_sub(c, en, zh)
    ys, xs = np.where(a[:, :, 3] > 0)
    assert xs.size and xs.min() >= c.CAP[0] and xs.max() <= c.CAP[2]
    assert ys.min() >= 0 and ys.max() < c.SUB_H
    # A high-contrast plate and legible foreground, rather than a bare thin caption.
    assert ((a[:, :, 0] < 30) & (a[:, :, 3] > 200)).sum() > 500
    assert ((a[:, :, :3].min(axis=2) > 235) & (a[:, :, 3] > 250)).sum() > 100


@pytest.mark.parametrize("options,motion", [
    ('dict(fit="contain", z=2)', 'still'),
    ('dict(fit="contain", c=(0.5, 0.2))', 'in'),
    ('dict(fit="contain")', 'panL'),
    ('dict(z=0)', 'still'),
    ('dict(c=(0.5, 2))', 'still'),
])
def test_photo_framing_rejects_ignored_or_invalid_requests(options, motion):
    script = f'SCRIPT = [(0, [], [("p0001", 1, "{motion}", {options})])]'
    assert PS.spec_error(script)


def test_detail_framing_changes_the_visible_source_region():
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'workflows/photo-story/scripts'))
    from photostory.shots import ImageShot
    im = Image.new("RGB", (400, 400), "white")
    im.paste((255, 0, 0), (150, 30, 250, 130))
    ctx = SimpleNamespace(BOX_W=200, BOX_H=200, open_img=lambda _: im.copy())
    base = dict(start=0, end=3, tail=0, motion="still")
    wide = ImageShot(ctx, dict(base, fit="contain"), "p0001").frame(1)
    detail = ImageShot(ctx, dict(base, fit="cover", c=(0.5, 0.2), z=3), "p0001").frame(1)
    def red_area(frame):
        return np.mean((frame[:,:,0] > 240) & (frame[:,:,1] < 15))
    assert red_area(detail) > red_area(wide) * 5
    assert PS.spec_error('SCRIPT = [(0, [], [("p0001", 1, "still", dict(fit="cover", c=(0.5,0.2), z=3))])]') is None


@pytest.mark.parametrize("brief", ["No music", "不要配乐", "A silent product film"])
def test_explicit_silence_never_selects_music_even_in_music_mode(tmp_path, monkeypatch, brief):
    from types import SimpleNamespace
    from vstudio import music
    supplied = tmp_path / "unused.wav"
    supplied.write_bytes(b"unused input")
    ctx = SimpleNamespace(inputs={"music": str(supplied)})
    monkeypatch.setattr(music, "choose", lambda *a, **k: pytest.fail("Must not choose a bed"))
    assert PS.music_bed(ctx, str(tmp_path), brief, 12, True) is None


def test_silent_draft_overrides_model_music(tmp_path):
    photo = tmp_path / 'bottle.png'
    Image.new('RGB', (100, 150), 'green').save(photo)
    ctx = DR.Ctx(str(tmp_path), 'main', dict(_inputs=dict(photos=[str(photo)]),
        _item_dir=str(tmp_path/'item'), mode='music'), 'photo-story')
    ctx.request_text = 'A silent 12-second product film, no music'
    def complete(*a, **kw):
        return dict(provider='test', json=dict(content='SCRIPT = [(0, [("Bottle", "瓶子")], [("p0001", 1, "still", None)])]\nBGM = "invented.wav"\nMUSIC = dict(grid="beat", length=12)'))
    dest = str(tmp_path/'item/work/spec.py')
    assert PS.draft_spec(ctx, dict(id='story', author={}), dest, complete=complete)
    text = open(dest).read()
    assert PS._spec_value(text, 'BGM') is None
    assert PS._spec_value(text, 'MUSIC')['grid'] == 'seconds'


@pytest.mark.parametrize("motion", ["in", "out"])
def test_product_photo_move_keeps_all_source_corners_visible(motion):
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'workflows/photo-story/scripts'))
    from photostory.shots import ImageShot
    im = Image.new("RGB", (400, 600), "white")
    colours = [(240, 10, 10), (10, 240, 10), (10, 10, 240), (240, 10, 240)]
    for colour, box in zip(colours, [(0, 0, 30, 30), (370, 0, 400, 30), (0, 570, 30, 600), (370, 570, 400, 600)]):
        im.paste(colour, box)
    ctx = SimpleNamespace(BOX_W=240, BOX_H=320, open_img=lambda _: im.copy())
    shot = ImageShot(ctx, dict(start=0, end=3, tail=0, motion=motion, fit="contain"), "product")
    frames = [shot.frame(t) for t in (0, 1.5, 3)]
    assert np.mean(np.abs(frames[0] - frames[-1])) > 0.5
    for frame in frames:
        for colour in colours:
            assert (np.max(np.abs(frame - np.array(colour)), axis=2) < 10).sum() > 50
