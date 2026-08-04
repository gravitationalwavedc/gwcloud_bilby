import importlib
import os
import unittest
from unittest.mock import patch

import settings


class TestSettings(unittest.TestCase):
    def test_missing_db_path_exits(self):
        with patch.object(settings, "DB_PATH", None):
            with self.assertRaises(SystemExit) as cm:
                settings.validate_settings()
            self.assertEqual(cm.exception.code, 1)

    def test_valid_db_path_passes(self):
        with patch.object(settings, "DB_PATH", "/tmp/test.db"):
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
