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
            patch.object(settings, "ACCESSIBLE_FILE_SYSTEMS", ("fs_a", "fs_b")),
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


class TestAccessibleFileSystems(unittest.TestCase):
    """ST-1..ST-7: gwflow_cron/settings.py::ACCESSIBLE_FILE_SYSTEMS (design D3, §6.4).

    Covers env parsing (unset/blank/normal/whitespace) and validate_settings()'s
    fail-closed behaviour (unset, blank, empty-entry, duplicate-entry), plus a
    regression check that the four pre-existing required settings are still
    validated unchanged.
    """

    def setUp(self):
        # Only the four pre-existing required settings are patched valid here;
        # ACCESSIBLE_FILE_SYSTEMS is left to each test, since it is the subject
        # under test.
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

    def test_st1_unset_parses_to_empty_tuple_and_fails_closed(self):
        """ST-1: unset ACCESSIBLE_FILE_SYSTEMS parses to () and validate_settings exits 1."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ACCESSIBLE_FILE_SYSTEMS", None)
            importlib.reload(settings)
            self.assertEqual(settings.ACCESSIBLE_FILE_SYSTEMS, ())
        with patch.object(settings, "ACCESSIBLE_FILE_SYSTEMS", ()):
            with self.assertRaises(SystemExit) as cm:
                settings.validate_settings()
            self.assertEqual(cm.exception.code, 1)

    def test_st2_blank_parses_to_empty_tuple_and_fails_closed(self):
        """ST-2: a blank ACCESSIBLE_FILE_SYSTEMS parses to () and validate_settings exits 1."""
        with patch.dict(os.environ, {"ACCESSIBLE_FILE_SYSTEMS": ""}):
            importlib.reload(settings)
            self.assertEqual(settings.ACCESSIBLE_FILE_SYSTEMS, ())
        with patch.object(settings, "ACCESSIBLE_FILE_SYSTEMS", ()):
            with self.assertRaises(SystemExit) as cm:
                settings.validate_settings()
            self.assertEqual(cm.exception.code, 1)

    def test_st3_normal_parse_preserves_order(self):
        """ST-3: comma-separated values parse into an ordered tuple; rank is preserved."""
        with patch.dict(os.environ, {"ACCESSIBLE_FILE_SYSTEMS": "CIT,LDAS,ARGONNE"}):
            importlib.reload(settings)
            self.assertEqual(settings.ACCESSIBLE_FILE_SYSTEMS, ("CIT", "LDAS", "ARGONNE"))

    def test_st4_whitespace_around_entries_is_stripped(self):
        """ST-4: whitespace around entries is tolerated and stripped."""
        with patch.dict(os.environ, {"ACCESSIBLE_FILE_SYSTEMS": " fs_a , fs_b "}):
            importlib.reload(settings)
            self.assertEqual(settings.ACCESSIBLE_FILE_SYSTEMS, ("fs_a", "fs_b"))

    def test_st5_empty_entry_fails_closed(self):
        """ST-5: an empty entry (e.g. from 'a,,b') makes validate_settings exit 1."""
        with patch.object(settings, "ACCESSIBLE_FILE_SYSTEMS", ("a", "", "b")):
            with self.assertRaises(SystemExit) as cm:
                settings.validate_settings()
            self.assertEqual(cm.exception.code, 1)

    def test_st6_duplicate_entry_fails_closed(self):
        """ST-6: a duplicate entry makes validate_settings exit 1."""
        with patch.object(settings, "ACCESSIBLE_FILE_SYSTEMS", ("fs_a", "fs_b", "fs_a")):
            with self.assertRaises(SystemExit) as cm:
                settings.validate_settings()
            self.assertEqual(cm.exception.code, 1)

    def test_st7_preexisting_required_settings_still_validated_unchanged(self):
        """ST-7: the four pre-existing required settings are still validated, unchanged."""
        with patch.object(settings, "ACCESSIBLE_FILE_SYSTEMS", ("fs_a", "fs_b")):
            with patch.object(settings, "DB_PATH", None):
                with self.assertRaises(SystemExit) as cm:
                    settings.validate_settings()
                self.assertEqual(cm.exception.code, 1)
            with patch.object(settings, "GWCLOUD_TOKEN", ""):
                with self.assertRaises(SystemExit) as cm:
                    settings.validate_settings()
                self.assertEqual(cm.exception.code, 1)
            with patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", None):
                with self.assertRaises(SystemExit) as cm:
                    settings.validate_settings()
                self.assertEqual(cm.exception.code, 1)
            with patch.object(settings, "JOB_CONTROLLER_BUNDLE", None):
                with self.assertRaises(SystemExit) as cm:
                    settings.validate_settings()
                self.assertEqual(cm.exception.code, 1)
            # A fully valid combination (including ACCESSIBLE_FILE_SYSTEMS) still passes.
            try:
                settings.validate_settings()
            except SystemExit:
                self.fail("validate_settings raised SystemExit unexpectedly")


if __name__ == "__main__":
    unittest.main()
