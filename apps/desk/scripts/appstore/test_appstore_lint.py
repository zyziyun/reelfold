"""Tests for the App Store lint (run: npm run test:appstore, or python3 -m unittest discover -s scripts/appstore)."""
import json
import os
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import appstore_lint as L  # noqa: E402

DENY = L.load_denylist()
MAC = sys.platform == "darwin" and shutil.which("cc") and shutil.which("nm") and shutil.which("codesign")


class DenylistTest(unittest.TestCase):
    def test_the_rejection_list_is_in_the_data_file(self):
        names = {p for p, _ in DENY}
        for s in ["_Tcl_*", "_TclBN_*", "_Tk_*", "_NSWindowDidOrderOnScreenNotification", "_sgemm", "_xerbla_array__",
                  "_lsame_", "_dcabs1_", "_OBJC_CLASS_$_CALayerHost"]:
            self.assertIn(s, names)
        self.assertEqual(dict(DENY)["_sgemm"], "Accelerate")
        self.assertIsNone(dict(DENY)["_Tcl_*"])
        self.assertEqual(len([p for p, lib in DENY if lib == "Accelerate"]), 43)   # Apple's list, one entry each


class SymbolRuleTest(unittest.TestCase):
    NM = """                 (undefined) external _Tcl_CreateInterp (from libtcl9)
                 (undefined) external _sgemm (from Accelerate)
                 (undefined) external _dgesv_ (from Accelerate)
                 (undefined) external _cblas_sgemm (from Accelerate)
                 (undefined) external _cblas_sgemm$NEWLAPACK (from Accelerate)
                 (undefined) external _dgemm$NEWLAPACK$ILP64 (from Accelerate)
                 (undefined) external _vDSP_fft_zrip (from Accelerate)
                 (undefined) external _vvsqrtf (from Accelerate)
                 (undefined) external _BNNSFilterDestroy (from Accelerate)
                 (undefined) external _foo_bar__ (from Accelerate)
                 (undefined) external _sgemm (from libfoo)
                 (undefined) external _Tk_Init (dynamically looked up)
                 (undefined) external _OBJC_CLASS_$_CALayerHost (from QuartzCore)
                 (undefined) external _malloc (from libSystem)
"""

    def test_parse_nm(self):
        syms = L.parse_nm(self.NM)
        self.assertIn(("_sgemm", "Accelerate"), syms)
        self.assertIn(("_Tk_Init", ""), syms)
        self.assertEqual(len(syms), 14)

    def test_flags_what_app_review_rejects_and_nothing_public(self):
        bad, legacy = L.symbol_problems(L.parse_nm(self.NM), DENY)
        flagged = {b.split(" ")[0] for b in bad}
        self.assertEqual(flagged, {"_Tcl_CreateInterp", "_sgemm", "_foo_bar__", "_Tk_Init", "_OBJC_CLASS_$_CALayerHost"})
        # an unprefixed BLAS name bound elsewhere is not Accelerate's
        self.assertEqual(sum(1 for b in bad if b.startswith("_sgemm ")), 1)
        self.assertEqual(sorted(legacy), ["_cblas_sgemm", "_dgesv_"])

    def test_accelerate_kinds(self):
        k = L.accelerate_kind
        self.assertEqual(k("_caxpy", "Accelerate"), "bad")
        self.assertEqual(k("_xerbla_array__", "vecLib"), "bad")
        self.assertEqual(k("_caxpy$NEWLAPACK", "Accelerate"), None)
        self.assertEqual(k("_sgesv_", "Accelerate"), "legacy")
        self.assertEqual(k("_clapack_sgesv", "Accelerate"), "legacy")
        self.assertEqual(k("_la_matrix_from_float_buffer", "Accelerate"), None)
        self.assertEqual(k("_sparse_matrix_create_float", "Accelerate"), None)
        self.assertEqual(k("_caxpy", "libSystem"), None)


