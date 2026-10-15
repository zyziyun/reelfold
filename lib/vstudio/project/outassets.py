"""Freeze remote AI sticker images into the output's own edit assets before validation.

Rendering and replay use local PNGs; a web page / URL is never passed to Pillow as a file.
"""
import hashlib
import io
import ipaddress
import os
import socket
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 16_000_000


def _public_https(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.port not in (None, 443):
        raise ValueError("use a public HTTPS image link")
    addresses = socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)
    # Some system VPNs resolve CDN names into their benchmark-range DNS proxy. HTTPS still verifies
    # the named CDN's certificate. Do not grant this exception to arbitrary model-provided hosts.
    proxy_cdn = u.hostname.lower() in {"raw.githubusercontent.com", "cdn.jsdelivr.net"}
    def allowed(value):
        address = ipaddress.ip_address(value)
        return address.is_global or (proxy_cdn and address in ipaddress.ip_network("198.18.0.0/15"))
    if not addresses or any(not allowed(a[4][0]) for a in addresses):
        raise ValueError("the image link must point to a public server")


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _public_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def image(url, directory):
    """Download a bounded raster image, decode it and keep a stable, local PNG."""
    _public_https(url)
    req = urllib.request.Request(url, headers={"User-Agent": "Reelfold/1.0", "Accept": "image/*"})
    with urllib.request.build_opener(_Redirect()).open(req, timeout=20) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("the sticker image is larger than 8 MB")
    with Image.open(io.BytesIO(raw)) as src:
        if src.format not in ("PNG", "JPEG", "WEBP", "GIF"):
            raise ValueError("use a PNG, JPEG, WebP or GIF image link")
        if src.width * src.height > MAX_PIXELS:
            raise ValueError("the sticker image is larger than 16 megapixels")
        src.seek(0)
        rgba = src.convert("RGBA")
    dest = Path(directory) / "assets" / ("sticker-" + hashlib.sha256(raw).hexdigest()[:24] + ".png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".sticker-", suffix=".png", dir=dest.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            rgba.save(f, format="PNG")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return str(dest)


def prepare(doc, op):
    """Only AI effect proposals materialize URLs; ordinary validation stays network-free."""
    from . import outfx as FX
    from .outputs import OutputError

    params = op.get("params")
    if op.get("op") not in ("effect_add", "effect_update") or not isinstance(params, dict):
        return op
    effect = op.get("effect")
    if op.get("op") == "effect_update":
        effect = next((e["effect"] for e in doc.state()["effects"] if e["id"] == op.get("id")), effect)
    value = params.get("image")
    if FX.resolve(effect) != "overlay-images" or not isinstance(value, str) or not value.startswith(("https:", "http:")):
        return op
    try:
        path = image(value, doc.dir)
    except (ValueError, OSError, urllib.error.URLError) as e:
        raise OutputError("sticker-download", "Could not load the sticker image. Use a direct public PNG, JPEG or WebP link.",
                          "无法载入贴纸图片，请使用可访问的 PNG、JPEG 或 WebP 图片直链。", detail=str(e)) from e
    return dict(op, params=dict(params, image=path, style="image"))
