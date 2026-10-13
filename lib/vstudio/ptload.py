"""Read a PyTorch ``.pth`` state dict into numpy arrays WITHOUT torch (the bundled runtime has no torch).

    from vstudio.ptload import load_state_dict
    sd = load_state_dict("realesr-general-x4v3.pth")      # {"params": {"body.0.weight": ndarray, ...}}

Only the zip format (torch >= 1.6 ``torch.save``) of plain tensors in (ordered) dicts / lists is understood. The
unpickler is restricted: it resolves the handful of torch / collections names a state dict uses and refuses any
other global, so a crafted file cannot run code.
"""
import collections
import pickle
import zipfile

import numpy as np

_DTYPES = {
    "FloatStorage": np.float32, "HalfStorage": np.float16, "DoubleStorage": np.float64,
    "BFloat16Storage": None, "LongStorage": np.int64, "IntStorage": np.int32, "ShortStorage": np.int16,
    "CharStorage": np.int8, "ByteStorage": np.uint8, "BoolStorage": np.bool_,
}


class _Storage:
    def __init__(self, name):
        self.name = name


def _rebuild_tensor(storage, offset, size, stride, *_rest):
    arr, = storage
    n = int(np.prod(size)) if size else 1
    if not size:
        return arr[offset].copy()
    item = arr.dtype.itemsize
    return np.lib.stride_tricks.as_strided(arr[offset:], shape=tuple(size),
                                           strides=tuple(s * item for s in stride)).copy() if n else \
        np.zeros(tuple(size), arr.dtype)


def _rebuild_parameter(data, *_rest):
    return data


class _Unpickler(pickle.Unpickler):
    def __init__(self, f, zf, prefix):
        super().__init__(f)
        self.zf, self.prefix, self.cache = zf, prefix, {}

    def find_class(self, module, name):
        if module == "collections" and name == "OrderedDict":
            return collections.OrderedDict
        if module == "torch._utils" and name in ("_rebuild_tensor_v2", "_rebuild_tensor"):
            return _rebuild_tensor
        if module == "torch._utils" and name == "_rebuild_parameter":
            return _rebuild_parameter
        if module == "torch" and name in _DTYPES:
            return _Storage(name)
        raise pickle.UnpicklingError(f"ptload: refusing global {module}.{name}")

    def persistent_load(self, pid):
        kind, stype, key = pid[0], pid[1], str(pid[2])
        if kind != "storage" or not isinstance(stype, _Storage):
            raise pickle.UnpicklingError(f"ptload: unsupported persistent id {pid[:2]}")
        if key not in self.cache:
            raw = self.zf.read(f"{self.prefix}/data/{key}")
            if stype.name == "BFloat16Storage":     # bf16 -> f32: the high half of a float32
                u = np.frombuffer(raw, np.uint16).astype(np.uint32) << 16
                self.cache[key] = u.view(np.float32)
            else:
                self.cache[key] = np.frombuffer(raw, _DTYPES[stype.name])
        return (self.cache[key],)


def load_state_dict(path):
    """``torch.save``d object (dicts / lists / tensors) -> the same structure with numpy arrays."""
    with zipfile.ZipFile(path) as zf:
        pkl = next((n for n in zf.namelist() if n.endswith("/data.pkl")), None)
        if pkl is None:
            raise ValueError(f"{path}: not a torch zip checkpoint (legacy torch.save format is not supported)")
        prefix = pkl[: -len("/data.pkl")]
        with zf.open(pkl) as f:
            return _Unpickler(f, zf, prefix).load()
