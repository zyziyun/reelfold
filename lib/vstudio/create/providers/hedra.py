"""Hedra: a talking presenter (lip-synced avatar video) from ONE portrait image + the narration audio.

Hedra's public API with the creator's own key (env HEDRA_API_KEY - the desk puts it there from the OS keychain,
Settings > Video generation > Hedra; it is never written to a file). Spends her Hedra plan's credits.

    POST {BASE}/assets {name, type: image|audio} -> {id};  POST {BASE}/assets/{id}/upload (multipart "file")
    GET  {BASE}/models -> the video models; the Character-3 one is picked by name (env HEDRA_MODEL_ID overrides)
    POST {BASE}/generations {type: video, ai_model_id, start_keyframe_id, audio_id,
                             generated_video_inputs: {text_prompt, resolution, aspect_ratio}} -> {id}
    GET  {BASE}/generations/{id}/status -> {status: queued|processing|complete|error, progress, url | asset_id}
Uploading the two assets costs nothing; the generation is the paid call (``submit``, once, after the spend gate:
``vstudio.create.presenter``). Docs: https://www.hedra.com/docs (the "public" API; Hedra's newer v3 API bills a
separate prepaid USD wallet instead of the plan's credits).
[unverified against a live key in this build: unit-tested with a fake transport only; the first paid run is the
creator's own.]
"""
import json
import mimetypes
import os
import urllib.error
import urllib.request
import uuid

from .base import Provider, SubmitTimeout

BASE = "https://api.hedra.com/web-app/public"
ASPECTS = ("16:9", "9:16", "1:1")
RESOLUTIONS = ("540p", "720p")


class TransportError(RuntimeError):
    pass


def _http(url, data=None, headers=None, method=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        body = e.read()[:400].decode("utf-8", "replace")
        if e.code == 429 or e.code >= 500:
            raise TransportError(f"HTTP {e.code}: {body}") from e
        raise RuntimeError(f"HTTP {e.code}: {body}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise TransportError(str(e)) from e


def multipart(path, field="file"):
    """(body bytes, content-type) for one file upload."""
    boundary = uuid.uuid4().hex
    name = os.path.basename(path)
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        data = f.read()
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{name}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode()
    return head + data + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


class Hedra(Provider):
    info = dict(id="hedra", label={"en": "Hedra", "zh": "Hedra", "fr": "Hedra"}, kind="cloud",
                needs=["HEDRA_API_KEY"], tos="Hedra public API with your own key; spends your Hedra plan's credits",
                license=None, models=["character-3"], concurrency=1)

    def __init__(self, key=None, base=None, transport=None):
        self._key, self.base = key, base or os.environ.get("HEDRA_API_BASE", BASE)
        self._transport = transport or _http

    def _h(self, ctype="application/json"):
        k = self._key or os.environ.get("HEDRA_API_KEY")
        if not k:
            raise RuntimeError("HEDRA_API_KEY is not set (Settings > Video generation > Hedra)")
        h = {"X-API-Key": k}
        if ctype:
            h["Content-Type"] = ctype
        return h

    def _json(self, path, body=None, method="GET"):
        raw, _ = self._transport(f"{self.base}{path}", None if body is None else json.dumps(body).encode(),
                                 self._h(), method)
        return json.loads(raw or b"{}")

    def model_id(self):
        """The Character-3 model id (read-only GET /models), or env HEDRA_MODEL_ID."""
        if os.environ.get("HEDRA_MODEL_ID"):
            return os.environ["HEDRA_MODEL_ID"]
        models = self._json("/models")
        if isinstance(models, dict):
            models = models.get("data") or models.get("models") or []
        for m in models or []:
            name = f"{m.get('name') or ''} {m.get('slug') or ''}".lower().replace("-", " ")
            if "character" in name and "3" in name:
                return m.get("id") or m.get("slug")
        raise RuntimeError("Hedra lists no Character-3 model for this key (set HEDRA_MODEL_ID)")

    def upload(self, path, kind):
        """Create + upload one asset (free) -> its id."""
        r = self._json("/assets", {"name": os.path.basename(path), "type": kind}, "POST")
        aid = r.get("id")
        if not aid:
            raise RuntimeError(f"asset not created: {str(r)[:200]}")
        body, ctype = multipart(path)
        self._transport(f"{self.base}/assets/{aid}/upload", body, self._h(ctype), "POST", 600)
        return aid

    @staticmethod
    def body(model, image_id, audio_id, job):
        return {"type": "video", "ai_model_id": model, "start_keyframe_id": image_id, "audio_id": audio_id,
                "generated_video_inputs": {
                    "text_prompt": job.prompt or "A teacher explaining calmly to the camera",
                    "resolution": job.resolution if job.resolution in RESOLUTIONS else "540p",
                    "aspect_ratio": job.aspect if job.aspect in ASPECTS else "16:9"}}

    def submit(self, job):
        """PAID: the uploads first (free, retried by the caller's error), then ONE generation request."""
        image = (job.refs or {}).get("first_frame")
        audio = (job.extra or {}).get("audio")
        for p in (image, audio):
            if not p or not os.path.isfile(str(p)):
                raise RuntimeError(f"missing input file: {p}")
        model = self.model_id()
        image_id, audio_id = self.upload(image, "image"), self.upload(audio, "audio")
        try:
            r = self._json("/generations", self.body(model, image_id, audio_id, job), "POST")
        except TransportError as e:
            raise SubmitTimeout(str(e)) from e
        gid = r.get("id") or r.get("generation_id")
        if not gid:
            raise RuntimeError(f"submit rejected: {str(r)[:300]}")
        return gid

    def poll(self, task_id):
        r = self._json(f"/generations/{task_id}/status")
        st = str(r.get("status") or "").lower()
        if st in ("error", "failed"):
            return {"status": "failed", "urls": [], "raw": r}
        if st != "complete":
            return {"status": "pending", "urls": [], "raw": r}
        url = r.get("url") or r.get("download_url")
        if not url and r.get("asset_id"):
            a = self._json(f"/assets?type=video&ids={r['asset_id']}")
            rows = a.get("data") if isinstance(a, dict) else a
            for row in rows or []:
                url = (row.get("asset") or {}).get("url") or row.get("url")
                if url:
                    break
        return {"status": "done" if url else "failed", "urls": [url] if url else [], "raw": r}

    def download(self, url, path):
        raw, _ = self._transport(url, None, {}, "GET", 600)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(raw)
        return path
