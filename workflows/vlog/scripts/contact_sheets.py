#!/usr/bin/env python3
"""Make a thumbnail contact sheet per clip so you can SEE the footage and decide
which windows are good (subject clearly framed, smooth move) vs bad (empty,
shaky, approach/retreat tails, pocket shots).

    python3 contact_sheets.py OUT_DIR EVERY_SEC CLIP1 [CLIP2 ...]
    python3 contact_sheets.py work/sheets 4 footage/*.MP4

One frame every EVERY_SEC seconds, tiled 5 across x 6 down (30 tiles = the first
30*EVERY_SEC seconds; raise EVERY_SEC for long takes). Read left->right,
top->bottom: each tile is labelled with its source time (tile n = (n-1)*EVERY_SEC); a short clip's
sheet is one row of just its stills.
Portrait clips get portrait tiles (rotation metadata honoured).
Thin wrapper over vstudio.media.contact_sheet (PIL labels, no drawtext needed); plain Python so the
recipe's sheets stage runs on Windows too (no bash there, or WSL's without a distribution).
"""
import os
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
from vstudio import media  # noqa: E402


def sheet(f, out, every):
    i = media.probe(f)
    w, h = (i["h"], i["w"]) if abs(i["rotation"]) % 180 == 90 else (i["w"], i["h"])
    base = os.path.splitext(os.path.basename(f))[0]
    dst = os.path.join(out, f"{base}_sheet.jpg")
    media.contact_sheet(f, dst, every=every, cols=5, max_frames=30, start=0,
                        thumb_w=224 if h > w else 400)
    print(f"sheet: {base}", flush=True)


def main(argv):
    if len(argv) < 3 or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    out, every, clips = argv[0], float(argv[1]), argv[2:]
    os.makedirs(out, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(lambda f: sheet(f, out, every), clips))
    print(f"done -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
