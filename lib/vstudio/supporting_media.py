"""Verified supporting-media IDs for spoken finishing; originals remain read-only."""
import os


def paths(job, spec):
    p = job.get("params") or {}
    value = (p.get("_inputs") or {}).get("broll", p.get("broll", (spec.get("inputs") or {}).get("broll", [])))
    return list(dict.fromkeys(os.path.abspath(x) for x in (value if isinstance(value, list) else [value]) if x))


def context(paths, work):
    from PIL import Image, ImageOps
    from vstudio import footage, broll
    from vstudio.project.adapters import photo_inputs
    photos, videos = [], []
    for path in paths:
        if not os.path.isfile(path):
            raise ValueError(f"Supporting material is missing: {path}")
        ext = os.path.splitext(path)[1].lower()
        if ext in broll.IMG_EXT:
            photos.append(path)
        elif ext in footage.VIDEO_EXT:
            videos.append(path)
        else:
            raise ValueError(f"Unsupported supporting material: {path}")
    lines, images, assets = [], [], []
    if videos:
        ids = [f"v{i+1:04d}" for i in range(len(videos))]
        text, sheets, facts = footage.context(videos, os.path.join(work, "videos"), ids=ids, max_clips=len(videos))
        available = {os.path.splitext(os.path.basename(p))[0] for p in sheets}
        lines.append(text)
        images.extend(sheets)
        assets += [dict(id=f["id"], kind="video", path=f["path"], duration=f["dur"])
                   for f in facts if f["id"] in available]
        lines.extend(f"UNAVAILABLE: {vid} (no visual preview; do not use)" for vid in ids if vid not in available)
    if photos:
        text, sheets, _ = photo_inputs.context(photos, work)
        lines.append(text)
        images.extend(sheets)
        # Freeze the same EXIF-oriented pixels the planner saw, avoiding rotated exports.
        for i, path in enumerate(photos):
            pid = f"p{i+1:04d}"
            dest = os.path.join(work, "source_photos", pid + "-render.png")
            with Image.open(path) as im:
                oriented = ImageOps.exif_transpose(im).convert("RGB")
                oriented.save(dest)
                size = list(oriented.size)
            assets.append(dict(id=pid, kind="image", path=dest, size=size))
            lines.append(f"{pid}: displayed source pixels {size[0]}x{size[1]}; detail rectangles use these coordinates, not sheet pixels.")
    lines.append("Available IDs: " + ", ".join(a["id"] for a in assets))
    return "\n".join(lines), images, assets
