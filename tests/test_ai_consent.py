"""Use a real Unix broker; content must never leave on refusal/unavailable consent."""
import contextlib
import http.server
import json
import os
import socketserver
import threading
from unittest.mock import Mock

import pytest

from vstudio import ai_consent as C


@contextlib.contextmanager
def broker(tmp_path, monkeypatch, allowed=True):
    if os.name == "nt":
        pytest.skip("MAS permission broker is Unix-only")
    calls = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append((self.path, self.headers.get('Authorization'),
                          json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(dict(allowed=allowed)).encode())
        def log_message(self, *args):
            pass
    # macOS sun_path is short; pytest's nested temp directory need not be.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='rf-consent-') as d:
        server = socketserver.UnixStreamServer(os.path.join(d, 's'), Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        monkeypatch.setenv('VSTUDIO_AI_CONSENT_REQUIRED', '1')
        monkeypatch.setenv('VSTUDIO_AI_CONSENT_SOCKET', server.server_address)
        monkeypatch.setenv('VSTUDIO_AI_CONSENT_TOKEN', 'test-token')
        try:
            yield calls
        finally:
            server.shutdown(); server.server_close(); t.join()


def test_real_broker_receives_only_origin_and_fixed_purpose(tmp_path, monkeypatch):
    with broker(tmp_path, monkeypatch) as calls:
        C.require('https://AI.Example:443/private/key?token=secret', 'analysis')
    assert calls == [('/consent', 'Bearer test-token', dict(origin='https://ai.example', purpose='analysis'))]


@pytest.mark.parametrize('url', ['http://localhost:11434/v1', 'http://127.0.0.2:8000', 'http://[::1]:9000'])
def test_loopback_needs_no_broker(monkeypatch, url):
    monkeypatch.setenv('VSTUDIO_AI_CONSENT_REQUIRED', '1')
    monkeypatch.delenv('VSTUDIO_AI_CONSENT_SOCKET', raising=False)
    C.require(url, 'analysis')


@pytest.mark.parametrize('url', ['http://192.168.1.10/v1', 'https://api.openai.com', 'http://localhost.evil.test'])
def test_remote_or_lan_is_not_implicitly_local(monkeypatch, url):
    monkeypatch.setenv('VSTUDIO_AI_CONSENT_REQUIRED', '1')
    monkeypatch.delenv('VSTUDIO_AI_CONSENT_SOCKET', raising=False)
    with pytest.raises(C.ConsentDenied, match='unavailable'):
        C.require(url, 'analysis')


def test_non_mas_unchanged(monkeypatch):
    monkeypatch.delenv('VSTUDIO_AI_CONSENT_REQUIRED', raising=False)
    C.require('https://api.openai.com', 'analysis')
    assert C.sdk_transport() == {}


def test_refusal_blocks_real_http_tts(tmp_path, monkeypatch):
    from vstudio import tts
    send = Mock(side_effect=AssertionError('network must not be reached'))
    monkeypatch.setattr(C, 'urlopen', send)
    with broker(tmp_path, monkeypatch, allowed=False):
        with pytest.raises(C.ConsentDenied):
            tts._speech_http('https://api.example/speech', {'input': 'private text'}, {}, str(tmp_path / 'out.wav'))
    send.assert_not_called()


def test_refusal_is_terminal_through_llm_retry_and_fallback(tmp_path, monkeypatch):
    from vstudio import llm
    calls = []
    def first(*args):
        calls.append('first')
        C.require('https://api.example', 'analysis')
    def second(*args):
        calls.append('fallback')
        raise AssertionError('denial must not fall back')
    monkeypatch.setattr(llm, '_fn', lambda p: first if p == 'openai' else second)
    with broker(tmp_path, monkeypatch, allowed=False):
        with pytest.raises(C.ConsentDenied):
            llm.complete('copy', '', 'private', provider='openai', fallback=['anthropic'], retries=2)
    assert calls == ['first']


def test_generation_http_refusal_precedes_transport(tmp_path, monkeypatch):
    from vstudio.create.providers import hedra, veo
    send = Mock(side_effect=AssertionError('no upload before permission'))
    monkeypatch.setattr(C, 'urlopen', send)
    with broker(tmp_path, monkeypatch, allowed=False):
        for module in (hedra, veo):
            with pytest.raises(C.ConsentDenied):
                module._http('https://vendor.example/assets', b'private media')
    send.assert_not_called()


def test_cloud_asr_refusal_precedes_audio_preparation(tmp_path, monkeypatch):
    from vstudio import asr
    prepare = Mock(side_effect=AssertionError('must not prepare or upload audio'))
    monkeypatch.setattr(asr.media, 'run', prepare)
    with broker(tmp_path, monkeypatch, allowed=False):
        with pytest.raises(C.ConsentDenied):
            asr._openai_api('private.wav', 'en', '', True, 'whisper-1', key='test')
    prepare.assert_not_called()


def test_redirects_never_forward_approved_content(monkeypatch):
    monkeypatch.setenv('VSTUDIO_AI_CONSENT_REQUIRED', '1')
    assert C._NoRedirect().redirect_request(None, None, 307, '', {}, 'https://other.example') is None
    client = C.sdk_transport()['http_client']
    assert client.follow_redirects is False
    client.close()


def test_standalone_ai_video_keeps_shared_consent_import_without_pythonpath(monkeypatch):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    code = """
import sys, io, os
sys.path.insert(0, sys.argv[1])
import providers
assert 'vstudio.ai_consent' not in sys.modules
class Response(io.BytesIO):
    headers = {}
providers.urllib.request.urlopen = lambda *a, **kw: Response(b'{}')
assert providers._http('https://test.invalid', b'{}')[0] == b'{}'
"""
    env = dict(os.environ)
    env.pop('VSTUDIO_AI_CONSENT_REQUIRED', None)
    subprocess.run([sys.executable, '-I', '-c', code, str(root / 'workflows/ai-video/scripts')],
                   env=env, check=True, capture_output=True)