class EntitlementRuleTest(unittest.TestCase):
    APP = {"com.apple.security.app-sandbox": True, "com.apple.security.network.client": True,
           "com.apple.security.application-groups": ["T.app.reelfold.desk"], "com.apple.application-identifier": "T.x"}

    def test_app(self):
        self.assertEqual(L.entitlement_problems(self.APP, "app"), [])
        p = L.entitlement_problems({**self.APP, "com.apple.security.network.server": True}, "app")
        self.assertTrue(any("network.server" in m for m in p), p)
        p = L.entitlement_problems({**self.APP, "com.apple.security.cs.disable-library-validation": True}, "app")
        self.assertTrue(any("unexpected" in m for m in p), p)
        self.assertTrue(L.entitlement_problems({"com.apple.security.network.client": True}, "app"))

    def test_child_and_login(self):
        ok = {"com.apple.security.app-sandbox": True, "com.apple.security.inherit": True}
        self.assertEqual(L.entitlement_problems(ok, "child"), [])
        self.assertTrue(L.entitlement_problems({**ok, "com.apple.security.network.client": True}, "child"))
        self.assertTrue(L.entitlement_problems({"com.apple.security.app-sandbox": True}, "child"))
        self.assertEqual(L.entitlement_problems({"com.apple.security.app-sandbox": True}, "login"), [])

    def test_the_repository_entitlement_files_pass(self):
        out = L.check_entitlement_files(os.path.join(L.DESK, "packaging", "mac"), log=lambda m: None)
        self.assertEqual(out, [])

    def test_roles(self):
        app = "/x/Reelfold.app"
        self.assertEqual(L.role_of(f"{app}/Contents/MacOS/Reelfold", app), "app")
        self.assertEqual(L.role_of(f"{app}/Contents/Library/LoginItems/H.app/Contents/MacOS/H", app), "login")
        self.assertEqual(L.role_of(f"{app}/Contents/Resources/runtime/python/bin/python3.12", app), "child")


class StringsTest(unittest.TestCase):
    def test_itms_services_in_python_files(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "urllib"))
            with open(os.path.join(d, "urllib", "parse.py"), "w") as f:
                f.write("uses_netloc = ['', 'ftp', 'itms-services']\n")
            with open(os.path.join(d, "ok.py"), "w") as f:
                f.write("x = 1\n")
            out = L.check_strings(d, log=lambda m: None)
            self.assertEqual([os.path.basename(p) for p, _ in out], ["parse.py"])
        finally:
            shutil.rmtree(d)


class AsarTest(unittest.TestCase):
    @staticmethod
    def write_asar(path, top):
        tree = json.dumps({"files": {k: {"files": {}} if "." not in k else {"size": 1, "offset": "0"} for k in top}}).encode()
        pad = (4 - len(tree) % 4) % 4
        with open(path, "wb") as f:
            f.write(struct.pack("<4I", 4, len(tree) + pad + 8, len(tree) + pad + 4, len(tree)) + tree + b"\0" * pad + b"x")

    def test_only_the_built_app_in_app_asar(self):
        d = tempfile.mkdtemp()
        try:
            res = os.path.join(d, "R.app", "Contents", "Resources")
            os.makedirs(res)
            self.write_asar(os.path.join(res, "app.asar"), ["out", "package.json", "node_modules"])
            self.assertEqual(L.check_asar(os.path.join(d, "R.app"), log=lambda m: None), [])
            self.write_asar(os.path.join(res, "app.asar"), ["out", "package.json", "build", "src", "tests"])
            out = L.check_asar(os.path.join(d, "R.app"), log=lambda m: None)
            self.assertEqual(len(out), 1)
            self.assertIn("build, src, tests", out[0][1][0])
            self.assertEqual(L.asar_top_level(os.path.join(res, "app.asar")), ["build", "out", "package.json", "src", "tests"])
        finally:
            shutil.rmtree(d)


