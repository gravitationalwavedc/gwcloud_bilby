import importlib
import os
import unittest
from unittest.mock import patch

import settings


class TestSettings(unittest.TestCase):
    def setUp(self):
        self.patchers = [
            patch.object(settings, "DB_PATH", "/tmp/test.db"),
            patch.object(settings, "GWCLOUD_TOKEN", "valid_token"),
            patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", "valid_secret"),
            patch.object(settings, "JOB_CONTROLLER_BUNDLE", "valid_bundle"),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()

    def test_missing_db_path_exits(self):
        with patch.object(settings, "DB_PATH", None):
            with self.assertRaises(SystemExit) as cm:
                settings.validate_settings()
            self.assertEqual(cm.exception.code, 1)

    def test_missing_gwcloud_token_exits(self):
        with patch.object(settings, "GWCLOUD_TOKEN", ""):
            with self.assertRaises(SystemExit) as cm:
                settings.validate_settings()
            self.assertEqual(cm.exception.code, 1)

    def test_missing_job_controller_jwt_secret_exits(self):
        with patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", None):
            with self.assertRaises(SystemExit) as cm:
                settings.validate_settings()
            self.assertEqual(cm.exception.code, 1)

    def test_missing_job_controller_bundle_exits(self):
        with patch.object(settings, "JOB_CONTROLLER_BUNDLE", None):
            with self.assertRaises(SystemExit) as cm:
                settings.validate_settings()
            self.assertEqual(cm.exception.code, 1)

    def test_all_valid_settings_passes(self):
        try:
            settings.validate_settings()
        except SystemExit:
            self.fail("validate_settings raised SystemExit unexpectedly")

    def test_env_defaults(self):
        with patch.dict(os.environ, {"DB_PATH": "/env/path.db"}):
            importlib.reload(settings)
            self.assertEqual(settings.DB_PATH, "/env/path.db")
            self.assertEqual(settings.MAX_FILES_PER_RUN, 50)


if __name__ == "__main__":
    unittest.main()
