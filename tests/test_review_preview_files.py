"""Layout review must receive image evidence, including late-shot changes."""
from types import SimpleNamespace

from vstudio.project.adapters import common


def test_stills_directory_exposes_every_frame_and_hash(tmp_path):
    stills = tmp_path / 'stills'
    stills.mkdir()
    paths = []
    for i in range(16):
        path = stills / f'st_frame_{i:08d}.jpg'
        path.write_bytes(f'frame {i}'.encode())
        paths.append(str(path))
    (stills / 'notes.txt').write_text('not image evidence')
    (stills / 'nested').mkdir()
    env = SimpleNamespace(params={}, inputs={'stills': {'files': [str(stills), paths[0]]}})
    before = common.publish_payload(env, {'after': 'stills'})
    assert [p['path'] for p in before['previews']] == paths
    assert all(p['kind'] == 'image' for p in before['previews'])
    assert all(o['sha'] for o in before['options'])
    (stills / 'st_frame_00000015.jpg').write_bytes(b'changed ending')
    after = common.publish_payload(env, {'after': 'stills'})
    assert before['options'][:-1] == after['options'][:-1]
    assert before['options'][-1]['sha'] != after['options'][-1]['sha']


def test_export_previews_remain_preferred(tmp_path):
    movie = tmp_path / 'final.mp4'
    movie.write_bytes(b'movie')
    env = SimpleNamespace(params={}, inputs={
        'stills': {'files': [str(tmp_path)]},
        'export': {'exports': [{'file': str(movie), 'platform': 'youtube'}]}})
    payload = common.publish_payload(env, {})
    assert payload['previews'] == [{'kind': 'video', 'path': str(movie), 'platform': 'youtube'}]
