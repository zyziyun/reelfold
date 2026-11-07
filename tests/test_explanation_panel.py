"""An explicit information panel must never paint outside its reserved region."""
import numpy as np
import pytest
from vstudio.project import outfx


@pytest.mark.parametrize('size', [(360,640), (720,1280), (640,360)])
def test_panel_preserves_source_pixels_and_is_seek_safe(size):
    w,h=size
    box=[.05,.6,.9,.35] if h>w else [.5,.05,.45,.9]
    params,warnings=outfx.validate('explanation-card',dict(title='条件',kind='takeaway',items=['仍有选择'],panel_box=box))
    assert not warnings
    layer=outfx.make_layer(dict(effect='explanation-card',params=params),w,h)
    rng=np.random.default_rng(1);base=rng.integers(0,256,(h,w,3),dtype=np.uint8)
    x,y,bw,bh=box;x0,y0,x1,y1=round(x*w),round(y*h),round((x+bw)*w),round((y+bh)*h)
    outside=np.ones((h,w),bool);outside[y0:y1,x0:x1]=False
    frames=[]
    for t in (0,1.5,.4,1.5,3):
        frame=base.copy();layer.draw(frame,t,3);frames.append(frame)
        assert np.array_equal(frame[outside],base[outside])
    assert np.array_equal(frames[0],base)
    assert np.array_equal(frames[-1],base)
    assert np.array_equal(frames[1],frames[3])
    assert not np.array_equal(frames[1],base)


@pytest.mark.parametrize('box', [[0,0,2,1],[0,0,float('nan'),1],[0,0,0,1],[True,0,.5,.5],[0,0,.5]])
def test_invalid_panel_fails_instead_of_falling_back_to_fullframe(box):
    with pytest.raises(ValueError,match='panel_box'):
        outfx.validate('explanation-card',dict(title='x',items=['y'],panel_box=box))
    with pytest.raises(ValueError,match='panel_box'):
        outfx.validate('explanation-card',dict(panel_box=box),partial=True)


@pytest.mark.parametrize('size', [(1080,1920), (2160,3840)])
def test_tiny_panel_cannot_hide_unreadable_type_in_high_resolution(size):
    layer=outfx.make_layer(dict(effect='explanation-card',params=dict(
        title='要点',kind='takeaway',items=['保留选择'],panel_box=[.05,.65,.2,.1])),*size)
    with pytest.raises(ValueError,match='text does not fit'):
        layer.setup()


def test_enlarging_panel_keeps_the_same_copy_readable():
    layer=outfx.make_layer(dict(effect='explanation-card',params=dict(
        title='要点',kind='takeaway',items=['保留选择'],panel_box=[.05,.6,.9,.3])),1080,1920)
    layer.setup()
    assert layer.panel.texts[0].height >= 48


def test_reserved_shallow_panel_uses_its_height_without_shrinking_type():
    layer = outfx.make_layer(dict(effect='explanation-card', params=dict(
        title='先保存，再导出', kind='chain', items=['保存草稿', '导出视频'],
        panel_box=[.06, .12, .82, 250/1920])), 1080, 1920)
    layer.setup()
    assert all(t.height >= 48 for t in layer.panel.texts)
    base = np.full((1920, 1080, 3), 90, np.uint8)
    frame = base.copy()
    layer.draw(frame, 1.5, 4)
    x0, y0, x1, y1 = layer.panel_rect
    outside = np.ones(base.shape[:2], bool)
    outside[y0:y1, x0:x1] = False
    assert np.array_equal(frame[outside], base[outside])
    assert not np.array_equal(frame[y0:y1, x0:x1], base[y0:y1, x0:x1])
