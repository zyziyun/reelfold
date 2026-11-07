import json
from vstudio.project.adapters.photostory import _framing_note


def rows(note):
    return json.loads(note.split('\n')[1])


def test_geometry_exposes_undersized_portrait_regions():
    current = 'SCRIPT=[(0, [], [("vsource", 8, "still", dict(fit="contain", source_region=[160,0,1600,1080]))])]'
    data = rows(_framing_note([dict(id='source',w=1920,h=1080)], ['tiktok'], current))
    full, region = data
    assert full['canvas'] == [1080,1920]
    assert full['contain_size'] == [1080,608]
    assert full['contain_canvas_percent'] == 31.6
    assert full['cover_visible_source_size'] == [608,1080]
    assert region['contain_canvas_percent'] == 38.0
    assert region['contain_size'] == [1080,729]


def test_geometry_is_per_target_and_not_subject_detection():
    data = rows(_framing_note([dict(id='portrait',w=1080,h=1920)], ['tiktok','youtube']))
    assert data[0]['contain_canvas_percent'] == 100
    assert data[1]['contain_canvas_percent'] == 31.6
    assert _framing_note([], ['tiktok']) == ''
    assert _framing_note([dict(id='bad',w=0,h=1080)], ['tiktok']) == ''
