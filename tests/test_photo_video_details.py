"""Native moving-video layouts preserve overview, selected detail and time."""
import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from vstudio import media

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'workflows/photo-story/scripts'))
from photostory.shots import prep_video


@pytest.mark.parametrize('layout', ['contain', 'detail', 'region', 'caption-safe', 'caption-label'])
def test_native_video_layout_preserves_source_and_fps(tmp_path, layout):
    src = str(tmp_path/'source.mp4')
    media.run(['ffmpeg','-y','-f','lavfi','-i',
        'color=red:s=320x180:r=30:d=2,drawbox=x=160:y=0:w=160:h=180:color=blue:t=fill',
        '-c:v','libx264','-pix_fmt','yuv420p',src])
    C = SimpleNamespace(VCROP={}, VEQ={}, VEQ_FILTER='', cache_dir=str(tmp_path),
        BOX_W=180, BOX_H=320, FPS=24, SUB_Y0=108, SUB_H=30, HDR=0,
        pal={'paper':(240,235,225)}, find_video=lambda n:src, vid_dirs=[str(tmp_path)])
    if layout in ('caption-safe', 'caption-label'):
        C.spec = SimpleNamespace(LAYOUT=dict(video_caption_safe=True,
            caption_style='label' if layout == 'caption-label' else 'plain'))
        C.overlay_subs = True
    sh = dict(start=0,end=.4,tail=0,off=0,speed=2,motion='still')
    sh.update({'fit':'contain', 'source_region':[160,0,160,180]} if layout=='region' else
              {'fit':'contain'} if layout in ('contain', 'caption-safe', 'caption-label') else {'detail_regions':[[160,0,160,180]]})
    out = prep_video(C,sh,'source')
    info = media.probe(out)
    assert abs(float(info['fps'])-24)<.01
    assert abs(info['duration']-1)<.09
    data=subprocess.check_output([media.ffmpeg_bin(),'-v','error','-i',out,'-frames:v','1',
        '-pix_fmt','rgb24','-f','rawvideo','-'])
    a=np.frombuffer(data,dtype=np.uint8).reshape(320,180,3)
    if layout=='contain':
        assert a[160,30,0]>220 and a[160,150,2]>220
        assert np.all(a[10,90]>200)
    elif layout in ('caption-safe', 'caption-label'):
        assert np.all(a[108:138, :, :] > 200)
        assert np.any((a[:, :, 0] > 220) & (a[:, :, 2] < 30))
        assert np.any((a[:, :, 2] > 220) & (a[:, :, 0] < 30))
        if layout == 'caption-label':
            subject = (a[:, :, 0] > 220) & (a[:, :, 2] < 30)
            assert np.where(subject)[0].min() == 144
            C.spec.LAYOUT['caption_style'] = 'plain'
            assert prep_video(C, sh, 'source') != out
            C.spec.LAYOUT['caption_style'] = 'label'
        C.spec.LAYOUT['video_caption_safe'] = False
        assert prep_video(C, sh, 'source') != out
        C.spec.LAYOUT['video_caption_safe'] = True
    elif layout == 'region':
        blue = (a[:,:,2] > 220) & (a[:,:,0] < 30)
        ys, xs = np.where(blue)
        assert len(xs) > 15000
        assert ys.min() >= 138 and ys.max() < 320
        assert not np.any((a[:,:,0] > 220) & (a[:,:,2] < 30))
        assert np.all(a[120,90] > 200)
        assert xs.max() - xs.min() > 140  # complete region fits without extra portrait crop
    else:
        assert a[40,35,0]>220 and a[40,145,2]>220
        assert a[230,90,2]>220 and a[230,90,0]<30
        assert np.all(a[120,90]>200)  # caption gap excludes both moving pictures
    C.FPS = 30
    new_fps = prep_video(C,sh,'source')
    assert new_fps != out and float(media.probe(new_fps)['fps']) == 30
    C.pal['paper'] = (10,20,30)
    new_paper = prep_video(C,sh,'source')
    assert new_paper != new_fps
    st = os.stat(src)
    os.utime(src, ns=(st.st_atime_ns,st.st_mtime_ns+1000000))
    assert prep_video(C,sh,'source') != new_paper
    changed = dict(sh,fit='cover'); changed.pop('detail_regions',None); changed.pop('source_region',None)
    assert prep_video(C,changed,'source') != out


