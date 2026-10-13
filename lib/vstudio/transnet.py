"""TransNet V2 (Souček & Lokoč 2020; MIT code + weights) shot-boundary network, run without TensorFlow or torch.

    from vstudio import transnet
    transnet.available()                         # weights on disk (models/transnetv2/variables.*)
    p = transnet.predict(frames)                 # frames: uint8 (n, 27, 48, 3) RGB -> per-frame cut probability
    transnet.scenes(p)                           # [(first, last)] frame ranges, threshold 0.5 (as upstream)

The official weights are a TF SavedModel; only its variables (a TF tensor bundle: a leveldb-style index + one data
shard) are read here, by a small parser, and the network runs in numpy (MLX on Apple silicon when installed). Same
windowing as upstream ``predict_frames``: 100-frame windows, stride 50, the middle 50 kept, the clip padded with copies
of its first / last frame.

Weights lookup: env VSTUDIO_TRANSNETV2 (a folder with variables.index + variables.data-00000-of-00001) >
<cache>/models/transnetv2/ (downloaded on first run; sha256 pinned in apps/desk/packaging/assets.json).
"""
import os
import struct

import numpy as np

ENV = "VSTUDIO_TRANSNETV2"
INDEX = "variables.index"
DATA = "variables.data-00000-of-00001"
H, W = 27, 48


def weights_dir():
    env = os.environ.get(ENV)
    cands = [env] if env else []
    from .config import cache_dirs
    cands += cache_dirs("models", "transnetv2")
    for d in cands:
        if d and os.path.isfile(os.path.join(d, INDEX)) and os.path.isfile(os.path.join(d, DATA)):
            return d
    return None


def available():
    return weights_dir() is not None


# ------------------------------------------------------------------ TF tensor bundle reader
def _varint(b, i):
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


def _block(buf, off, size):
    b = buf[off:off + size]
    if buf[off + size] != 0:
        raise ValueError("compressed tensor-bundle index blocks are not supported")
    nr = struct.unpack("<I", b[-4:])[0]
    end = len(b) - 4 - 4 * nr
    i, key, out = 0, b"", []
    while i < end:
        sh, i = _varint(b, i)
        ns, i = _varint(b, i)
        vl, i = _varint(b, i)
        key = key[:sh] + b[i:i + ns]
        i += ns
        out.append((key, b[i:i + vl]))
        i += vl
    return out


def _fields(b):
    i, out = 0, {}
    while i < len(b):
        tag, i = _varint(b, i)
        f, wt = tag >> 3, tag & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 2:
            n, i = _varint(b, i)
            v, i = b[i:i + n], i + n
        elif wt == 5:
            v, i = b[i:i + 4], i + 4
        elif wt == 1:
            v, i = b[i:i + 8], i + 8
        else:
            raise ValueError(f"protobuf wire type {wt}")
        out.setdefault(f, []).append(v)
    return out


def read_bundle(d):
    """{checkpoint key: float32 array} from a TF variables.index / data pair (float32 tensors only)."""
    with open(os.path.join(d, INDEX), "rb") as fh:
        buf = fh.read()
    if struct.unpack("<Q", buf[-8:])[0] != 0xDB4775248B80FB57:
        raise ValueError("not a TF tensor-bundle index")
    ft = buf[-48:]
    i = 0
    for _ in range(2):                                   # metaindex handle (unused)
        _, i = _varint(ft, i)
    io, i = _varint(ft, i)
    isz, i = _varint(ft, i)
    data = np.memmap(os.path.join(d, DATA), dtype=np.uint8, mode="r")
    out = {}
    for _, h in _block(buf, io, isz):
        o, j = _varint(h, 0)
        s, j = _varint(h, j)
        for k, v in _block(buf, o, s):
            if not k:
                continue
            f = _fields(v)
            if f.get(1, [0])[0] != 1:                    # DT_FLOAT only
                continue
            shape = [_fields(dm).get(1, [0])[0] for dm in _fields(f[2][0]).get(2, [])] if 2 in f else []
            off, size = f.get(4, [0])[0], f.get(5, [0])[0]
            out[k.decode()] = np.frombuffer(bytes(data[off:off + size]), "<f4").reshape(shape).copy()
    return out


# variables/<n> of the SavedModel, in the order TransNetV2 creates them (names from saved_model.pb's object graph)
def _names():
    names = []
    for s in (1, 2, 3):
        for dd in (1, 2):
            for c in (1, 2, 4, 8):
                names += [f"SDDCNN_{s}/DDCNN_{dd}/Conv3D_{c}/conv_spatial/kernel",
                          f"SDDCNN_{s}/DDCNN_{dd}/Conv3D_{c}/conv_temporal/kernel"]
            names += [f"SDDCNN_{s}/DDCNN_{dd}/bn/gamma", f"SDDCNN_{s}/DDCNN_{dd}/bn/beta"]
    for s in (1, 2, 3):
        for dd in (1, 2):
            names += [f"SDDCNN_{s}/DDCNN_{dd}/bn/moving_mean", f"SDDCNN_{s}/DDCNN_{dd}/bn/moving_variance"]
    names += ["dense/kernel", "dense/bias", "dense_1/kernel", "dense_1/bias", "dense_2/kernel", "dense_2/bias",
              "FrameSimilarity/dense_3/kernel", "FrameSimilarity/dense_3/bias",
              "FrameSimilarity/dense_4/kernel", "FrameSimilarity/dense_4/bias",
              "ColorHistograms/dense_5/kernel", "ColorHistograms/dense_5/bias"]
    return names


