"""Should this join be a dissolve? A long dissolve between two framings of the SAME subject at different places in the
frame shows it twice - a ghosted double exposure (two Space Needles side by side for most of a second, DJI review
2026-10-12, 01 at 68 s). Between different scenes a dissolve is the calm default; between two moments of one steady
move it is invisible; only the "same thing, moved" case needs a cut or a short dissolve.

    from vstudio import dissolve as DS
    r = DS.ghost_risk(frame_a, frame_b)      # grey or RGB uint8 frames, any size
    r -> {"risk": True, "shift": 0.18, "scale": 1.04, "inliers": 63, "why": "..."}
    DS.choose(r, trd=0.8)                    # -> ("cut", 0.0) | ("fade", 0.3) | ("fade", 0.8)

Method: ORB key points matched across the two frames (Hamming, cross-checked), a similarity transform fitted with
RANSAC. Many inliers = the same subject is in both; the transform's translation (fraction of the frame width) and
scale say how far it moved. Few matches = different scenes (a dissolve is fine). OpenCV only (Apache-2.0).
"""
import numpy as np

MIN_INLIERS = 18          # this many consistent matches: both frames show the same thing
SHIFT_GHOST = 0.035       # the subject moved this much (fraction of the width) -> two copies show during a dissolve
SCALE_GHOST = 0.08        # ... or grew / shrank this much
SHIFT_CUT = 0.10          # moved this far -> a cut; between SHIFT_GHOST and this, a short dissolve
SHORT_TRD = 0.3


def _grey(img, width=480):
    import cv2
    a = np.asarray(img)
    if a.dtype != np.uint8:
        a = np.clip(a, 0, 255).astype(np.uint8)
    if a.ndim == 3:
        a = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
    if a.shape[1] != width:
        a = cv2.resize(a, (width, max(2, round(a.shape[0] * width / a.shape[1]))), interpolation=cv2.INTER_AREA)
    return cv2.equalizeHist(a)        # night shots: lights on black still give corners after equalising


def ghost_risk(a, b):
    """-> {risk, shift, scale, inliers, matches, why}: ``risk`` when both frames show the same subject at a different
    place / size (module doc)."""
    import cv2
    ga, gb = _grey(a), _grey(b)
    orb = cv2.ORB_create(nfeatures=900, fastThreshold=12)
    ka, da = orb.detectAndCompute(ga, None)
    kb, db = orb.detectAndCompute(gb, None)
    out = dict(risk=False, shift=0.0, scale=1.0, inliers=0, matches=0, why="different scenes")
    if da is None or db is None or len(ka) < 8 or len(kb) < 8:
        out["why"] = "too few features"
        return out
    m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(da, db)
    m = [x for x in m if x.distance <= 48]
    out["matches"] = len(m)
    if len(m) < MIN_INLIERS:
        return out
    pa = np.float32([ka[x.queryIdx].pt for x in m])
    pb = np.float32([kb[x.trainIdx].pt for x in m])
    M, inl = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC, ransacReprojThreshold=4.0, maxIters=4000)
    n = int(inl.sum()) if inl is not None else 0
    out["inliers"] = n
    if M is None or n < MIN_INLIERS:
        return out
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    w, h = ga.shape[1], ga.shape[0]
    # where the frame's centre goes: the subject's displacement as the viewer sees it (rotation + scale included)
    c = np.array([w / 2, h / 2, 1.0])
    d = M @ c - c[:2]
    shift = float(np.hypot(*d) / w)
    out.update(shift=round(shift, 4), scale=round(scale, 4))
    if shift >= SHIFT_GHOST or abs(scale - 1) >= SCALE_GHOST:
        out.update(risk=True, why=f"the same subject {shift:.0%} of the width apart, scale {scale:.2f}")
    else:
        out["why"] = "one continuous framing"
    return out


def choose(r, trd, tr="fade"):
    """The join for a ghost_risk result: (tr, trd). A dissolve that would ghost becomes a cut (big move) or a short
    dissolve (small move); anything else keeps ``tr`` / ``trd``."""
    if tr != "fade" or not r.get("risk") or trd <= SHORT_TRD:
        return tr, trd
    if r["shift"] >= SHIFT_CUT or abs(r["scale"] - 1) >= 2 * SCALE_GHOST:
        return "cut", 0.0
    return "fade", SHORT_TRD
