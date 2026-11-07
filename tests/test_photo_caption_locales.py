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


@pytest.mark.parametrize('palette,expected', [({}, (214,198,168)),
    ({'sub_en': '#f8f9fa'}, (248,249,250)), ({'sub_en': (70,180,230)}, (70,180,230))])
def test_music_title_respects_authored_colour(tmp_path, palette, expected):
    import numpy as np
    from photostory.subtitles import make_title_text
    c = Ctx(SimpleNamespace(__file__=str(tmp_path/'spec.py'), PLATFORM='youtube',
        MODE='music', MUSIC=dict(captions='title'), LOOK='cinema', PALETTE=palette,
        TITLE_SHADOW=0, TITLE_GLOW=0))
    rendered = make_title_text(c, 'Northline', '')
    solid = rendered[:,:,3] > 250
    assert solid.any()
    assert np.any(np.all(rendered[:,:,:3][solid] == np.array(expected), axis=1))


@pytest.mark.parametrize('platform', ['youtube', 'tiktok', 'xiaohongshu'])
def test_commercial_roles_have_distinct_safe_geometry(tmp_path, platform):
    import numpy as np
    from photostory.subtitles import title_context, make_title_text
    from photostory.music import MusicTimeline
    c = Ctx(SimpleNamespace(__file__=str(tmp_path/'spec.py'), PLATFORM=platform,
        MODE='music', MUSIC=dict(grid='seconds', length=9, captions='title',
            text_roles={0:'headline',1:'statement',2:'label'}),
        SECTIONS=['Brand'], SCRIPT=[(0,[('Make the next step clear','让下一步清晰可见')],
            [('p0',3,'still',{})]) for _ in range(3)], LOOK='cinema',
        LAYOUT=dict(header=0,overlay_subs=True), TITLE_SHADOW=0, TITLE_GLOW=0))
    timeline=MusicTimeline(c)
    assert [s['text_role'] for s in timeline.subs] == ['headline','statement','label']
    original=(c.SUB_Y0,c.SUB_H,c.ZH_SIZE)
    contexts=[title_context(c,s['text_role']) for s in timeline.subs]
    assert contexts[0].ZH_SIZE > contexts[1].ZH_SIZE > contexts[2].ZH_SIZE
    assert len({cc.SUB_Y0 for cc in contexts}) == 3
    for cc in contexts:
        assert c.SAFE[1] <= cc.SUB_Y0 < cc.SUB_Y0+cc.SUB_H <= c.SAFE[3]
        rgba=make_title_text(cc,'Make the next step clear','让下一步清晰可见')
        ys,xs=np.nonzero(rgba[:,:,3]>200)
        assert len(xs)>0
        assert xs.min() >= c.SAFE[0] and xs.max() < c.SAFE[2]
        assert ys.min()>0 and ys.max()<cc.SUB_H-1
    assert (c.SUB_Y0,c.SUB_H,c.ZH_SIZE)==original


@pytest.mark.parametrize('roles', [{0:'unknown'},{2:'headline'},{'0':'label'},{0:[]},[]])
def test_invalid_music_role_reports_authored_setting(tmp_path, roles):
    from photostory.music import MusicTimeline
    c=Ctx(SimpleNamespace(__file__=str(tmp_path/'spec.py'), MODE='music',
        MUSIC=dict(grid='seconds',length=3,text_roles=roles),SECTIONS=['A'],
        SCRIPT=[(0,[('Hello','你好')],[('p0',3,'still',{})])]))
    with pytest.raises(ValueError,match='MUSIC.text_roles'):
        MusicTimeline(c)


@pytest.mark.parametrize('platform', ['youtube', 'tiktok', 'xiaohongshu'])
@pytest.mark.parametrize('text', ['\n'.join(['A separate authored line']*12),
                                 '超长的品牌宣传文字需要完整显示不能截断'*40])
def test_oversized_commercial_copy_fails_before_silent_clipping(tmp_path, platform, text):
    from photostory.subtitles import title_context, make_title_text
    c=Ctx(SimpleNamespace(__file__=str(tmp_path/'spec.py'),PLATFORM=platform,
        LOOK='cinema',TTS={'language':'en'},TEXT_LANGUAGE='en'))
    c.sub_pair=lambda en, zh:(en,zh)
    with pytest.raises(ValueError,match='Shorten the copy or split'):
        make_title_text(title_context(c,'headline'),text,'')