@unittest.skipUnless(MAC, "macOS with the Xcode command line tools")
class MachOTest(unittest.TestCase):
    """A tiny real Mach-O importing denylisted symbols, signed ad hoc with and without network.server."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="asl-")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def build(self, name, src, *flags):
        c = os.path.join(self.d, name + ".c")
        with open(c, "w") as f:
            f.write(src)
        exe = os.path.join(self.d, name)
        subprocess.run(["cc", "-o", exe, c, *flags], check=True, capture_output=True)
        return exe

    def test_symbols_found_in_a_real_binary(self):
        src = ("extern void sgemm(void); extern void sgemm_(void); extern void Tcl_CreateInterp(void);\n"
               "int main(int c, char **v) { if (c > 5) { sgemm(); sgemm_(); Tcl_CreateInterp(); } return 0; }\n")
        self.build("bad", src, "-framework", "Accelerate", "-Wl,-U,_Tcl_CreateInterp")
        self.build("good", "int main(void) { return 0; }\n")
        out = L.check_symbols(self.d, DENY, log=lambda m: None)
        self.assertEqual([os.path.basename(p) for p, _ in out], ["bad"])
        self.assertTrue(any(m.startswith("_sgemm (from Accelerate)") for m in out[0][1]), out)
        self.assertTrue(any(m.startswith("_Tcl_CreateInterp") for m in out[0][1]), out)
        self.assertFalse(any(m.startswith("_sgemm_ ") for m in out[0][1]), out)    # documented Fortran name: allowed

    def test_signed_entitlements_per_slice(self):
        app = os.path.join(self.d, "T.app")
        os.makedirs(os.path.join(app, "Contents", "MacOS"))
        os.makedirs(os.path.join(app, "Contents", "Resources", "bin"))
        main = os.path.join(app, "Contents", "MacOS", "T")
        child = os.path.join(app, "Contents", "Resources", "bin", "tool")
        shutil.copy(self.build("m", "int main(void) { return 0; }\n"), main)
        shutil.copy(self.build("c", "int main(void) { return 0; }\n"), child)

        def sign(path, ent):
            p = os.path.join(self.d, "e.plist")
            with open(p, "wb") as f:
                plistlib.dump(ent, f)
            subprocess.run(["codesign", "-s", "-", "-f", "--entitlements", p, path], check=True, capture_output=True)
        sign(child, {"com.apple.security.app-sandbox": True, "com.apple.security.inherit": True})
        sign(main, {"com.apple.security.app-sandbox": True, "com.apple.security.network.server": True})
        out = L.check_signed_entitlements(app, log=lambda m: None)
        self.assertEqual(len(out), 1, out)
        self.assertTrue(out[0][0].endswith("MacOS/T") and "network.server" in out[0][1][0], out)
        sign(main, {"com.apple.security.app-sandbox": True})
        self.assertEqual(L.check_signed_entitlements(app, log=lambda m: None), [])
        sign(child, {"com.apple.security.app-sandbox": True})                       # inherit missing
        self.assertEqual(len(L.check_signed_entitlements(app, log=lambda m: None)), 1)

    def test_quarantine(self):
        f = os.path.join(self.d, "q")
        open(f, "w").close()
        self.assertEqual(L.check_quarantine(self.d, log=lambda m: None), [])
        subprocess.run(["xattr", "-w", "com.apple.quarantine", "0081;00000000;test;", f], check=True)
        self.assertEqual([p for p, _ in L.check_quarantine(self.d, log=lambda m: None)], [f])


class ScanFailureTest(unittest.TestCase):
    def test_symbol_tool_failure_cannot_report_clean(self):
        with mock.patch.object(L, 'walk_files', return_value=['broken']), mock.patch.object(L, 'is_macho', return_value=True), mock.patch.object(L.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'unreadable')):
            self.assertIn('nm failed', str(L.check_symbols('root', DENY, lambda m: None)))

    def test_failed_architecture_enumeration_is_an_error(self):
        with mock.patch.object(L.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'bad slice')):
            with self.assertRaisesRegex(ValueError, 'cannot enumerate architectures'):
                L.archs('broken')

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS xattrs')
    def test_failed_quarantine_scan_is_an_error(self):
        with mock.patch.object(L.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'denied')):
            self.assertIn('quarantine scan failed', str(L.check_quarantine('root', lambda m: None)))


class BundleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = os.path.join(self.tmp.name, 'Reelfold.app')
        self.res = os.path.join(self.app, 'Contents', 'Resources')
        os.makedirs(self.res)
        self.info_path = os.path.join(self.app, 'Contents', 'Info.plist')
        self.info = dict(CFBundleIdentifier='app.reelfold.desk', ElectronTeamID='ZH47R7RVKB',
                         CFBundleShortVersionString='0.2.9', CFBundleVersion='20261015.1200.0',
                         ITSAppUsesNonExemptEncryption=False,
                         NSCameraUsageDescription='Record a video with your camera in Home > Record.',
                         NSMicrophoneUsageDescription='Record your voice with the microphone in Home > Record.')
        self.write_info()
        shutil.copy(os.path.join(L.DESK, 'packaging/mac/PrivacyInfo.xcprivacy'), self.res)
        # Real archive header shape, including the required nested files.
        tree = {'package.json': {'size': 0, 'offset': '0'}, 'out': {'files': {
            'main': {'files': {'index.cjs': {'size': 0, 'offset': '0'}}},
            'preload': {'files': {'index.cjs': {'size': 0, 'offset': '0'}}},
            'renderer': {'files': {'index.html': {'size': 0, 'offset': '0'}}}}}}
        raw = json.dumps({'files': tree}).encode()
        with open(os.path.join(self.res, 'app.asar'), 'wb') as f:
            f.write(struct.pack('<4I', 4, len(raw) + 8, len(raw) + 4, len(raw)) + raw)

    def write_info(self):
        with open(self.info_path, 'wb') as f:
            plistlib.dump(self.info, f)

    def check(self):
        return L.check_bundle(self.app, True, os.path.join(L.DESK, 'packaging/mac'), lambda m: None)

    def test_complete_store_bundle(self):
        self.assertEqual(self.check(), [])

    def test_enabled_permissions_need_specific_purpose_strings(self):
        self.info.pop('NSCameraUsageDescription')
        self.info['NSMicrophoneUsageDescription'] = 'TODO'
        self.write_info()
        messages = str(self.check())
        self.assertIn('NSCameraUsageDescription', messages)
        self.assertIn('NSMicrophoneUsageDescription', messages)

    def test_incomplete_build_and_wrong_edition_fail(self):
        os.remove(os.path.join(self.res, 'app.asar'))
        os.makedirs(os.path.join(self.app, 'Contents/Frameworks/Squirrel.framework'))
        self.info['CFBundleVersion'] = '0.2.9-local.g123'
        self.write_info()
        messages = str(self.check())
        for expected in ('missing or invalid app archive', 'Squirrel.framework', 'CFBundleVersion'):
            self.assertIn(expected, messages)

    def test_missing_manifest_and_terminal_fail(self):
        os.remove(os.path.join(self.res, 'PrivacyInfo.xcprivacy'))
        os.makedirs(os.path.join(self.res, 'app.asar.unpacked/node_modules/node-pty'))
        messages = str(self.check())
        self.assertIn('privacy manifest', messages)
        self.assertIn('node-pty', messages)

    def test_sparse_archive_cannot_pass(self):
        AsarTest.write_asar(os.path.join(self.res, 'app.asar'), ['out', 'package.json'])
        self.assertIn('missing out/main/index.cjs', str(self.check()))

    def test_hardened_runtime_mic_entitlement_is_redundant_in_mas(self):
        ent = {'com.apple.security.app-sandbox': True, 'com.apple.security.device.audio-input': True}
        self.assertIn('hardened-runtime', str(L.entitlement_problems(ent, 'app')))

    def test_unknown_check_name_is_an_error(self):
        with self.assertRaises(SystemExit) as cm:
            L.main([self.app, '--only', 'bundel'])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