def load_weights(d=None):
    d = d or weights_dir()
    if not d:
        raise FileNotFoundError("TransNet V2 weights are not downloaded (models/transnetv2)")
    raw = read_bundle(d)
    # the three top dense layers are saved under the model's attribute names, the rest as variables/<n>
    alias = {"dense": "fc1", "dense_1": "cls_layer1", "dense_2": "cls_layer2"}
    w = {}
    for n, name in enumerate(_names()):
        head = name.split("/")[0]
        k = (f"{alias[head]}/{name.split('/')[1]}" if head in alias else f"variables/{n}") + "/.ATTRIBUTES/VARIABLE_VALUE"
        if k not in raw:
            raise ValueError(f"TransNet V2 weights miss {name}")
        w[name] = raw[k]
    return w


# ------------------------------------------------------------------ the network
class _Ops:
    def __init__(self, backend="auto"):
        self.mx = None
        if backend in ("auto", "mlx"):
            try:
                import mlx.core as mx
                self.mx = mx
            except Exception:  # noqa: BLE001 - Intel Mac / Windows: numpy
                if backend == "mlx":
                    raise
        self.name = "mlx" if self.mx is not None else "numpy"

    def arr(self, a):
        a = np.ascontiguousarray(a, np.float32)
        return self.mx.array(a) if self.mx is not None else a

    def np(self, a):
        return np.array(a) if self.mx is not None else a

    def mm(self, x, w):
        if self.mx is not None:
            return x @ w
        s = x.shape
        return (np.ascontiguousarray(x).reshape(-1, s[-1]) @ w).reshape(s[:-1] + (w.shape[1],))

    def pad(self, x, width):
        return self.mx.pad(x, width) if self.mx is not None else np.pad(x, width)

    def cat(self, xs, axis):
        return self.mx.concatenate(xs, axis=axis) if self.mx is not None else np.concatenate(xs, axis=axis)

    def relu(self, x):
        return self.mx.maximum(x, 0.0) if self.mx is not None else np.maximum(x, 0.0)


