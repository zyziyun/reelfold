"""Multi-canvas delivery retains every current export and its subtitle reference."""
import json

from vstudio import clipkit as CK, export as EX


def test_delivery_manifest_retains_current_canvases_and_removes_old_versions(tmp_path, monkeypatch):
    monkeypatch.setattr(CK, 'render_clip', lambda *a, **k: dict(
        cues=[], master='master.mp4', keepouts=[], timeline=[], duration=2,
        mask_report=[], content_policy={}, deferred_overlays=[], geometry={}))
    monkeypatch.setattr(CK, '_covers', lambda *a: [])
    monkeypatch.setattr(EX.media, 'probe', lambda _: dict(
        w=1920, h=1080, display_w=1920, display_h=1080, fps=30, duration=2, has_audio=True))

    def export_one(master, profile, directory, **kwargs):
        stem = f"{kwargs['clip_id']}.{profile.name}-{profile.orientation}"
        return dict(platform=profile.name, orientation=profile.orientation,
                    file=stem + '.mp4', warnings=[],
                    sidecars=[dict(file=stem + '.en.srt', lang='en')])

    monkeypatch.setattr(EX, 'export_one', export_one)
    targets = ['youtube:horizontal', 'tiktok:vertical']
    report = CK.deliver({'id': 'lesson'}, [], targets, str(tmp_path),
                        captions={'off': True}, firstpass=False)
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    assert len(manifest['exports']) == len(report['exports']) == 2
    assert {e['platform'] for e in manifest['exports']} == {'youtube', 'tiktok'}
    for entry in manifest['exports']:
        assert entry['sidecars'][0]['file'] == entry['file'].replace('.mp4', '.en.srt')

    # Rerunning with one selected version must drop the earlier run's other version.
    CK.deliver({'id': 'lesson'}, [], targets[:1], str(tmp_path),
               captions={'off': True}, firstpass=False)
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    assert [e['platform'] for e in manifest['exports']] == ['youtube']
