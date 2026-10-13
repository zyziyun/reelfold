"""LAION aesthetic predictor v2 (christophschuhmann/improved-aesthetic-predictor, Apache-2.0): a linear MLP on the
CLIP ViT-L/14 image embedding (OpenAI CLIP, MIT; ONNX export by Xenova) -> a 1..10 "how good does this look" score,
trained on SAC + LOGOS + AVA ratings. Used by ``vstudio.cover.score_frames`` next to sharpness / exposure / faces.

    from vstudio import aesthetic as A
    A.available()                  # weights downloaded + onnxruntime importable
    A.score([bgr, bgr, ...])       # -> [5.8, 6.4, ...]

Files: ``VSTUDIO_AESTHETIC_MODEL`` (the app's asset group ``cover-aesthetic``: a folder with ``vision_model.onnx``
(CLIP ViT-L/14 vision tower, q4f16: ranks like fp16, rho 0.97) and ``sac+logos+ava1-l14-linearMSE.pth``) or ``<cache>/models/aesthetic/``.
The MLP is read with ``vstudio.ptload`` and run in numpy; nothing needs torch.
"""
import os
from functools import lru_cache

import numpy as np

ENV = "VSTUDIO_AESTHETIC_MODEL"
DIR = "aesthetic"
CLIP_FILES = ("vision_model.onnx", "vision_model_q4f16.onnx", "vision_model_int8.onnx", "vision_model_quantized.onnx", "vision_model_fp16.onnx")
MLP_FILE = "sac+logos+ava1-l14-linearMSE.pth"
MEAN = np.array([0.48145466, 0.4578275, 0.40821073], np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], np.float32)


def model_dir():
    from .config import optional_asset
    d = optional_asset(ENV, DIR)
    if d and os.path.isfile(d):
        d = os.path.dirname(d)
    return d if d and os.path.isdir(d) else None


def files():
    """(clip onnx, mlp pth) or None."""
    d = model_dir()
    if not d:
        return None
    clip = next((os.path.join(d, n) for n in CLIP_FILES if os.path.exists(os.path.join(d, n))), None)
    mlp = os.path.join(d, MLP_FILE)
    return (clip, mlp) if clip and os.path.exists(mlp) else None


def available():
    import importlib.util
    return bool(files()) and importlib.util.find_spec("onnxruntime") is not None


@lru_cache(maxsize=1)
def _load(clip, mlp):
    import onnxruntime as ort

    from .matte import providers
    from .ptload import load_state_dict
    so = ort.SessionOptions()
    so.log_severity_level = 3
    # basic only: the extended fusions break on the fp16 export (SimplifiedLayerNormFusion cast bug)
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    sess = ort.InferenceSession(clip, sess_options=so, providers=providers())
    sd = load_state_dict(mlp)
    layers = sorted({int(k.split(".")[1]) for k in sd if k.startswith("layers.")})
    mats = [(sd[f"layers.{i}.weight"].astype(np.float32), sd[f"layers.{i}.bias"].astype(np.float32))
            for i in layers if f"layers.{i}.weight" in sd]
    return sess, mats


def preprocess(bgr):
    """CLIP preprocessing: shortest edge 224 (bicubic), centre crop 224, mean / std -> 1x3x224x224."""
    import cv2
    h, w = bgr.shape[:2]
    s = 224 / min(h, w)
    im = cv2.resize(bgr, (max(224, round(w * s)), max(224, round(h * s))), interpolation=cv2.INTER_CUBIC)
    y0, x0 = (im.shape[0] - 224) // 2, (im.shape[1] - 224) // 2
    rgb = cv2.cvtColor(im[y0:y0 + 224, x0:x0 + 224], cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return ((rgb - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)


def embed(bgrs):
    f = files()
    if not f:
        raise FileNotFoundError("the aesthetic model is not downloaded (asset group cover-aesthetic)")
    sess, _ = _load(*f)
    inp = sess.get_inputs()[0]
    names = [o.name for o in sess.get_outputs()]
    out_name = "image_embeds" if "image_embeds" in names else names[0]
    embs = []
    for b in bgrs:
        x = preprocess(b)
        x = x.astype(np.float16) if "float16" in inp.type else x
        e = np.asarray(sess.run([out_name], {inp.name: x})[0], np.float32).reshape(-1)
        embs.append(e / (np.linalg.norm(e) + 1e-8))
    return np.stack(embs) if embs else np.zeros((0, 768), np.float32)


def mlp(emb, mats):
    """The predictor head: Linear stack (dropout is a no-op at inference, no activations in v2 linearMSE)."""
    h = emb
    for w, b in mats:
        h = h @ w.T + b
    return h[..., 0]


def score(bgrs):
    """Aesthetic scores (about 1..10; ~5 average photo, 6.5+ striking) for BGR images."""
    f = files()
    if not f:
        raise FileNotFoundError("the aesthetic model is not downloaded (asset group cover-aesthetic)")
    _, mats = _load(*f)
    return [float(x) for x in mlp(embed(bgrs), mats)]
