"""Beat This! (Foscarin, Schlüter, Widmer - ISMIR 2024) beat + downbeat tracker, run without torch.

    from vstudio import beatthis
    beatthis.available()                       # the checkpoint is on disk (models/beat_this/final0.ckpt)
    beats, downbeats = beatthis.track(x, sr)   # seconds; ``x`` mono float32
    beats, downbeats = beatthis.track_file("music.mp3")

The official checkpoint (CPJKU/beat_this, MIT code + weights) is a PyTorch zip; it is read here with a restricted
unpickler (``vstudio.ptload``: only tensors, storages and plain containers can load) and the network runs in numpy, or in MLX on
Apple silicon when it is installed (the same maths; ~5x faster). Same pre- and post-processing as the reference
``Audio2Beats(dbn=False)``: 22.05 kHz log-mel (128 bands, 50 fps), 1500-frame chunks with 6-frame borders, peaks of the
logits within +-70 ms above 0, adjacent peaks merged, every downbeat moved onto its nearest beat. madmom's DBN (its
models are CC-BY-NC-SA) is never used.

Checkpoint lookup: env VSTUDIO_BEAT_THIS (a .ckpt file) > <cache>/models/beat_this/final0.ckpt (downloaded on first run
by the desk, ``install.sh`` for the CLI; sha256 pinned in apps/desk/packaging/assets.json).
"""
import math
import os

import numpy as np

SR = 22050
FPS = 50
HOP = 441
N_FFT = 1024
CHUNK = 1500
BORDER = 6
ENV = "VSTUDIO_BEAT_THIS"
CHECKPOINT = "final0"
# sha256 of the official checkpoints (https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/<name>.ckpt)
SHA256 = {"final0": "8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331",
          "small0": "6074be2c4d490c5f6101fcc374a1ec72ae93456e23bb6019783b849f5dc7d47b"}


class NotDownloaded(FileNotFoundError):
    pass


def checkpoint_path(name=CHECKPOINT):
    """The checkpoint file, or None when it is not on disk."""
    env = os.environ.get(ENV)
    if env and os.path.isfile(env):
        return env
    from .config import cache_dirs
    for d in cache_dirs("models", "beat_this"):
        p = os.path.join(d, f"{name}.ckpt")
        if os.path.isfile(p):
            return p
    return None


def available():
    return checkpoint_path() is not None


# ------------------------------------------------------------------ checkpoint (torch zip, no torch)
def load_checkpoint(path):
    """A PyTorch (Lightning) checkpoint -> dict with numpy arrays, without torch (``vstudio.ptload``'s restricted
    unpickler: tensors, storages and plain containers only)."""
    from .ptload import load_state_dict
    return load_state_dict(path)


# ------------------------------------------------------------------ log-mel spectrogram (torchaudio-equivalent)
def _hz_to_mel(f):
    f = np.asarray(f, float)
    lin = f / (200.0 / 3)
    logstep = math.log(6.4) / 27.0
    return np.where(f >= 1000.0, 15.0 + np.log(np.maximum(f, 1e-9) / 1000.0) / logstep, lin)


def _mel_to_hz(m):
    m = np.asarray(m, float)
    logstep = math.log(6.4) / 27.0
    return np.where(m >= 15.0, 1000.0 * np.exp(logstep * (m - 15.0)), m * 200.0 / 3)


