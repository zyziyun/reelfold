"""Per-language captions at export (references/AESTHETICS.md P9: one subtitle language per platform): ``--cues
lang=path`` tracks and the platform picking its own, the CLI parsing (lang=path vs a bare or Windows path), the
caption files (<stem>.<lang>.srt) of the upload-capable platforms with --start timing, ``--captions sidecar`` (a
clean YouTube video, still burned on 小红书) and the first-pass caption-language check. Synthetic media only."""
import json
import os
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from vstudio import export as X
from vstudio import firstpass as FP
from vstudio import platform as P
from vstudio.subs import Cue, srt_read

HAS_FFMPEG = bool(shutil.which("ffmpeg"))
media = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))


def _cues(path, cues, **extra):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict(cues=cues, **extra), f, ensure_ascii=False)
    return str(path)


EN = [dict(start=0.0, end=0.8, text="Gold on the water"), dict(start=0.8, end=1.6, text="Let the light take its time")]
ZH = [dict(start=0.0, end=0.8, text="金色落在水面"), dict(start=0.8, end=1.6, text="让光慢慢走")]


# ------------------------------------------------------------------------------------------- parsing + picking
def test_cli_cues_lang_path_bare_and_windows(tmp_path):
    assert X.parse_cues_arg(None) is None
    assert X.parse_cues_arg(["cues.json"]) == "cues.json"                     # one track for every platform
    assert X.parse_cues_arg(["en=cues.en.json", "zh-Hans=c.zh.json"]) == {"en": "cues.en.json",
                                                                          "zh-Hans": "c.zh.json"}
    assert X.parse_cues_arg([r"C:\clips\cues.json"]) == r"C:\clips\cues.json"   # a drive letter is not a language
    assert X.parse_cues_arg([r"C:\clips\a=b.json"]) == r"C:\clips\a=b.json"
    assert X.parse_cues_arg(["clips/a=b.json"]) == "clips/a=b.json"
    odd = tmp_path / "en=x.json"                                               # an existing file stays a path
    odd.write_text("[]")
    assert X.parse_cues_arg([str(odd)]) == str(odd)
    assert X.parse_cues_arg(["all.json", "zh=z.json"]) == {"zh": "z.json", "*": "all.json"}
    with pytest.raises(ValueError):
        X.parse_cues_arg(["a.json", "b.json"])


