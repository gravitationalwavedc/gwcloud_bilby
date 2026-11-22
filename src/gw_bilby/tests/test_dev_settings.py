import os

from django.conf import settings
from django.test import TestCase, override_settings


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class DevSettingsTestCase(TestCase):
    def test_storage_dirs_live_under_external_storage_path(self):
        # Test settings inherit from dev settings, so this guards the dev
        # storage block against omitting one of the derived directories.
        for name in (
            "JOB_UPLOAD_STAGING_DIR",
            "JOB_UPLOAD_DIR",
            "FILE_UPLOAD_TEMP_DIR",
            "SUPPORTING_FILE_UPLOAD_DIR",
            "GWFLOW_FILE_UPLOAD_DIR",
        ):
            with self.subTest(setting=name):
                self.assertEqual(
                    os.path.dirname(getattr(settings, name)),
                    settings.EXTERNAL_STORAGE_PATH,
                )
