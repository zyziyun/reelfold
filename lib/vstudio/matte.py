"""Subject cutout for stills (cover frames, speaker photos) -> alpha matte.

    from vstudio import matte as M
    fg, alpha, engine = M.matte(bgr)              # engine "auto": BiRefNet when downloaded, else MediaPipe
    M.engines()                                   # {"birefnet": True/False, "mediapipe": True/False}

Engines
  birefnet   BiRefNet-lite (ZhengPeng7/BiRefNet, MIT; ONNX export by onnx-community, MIT) on onnxruntime: any
             salient subject (people, a jet ski, a tower), clean hair and edges. 1024x1024 input, ~5-15 s per still
             on an Apple-silicon CPU. A first-run download: the app's asset group ``matte-birefnet`` sets
             ``VSTUDIO_BIREFNET_MODEL``; the CLI uses ``<cache>/models/birefnet-lite/`` (``python -m vstudio.assets
             fetch matte-birefnet``). ``VSTUDIO_ORT_COREML=1`` tries the CoreML execution provider first.
  mediapipe  MediaPipe selfie segmenter (Apache-2.0, in the core models) + an edge-aware guided filter. People only,
             fast; the fallback when BiRefNet is not downloaded or onnxruntime is missing.
RVM (GPL-3.0) stays an opt-in of ``workflows/cover/scripts/matte.py`` and is never used here.
"""
import os
from functools import lru_cache

import numpy as np

BIREFNET_ENV = "VSTUDIO_BIREFNET_MODEL"
BIREFNET_DIR = "birefnet-lite"
BIREFNET_FILES = ("model.onnx", "model_fp16.onnx")
SIZE = 1024
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def birefnet_path():
    from .config import optional_asset
    p = optional_asset(BIREFNET_ENV, BIREFNET_DIR, names=BIREFNET_FILES)
    return p if p and os.path.isfile(p) else None


def _has(mod):
    import importlib.util
    return importlib.util.find_spec(mod) is not None


def engines():
    """Which engines can run here."""
    mp_ok = False
    if _has("mediapipe"):
        try:
            from .config import model
            mp_ok = bool(model("selfie_segmenter"))
        except Exception:  # noqa: BLE001
            mp_ok = False
    return {"birefnet": bool(birefnet_path()) and _has("onnxruntime"), "mediapipe": mp_ok}


def providers():
    """onnxruntime providers: CPU (deterministic, sandbox-safe); CoreML first when VSTUDIO_ORT_COREML=1."""
    import onnxruntime as ort
    have = ort.get_available_providers()
    out = []
    if os.environ.get("VSTUDIO_ORT_COREML") == "1" and "CoreMLExecutionProvider" in have:
        out.append("CoreMLExecutionProvider")
    return out + ["CPUExecutionProvider"]


@lru_cache(maxsize=2)
def _session(path):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.log_severity_level = 3
    return ort.InferenceSession(path, sess_options=so, providers=providers())


def birefnet_alpha(bgr, path=None):
    """BiRefNet foreground probability (float32 0..1, the frame's size)."""
    import cv2
    path = path or birefnet_path()
    if not path:
        raise FileNotFoundError("BiRefNet is not downloaded (asset group matte-birefnet)")
    s = _session(path)
    inp = s.get_inputs()[0]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    x = cv2.resize(rgb, (SIZE, SIZE), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    x = ((x - MEAN) / STD).transpose(2, 0, 1)[None]
    x = x.astype(np.float16 if "float16" in inp.type else np.float32)
    y = s.run(None, {inp.name: x})[-1][0, 0].astype(np.float32)
    a = 1.0 / (1.0 + np.exp(-np.clip(y, -30, 30)))
    return np.clip(cv2.resize(a, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_LINEAR), 0, 1)


def _box(x, r):
    import cv2
    return cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), normalize=True, borderType=cv2.BORDER_REFLECT)


def guided(guide_gray, src, r=8, eps=1e-3):
    """He et al. guided filter (grey guide). Snaps a coarse mask to image edges."""
    I, p = guide_gray.astype(np.float32), src.astype(np.float32)
    mI, mp_ = _box(I, r), _box(p, r)
    a = (_box(I * p, r) - mI * mp_) / (_box(I * I, r) - mI * mI + eps)
    b = mp_ - a * mI
    return _box(a, r) * I + _box(b, r)


def mediapipe_alpha(bgr, lo=0.25, hi=0.75, radius=None):
    """MediaPipe selfie segmenter (people) refined with a guided filter (float32 0..1)."""
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    from .config import model

    opts = vision.ImageSegmenterOptions(base_options=mpt.BaseOptions(model_asset_path=model("selfie_segmenter")),
                                        output_confidence_masks=True, output_category_mask=False)
    with vision.ImageSegmenter.create_from_options(opts) as seg:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        res = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
    conf = res.confidence_masks[-1].numpy_view().astype(np.float32)   # last mask = person
    conf = cv2.resize(conf, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
    a = np.clip((conf - lo) / (hi - lo), 0, 1)
    a = a * a * (3 - 2 * a)                                            # smoothstep
    r = radius or max(4, int(min(bgr.shape[:2]) / 120))
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    a = np.clip(guided(gray, a, r=r, eps=2e-3), 0, 1)
    core = cv2.erode((conf > 0.9).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    a[core] = 1.0
    a[a < 0.04] = 0.0
    return a


def matte(bgr, engine="auto", log=None):
    """-> (foreground BGR, alpha float32 0..1, engine used). ``engine``: auto (BiRefNet, else MediaPipe) |
    birefnet | mediapipe. Raises RuntimeError when no engine can run."""
    say = log or (lambda m: None)
    order = ["birefnet", "mediapipe"] if engine == "auto" else [engine]
    errs = []
    for e in order:
        try:
            a = birefnet_alpha(bgr) if e == "birefnet" else mediapipe_alpha(bgr)
            return bgr, a.astype(np.float32), e
        except Exception as ex:  # noqa: BLE001  (the next engine; said, not hidden)
            errs.append(f"{e}: {str(ex)[:120]}")
            if engine == "auto":
                say(f"matte: {e} unavailable ({str(ex)[:100]}), trying the next engine")
    raise RuntimeError("no matte engine could run: " + "; ".join(errs))
