import os
import tempfile

from django.conf import settings
from django.test import TestCase, override_settings


@override_settings(
    IGNORE_ELASTIC_SEARCH=True,
    FILE_UPLOAD_TEMP_DIR=tempfile.gettempdir(),
)
class ProdSettingsTestCase(TestCase):
    def test_prod_settings_importable(self):
        os.environ.setdefault("GWOSC_INGEST_USER", "1")
        os.environ.setdefault("PERMITTED_EVENT_CREATION_USER_IDS", "[]")
        os.environ.setdefault("CLUSTERS", "[]")
        import gw_bilby.prod  # noqa: F401

        self.assertTrue(hasattr(settings, "DEBUG"))
