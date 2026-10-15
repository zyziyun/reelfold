import importlib.metadata as md
import unittest
from unittest.mock import patch

import check_requirements as C


class OpenCVProviderTest(unittest.TestCase):
    def test_contrib_satisfies_the_same_cv2_api_without_a_competing_base_wheel(self):
        def version(name):
            if name == 'opencv-contrib-python':
                return '5.0.0.93'
            raise md.PackageNotFoundError(name)
        with patch.object(C.md, 'version', side_effect=version), patch.object(C.importlib, 'import_module') as load:
            row = C.check('opencv-python')[0]
        self.assertNotIn('error', row)
        self.assertEqual(row['distribution'], 'opencv-contrib-python')
        load.assert_called_once_with('cv2')

    def test_no_opencv_distribution_is_still_a_failure(self):
        with patch.object(C.md, 'version', side_effect=md.PackageNotFoundError('opencv')):
            row = C.check('opencv-python')[0]
        self.assertIn('error', row)
