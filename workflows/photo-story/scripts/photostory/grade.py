"""The film's grade: every video shot matched in colour toward the film's reference shot and given the film look, one
3D LUT per shot (vstudio.colormatch; ffmpeg lut3d, LGPL). Photo shots get the look only, applied in numpy.

    from photostory.grade import plan
    report = plan(C, T)      # sets sh["_lut"] (a .cube path) on each video shot, sh["_lut_table"] on photo shots

Statistics come from the shot's own prepared clip (crop + scale + cadence already done, shots.prep_video: so a
crop of a wide frame is measured as it is shown), 5 frames across the part of it the shot plays. The LUTs live in
<cache>/luts/ under their content hash; shots.prep_video makes a graded copy of the clip with them (cached too).
"""
import os
from concurrent.futures import ThreadPoolExecutor

from vstudio import colormatch as CM

from .shots import parse_src, prep_video


def _video_shots(C, T):
    return [(k, sh, arg) for k, sh in enumerate(T.shots) for kind, arg in [parse_src(C, sh["src"])] if kind == "video"]


def plan(C, T):
    """-> {ref, look, shots: [{k, clip, jump_before, jump_after}]} (also printed); a no-op when COLOR_MATCH is 0 and
    there is no GRADE_LOOK."""
    match = float(getattr(C, "COLOR_MATCH", 0) or 0)
    lk = CM.look_name(getattr(C, "GRADE_LOOK", None))
    lk_s = float(getattr(C, "GRADE_LOOK_STRENGTH", CM.LOOK_STRENGTH))
    if match <= 0 and lk is None:
        return dict(ref=None, look=None, shots=[])
    vids = _video_shots(C, T)
    st = {}
    if match > 0 and len(vids) > 1:
        def measure(item):
            k, sh, name = item
            clip = prep_video(C, sh, name)
            dur = sh["end"] - sh["start"] + min(sh["tail"], 3.0)
            return k, CM.stats(CM.sample(clip, 0.0, max(0.2, dur)))
        with ThreadPoolExecutor(max_workers=3) as ex:
            st = dict(ex.map(measure, vids))
    prefer = None
    if C.COLOR_REF is not None:
        prefer = next((k for k, sh, name in vids if name == str(C.COLOR_REF) or sh["src"] == str(C.COLOR_REF)), None)
    ref = CM.reference(st, prefer) if st else None
    folder = os.path.join(C.cache_dir, "luts")
    rows = []
    for k, sh, name in vids:
        table = CM.shot_lut(st.get(k), st.get(ref) if ref is not None else None, lk, strength=match,
                            look_strength=lk_s)
        if not CM.is_identity(table):
            sh["_lut"] = CM.write_cube(table, folder, title=f"{name} -> shot {ref}, {lk or 'no look'}")
        rows.append(dict(k=k, clip=name, ref=k == ref))
    if lk is not None:
        photo = CM.shot_lut(None, None, lk, look_strength=lk_s)
        for sh in T.shots:
            if parse_src(C, sh["src"])[0] == "img":
                sh["_lut_table"] = photo
    before = [round(CM.chroma_jump(st[a["k"]], st[b["k"]]), 1) for a, b in zip(rows, rows[1:])
              if a["k"] in st and b["k"] in st]
    if st:
        print(f"[grade] colour match {match:.2f} toward shot {ref} ({next((r['clip'] for r in rows if r['ref']), '-')})"
              f", look {lk or 'none'} at {lk_s:.0%}; colour steps between shots before: max "
              f"{max(before) if before else 0:.1f}", flush=True)
    elif lk:
        print(f"[grade] look {lk} at {lk_s:.0%}", flush=True)
    return dict(ref=ref, look=lk, match=match, shots=rows, steps_before=before)
