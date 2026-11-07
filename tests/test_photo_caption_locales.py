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


@pytest.mark.parametrize('platform', [None, 'tiktok', 'youtube'])
@pytest.mark.parametrize('mode,captions', [('music', False), ('music', 'all'), ('narration', False)])
def test_lower_shot_labels_avoid_only_visible_caption_bands(tmp_path, platform, mode, captions):
    cfg = dict(__file__=str(tmp_path/'spec.py'), MODE=mode, MUSIC=dict(captions=captions),
               LOOK='cinema', CANVAS=(360,640), LAYOUT=dict(caption_y=.5, sub=.15))
    if platform:
        cfg['PLATFORM'] = platform
        cfg.pop('CANVAS')
    c = Ctx(SimpleNamespace(**cfg))
    if mode == 'music' and captions is False:
        assert c.LAB_BOT == min(c.BOX_H, c.SAFE[3] - c.HDR)
    elif platform:
        assert c.LAB_BOT <= c.SUB_Y0 - c.HDR
    else:
        assert c.LAB_BOT == c.BOX_H - c.SUB_H


@pytest.mark.parametrize('text', ['Nozzle lift', 'Inspect the equipment before starting the next process', '喷嘴抬升'])
@pytest.mark.parametrize('platform', ['tiktok', 'youtube'])
def test_informational_shot_label_is_a_bounded_readable_plate(tmp_path, text, platform):
    import numpy as np
    from photostory.subtitles import make_label
    c = Ctx(SimpleNamespace(__file__=str(tmp_path/'spec.py'), PLATFORM=platform,
        MODE='music', MUSIC=dict(captions=False), LOOK='cinema', SUBS='both',
        LAYOUT=dict(caption_style='label', sub=.18)))
    # Keep the text under test independent of platform translation policy.
    c.shown = lambda value: value
    plate = make_label(c, text)
    assert 1 < plate.shape[1] <= c.CAP[2] - c.CAP[0]
    assert 1 < plate.shape[0] <= c.SUB_H
    # Dark opaque backing keeps white text readable over bright moving sources.
    opaque_dark = (plate[:,:,3] > 204) & (plate[:,:,:3].max(axis=2) < 51)
    assert opaque_dark.mean() > .4
    assert np.any((plate[:,:,:3].min(axis=2) > 204) & (plate[:,:,3] > 204))
