"""Declared English captions use the speech runtime's existing phrase parser."""
import pytest
from vstudio import subs, textbreak, platform as P, export as X

TEXT = ('Record your screen first, then explain the main idea in your own words '
        'and show a concrete example. Before publishing, check the captions '
        'and listen to the entire recording.')


def test_other_languages_do_not_load_english_parser(monkeypatch):
    textbreak.phrase_spans.cache_clear()
    def unexpected():
        raise AssertionError('English parser should not be used')
    monkeypatch.setattr(textbreak, '_english_parser', unexpected)
    assert textbreak.phrase_spans('自己的话', 'zh') == ()
    assert textbreak.phrase_spans('vos propres mots', 'fr') == ()
    assert textbreak.phrase_spans('your own words', None) == ()


def test_real_english_phrases_survive_caption_wrapping():
    pytest.importorskip('en_core_web_sm')
    textbreak.phrase_spans.cache_clear()
    chunks = subs.caption_chunks(TEXT, 18, max_lines=1, language='en-US')
    assert subs.join_caption(chunks) == TEXT
    assert all(subs.text_width(c) <= 18 for c in chunks)
    for phrase in ('your own words', 'a concrete example', 'the entire recording'):
        assert any(phrase in c for c in chunks), chunks


def test_highlights_and_overwide_phrases_keep_text():
    pytest.importorskip('en_core_web_sm')
    text = 'Explain 【the main idea】 in your own words.'
    chunks = subs.caption_chunks(text, 13, max_lines=1, language='en')
    assert subs.strip_markup(subs.join_caption(chunks)) == subs.strip_markup(text)
    assert any('the main idea' in subs.strip_markup(c) for c in chunks)
    small = subs.caption_chunks(text, 5, max_lines=1, language='en')
    assert subs.strip_markup(subs.join_caption(small)) == subs.strip_markup(text)
    assert all(subs.text_width(subs.strip_markup(c)) <= 5 for c in small)


def test_export_fit_uses_declared_language():
    pytest.importorskip('en_core_web_sm')
    p = P.profile('instagram', use_persona=False)
    cues = X.fit_cues(p, [subs.Cue(0, 16, TEXT, meta={'lang': 'en'})])
    assert subs.join_caption(c.text for c in cues) == TEXT
    assert cues[0].start == 0 and cues[-1].end == 16
    lines = [line for c in cues for line in P.fit_text_size(p, c.text, language=c.meta['lang'])['lines']]
    for phrase in ('your own words', 'a concrete example', 'the entire recording'):
        assert any(phrase in line for line in lines), lines


def test_translation_line_uses_its_own_declared_language(monkeypatch):
    import numpy as np
    pytest.importorskip('en_core_web_sm')
    drawn = []
    original = X._lines_layer
    def record(lines, *args, **kwargs):
        drawn.append(lines)
        return original(lines, *args, **kwargs)
    monkeypatch.setattr(X, '_lines_layer', record)
    p = P.profile('instagram', use_persona=False)
    cue = subs.Cue(0, 12, '用自己的话解释，并展示一个例子。', TEXT,
                   {'lang': 'zh', 'alt_lang': 'en'})
    overlay = X.caption_overlay(p, [cue], 30)
    overlay(180, 6, np.full((p.h, p.w, 3), 50, dtype=np.uint8))
    assert subs.join_caption(drawn[-1]) == TEXT
    for phrase in ('your own words', 'a concrete example', 'the entire recording'):
        assert any(phrase in line for line in drawn[-1]), drawn[-1]
