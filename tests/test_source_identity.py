"""Same-named source files must not cross-wire planning and rendering."""
import os
from types import SimpleNamespace

import pytest
from vstudio import footage
from vstudio.source_identity import names, stage
from vstudio.project.adapters import common


def sources(tmp_path):
    paths = []
    for folder, data in [('a', b'first'), ('b', b'second')]:
        p = tmp_path / folder / 'clip.mp4'
        p.parent.mkdir(); p.write_bytes(data); paths.append(str(p))
    return paths


def test_unique_names_stable_across_input_order_and_extensions(tmp_path):
    paths = sources(tmp_path)
    paths += [str(tmp_path / 'unique.mov'), str(tmp_path / 'CLIP.MOV')]
    result = names(paths)
    assert result == names(list(reversed(paths)))
    assert result[paths[2]] == 'unique.mov'
    assert len({os.path.splitext(n)[0].casefold() for n in result.values()}) == 4


def test_prepare_and_footage_share_distinct_source_names(tmp_path, monkeypatch):
    paths = sources(tmp_path)
    env = SimpleNamespace(params={'_inputs': {'videos': paths}}, item_dir=str(tmp_path/'item'),
                          item_path=lambda name: str(tmp_path/'item'/name))
    linked = common.prepare(env)['inputs']
    assert [open(p, 'rb').read() for p in linked] == [b'first', b'second']
    monkeypatch.setattr(footage, 'facts', lambda p: dict(file=p, dur=1, w=10, h=10, orientation='horizontal'))
    monkeypatch.setattr(footage, 'sheet', lambda p, out, **kw: out)
    _, sheets, facts = footage.context(paths, str(tmp_path/'sheets'), shots=False)
    assert len(set(sheets)) == 2
    assert [f['id'] for f in facts] == [os.path.splitext(os.path.basename(p))[0] for p in linked]
    assert common.prepare(env)['inputs'] == linked
    with pytest.raises(ValueError, match='unique'):
        footage.context(paths, str(tmp_path/'sheets'), ids=['same', 'same'])


def test_existing_different_source_is_not_reused_or_overwritten(tmp_path):
    p=tmp_path/'clip.mp4'; p.write_bytes(b'new')
    folder=tmp_path/'inputs'; folder.mkdir()
    old=folder/'clip.mp4'; old.write_bytes(b'old')
    with pytest.raises(ValueError, match='another file'):
        stage([str(p)], str(folder))
    assert old.read_bytes() == b'old' and p.read_bytes() == b'new'


def test_story_planner_and_renderer_bind_the_same_source(tmp_path, monkeypatch):
    from vstudio.project import drafts as DR
    from vstudio.project.adapters import photostory as PS
    paths = sources(tmp_path)
    captured = []
    def context(files, folder, ids, **kw):
        captured.extend(ids)
        return 'Two sources', [], [dict(id=i, path=p, dur=5) for i, p in zip(ids, files)]
    monkeypatch.setattr(footage, 'context', context)
    monkeypatch.setenv('VSTUDIO_CACHE', str(tmp_path/'cache'))
    ctx = DR.Ctx(str(tmp_path), 'main', dict(_inputs=dict(videos=paths),
        _item_dir=str(tmp_path/'item'), mode='music'), 'photo-story')
    ctx.request_text = 'Two-second company film, no background music or voice-over'
    def complete(*a, **kw):
        script = [(i, [('Source', '素材')], [('v'+cid, 1, 'still', None)]) for i, cid in enumerate(captured)]
        return dict(provider='test', json=dict(content=f'MUSIC=dict(length=2)\nSCRIPT={script!r}\n'))
    dest=tmp_path/'item/work/spec.py'
    assert PS.draft_spec(ctx, dict(id='story', author={}), str(dest), complete=complete)
    assert len(set(captured)) == 2
    media = PS._spec_value(dest.read_text(), 'MEDIA')
    for cid, source in zip(captured, paths):
        assert os.path.samefile(dest.parent/media['videos']/(cid+'.mp4'), source)


@pytest.mark.parametrize('requested,expected', [('second', 'second'), ('basename', 'ambiguous-source'), ('foreign', 'unknown-source')])
def test_shot_swap_never_guesses_between_same_named_sources(tmp_path, monkeypatch, requested, expected):
    from vstudio.project import outputs as O
    paths = sources(tmp_path)
    mapping = dict(shots=[dict(start=0, end=1)], sources=[dict(path=p, duration=5) for p in paths])
    monkeypatch.setattr(O, 'shot_map', lambda _: mapping)
    source = {'second': paths[1], 'basename': 'clip.mp4', 'foreign': str(tmp_path/'other'/'clip.mp4')}[requested]
    if expected == 'second':
        result = O._shot_swap({}, {}, dict(shot=0, source=source, t=0), {})
        assert result['swap']['source'] == paths[1]
    else:
        with pytest.raises(O.OutputError) as error:
            O._shot_swap({}, {}, dict(shot=0, source=source, t=0), {})
        assert error.value.info['code'] == expected


def test_shot_swap_still_accepts_unique_filename(tmp_path, monkeypatch):
    from vstudio.project import outputs as O
    path = sources(tmp_path)[0]
    monkeypatch.setattr(O, 'shot_map', lambda _: dict(shots=[dict(start=0, end=1)], sources=[dict(path=path, duration=5)]))
    result = O._shot_swap({}, {}, dict(shot=0, source='clip.mp4', t=1), {})
    assert result['swap'] == dict(source=path, t=1)
