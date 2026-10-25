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


@pytest.mark.parametrize('layout', ['contain', 'detail'])
def test_native_video_layout_preserves_source_and_fps(tmp_path, layout):
    src = str(tmp_path/'source.mp4')
    media.run(['ffmpeg','-y','-f','lavfi','-i',
        'color=red:s=320x180:r=30:d=2,drawbox=x=160:y=0:w=160:h=180:color=blue:t=fill',
        '-c:v','libx264','-pix_fmt','yuv420p',src])
    C = SimpleNamespace(VCROP={}, VEQ={}, VEQ_FILTER='', cache_dir=str(tmp_path),
        BOX_W=180, BOX_H=320, FPS=24, SUB_Y0=108, SUB_H=30, HDR=0,
        pal={'paper':(240,235,225)}, find_video=lambda n:src, vid_dirs=[str(tmp_path)])
    sh = dict(start=0,end=.4,tail=0,off=0,speed=2,motion='still')
    sh.update({'fit':'contain'} if layout=='contain' else {'detail_regions':[[160,0,160,180]]})
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
    else:
        assert a[40,35,0]>220 and a[40,145,2]>220
        assert a[230,90,2]>220 and a[230,90,0]<30
        assert np.all(a[120,90]>200)  # caption gap excludes both moving pictures
    changed = dict(sh,fit='cover'); changed.pop('detail_regions',None)
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
