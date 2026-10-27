"""Explicit authored locales survive picture and caption export."""
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'workflows/photo-story/scripts'))
from photostory.ctx import Ctx

@pytest.mark.parametrize('locale,label', [('ja-JP','豆を量る'),('fr-FR','Peser le café'),('ko-KR','커피 준비')])
@pytest.mark.parametrize('platform', [None, 'youtube'])
def test_explicit_locale_survives_picture_and_cue_export(tmp_path, locale, label, platform):
    cfg=dict(__file__=str(tmp_path/'spec.py'), TTS={'language':locale}, TITLE_EN=label,
             TITLE_ZH='legacy translation', SECTIONS=['legacy'], SECTIONS_EN=[label])
    if platform: cfg['PLATFORM']=platform
    else: cfg['CANVAS']=(320,180)
    c=Ctx(SimpleNamespace(**cfg))
    assert c.shown(label)==label
    assert c.HEAD_MAIN==label and c.HEAD_SUB==''
    assert c.HEAD_SECTIONS==[label]
    assert c.sub_pair(label,'legacy translation')==(label,'')
    cue=c.export_cue(dict(start=3,end=4,en=label,zh='legacy translation'),offset=1).to_dict()
    assert cue==dict(start=2,end=3,text=label,meta={'lang':locale.lower()})


def test_voice_locale_override_and_explicit_legacy_selection(tmp_path):
    cfg=dict(__file__=str(tmp_path/'spec.py'),CANVAS=(320,180),TTS={'language':'en'},VOICE={'language':'ja-JP'})
    assert Ctx(SimpleNamespace(**cfg)).SUBS=='ja-jp'
    c=Ctx(SimpleNamespace(**cfg,SUBS='both'))
    assert c.TEXT_LANGUAGE is None and c.sub_pair('First','第二')==('First','第二')


def test_legacy_youtube_language_policy_unchanged(tmp_path):
    c=Ctx(SimpleNamespace(__file__=str(tmp_path/'spec.py'),PLATFORM='youtube',TTS={'language':'zh'},SUBS='both'))
    assert c.SUBS=='en'
    assert c.export_cue(dict(start=0,end=1,en='English',zh='中文')).to_dict()==dict(start=0,end=1,text='中文',alt='English')