def test_video_layout_rejects_conflicting_crop_before_render(tmp_path):
    from vstudio import clipkit
    geo=dict(canvas=(180,320),vertical=True,main=(0,0,180,320),camera=None)
    with pytest.raises(ValueError,match='Caption band'):
        clipkit.detail_geometry(geo,(320,180),[[0,0,100,100]],caption_band=(300,315))

@pytest.mark.parametrize('source,regions,extra', [
    ('p0001', [[0,0,100,100]], {}),
    ('vsource', [[-1,0,100,100]], {}),
    ('vsource', [[0,0,float('inf'),100]], {}),
    ('vsource', [], {}),
    ('vsource', [[0,0,100,100]], {'z':2}),
])
def test_planner_rejects_invalid_detail_options(source, regions, extra):
    from vstudio.project.adapters.photostory import spec_error
    options=dict(detail_regions=regions,**extra)
    text=f'SCRIPT=[(0,[("Action","动作")],[({source!r},1,"still",{options!r})])]'
    assert spec_error(text)

@pytest.mark.parametrize('canvas', [(180,320), (240,180)])
def test_video_zoom_magnifies_relative_to_fitted_crop(tmp_path, canvas):
    """A requested 2x detail must double a source marker on either canvas."""
    src = str(tmp_path/'marker.mp4')
    media.run(['ffmpeg','-y','-f','lavfi','-i',
        'color=black:s=640x360:r=24:d=1,drawbox=x=310:y=170:w=20:h=20:color=white:t=fill',
        '-c:v','libx264','-pix_fmt','yuv420p',src])
    w,h = canvas
    C = SimpleNamespace(VCROP={}, VEQ={}, VEQ_FILTER='', cache_dir=str(tmp_path),
        BOX_W=w, BOX_H=h, FPS=24, SUB_Y0=h-30, SUB_H=30, HDR=0,
        pal={'paper':(240,235,225)}, find_video=lambda n:src, vid_dirs=[str(tmp_path)])
    sizes=[]
    for zoom in (1,2):
        out=prep_video(C,dict(start=0,end=.3,tail=0,off=0,speed=1,motion='still',z=zoom),'marker')
        data=subprocess.check_output([media.ffmpeg_bin(),'-v','error','-i',out,'-frames:v','1',
            '-pix_fmt','rgb24','-f','rawvideo','-'])
        frame=np.frombuffer(data,dtype=np.uint8).reshape(h,w,3)
        ys,xs=np.where(frame[:,:,0]>200)
        sizes.append((xs.max()-xs.min()+1,ys.max()-ys.min()+1))
    for axis in (0,1):
        assert abs(sizes[1][axis]/sizes[0][axis]-2)<.2, sizes


@pytest.mark.parametrize('region,extra', [
    ([-1,0,100,100], {}), ([0,0,0,100], {}), ([0,0,100], {}),
    ([0,0,100,100], {'fit':'cover'}),
    ([0,0,100,100], {'detail_regions':[[0,0,100,100]]}),
    ([0,0,100,100], {'c':(.5,.5)}),
])
def test_planner_rejects_invalid_source_region(region, extra):
    from vstudio.project.adapters.photostory import spec_error
    options=dict(fit='contain', source_region=region, **{k:v for k,v in extra.items() if k!='fit'})
    options.update(extra)
    assert spec_error(f'SCRIPT=[(0,[("Cup","杯")],[("vsource",1,"still",{options!r})])]')


