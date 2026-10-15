"""MAS-only, fail-closed permission before transmitting user content to an AI service.

Full/CLI builds keep their existing behavior. The socket carries only a normalized
origin and a fixed purpose; no content, paths, keys or query parameters.
"""
import http.client
import ipaddress
import json
import os
import socket
import urllib.parse
import urllib.request


class ConsentDenied(PermissionError):
    """A refusal is terminal, not a provider outage eligible for fallback/retry."""


def required():
    return os.environ.get("VSTUDIO_AI_CONSENT_REQUIRED") == "1"


def origin(url):
    u = urllib.parse.urlsplit(str(url))
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
        raise ConsentDenied("The AI service needs an HTTP(S) address without credentials.")
    host = u.hostname.encode("idna").decode().lower()
    port = u.port
    authority = f"[{host}]" if ":" in host else host
    if port and port != (443 if u.scheme == "https" else 80):
        authority += f":{port}"
    return f"{u.scheme}://{authority}", host


def require(url, purpose):
    if not required():
        return
    destination, host = origin(url)
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == "localhost"
    if local:
        return
    if purpose not in ("analysis", "transcription", "speech", "generation"):
        raise ConsentDenied("Unknown AI data-sharing purpose.")
    sock = os.environ.get("VSTUDIO_AI_CONSENT_SOCKET")
    token = os.environ.get("VSTUDIO_AI_CONSENT_TOKEN")
    if not sock or not token:
        raise ConsentDenied("AI sharing permission is unavailable. Reopen Reelfold and try again.")
    conn = http.client.HTTPConnection("localhost", timeout=300)
    try:
        conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.sock.settimeout(300)
        conn.sock.connect(sock)
        conn.request("POST", "/consent", json.dumps(dict(origin=destination, purpose=purpose)),
                     {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        response = conn.getresponse()
        data = response.read(4097)
        allowed = response.status == 200 and len(data) <= 4096 and json.loads(data).get("allowed") is True
    except (OSError, ValueError, http.client.HTTPException) as e:
        raise ConsentDenied("AI sharing permission is unavailable. Reopen Reelfold and try again.") from e
    finally:
        conn.close()
    if not allowed:
        raise ConsentDenied("AI data sharing was not allowed. No content was sent to this service.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # An approved host must not forward content or credentials to a different destination.
        return None


def urlopen(req, timeout):
    if required():
        return urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def sdk_transport():
    """SDKs normally follow redirects; MAS content requests must stay on the approved origin."""
    if not required():
        return {}
    import httpx
    return {"http_client": httpx.Client(follow_redirects=False)}
