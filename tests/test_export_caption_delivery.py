"""Native exports keep verified subtitle files through the desktop file picker."""
import os
import subprocess
from types import SimpleNamespace

from vstudio import export as EX, media, platform, subs
from vstudio.project.adapters.common import collect_vstudio_exports
from desk_engine.outputs import _file_row


def test_real_export_caption_package_and_stale_file_rejection(tmp_path):
    master = tmp_path / 'master.mp4'
    subprocess.run([media.ffmpeg_bin(), '-v', 'error', '-y', '-f', 'lavfi',
                    '-i', 'color=c=blue:s=320x180:r=10:d=1', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', str(master)], check=True)
    out = tmp_path / 'out'
    profile = platform.profile('youtube', 'horizontal', overrides={'w': 320, 'h': 180})
    manifest = EX.export(str(master), [profile], str(out),
                         cues=[subs.Cue(0, .9, 'Bonjour le monde.', meta={'lang': 'fr'})],
                         captions='sidecar', caption_role='speech', watermark=False,
                         encoder='libx264', preset='ultrafast')
    entry = manifest['exports'][0]
    project = SimpleNamespace(manifest={'workflow': 'longform-course', 'outputs': {'files': []}})
    collected = collect_vstudio_exports(project, {'id': 'lesson', 'params': {'_item_dir': str(tmp_path)}}, [])
    native = next(e for e in collected if e.get('platform') == 'youtube')
    row = _file_row(native['file'], native)
    assert not row['caption_issues']
    track = row['sidecars'][0]
    assert track['lang'] == 'fr' and track['role'] == 'speech'
    assert os.path.isabs(track['file'])
    assert 'Bonjour le monde.' in open(track['file']).read()

    with open(track['file'], 'a') as f:
        f.write('changed')
    row = _file_row(native['file'], native)
    assert row['sidecars'] == []
    assert row['caption_issues'][0]['reason'] == 'file-changed'

    # A different selected video must not inherit this export's subtitle track.
    other = tmp_path / 'other.mp4'
    other.write_bytes(b'another output')
    row = _file_row(str(other), entry)
    assert row['sidecars'] == []
    assert row['caption_issues'][0]['reason'] == 'video-changed'


def test_legacy_caption_metadata_is_not_automatically_publishable(tmp_path):
    video = tmp_path / 'legacy.mp4'
    video.write_bytes(b'video')
    track = tmp_path / 'legacy.en.srt'
    track.write_text('1\n00:00:00,000 --> 00:00:01,000\nLegacy\n')
    row = _file_row(str(video), {'sidecars': [{'file': track.name, 'lang': 'en'}]})
    assert row['sidecars'] == []
    assert row['caption_issues'][0]['reason'] == 'video-changed'


def test_lesson_mono_captions_keep_declared_non_english_language(tmp_path, monkeypatch):
    from vstudio import clipkit as CK
    monkeypatch.setattr(CK, 'canvases', lambda _: {(1920, 1080): ['youtube']})
    monkeypatch.setattr(CK, 'render_clip', lambda *a, **k: dict(
        cues=[subs.Cue(0, 1, 'こんにちは')], master='master.mp4', keepouts=[], timeline=[], duration=1,
        mask_report=[], content_policy={}, deferred_overlays=[], geometry={}))
    monkeypatch.setattr(CK, '_covers', lambda *a: [])

    def check_export(master, keys, directory, **kwargs):
        tracks = EX.caption_tracks(kwargs['cues'], platform.profile('youtube'))
        assert list(tracks) == ['ja']
        assert tracks['ja'][0].text == 'こんにちは'
        assert kwargs['caption_role'] == 'speech'
        return {'exports': []}

    monkeypatch.setattr(EX, 'export', check_export)
    CK.deliver({'id': 'lesson'}, [], ['youtube'], str(tmp_path),
               CK.caption_config('mono', 'ja', proofread={'provider': 'none'}), firstpass=False)
