"""Bundled Python startup: make Pillow's existing Raqm/HarfBuzz use our pinned FriBiDi.

Copied to the runtime's site-packages/sitecustomize.py. Load only absolute paths
inside that runtime, before ImageFont initializes; never search PATH or the cwd.
No Pillow import here: non-visual engine commands keep their lazy imports.
"""
import ctypes
from pathlib import Path
import sys


def load_fribidi(root, platform):
    root = Path(root)
    if platform == "darwin":
        return None, ctypes.CDLL(str(root / "ffmpeg/lib/libfribidi.0.dylib"), mode=ctypes.RTLD_GLOBAL)
    if platform == "win32":
        import os
        directory = root / "ffmpeg/bin"
        # Pillow's shim uses these same names; accept only files in our locked runtime.
        library = next((directory / n for n in ("fribidi.dll", "fribidi-0.dll", "libfribidi-0.dll")
                        if (directory / n).is_file()), None)
        if library is None:
            raise FileNotFoundError("Bundled FriBiDi is missing; rebuild the engine runtime")
        search = os.add_dll_directory(str(directory))
        return search, ctypes.WinDLL(str(library))
    return None, None


if __name__ == "sitecustomize":
    # Keep both handles alive. Python's prefix is the bundled python/ folder on both platforms.
    _dll_directory, _fribidi = load_fribidi(Path(sys.prefix).resolve().parent, sys.platform)