@pytest.mark.parametrize("canvas", [(180,320), (320,180)])
def test_source_region_bounds_and_caption_geometry(canvas):
    from vstudio import clipkit as C
    W,H=canvas
    geo=dict(canvas=canvas,vertical=H>W,main=(0,0,W,H),camera=None)
    with pytest.raises(ValueError,match='outside'):
        C.region_geometry(geo,(320,180),[250,0,100,180])
    with pytest.raises(ValueError,match='Caption band'):
        C.region_geometry(geo,(320,180),[0,0,100,100],(0,H))
    for band in [(0,30),(H-30,H),(H//2,H//2+30)]:
        g=C.region_geometry(geo,(320,180),[0,0,100,100],band)
        x,y,w,h=g['main']
        assert y+h <= band[0] or y >= band[1]
        assert 0 <= x < x+w <= W and 0 <= y < y+h <= H
        assert abs(w-h) <= 1


@pytest.mark.parametrize('band', [(30, 60), (240, 270)])
def test_contained_label_and_subject_stay_adjacent(band):
    from vstudio import clipkit as C
    geo = dict(canvas=(180, 320), vertical=True, main=(0, 0, 180, 320), camera=None)
    region = [0, 0, 320, 180]
    centered = C.region_geometry(geo, (320, 180), region, band)
    adjacent = C.region_geometry(geo, (320, 180), region, band, caption_adjacent=True)
    x, y, w, h = adjacent['main']
    assert (w, h) == centered['main'][2:]
    assert adjacent['source_region'] == centered['source_region']
    margin = max(2, int(180 * .035))
    gap = y - band[1] if band[0] < 160 else band[0] - (y + h)
    assert gap == margin

@pytest.mark.parametrize('mode,captions,reserved', [
    ('music', False, False), ('music', 'all', True), ('narration', False, True),
])
@pytest.mark.parametrize('region', [False, True])
def test_contained_video_reserves_only_active_music_captions(tmp_path, mode, captions, reserved, region):
    """Disabling music captions must not leave a phantom band in portrait footage."""
    src = str(tmp_path/'portrait.mp4')
    media.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=red:s=180x320:r=30:d=1',
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', src])
    C = SimpleNamespace(MODE=mode, spec=SimpleNamespace(
        LAYOUT=dict(video_caption_safe=True, caption_style='label'), MUSIC=dict(captions=captions)),
        VCROP={}, VEQ={}, VEQ_FILTER='', cache_dir=str(tmp_path), BOX_W=180, BOX_H=320,
        FPS=30, SUB_Y0=210, SUB_H=40, HDR=0, overlay_subs=True,
        pal={'paper':(240,235,225)}, find_video=lambda n:src, vid_dirs=[str(tmp_path)])
    sh = dict(start=0, end=.2, tail=0, off=0, speed=1, motion='still', fit='contain')
    if region:
        sh['source_region'] = [0, 0, 180, 320]
    out = prep_video(C, sh, 'portrait')
    raw = subprocess.check_output([media.ffmpeg_bin(), '-v', 'error', '-i', out,
        '-frames:v', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    frame = np.frombuffer(raw, dtype=np.uint8).reshape(320, 180, 3)
    red = (frame[:,:,0] > 220) & (frame[:,:,2] < 30)
    if reserved:
        assert not red[210:250].any()
    else:
        # Region layouts retain their documented small perimeter margin,
        # but the disabled caption band must contain picture, not a matte gap.
        assert red[210:250, 20:-20].all()
        assert red.mean() > (.85 if region else .95)


def test_side_label_video_preserves_full_source_without_changing_wide_shots(tmp_path):
    from photostory.layouts import plan
    src = str(tmp_path/'narrow.mp4')
    media.run(['ffmpeg', '-y', '-f', 'lavfi', '-i',
               'color=red:s=100x200:r=30:d=1,drawbox=x=50:y=0:w=50:h=200:color=blue:t=fill',
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', src])
    C = SimpleNamespace(MODE='music', spec=SimpleNamespace(
        LAYOUT=dict(video_caption_safe=True, caption_style='label'), MUSIC=dict(captions='all')),
        VCROP={}, VEQ={}, VEQ_FILTER='', cache_dir=str(tmp_path), BOX_W=320, BOX_H=180,
        W=320, H=180, SAFE=(10,10,310,170), CAP=(10,120,310,150), FPS=30,
        SUB_Y0=120, SUB_H=30, HDR=0, overlay_subs=True,
        pal={'paper':(240,235,225)}, find_video=lambda n:src if n == 'narrow' else None, vid_dirs=[str(tmp_path)])
    shot = dict(src='vnarrow', start=0, end=.2, tail=0, off=0, speed=1, fit='contain')
    wide = dict(shot, fit='cover', start=.2, end=.4)
    timeline = SimpleNamespace(shots=[shot,wide], subs=[])
    plan(C,timeline)
    x,y,w,h = shot['_video_box']
    assert h == 160 and w == 80
    assert shot['_caption_context'].CAP[2] < x
    assert C.CAP == (10,120,310,150) and '_video_box' not in wide
    out = prep_video(C,shot,'narrow')
    raw = subprocess.check_output([media.ffmpeg_bin(), '-v', 'error', '-i', out,
        '-frames:v', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    frame = np.frombuffer(raw,dtype=np.uint8).reshape(180,320,3)
    assert frame[y+5,x+5,0] > 220 and frame[y+h-5,x+w-5,2] > 220
    assert np.all(frame[120:150,10:shot['_caption_context'].CAP[2]] > 200)
    # Film matte follows the canvas palette, not the collage paper colour.
    C.pal['ground'] = (22, 18, 15)
    dark = prep_video(C,shot,'narrow')
    assert dark != out
    raw = subprocess.check_output([media.ffmpeg_bin(), '-v', 'error', '-i', dark,
        '-frames:v', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    dark_frame = np.frombuffer(raw,dtype=np.uint8).reshape(180,320,3)
    assert np.max(np.abs(dark_frame[30,30].astype(int) - np.array([22,18,15]))) < 5
    assert dark_frame[y+5,x+5,0] > 220 and dark_frame[y+h-5,x+w-5,2] > 220
    C.pal['paper'] = (1, 2, 3)
    assert prep_video(C,shot,'narrow') == dark
    # The old reserved-band cache must not be reused for the new geometry.
    old = dict(shot); old.pop('_video_box')
    assert prep_video(C,old,'narrow') != out
    for change in ('disabled','title','transition'):
        fresh = dict(old); fresh.pop('_caption_context')
        C.spec.LAYOUT['video_caption_side'] = change != 'disabled'
        fresh['trd'] = .4 if change == 'transition' else 0
        cues = [dict(start=0,end=.2,style='title')] if change == 'title' else []
        plan(C,SimpleNamespace(shots=[fresh],subs=cues))
        assert '_video_box' not in fresh


def test_detail_video_removes_disabled_caption_gap_and_invalidates_cache(tmp_path):
    src = str(tmp_path/'detail.mp4')
    media.run(['ffmpeg','-y','-f','lavfi','-i',
        'color=red:s=320x180:r=30:d=1,drawbox=x=160:y=0:w=160:h=180:color=blue:t=fill',
        '-c:v','libx264','-pix_fmt','yuv420p',src])
    C = SimpleNamespace(MODE='music',spec=SimpleNamespace(
        LAYOUT={}, MUSIC=dict(captions='all')), VCROP={},VEQ={},VEQ_FILTER='',
        cache_dir=str(tmp_path),BOX_W=180,BOX_H=320,FPS=30,SUB_Y0=110,SUB_H=40,HDR=0,
        overlay_subs=True,pal={'paper':(240,235,225)},find_video=lambda n:src,vid_dirs=[str(tmp_path)])
    shot=dict(start=0,end=.2,tail=0,off=0,speed=1,detail_regions=[[160,0,160,180]])
    def render():
        path=prep_video(C,shot,'detail')
        raw=subprocess.check_output([media.ffmpeg_bin(),'-v','error','-i',path,
            '-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'])
        return path,np.frombuffer(raw,dtype=np.uint8).reshape(320,180,3)
    before,active=render()
    assert np.all(active[110:150,:,:] > 200)
    C.spec.MUSIC['captions']=False
    after,disabled=render()
    assert before != after
    blue=(disabled[:,:,2]>220)&(disabled[:,:,0]<30)
    assert blue[130:150,60:120].all()
    # Both the complete overview and the verified enlarged detail survive.
    assert ((disabled[:,:,0]>220)&(disabled[:,:,2]<30)).any()
    assert blue.sum() > ((active[:,:,2]>220)&(active[:,:,0]<30)).sum()
