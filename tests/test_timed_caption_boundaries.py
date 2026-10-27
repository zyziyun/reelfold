import copy
import pytest
from vstudio import subs as S


def words(text):
    return [dict(word=t, start=i*.4, end=(i+1)*.4) for i,t in enumerate(text.split())]


def test_sentence_boundary_and_word_clocks():
    pytest.importorskip('en_core_web_sm')
    ws=words('Show a concrete example. Before publishing, check the captions.')
    before=copy.deepcopy(ws)
    cues=S.cues_from_words(ws,max_chars=100,linger=0,fixes=False,language='en-US')
    assert [c.text for c in cues]==['Show a concrete example.','Before publishing, check the captions.']
    assert cues[1].start==ws[4]['start']
    assert cues[0].end==ws[3]['end']
    assert all(c.meta['lang']=='en-US' for c in cues)
    assert ws==before


def test_noun_phrases_and_real_pause_precedence():
    pytest.importorskip('en_core_web_sm')
    ws=words('Explain the main idea in your own words and show a concrete example.')
    cues=S.cues_from_words(ws,max_chars=18,linger=0,fixes=False,language='en')
    assert S.join_caption(c.text for c in cues)==S.join_caption(w['word'] for w in ws)
    assert all(S.text_width(c.text)<=18 for c in cues)
    for phrase in ('the main idea','your own words','a concrete example'):
        assert any(phrase in c.text for c in cues)
    ws=words('your own words')
    ws[2].update(start=2.,end=2.4)
    cues=S.cues_from_words(ws,max_chars=18,linger=0,fixes=False,language='en')
    assert [c.text for c in cues]==['your own','words']
    assert cues[1].start==2


def test_punctuation_cannot_push_a_phrase_over_width():
    pytest.importorskip('en_core_web_sm')
    cues=S.cues_from_words(words('A concrete example.'),max_chars=9,linger=0,fixes=False,language='en')
    assert all(S.text_width(c.text)<=9 for c in cues)
    assert S.join_caption(c.text for c in cues)=='A concrete example.'
