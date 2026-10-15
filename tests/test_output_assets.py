"""AI web stickers become durable local images; failed downloads do not become applied edits."""
import io
from types import SimpleNamespace
from pathlib import Path

import pytest
from PIL import Image
from vstudio.project import outassets as A
from vstudio.project import outfx as FX
from vstudio.project.outputs import OutputError


def png():
    out = io.BytesIO()
    Image.new('RGBA', (80, 80), (255, 150, 0, 180)).save(out, 'PNG')
    return out.getvalue()


def server(monkeypatch, raw):
    monkeypatch.setattr(A.socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('8.8.8.8', 443))])
    monkeypatch.setattr(A.urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=lambda *a, **k: io.BytesIO(raw)))


def test_ai_sticker_survives_url_and_replays_as_local_image(tmp_path, monkeypatch):
    server(monkeypatch, png())
    op = dict(op='effect_add', effect='sticker', start=23, end=36,
              params=dict(image='https://example.com/cat.png', x=.5, y=.4))
    clean = A.prepare(SimpleNamespace(dir=str(tmp_path)), op)
    assert op['params']['image'].startswith('https:')
    path = Path(clean['params']['image'])
    assert path.parent == tmp_path / 'assets'
    assert Image.open(path).mode == 'RGBA'
    params, _ = FX.validate('overlay-images', clean['params'])
    assert params['style'] == 'image'
    assert A.prepare(SimpleNamespace(dir=str(tmp_path)), clean) == clean
    assert A.prepare(SimpleNamespace(dir=str(tmp_path)), op)['params']['image'] == str(path)


@pytest.mark.parametrize('raw', [b'<html>not an image</html>', b'x' * (A.MAX_BYTES + 1)],
                         ids=['invalid-image', 'oversized-image'])
def test_bad_or_oversized_download_is_specific_error(tmp_path, monkeypatch, raw):
    server(monkeypatch, raw)
    with pytest.raises(OutputError) as e:
        A.prepare(SimpleNamespace(dir=str(tmp_path)), dict(op='effect_add', effect='overlay-images',
                  params=dict(image='https://example.com/image.png')))
    assert e.value.info['code'] == 'sticker-download'
    assert not list(tmp_path.rglob('*.png'))


@pytest.mark.parametrize('url', ['http://example.com/cat.png', 'https://user:pass@example.com/cat.png',
                                'https://example.com:8000/cat.png'])
def test_reject_non_public_https_urls(url):
    with pytest.raises(ValueError):
        A._public_https(url)


def test_reject_private_hosts_and_redirects(monkeypatch):
    monkeypatch.setattr(A.socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('127.0.0.1', 443))])
    with pytest.raises(ValueError):
        A._public_https('https://localhost/cat.png')
    with pytest.raises(ValueError):
        A._Redirect().redirect_request(None, None, 302, '', {}, 'https://localhost/cat.png')
