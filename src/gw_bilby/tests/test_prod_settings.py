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
        os.environ["GWOSC_INGEST_USER"] = "1"
        os.environ["GWFLOW_INGEST_USER"] = "1"
        os.environ["PERMITTED_EVENT_CREATION_USER_IDS"] = "[]"
        os.environ["CLUSTERS"] = "[]"

        self.assertTrue(hasattr(settings, "DEBUG"))
