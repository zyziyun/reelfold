"""Joins that would ghost: a long dissolve between two video shots that show the same subject at different places
(two Space Needles at once) becomes a cut or a short dissolve (vstudio.dissolve). Runs once per render, after the
timeline, on the prepared clips (shots.prep_video, cached): the frames compared are the ones the dissolve would mix.

    from photostory.dissolves import plan
    plan(C, T)      # may change sh["tr"] / sh["trd"] (and the previous shot's tail); returns the changes
"""
import subprocess

import numpy as np

from vstudio import dissolve as DS, media as vmedia

from .shots import parse_src, prep_video


def frame_at(clip, t, width=480):
    """One RGB frame of a prepared clip at ``t`` seconds (uint8, ``width`` wide), None past its end."""
    r = subprocess.run([vmedia.ffmpeg_bin(), "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", clip, "-frames:v", "1",
                        "-vf", f"scale={width}:-2,format=rgb24", "-f", "rawvideo", "-"], capture_output=True)
    if not r.stdout:
        return None
    a = np.frombuffer(r.stdout, np.uint8)
    h = a.size // (width * 3)
    return a[:h * width * 3].reshape(h, width, 3) if h else None


def plan(C, T):
    changes = []
    if getattr(C.spec, "KEEP_DISSOLVES", False):
        return changes
    shots = T.shots
    for k in range(1, len(shots)):
        sh, pv = shots[k], shots[k - 1]
        if sh.get("tr") != "fade" or float(sh.get("trd") or 0) <= DS.SHORT_TRD:
            continue
        ka, a = parse_src(C, pv["src"])
        kb, b = parse_src(C, sh["src"])
        if ka != "video" or kb != "video":
            continue
        mid = sh["trd"] / 2
        fa = frame_at(prep_video(C, pv, a), sh["start"] - pv["start"] + mid)
        fb = frame_at(prep_video(C, sh, b), mid)
        if fa is None or fb is None:
            continue
        r = DS.ghost_risk(fa, fb)
        tr, trd = DS.choose(r, sh["trd"])
        if (tr, trd) != (sh["tr"], sh["trd"]):
            changes.append(dict(k=k, at=round(sh["start"], 2), was=sh["trd"], tr=tr, trd=trd, why=r["why"]))
            sh["tr"], sh["trd"] = tr, trd
            pv["tail"] = trd
    for c in changes:
        now = "a cut" if c["tr"] == "cut" else "a %.1fs dissolve" % c["trd"]
        print(f"[joins] {c['at']:.1f}s: {c['why']} -> {now} (was a {c['was']:.1f}s dissolve)", flush=True)
    return changes
