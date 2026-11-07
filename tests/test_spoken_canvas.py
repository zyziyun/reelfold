"""Target-aware planning uses verified fit margins and the real export renderer."""
import json
import subprocess

import cv2
import numpy as np
import pytest

from vstudio import export, platform, spoken
from vstudio.batch import stages
from vstudio.batch.recipes import Ctx


CUES = [dict(start=i, end=i+1, text='先保存草稿，再导出视频。') for i in range(8)]
BEAT = dict(**{'from': 3, 'to': 5}, kind='chain', title='操作顺序',
            items=['保存', '导出'], evidence='先保存草稿，再导出视频。', panel='top')


def test_margin_geometry_excludes_source_and_reserved_bands():
    p = platform.profile('tiktok', 'vertical', use_persona=False)
    for captions in (False, True):
        canvas = spoken.canvas_context(p, (1920, 1080), 'letterbox', captions)
        assert 'top' in canvas['panels']
        for x, y, w, h in canvas['panels'].values():
            assert (y+h)*p.h <= (p.h-p.w*1080/1920)/2 or y*p.h >= (p.h+p.w*1080/1920)/2
            if captions:
                _, a, _, b = platform.caption_box(p)
                assert (y+h)*p.h <= a or y*p.h >= b
    assert not spoken.canvas_context(p, (1920, 1080), 'face')['panels']
    assert not spoken.canvas_context(p, (1080, 1920), 'letterbox')['panels']


@pytest.mark.parametrize('panel', ['made-up', 'top', ['top']])
def test_unavailable_panel_does_not_fall_back_to_covering_source(panel):
    with pytest.raises(ValueError, match='panel'):
        spoken.validate(dict(beats=[dict(BEAT, panel=panel)]), CUES, 8,
                        canvas=dict(panels={}))