def mel_filters(n_freqs=N_FFT // 2 + 1, f_min=30.0, f_max=11000.0, n_mels=128, sr=SR):
    allf = np.linspace(0, sr // 2, n_freqs)
    fp = _mel_to_hz(np.linspace(_hz_to_mel(f_min), _hz_to_mel(f_max), n_mels + 2))
    fd = np.diff(fp)
    slopes = fp[None, :] - allf[:, None]
    down = -slopes[:, :-2] / fd[:-1]
    up = slopes[:, 2:] / fd[1:]
    return np.maximum(0, np.minimum(down, up)).astype(np.float32)        # (n_freqs, n_mels)


def log_mel(x):
    """Mono float32 at 22.05 kHz -> (frames, 128) log(1 + 1000 * mel magnitude), frames at 50 fps."""
    x = np.asarray(x, np.float32)
    pad = N_FFT // 2
    if len(x) <= pad:
        x = np.pad(x, (0, pad + 1 - len(x)))
    xp = np.pad(x, (pad, pad), mode="reflect")
    n = 1 + (len(xp) - N_FFT) // HOP
    win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)   # periodic Hann
    fb = mel_filters()
    out = np.empty((n, fb.shape[1]), np.float32)
    for c0 in range(0, n, 4096):
        c1 = min(n, c0 + 4096)
        idx = (np.arange(c0, c1) * HOP)[:, None] + np.arange(N_FFT)[None, :]
        mag = np.abs(np.fft.rfft(xp[idx] * win, axis=1)).astype(np.float32) / math.sqrt(N_FFT)
        out[c0:c1] = mag @ fb
    return np.log1p(1000.0 * out)


# ------------------------------------------------------------------ the network
def _erf(x):
    # Abramowitz-Stegun 7.1.26 (|error| < 1.5e-7): exact-GELU without scipy
    s = np.sign(x)
    a = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * a)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * \
        np.exp(-a * a)
    return s * y


