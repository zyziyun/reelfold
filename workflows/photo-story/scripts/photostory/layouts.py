"""Per-shot space for factual labels beside narrow, uncropped video."""
from copy import copy

from vstudio import media
from photostory.music import captions_enabled
from photostory.shots import parse_src


def plan(C, T):
    layout = getattr(C.spec, "LAYOUT", {}) or {}
    if not (layout.get("video_caption_safe") and layout.get("caption_style") == "label"
            and C.overlay_subs and C.W > C.H and C.HDR == 0 and captions_enabled(C)):
        return
    if layout.get("video_caption_side") is False:
        return
    for i, shot in enumerate(T.shots):
        # A whole-frame dissolve would also blend the previous picture under
        # the side copy. Keep authored transitions until they share this layout.
        if shot.get("trd", 0) or (i + 1 < len(T.shots) and T.shots[i + 1].get("trd", 0)):
            continue
        if any(s.get("style") == "title" for s in T.subs
               if s["start"] < shot["end"] and s["end"] > shot["start"]):
            continue
        if (shot.get("fit") != "contain" or shot.get("source_region") or shot.get("detail_regions")
                or shot.get("c") or shot.get("z", 1) != 1 or shot["src"] in C.VCROP):
            continue
        kind, name = parse_src(C, shot["src"])
        if kind != "video" or name in C.VCROP:
            continue
        source = C.find_video(name)
        info = media.probe(source)
        w, h = info["display_w"], info["display_h"]
        if w >= h:
            continue
        x0, y0, x1, y1 = C.SAFE
        gap = max(2, round(C.W * .025))
        divide = round(C.W * .40)
        scale = min((x1 - divide) / w, (y1 - y0) / h)
        width, height = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
        shot["_video_box"] = (divide + (x1 - divide - width) // 2,
                              y0 + (y1 - y0 - height) // 2, width, height)
        caption = copy(C)
        caption.CAP = (x0, C.CAP[1], divide - gap, C.CAP[3])
        shot["_caption_context"] = caption