def test_finish_routes_distinct_plans_to_real_target_exports(tmp_path, monkeypatch):
    monkeypatch.setenv('VSTUDIO_DEFAULT_PERSONA', '1')
    source = tmp_path/'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'color=c=blue:s=320x180:r=10:d=8', '-c:v', 'libx264', str(source)], check=True)
    cues = tmp_path/'cues.json'; cues.write_text(json.dumps(CUES))
    targets = ['youtube:horizontal', 'tiktok:vertical']
    params = dict(platforms=targets, layout='letterbox', captions=False)
    ctx = Ctx(dict(params=params), {}, str(tmp_path),
              dict(compose=dict(master=str(source), cues=str(cues), duration=8)), str(tmp_path))
    real_plan = spoken.plan
    seen = []
    def local_plan(*args, **kwargs):
        canvas = kwargs['canvas']; seen.append(canvas['target'])
        def model(_task, system, prompt, **kw):
            assert 'OUTPUT CANVAS' in prompt
            return dict(json=dict(beats=[BEAT] if canvas['panels'] else []))
        return real_plan(*args, **kwargs, complete=model)
    monkeypatch.setattr(spoken, 'plan', local_plan)
    finished = stages.run_finish(ctx)
    assert seen == targets
    assert finished['effects_by_target'][targets[0]] == []
    effect = finished['effects_by_target'][targets[1]][0]
    assert effect['params']['panel_box']
    from vstudio.project import outfx
    with pytest.raises(ValueError, match='aspect changed'):
        outfx.make_layer(effect, 1920, 1080).setup()
    result = export.export(str(source), targets, out_dir=str(tmp_path/'exports'),
                           effects_by_target=finished['effects_by_target'],
                           mode='letterbox', captions=False, watermark=False,
                           encoder='libx264', preset='ultrafast')
    for entry in result['exports']:
        cap = cv2.VideoCapture(str(tmp_path/'exports'/entry['file']))
        cap.set(cv2.CAP_PROP_POS_MSEC, 4500)
        ok, frame = cap.read(); cap.release()
        assert ok
        h, w = frame.shape[:2]
        # The entire centre remains the blue source in both target versions.
        assert frame[h//2, w//2, 0] > 230
        assert max(frame[h//2, w//2, 1:]) < 30
        if entry['platform'] == 'tiktok':
            x, y, pw, ph = effect['params']['panel_box']
            panel = frame[round(y*h):round((y+ph)*h), round(x*w):round((x+pw)*w)]
            assert np.mean(panel) > 150
    saved = json.loads((tmp_path/'editorial-plan.json').read_text())
    assert set(saved['targets']) == set(targets)
    from vstudio.project import outputs
    monkeypatch.setattr(outputs, '_owner', lambda d: (d, 'project'))
    rows = [dict(id=e['file'], file=str(tmp_path/'exports'/e['file']), platform=e['platform'],
                 orientation=e['orientation'], _params=params,
                 _rows=dict(compose=dict(out=ctx.inputs['compose']), finish=dict(out=finished)))
            for e in result['exports']]
    monkeypatch.setattr(outputs, '_project_outputs', lambda *a, **k: rows)
    for row in rows:
        record = outputs.resolve(str(tmp_path), row['id'])
        assert record['baseline_effects'] == finished['effects_by_target'][record['platform']]
        assert record['framing_mode'] == 'letterbox'
        if record['platform'] == 'tiktok:vertical':
            from vstudio.project import outrender
            doc = outputs.Doc(record)
            state = doc.state()
            target = outrender.targets_of(record, state)[0]
            edit_plan = outrender.plan(record, doc, state, target, 'preview', watermark=False)
            assert edit_plan['canvas']['mode'] == 'letterbox'
            reframed = outrender.run_canvas(edit_plan['canvas'], str(tmp_path/'second-edit.mp4'),
                                            'preview', edit_plan['canvas']['safe'])
            cap = cv2.VideoCapture(reframed)
            ok, frame = cap.read(); cap.release()
            assert ok and np.max(frame[20, 20]) < 10
            # A stale/foreign crop sidecar must not dictate this output's framing.
            from pathlib import Path
            crop_file = Path(row['file']).with_suffix('.crop.json')
            crop = json.loads(crop_file.read_text())
            for bad in (dict(crop, src='another-source.mp4'), dict(crop, target=[640, 360]),
                        dict(crop, region=[0, 0, 100, 100])):
                crop_file.write_text(json.dumps(bad))
                assert 'framing_mode' not in outputs.resolve(str(tmp_path), row['id'])
            crop_file.write_text(json.dumps(crop))
    overlapping = dict(effect, params=dict(effect['params'], panel_box=[0, 0, 1, 1]))
    with pytest.raises(ValueError, match='overlaps rendered captions'):
        export.export_one(str(source), platform.profile('tiktok', 'vertical', use_persona=False),
                          str(tmp_path/'overlap'), effects=[overlapping], cues=str(cues),
                          mode='letterbox', captions=True, watermark=False)


def test_source_preserving_split_keeps_full_frame_and_is_seek_safe():
    from vstudio.project import outfx
    canvas = dict(size=[960, 540], safe=[48, 27, 912, 513], panels={}, preserve_source=True)
    beat = dict(BEAT, panel=None)
    effect = spoken.validate(dict(beats=[beat]), CUES, 8, canvas=canvas)[0]
    assert effect['params']['preserve_source'] is True
    layer = outfx.make_layer(effect, 960, 540, canvas['safe'])
    layer.setup()
    source = np.zeros((540, 960, 3), np.uint8)
    source[:40, :40] = [0, 0, 255]
    source[-40:, -40:] = [0, 255, 0]
    source[480:500, 100:800] = 255  # burned subtitle-like band
    frames = []
    for t in (0, 1.5, .5, 1.5, 3):
        frame = source.copy(); layer.draw(frame, t, 3); frames.append(frame)
    assert np.array_equal(frames[0], source) and np.array_equal(frames[-1], source)
    assert np.array_equal(frames[1], frames[3])
    x, y, w, h = layer.source_rect
    expected = cv2.resize(source, (w, h), interpolation=cv2.INTER_AREA)
    assert np.array_equal(frames[1][y:y+h, x:x+w], expected)
    assert np.max(frames[1][y:y+20, x:x+20, 2]) == 255
    assert np.max(frames[1][y+h-20:y+h, x+w-20:x+w, 1]) == 255
    assert np.mean(frames[1][:, x+w+30:]) > 100
