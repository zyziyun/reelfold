"""Readable, unambiguous photo IDs and contact sheets for the story planner.

Originals are read-only; aliases and previews live inside the item's work folder.
The renderer uses those same IDs, including when two sources share a basename.
"""
import os
import shutil
import subprocess


def _readable(path, folder, pid):
    if os.path.splitext(path)[1].lower() not in (".heic", ".heif"):
        return path
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        return path
    except ImportError:
        if not shutil.which("sips"):
            raise ValueError("photo-story: HEIC photo planning needs pillow-heif; use JPEG or install HEIC support")
        preview = os.path.join(folder, pid + "-preview.jpg")
        if not os.path.isfile(preview) or os.path.getmtime(preview) < os.path.getmtime(path):
            subprocess.run(["sips", "-s", "format", "jpeg", path, "--out", preview], check=True,
                           capture_output=True, timeout=30)
        return preview


def context(paths, work):
    from PIL import Image, ImageDraw, ImageOps
    paths = list(dict.fromkeys(os.path.abspath(p) for p in paths))
    if not paths:
        return "", [], set()
    folder = os.path.join(work, "source_photos")
    os.makedirs(folder, exist_ok=True)
    lines, pages, ids, tiles = [], [], set(), []
    for i, path in enumerate(paths):
        pid = f"p{i + 1:04d}"
        ext = os.path.splitext(path)[1].lower()
        alias = os.path.join(folder, pid + ext)
        if not os.path.isfile(alias) or os.path.getmtime(alias) != os.path.getmtime(path) or os.path.getsize(alias) != os.path.getsize(path):
            shutil.copy2(path, alias)
        with Image.open(_readable(path, folder, pid)) as source:
            photo = ImageOps.exif_transpose(source).convert("RGB")
            lines.append(f"{pid}: {os.path.basename(path)} ({photo.width}x{photo.height})")
            photo.thumbnail((304, 220), Image.Resampling.LANCZOS)
            tile = Image.new("RGB", (320, 252), (245, 243, 237))
            tile.paste(photo, ((320 - photo.width) // 2, 6 + (220 - photo.height) // 2))
            ImageDraw.Draw(tile).text((12, 232), pid, fill=(30, 35, 32))
            tiles.append(tile)
        ids.add(pid)
        if len(tiles) == 12 or i == len(paths) - 1:
            page = Image.new("RGB", (1280, 252 * ((len(tiles) + 3) // 4)), (245, 243, 237))
            for k, tile in enumerate(tiles):
                page.paste(tile, ((k % 4) * 320, (k // 4) * 252))
            dest = os.path.join(folder, f"sheet-{len(pages) + 1}.jpg")
            page.save(dest, quality=88)
            pages.append(dest)
            tiles = []
    return "\n".join(lines), pages, ids


def caption_ink(paths, work):
    """Choose a theme ink against the supplied studio backdrops, not hardcoded ad colours."""
    from PIL import Image
    from vstudio import theme as TH
    colours = []
    for i, path in enumerate(paths):
        with Image.open(_readable(path, os.path.join(work, "source_photos"), f"p{i + 1:04d}")) as im:
            im = im.convert("RGB").resize((8, 8))
            colours += [im.getpixel(p) for p in ((0, 0), (7, 0), (0, 7), (7, 7))]
    if not colours:
        return None
    background = tuple(sorted(c[k] for c in colours)[len(colours) // 2] for k in range(3))
    theme = TH.resolve(recipe="photo-story")
    return max((TH.rgb(theme, "ink"), TH.rgb(theme, "paper")), key=lambda c: TH.contrast(c, background))
