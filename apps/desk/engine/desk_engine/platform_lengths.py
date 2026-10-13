"""Settings › Publishing › Video length: each platform's length habits (``vstudio.platform_habits``: the bands per
content kind from references/platforms/<name>.md, persona overrides) and her own range per platform
(``$VSTUDIO_HOME/platforms.json``, shared with the CLI skill: every kind's band is clamped into it).

    GET  /api/platform-lengths      {kinds, platforms [{platform, label, form, source, limits, hard, lengths}]}
    POST /api/platform-lengths      {platform, min_s?, max_s?, reset?} -> the same document
"""
from .common import BadRequest, need


def _h():
    try:
        from vstudio import platform_habits as H
    except ImportError as e:                         # an engine without platform habits
        raise BadRequest(f"this engine has no platform length habits ({e})") from None
    return H


class PlatformLengths:
    def doc(self):
        H = _h()
        return dict(kinds=list(H.KINDS), platforms=H.table())

    def set(self, body):
        H = _h()
        need(isinstance(body, dict), "body: {platform, min_s?, max_s?, reset?}")
        name = body.get("platform")
        need(isinstance(name, str) and 0 < len(name) < 40, "platform: a platform id")
        for k in ("min_s", "max_s"):
            v = body.get(k)
            need(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)), f"{k}: seconds or absent")
        need(body.get("reset") in (None, True, False), "reset: true, false or absent")
        try:
            H.set_limits(name, min_s=body.get("min_s"), max_s=body.get("max_s"), reset=bool(body.get("reset")))
        except ValueError as e:
            need(False, str(e))
        return self.doc()

    def route(self, method, parts, body, query=None):
        """None = not mine."""
        if parts == ["platform-lengths"] and method == "GET":
            return self.doc()
        if parts == ["platform-lengths"] and method == "POST":
            return self.set(body)
        return None