class _NP:
    """numpy ops."""
    name = "numpy"

    @staticmethod
    def asarray(a):
        return np.asarray(a, np.float32)

    @staticmethod
    def gelu(x):
        return 0.5 * x * (1.0 + _erf(x * np.float32(1 / math.sqrt(2)))).astype(np.float32)

    @staticmethod
    def sigmoid(x):
        return 1.0 / (1.0 + np.exp(-x))

    @staticmethod
    def softmax(x):
        x = x - x.max(-1, keepdims=True)
        np.exp(x, out=x)
        x /= x.sum(-1, keepdims=True)
        return x

    @staticmethod
    def numpy(x):
        return np.asarray(x)

    @staticmethod
    def linear(x, wt):
        # numpy's matmul only reaches BLAS for contiguous 2-D operands: flatten the batch dims first
        s = x.shape
        y = np.ascontiguousarray(x).reshape(-1, s[-1]) @ wt
        return y.reshape(s[:-1] + (wt.shape[1],))

    transpose = staticmethod(np.transpose)
    reshape = staticmethod(np.reshape)
    concatenate = staticmethod(np.concatenate)
    sqrt = staticmethod(np.sqrt)
    maximum = staticmethod(np.maximum)
    stack = staticmethod(np.stack)
    pad = staticmethod(lambda x, w: np.pad(x, w))
    zeros = staticmethod(lambda s: np.zeros(s, np.float32))
    sum = staticmethod(lambda x, axis, keepdims=False: x.sum(axis=axis, keepdims=keepdims))

    def sdpa(self, q, k, v, scale):
        # q, k, v: (B, H, N, D); chunked over the batch so a 1500x1500 score matrix per head never piles up
        B, H, N, _ = q.shape
        out = np.empty_like(q)
        per = max(1, int(6e7 // (H * N * N)))
        q, k, v = (np.ascontiguousarray(a) for a in (q, k, v))
        for b0 in range(0, B, per):
            s = np.matmul(q[b0:b0 + per] * np.float32(scale), np.ascontiguousarray(np.swapaxes(k[b0:b0 + per], -1, -2)))
            out[b0:b0 + per] = np.matmul(self.softmax(s), v[b0:b0 + per])
        return out


class _MLX:
    """MLX ops (Apple silicon GPU)."""
    name = "mlx"

    def __init__(self):
        import mlx.core as mx
        self.mx = mx

    def asarray(self, a):
        return self.mx.array(np.asarray(a, np.float32))

    def gelu(self, x):
        return 0.5 * x * (1.0 + self.mx.erf(x * (1 / math.sqrt(2))))

    def sigmoid(self, x):
        return self.mx.sigmoid(x)

    def numpy(self, x):
        return np.array(x)

    def linear(self, x, wt):
        return x @ wt

    def transpose(self, x, axes):
        return self.mx.transpose(x, axes)

    def reshape(self, x, s):
        return self.mx.reshape(x, s)

    def concatenate(self, xs, axis=0):
        return self.mx.concatenate(xs, axis=axis)

    def sqrt(self, x):
        return self.mx.sqrt(x)

    def maximum(self, a, b):
        return self.mx.maximum(a, b)

    def stack(self, xs, axis=0):
        return self.mx.stack(xs, axis=axis)

    def pad(self, x, w):
        return self.mx.pad(x, w)

    def zeros(self, s):
        return self.mx.zeros(s)

    def sum(self, x, axis, keepdims=False):
        return self.mx.sum(x, axis=axis, keepdims=keepdims)

    def sdpa(self, q, k, v, scale):
        B, H, N, _ = q.shape
        per = max(1, int(1.5e8 // (H * N * N)))
        outs = []
        for b0 in range(0, B, per):
            o = self.mx.fast.scaled_dot_product_attention(q[b0:b0 + per], k[b0:b0 + per], v[b0:b0 + per], scale=scale)
            self.mx.eval(o)
            outs.append(o)
        return outs[0] if len(outs) == 1 else self.mx.concatenate(outs, axis=0)


def _backend(prefer="auto"):
    if prefer in ("auto", "mlx"):
        try:
            import mlx.core  # noqa: F401
            return _MLX()
        except Exception:  # noqa: BLE001 - no MLX (Intel Mac, Windows) -> numpy
            if prefer == "mlx":
                raise
    return _NP()


class BeatThis:
    """The Beat This! network (frontend: BN + conv stem, 3 blocks of partial freq/time RoFormers + conv; 6 RoFormer
    layers; a sum head). Weights from ``load_checkpoint``."""

    def __init__(self, ckpt, backend="auto"):
        hp = ckpt["hyper_parameters"]
        self.dim = int(hp.get("transformer_dim", 512))
        self.head_dim = int(hp.get("head_dim", 32))
        self.n_layers = int(hp.get("n_layers", 6))
        if not hp.get("partial_transformers", True) or not hp.get("sum_head", True):
            raise ValueError("only the published Beat This! configuration (partial transformers, sum head) is supported")
        sd = {k[len("model."):] if k.startswith("model.") else k: v for k, v in ckpt["state_dict"].items()}
        self.ops = _backend(backend)
        o = self.ops
        # linear / conv weights are stored transposed ((in, out), contiguous) for x @ W
        self.W = {k: o.asarray(np.ascontiguousarray(v.reshape(v.shape[0], -1).T) if k.endswith(".weight") and v.ndim >= 2
                               else v) for k, v in sd.items() if not k.endswith("num_batches_tracked")}
        self.np = {k: np.asarray(v, np.float32) for k, v in sd.items() if not k.endswith("num_batches_tracked")}
        fr = self.np["transformer_blocks.layers.0.0.rotary_embed.freqs"]
        self.freqs = fr
        self._rot = {}

    # -- helpers
    def _bn(self, x, p, axis):
        w, b, m, v = (self.np[f"{p}.{s}"] for s in ("weight", "bias", "running_mean", "running_var"))
        scale = w / np.sqrt(v + 1e-5)
        shift = b - m * scale
        shp = [1] * len(x.shape)
        shp[axis] = -1
        return x * self.ops.asarray(scale.reshape(shp)) + self.ops.asarray(shift.reshape(shp))

    def _lin(self, x, p, bias=True):
        y = self.ops.linear(x, self.W[f"{p}.weight"])
        return y + self.W[f"{p}.bias"] if bias else y

    def _rms(self, x, p):
        n = self.ops.sqrt(self.ops.sum(x * x, -1, keepdims=True))
        return x / self.ops.maximum(n, 1e-12) * (math.sqrt(x.shape[-1])) * self.W[f"{p}.gamma"]

    def _rope(self, n):
        if n not in self._rot:
            ang = np.arange(n, dtype=np.float32)[:, None] * self.freqs[None, :]
            ang = np.repeat(ang, 2, axis=1)                                 # interleaved pairs
            self._rot[n] = (self.ops.asarray(np.cos(ang)), self.ops.asarray(np.sin(ang)))
        return self._rot[n]

    def _rotate(self, t, cos, sin):
        o = self.ops
        s = t.shape
        pairs = o.reshape(t, s[:-1] + (s[-1] // 2, 2))
        x1, x2 = pairs[..., 0], pairs[..., 1]
        rh = o.reshape(o.stack([-x2, x1], axis=-1), s)
        return t * cos + rh * sin

    def _attn(self, x, p):
        o = self.ops
        B, N, C = x.shape
        H = C // self.head_dim
        x = self._rms(x, f"{p}.norm")
        qkv = self._lin(x, f"{p}.to_qkv", bias=False)                      # (B, N, 3*H*D)
        qkv = o.transpose(o.reshape(qkv, (B, N, 3, H, self.head_dim)), (2, 0, 3, 1, 4))
        cos, sin = self._rope(N)
        q = self._rotate(qkv[0], cos, sin)
        k = self._rotate(qkv[1], cos, sin)
        out = o.sdpa(q, k, qkv[2], self.head_dim ** -0.5)                   # (B, H, N, D)
        gates = o.sigmoid(self._lin(x, f"{p}.to_gates"))                    # (B, N, H)
        out = out * o.transpose(gates, (0, 2, 1))[..., None]
        out = o.reshape(o.transpose(out, (0, 2, 1, 3)), (B, N, H * self.head_dim))
        return o.linear(out, self.W[f"{p}.to_out.0.weight"])

    def _ff(self, x, p):
        h = self._rms(x, f"{p}.net.0")
        h = self.ops.gelu(self._lin(h, f"{p}.net.1"))
        return self._lin(h, f"{p}.net.4")

    def _conv(self, x, p, kf):
        """Conv2d over (C, F, T) with kernel (kf, 3), stride (kf, 1), padding (0, 1), no bias -> (C', F/kf, T)."""
        o = self.ops
        w = self.W[f"{p}.weight"]                                              # (Ci*kf*3, Co)
        C, F, T = x.shape
        xp = o.pad(x, [(0, 0), (0, 0), (1, 1)])
        Fo = F // kf
        # gather (Fo, T, Ci*kf*3) patches as kf*3 shifted views, then one matmul
        cols = []
        for a in range(kf):
            for b in range(3):
                cols.append(xp[:, a:a + Fo * kf:kf, b:b + T])                    # (Ci, Fo, T)
        pt = o.stack(cols, axis=-1)                                          # (Ci, Fo, T, kf*3)
        pt = o.reshape(o.transpose(pt, (1, 2, 0, 3)), (Fo * T, C * kf * 3))
        y = o.linear(pt, w)                                                  # (Fo*T, Co)
        return o.transpose(o.reshape(y, (Fo, T, w.shape[1])), (2, 0, 1))

    def logits(self, spect):
        """(T, 128) log-mel -> (beat, downbeat) logits, each (T,), numpy."""
        o = self.ops
        x = o.asarray(spect.T)                                               # (F, T)
        x = self._bn(x, "frontend.stem.bn1d", 0)
        x = self._conv(x[None], "frontend.stem.conv2d", 4)                   # (32, 32, T)
        x = o.gelu(self._bn(x, "frontend.stem.bn2d", 0))
        for i in range(3):
            p = f"frontend.blocks.{i}"
            C, F, T = x.shape
            h = o.transpose(x, (2, 1, 0))                                    # (T, F, C): attention over F
            h = h + self._attn(h, f"{p}.partial.attnF")
            h = h + self._ff(h, f"{p}.partial.ffF")
            h = o.transpose(h, (1, 0, 2))                                    # (F, T, C): attention over T
            h = h + self._attn(h, f"{p}.partial.attnT")
            h = h + self._ff(h, f"{p}.partial.ffT")
            x = o.transpose(h, (2, 0, 1))                                    # (C, F, T)
            x = o.gelu(self._bn(self._conv(x, f"{p}.conv2d", 2), f"{p}.norm", 0))
        C, F, T = x.shape
        h = o.reshape(o.transpose(x, (2, 0, 1)), (1, T, C * F))
        h = self._lin(h, "frontend.linear")
        for i in range(self.n_layers):
            p = f"transformer_blocks.layers.{i}"
            h = h + self._attn(h, f"{p}.0")
            h = h + self._ff(h, f"{p}.1")
        h = self._rms(h, "transformer_blocks.norm")
        bd = o.numpy(self._lin(h, "task_heads.beat_downbeat_lin"))[0]        # (T, 2)
        return bd[:, 0] + bd[:, 1], bd[:, 1]


# ------------------------------------------------------------------ inference + post-processing
def _split(spect):
    T = len(spect)
    starts = np.arange(-BORDER, T - BORDER, CHUNK - 2 * BORDER)
    if T > CHUNK - 2 * BORDER:
        starts[-1] = T - (CHUNK - BORDER)
    chunks = []
    for s in starts:
        c = spect[max(s, 0):min(s + CHUNK, T)]
        left, right = max(0, -s), max(0, min(BORDER, s + CHUNK - T))
        chunks.append(np.pad(c, ((left, right), (0, 0))))
    return chunks, starts


def frame_logits(model, spect):
    """Whole-piece logits (keep_first overlap, as the reference)."""
    T = len(spect)
    chunks, starts = _split(spect)
    beat = np.full(T, -1000.0, np.float32)
    down = np.full(T, -1000.0, np.float32)
    preds = [model.logits(c) for c in chunks]
    for s, (b, d) in reversed(list(zip(starts, preds))):
        b, d = b[BORDER:-BORDER], d[BORDER:-BORDER]
        lo, hi = s + BORDER, s + CHUNK - BORDER
        a0, a1 = max(lo, 0), min(hi, T)
        beat[a0:a1] = b[a0 - lo:a1 - lo]
        down[a0:a1] = d[a0 - lo:a1 - lo]
    return beat, down


def _dedup(frames, width=1):
    out = []
    it = iter(int(f) for f in frames)
    try:
        p = next(it)
    except StopIteration:
        return np.zeros(0)
    c = 1
    for p2 in it:
        if p2 - p <= width:
            c += 1
            p += (p2 - p) / c
        else:
            out.append(p)
            p, c = p2, 1
    out.append(p)
    return np.asarray(out, float)


def peaks(logits):
    """Frames that are the max within +-3 frames and above logit 0, adjacent ones merged -> seconds."""
    x = np.asarray(logits, np.float32)
    xp = np.pad(x, 3, constant_values=-np.inf)
    mx = np.lib.stride_tricks.sliding_window_view(xp, 7).max(1)
    return _dedup(np.nonzero((x == mx) & (x > 0))[0]) / FPS


def postprocess(beat_logits, down_logits):
    beats = peaks(beat_logits)
    downs = peaks(down_logits)
    if len(beats):
        downs = np.unique(beats[np.abs(beats[None, :] - downs[:, None]).argmin(1)]) if len(downs) else downs
    return beats, downs


_MODELS = {}


def model(path=None, backend="auto"):
    path = path or checkpoint_path()
    if not path:
        raise NotDownloaded("Beat This! checkpoint is not downloaded (models/beat_this/final0.ckpt)")
    key = (os.path.abspath(path), backend)
    if key not in _MODELS:
        _MODELS[key] = BeatThis(load_checkpoint(path), backend=backend)
    return _MODELS[key]


def _resample(x, sr):
    if sr == SR:
        return np.asarray(x, np.float32)
    n = int(round(len(x) * SR / sr))
    X = np.fft.rfft(np.asarray(x, np.float64))
    m = n // 2 + 1
    Y = np.zeros(m, complex)
    k = min(m, len(X))
    Y[:k] = X[:k]
    return (np.fft.irfft(Y, n) * (n / len(x))).astype(np.float32)


def track(x, sr, path=None, backend="auto"):
    """Mono (or (n, ch)) audio -> (beats, downbeats) in seconds."""
    x = np.asarray(x, np.float32)
    if x.ndim > 1:
        x = x.mean(1)
    spect = log_mel(_resample(x, sr))
    return postprocess(*frame_logits(model(path, backend), spect))


def track_file(path, ckpt=None, backend="auto"):
    from .audio import decode_audio
    return track(decode_audio(str(path), sr=SR, channels=1)[:, 0], SR, ckpt, backend)
