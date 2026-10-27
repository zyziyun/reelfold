"""「加中文字幕」 means Chinese captions: the request sets the caption language (not the speech language), the export
translates English speech into it, and when no translation model answers the captions stay as spoken and QC says so
(never silently English)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from vstudio import bilingual as B  # noqa: E402
from vstudio.batch import stages as ST  # noqa: E402
from vstudio.batch.qc import run_gates  # noqa: E402
from vstudio.intake import rules as R  # noqa: E402
from vstudio.subs import Cue  # noqa: E402


def test_the_request_names_the_caption_language():
    for text, lang in (("帮我剪一下，加中文字幕", "zh"), ("add Chinese captions please", "zh"),
                       ("字幕用英文", "en"), ("English subtitles", "en")):
        it = R.parse_prompt(text)
        assert it.get("subtitle_lang") == lang, (text, it)
        assert "language" not in it, (text, it)                 # the speech language is not what she named
    assert R.subtitles_of("中英双语字幕") == dict(subtitles="bilingual")
    assert "subtitle_lang" not in R.parse_prompt("去掉停顿，加字幕")


class Ctx:
    def __init__(self, params, tmp):
        self.params, self.spec, self.tmp, self.logs = params, {}, tmp, []

    def log(self, m):
        self.logs.append(m)

    def path(self, *a):
        return os.path.join(self.tmp, *a)


CUES = [dict(start=0.0, end=2.0, text="You record once."), dict(start=2.0, end=4.0, text="You cut it into clips.")]


def test_english_speech_gets_chinese_captions(tmp_path, monkeypatch):
    def fake(cues, src, tgt, **kw):
        assert (src, tgt) == ("en", "zh")
        zh = {"You record once.": "你只录一次。", "You cut it into clips.": "你把它剪成很多条。"}
        return [Cue(c["start"], c["end"], c["text"], zh[c["text"]], {}) for c in cues], {}
    monkeypatch.setattr(B, "translate_cues", fake)
    out, rep = ST.caption_language(Ctx(dict(subtitle_lang="zh", language="en"), str(tmp_path)), CUES)
    assert [c["text"] for c in out] == ["你只录一次。", "你把它剪成很多条。"]
    assert rep["mode"] == "translated" and rep["translated"] == 2
    out, rep = ST.caption_language(Ctx(dict(subtitle_lang="zh", subtitles="bilingual", language="en"), str(tmp_path)), CUES)
    assert [(c["text"], c["alt"]) for c in out][0] == ("You record once.", "你只录一次。")
    same, rep = ST.caption_language(Ctx(dict(subtitle_lang="en", language="en"), str(tmp_path)), CUES)
    assert same is CUES and rep["translated"] == 0                # already in her language: nothing to do


def test_no_model_keeps_the_speech_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "translate_cues", lambda cues, s, t, **kw: (
        [Cue(c["start"], c["end"], c["text"], "", {}) for c in cues], dict(error="no translation provider configured")))
    ctx = Ctx(dict(subtitle_lang="zh", language="en"), str(tmp_path))
    out, rep = ST.caption_language(ctx, CUES)
    assert out is CUES and rep["translated"] == 0 and "no translation provider" in rep["error"]
    assert any("asked for zh" in m for m in ctx.logs)
    man = tmp_path / "manifest.json"
    man.write_text('{"exports": []}')
    qc = run_gates(dict(id="j", params={}), {}, dict(export=dict(manifest=str(man), exports=[], caption_lang=rep)))
    assert any("captions asked in zh, made in en" in w for w in qc["warnings"]), qc["warnings"]


@pytest.mark.parametrize("complete", [False, True])
def test_translation_coverage_is_visible_in_export_qc(tmp_path, monkeypatch, complete):
    # Exercise real translation parsing and caption-file serialization; only the
    # provider response is fixed. One missing line must not look fully translated.
    import json
    lines = [{'n': 1, 't': 'Vous enregistrez une fois.'}]
    if complete:
        lines.append({'n': 2, 't': 'Vous découpez des clips.'})
    monkeypatch.setattr(B, '_llm_call', lambda *a, **kw: lambda *a: (
        {'lines': lines}, {'provider': 'test'}))
    source = tmp_path / 'cues.json'
    source.write_text(json.dumps({'cues': CUES + [dict(start=4, end=5, text='')]}))
    for mode in ('translated', 'bilingual'):
        ctx = Ctx(dict(subtitle_lang='fr', language='en', subtitles=mode), str(tmp_path))
        ctx.inputs = {'compose': {'cues': str(source)}}
        path = ST.caption_cues(ctx)
        saved = json.loads(open(path).read())['cues']
        assert len(saved) == 3
        if not complete:
            assert saved[1]['text'] == CUES[1]['text']
        assert ctx.caption_lang['missing'] == (0 if complete else 1)
        assert ctx.caption_lang['of'] == 2  # blank cues need no translation
        assert any('1 of 2' in m for m in ctx.logs) == (not complete)
        man = tmp_path / 'manifest.json'
        man.write_text('{"exports": []}')
        qc = run_gates(dict(id='j', params={}), {}, dict(export=dict(
            manifest=str(man), exports=[], caption_lang=ctx.caption_lang)))
        checks = [c for c in qc['checks'] if c['name'] == 'caption-language']
        if complete:
            assert checks == []
        else:
            assert len(checks) == 1 and not checks[0]['ok']
            assert '1 of 2' in checks[0]['reason'] and 'fr' in checks[0]['reason']