def test_cli_passes_the_map(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(X, "export", lambda *a, **k: seen.update(k) or dict(exports=[], warnings=[]))
    X.main(["m.mp4", "--platforms", "youtube", "--cues", "en=a.json", "--cues", "zh=b.json", "--captions", "sidecar",
            "--out", str(tmp_path)])
    assert seen["cues"] == {"en": "a.json", "zh": "b.json"} and seen["captions"] == "sidecar"
    X.main(["m.mp4", "--platforms", "youtube", "--cues", "a.json", "--no-captions", "--out", str(tmp_path)])
    assert seen["cues"] == "a.json" and seen["captions"] == "off"


def test_pick_track_by_platform_language(tmp_path):
    en, zh = _cues(tmp_path / "en.json", EN), _cues(tmp_path / "zh.json", ZH)
    yt, xhs, bili = P.profile("youtube"), P.profile("xiaohongshu"), P.profile("bilibili")
    assert X.pick_track(yt, {"en": en, "zh": zh}) == (en, "en", [])
    assert X.pick_track(xhs, {"en": en, "zh-Hans": zh}) == (zh, "zh-Hans", [])
    src, lang, warn = X.pick_track(bili, {"en": en})
    assert src == en and lang == "en" and "no Chinese caption track" in warn[0] and "en track" in warn[0]
    assert X.pick_track(yt, {"zh": zh, "*": en}) == (en, None, [])
    assert X.pick_track(yt, en) == (en, None, [])                              # one track: unchanged


def test_caption_tracks_of_a_bilingual_file_and_a_map(tmp_path):
    bi = _cues(tmp_path / "bi.json", [dict(start=0, end=1, text="金色落在水面", alt="Gold on the water"),
                                      dict(start=1, end=2, text="2026"),
                                      dict(start=2, end=3, text="只有中文")])
    tr = X.caption_tracks(bi, P.profile("youtube"))
    assert list(tr) == ["en", "zh"]
    assert [c.text for c in tr["en"]] == ["Gold on the water", "2026"]         # a year belongs to both
    assert [c.text for c in tr["zh"]] == ["金色落在水面", "2026", "只有中文"]
    assert list(X.caption_tracks(bi, P.profile("bilibili"))) == ["zh", "en"]   # the platform's language first
    m = X.caption_tracks({"en": _cues(tmp_path / "e.json", EN), "zh": _cues(tmp_path / "z.json", ZH)},
                         P.profile("x"))
    assert list(m) == ["en", "zh"] and m["zh"][0].text == "金色落在水面"


def test_upload_capable_platforms_in_the_registry():
    up = {n for n in P.PLATFORMS if P.profile(n).extra.get("caption_upload")}
    assert {"youtube", "youtube-shorts", "x"} <= up
    assert not up & {"xiaohongshu", "douyin", "tiktok", "instagram", "wechat-channels"}


def test_captions_mode():
    assert X.captions_mode(True) == "both" and X.captions_mode(None) == "both"
    assert X.captions_mode(False) == "off" and X.captions_mode("sidecar") == "sidecar"
    with pytest.raises(ValueError):
        X.captions_mode("subtitles")


# ------------------------------------------------------------------------------------------- real exports
def _clip(path, w=640, h=360, d=1.6):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x404040:s={w}x{h}:d={d}:r=25",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={d}", "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return str(path)


def _caption_drawn(video, prof, t=0.4):
    from vstudio import media as M
    png = video + ".png"
    M.grab_frame(video, t, png)
    img = np.asarray(Image.open(png).convert("RGB")).astype(np.int16)
    x0, y0, x1, y1 = (int(v) for v in P.caption_box(prof))
    base = np.median(img.reshape(-1, 3), axis=0)
    return float(np.abs(img[y0:y1, x0:x1] - base).max()) > 80


@media
def test_sidecar_mode_clean_youtube_burned_xiaohongshu(tmp_path):
    master = _clip(tmp_path / "m.mp4")
    tracks = {"en": _cues(tmp_path / "en.json", EN), "zh": _cues(tmp_path / "zh.json", ZH)}
    out = str(tmp_path / "ex")
    post = dict(en=dict(title="Gold on the water", body="A quiet evening."),
                zh=dict(title="水面的金色", body="安静的傍晚。"))
    man = X.export(master, ["youtube", "xiaohongshu:horizontal"], out, cues=tracks, captions="sidecar",
                   mode="pad-blur", post=post)
    yt, xhs = man["exports"]
    assert yt["platform"] == "youtube" and xhs["platform"] == "xiaohongshu"
    assert yt["captions"] == 0 and yt["captions_mode"] == "sidecar" and yt["caption_track"] == "en"
    assert not _caption_drawn(os.path.join(out, yt["file"]), P.profile("youtube"))
    assert yt["sidecars"] == [dict(lang="en", file="youtube-horizontal.en.srt"),
                              dict(lang="zh", file="youtube-horizontal.zh.srt")]
    en = srt_read(os.path.join(out, "youtube-horizontal.en.srt"))
    assert [c.text for c in en] == ["Gold on the water", "Let the light take its time"]
    assert [c.text for c in srt_read(os.path.join(out, "youtube-horizontal.zh.srt"))][0] == "金色落在水面"
    note = open(os.path.join(out, yt["post"]), encoding="utf-8").read()
    assert "## Caption files" in note and "youtube-horizontal.en.srt" in note and yt["post_lang"] == "en"
    # 小红书 takes no caption file: still burned, in Chinese, and no .srt written
    assert xhs["captions"] == 2 and xhs["caption_track"] == "zh" and "sidecars" not in xhs
    assert _caption_drawn(os.path.join(out, xhs["file"]), P.profile("xiaohongshu", "horizontal"))
    assert not [f for f in os.listdir(out) if f.startswith("xiaohongshu") and f.endswith(".srt")]
    assert xhs["post_lang"] == "zh"


@media
def test_sidecar_timing_follows_start_and_dur_and_burn_writes_none(tmp_path):
    master = _clip(tmp_path / "m.mp4", d=2.0)
    cues = _cues(tmp_path / "bi.json", [dict(start=0.2, end=0.6, text="before the cut"),
                                        dict(start=0.9, end=1.4, text="first line", alt="第一句"),
                                        dict(start=1.5, end=1.95, text="cut at dur", alt="被截断")])
    d = str(tmp_path / "a")
    os.makedirs(d)
    e = X.export_one(master, P.profile("youtube"), d, cues=cues, start=0.8, dur=1.0)
    assert e["captions_mode"] == "both" and e["captions"] >= 1                 # default: burned AND the files
    en = srt_read(os.path.join(d, "youtube-horizontal.en.srt"))
    assert [c.text for c in en] == ["first line", "cut at dur"]
    assert abs(en[0].start - 0.1) < 0.002 and abs(en[0].end - 0.6) < 0.002
    assert abs(en[1].start - 0.7) < 0.002 and abs(en[1].end - 1.0) < 0.002   # cut at --dur
    zh = srt_read(os.path.join(d, "youtube-horizontal.zh.srt"))
    assert [c.text for c in zh] == ["第一句", "被截断"] and abs(zh[0].start - 0.1) < 0.002
    b = str(tmp_path / "b")
    os.makedirs(b)
    e = X.export_one(master, P.profile("youtube"), b, cues=cues, captions="burn", start=0.8, dur=1.0)
    assert "sidecars" not in e and not [f for f in os.listdir(b) if f.endswith(".srt")]


# ------------------------------------------------------------------------------------------- firstpass
def test_firstpass_caption_language():
    yt, xhs = P.profile("youtube"), P.profile("xiaohongshu")
    zh = [dict(text="金色落在水面"), dict(text="让光慢慢走 AWS"), dict(text="2026")]
    en = [dict(text="Gold on the water"), dict(text="Claude Code")]
    bad = FP.check_caption_lang(zh, yt)
    assert bad[0]["id"] == "caption-lang" and bad[0]["ok"] is False and bad[0]["severity"] == "red"
    assert FP.check_caption_lang(en, yt)[0]["ok"] is True
    warn = FP.check_caption_lang(en, xhs)[0]                                   # not a fixed-language platform
    assert warn["ok"] is False and warn["severity"] == "warn"
    assert FP.check_caption_lang([dict(text="金色", alt="Gold on the water")], yt)[0]["ok"] is True   # alt line
    assert FP.check_caption_lang([dict(text="2026"), dict(text="AWS")], yt) == []    # names / numbers: no verdict
    t = FP.check_caption_lang(en, yt, title="水面的金色", text="安静的傍晚，金色落在水面上。")
    assert {i["id"] for i in t if i["ok"] is False} == {"title-lang", "post-lang"}
    assert not [i for i in FP.check_caption_lang(en, yt, "Gold on the water", "A quiet evening on the lake.")
                if i["ok"] is False]


@pytest.mark.parametrize('language,translation', [('ja', 'まず画面を録画します。'),
                                                 ('ar', 'سجل الشاشة أولاً.'),
                                                 ('fr', 'Enregistrez votre écran.')])
@pytest.mark.parametrize('mode', ['bilingual', 'translated', 'mono'])
def test_translation_metadata_reaches_language_sidecars(tmp_path, language, translation, mode):
    from vstudio import bilingual as B
    original = [dict(start=0, end=1, text='Record your screen.'),
                dict(start=1, end=2, text='Explain the idea.')]
    cs, _ = B.translate_cues(original, 'en', language, fix_terms=False, gl={}, call=lambda *a: (
        {'lines': [{'n': 1, 't': translation}]}, {'provider': 'test'}))
    shown = B.apply_mode(cs, mode)
    path = _cues(tmp_path / 'translated.json', [c.to_dict() for c in shown])
    sidecars = X.write_sidecars(P.profile('youtube'), path, str(tmp_path), 'clip')
    tracks = {row['lang']: srt_read(tmp_path / row['file']) for row in sidecars}
    assert set(tracks) == ({'en'} if mode == 'mono' else {'en', language})
    assert [c.text for c in tracks['en']] == (['Explain the idea.'] if mode == 'translated'
                                            else ['Record your screen.', 'Explain the idea.'])
    if mode != 'mono':
        assert [c.text for c in tracks[language]] == [translation]
        assert tracks[language][0].start == 0 and tracks[language][0].end == 1
    assert cs[0].meta == {'lang': 'en', 'alt_lang': language}  # transformations don't mutate input


def test_named_track_keeps_declared_language_and_mixed_timeline_order():
    cs = [Cue(0, 1, 'An older cue.'),
          Cue(1, 2, 'Explain.', '説明します。', {'lang': 'en', 'alt_lang': 'ja', 'style': {'fill': 'white'}}),
          Cue(2, 3, 'A final cue.')]
    tracks = X.caption_tracks(cs, P.profile('youtube'))
    assert [c.text for c in tracks['en']] == ['An older cue.', 'Explain.', 'A final cue.']
    named = X.caption_tracks({'ja': cs[1:]}, P.profile('youtube'))
    assert named['ja'][0].text == '説明します。'
    assert named['ja'][0].meta['style'] == {'fill': 'white'}
