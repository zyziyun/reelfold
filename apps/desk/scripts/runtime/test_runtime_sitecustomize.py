"""Trusted runtime-only loader; native shaping is also verified in bundle.mjs and packaged tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, sentinel

spec = importlib.util.spec_from_file_location("runtime_text_layout", Path(__file__).with_name("runtime_sitecustomize.py"))
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


class TextLayoutLoader(unittest.TestCase):
    def test_mac_loads_absolute_bundled_file_without_importing_pillow(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(loader.ctypes, "CDLL", return_value=sentinel.lib) as load:
            search, library = loader.load_fribidi(tmp, "darwin")
            self.assertIsNone(search)
            self.assertIs(library, sentinel.lib)
            load.assert_called_once_with(str(Path(tmp) / "ffmpeg/lib/libfribidi.0.dylib"), mode=loader.ctypes.RTLD_GLOBAL)

    def test_mac_load_error_is_visible_not_a_silent_basic_layout(self):
        with patch.object(loader.ctypes, "CDLL", side_effect=OSError("signature mismatch")):
            with self.assertRaisesRegex(OSError, "signature mismatch"):
                loader.load_fribidi("/private/runtime", "darwin")

    def test_windows_loads_only_bundled_dll_and_retains_search_handle(self):
        for name in ("fribidi.dll", "fribidi-0.dll", "libfribidi-0.dll"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp) / "ffmpeg/bin"
                directory.mkdir(parents=True)
                (directory / name).touch()
                with patch("os.add_dll_directory", return_value=sentinel.search, create=True) as search, \
                        patch.object(loader.ctypes, "WinDLL", return_value=sentinel.lib, create=True) as load:
                    self.assertEqual(loader.load_fribidi(tmp, "win32"), (sentinel.search, sentinel.lib))
                    search.assert_called_once_with(str(directory))
                    load.assert_called_once_with(str(directory / name))

    def test_missing_windows_library_does_not_search_path_or_cwd(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(loader.ctypes, "WinDLL", create=True) as load:
            with self.assertRaisesRegex(FileNotFoundError, "Bundled FriBiDi is missing"):
                loader.load_fribidi(tmp, "win32")
            load.assert_not_called()

    def test_other_python_installations_are_not_changed(self):
        with patch.object(loader.ctypes, "CDLL") as load:
            self.assertEqual(loader.load_fribidi("/private/runtime", "linux"), (None, None))
            load.assert_not_called()