class TransNetV2:
    def __init__(self, weights=None, backend="auto"):
        w = weights if weights is not None else load_weights()
        self.o = o = _Ops(backend)
        self.blocks = []
        for s in (1, 2, 3):
            dds = []
            for dd in (1, 2):
                p = f"SDDCNN_{s}/DDCNN_{dd}"
                sp = [w[f"{p}/Conv3D_{c}/conv_spatial/kernel"][0] for c in (1, 2, 4, 8)]     # (3, 3, Ci, 2F)
                cat = np.concatenate(sp, axis=-1)                                          # (3, 3, Ci, 4*2F)
                tk = [w[f"{p}/Conv3D_{c}/conv_temporal/kernel"][:, 0, 0] for c in (1, 2, 4, 8)]  # (3, 2F, F)
                g, b = w[f"{p}/bn/gamma"], w[f"{p}/bn/beta"]
                m, v = w[f"{p}/bn/moving_mean"], w[f"{p}/bn/moving_variance"]
                sc = g / np.sqrt(v + 1e-3)
                dds.append(dict(spatial=[[o.arr(cat[i, j]) for j in range(3)] for i in range(3)],
                                f2=sp[0].shape[-1], temporal=[[o.arr(t[k]) for k in range(3)] for t in tk],
                                scale=o.arr(sc), shift=o.arr(b - m * sc)))
            self.blocks.append(dds)
        self.fc1 = (o.arr(w["dense/kernel"]), o.arr(w["dense/bias"]))
        self.cls1 = (o.arr(w["dense_1/kernel"]), o.arr(w["dense_1/bias"]))
        self.cls2 = (o.arr(w["dense_2/kernel"]), o.arr(w["dense_2/bias"]))
        self.sim_proj = (w["FrameSimilarity/dense_3/kernel"], w["FrameSimilarity/dense_3/bias"])
        self.sim_fc = (w["FrameSimilarity/dense_4/kernel"], w["FrameSimilarity/dense_4/bias"])
        self.hist_fc = (w["ColorHistograms/dense_5/kernel"], w["ColorHistograms/dense_5/bias"])

    def _ddcnn(self, x, p, act):
        """x: (T, H, W, C) -> (T, H, W, 4F)."""
        o = self.o
        T, Hh, Ww, _ = x.shape
        xp = o.pad(x, [(0, 0), (1, 1), (1, 1), (0, 0)])
        y = None
        for i in range(3):
            for j in range(3):
                t = o.mm(xp[:, i:i + Hh, j:j + Ww, :], p["spatial"][i][j])
                y = t if y is None else y + t
        f2 = p["f2"]
        outs = []
        for bi, d in enumerate((1, 2, 4, 8)):
            yb = y[..., bi * f2:(bi + 1) * f2]
            yp = o.pad(yb, [(d, d), (0, 0), (0, 0), (0, 0)])
            z = None
            for k in range(3):
                t = o.mm(yp[k * d:k * d + T], p["temporal"][bi][k])
                z = t if z is None else z + t
            outs.append(z)
        x = o.cat(outs, -1) * p["scale"] + p["shift"]
        return o.relu(x) if act else x

    @staticmethod
    def _lookup(sim, window=101):
        T = sim.shape[0]
        half = (window - 1) // 2
        sp = np.pad(sim, [(0, 0), (half, half)])
        idx = np.arange(T)[:, None] + np.arange(window)[None, :]
        return sp[np.arange(T)[:, None], idx]

    def _hist_feat(self, frames):
        f = frames.astype(np.int32)
        b = ((f[..., 0] >> 5) << 6) + ((f[..., 1] >> 5) << 3) + (f[..., 2] >> 5)
        T = len(frames)
        hist = np.zeros((T, 512), np.float32)
        np.add.at(hist, (np.repeat(np.arange(T), b[0].size), b.reshape(-1)), 1.0)
        hist /= np.maximum(np.linalg.norm(hist, axis=1, keepdims=True), 1e-12)
        s = self._lookup(hist @ hist.T)
        return np.maximum(s @ self.hist_fc[0] + self.hist_fc[1], 0)

    def window(self, frames):
        """uint8 (100, 27, 48, 3) -> (single, many) probabilities, (100,) each."""
        o = self.o
        x = o.arr(frames.astype(np.float32) / 255.0)
        means = []
        for dds in self.blocks:
            x = self._ddcnn(x, dds[0], True)
            short = x
            x = self._ddcnn(x, dds[1], False)
            x = o.relu(x) + short
            T, Hh, Ww, C = x.shape
            Ho, Wo = Hh // 2, Ww // 2
            x = x[:, :Ho * 2, :Wo * 2, :]
            x = (x[:, 0::2, 0::2] + x[:, 1::2, 0::2] + x[:, 0::2, 1::2] + x[:, 1::2, 1::2]) * 0.25
            means.append(o.np(x).mean(axis=(1, 2)))
        T = x.shape[0]
        feat = o.np(x).reshape(T, -1)                                       # (T, 3*6*256) in (H, W, C) order
        e = np.concatenate(means, 1) @ self.sim_proj[0] + self.sim_proj[1]
        e /= np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-12)
        sim = np.maximum(self._lookup(e @ e.T) @ self.sim_fc[0] + self.sim_fc[1], 0)
        h = np.concatenate([self._hist_feat(frames), sim, feat], 1).astype(np.float32)
        h = o.relu(o.mm(o.arr(h), self.fc1[0]) + self.fc1[1])
        one = o.np(o.mm(h, self.cls1[0]) + self.cls1[1])[:, 0]
        many = o.np(o.mm(h, self.cls2[0]) + self.cls2[1])[:, 0]
        return 1 / (1 + np.exp(-one)), 1 / (1 + np.exp(-many))


_MODEL = {}


def model(backend="auto"):
    if backend not in _MODEL:
        _MODEL[backend] = TransNetV2(backend=backend)
    return _MODEL[backend]


def predict(frames, backend="auto", with_many=False):
    """uint8 (n, 27, 48, 3) RGB frames -> per-frame transition probability (n,) [and the 'many hot' head]."""
    frames = np.asarray(frames, np.uint8)
    n = len(frames)
    if n == 0:
        return (np.zeros(0), np.zeros(0)) if with_many else np.zeros(0)
    m = model(backend)
    end_pad = 25 + 50 - (n % 50 if n % 50 else 50)
    padded = np.concatenate([np.repeat(frames[:1], 25, 0), frames, np.repeat(frames[-1:], end_pad, 0)])
    one, many = [], []
    for p in range(0, len(padded) - 99, 50):
        a, b = m.window(padded[p:p + 100])
        one.append(a[25:75])
        many.append(b[25:75])
    one = np.concatenate(one)[:n]
    many = np.concatenate(many)[:n]
    return (one, many) if with_many else one


def scenes(pred, threshold=0.5):
    """Upstream ``predictions_to_scenes``: [(first frame, last frame)] of each shot."""
    p = (np.asarray(pred) > threshold).astype(np.uint8)
    out, t_prev, start, t = [], 0, 0, 0
    for i, t in enumerate(p):
        if t_prev == 1 and t == 0:
            start = i
        if t_prev == 0 and t == 1 and i != 0:
            out.append((start, i))
        t_prev = t
    if len(p) and t == 0:
        out.append((start, len(p) - 1))
    return out or [(0, max(0, len(p) - 1))]
