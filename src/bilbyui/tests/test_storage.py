from unittest.mock import patch

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
from django.test import TestCase, override_settings

from bilbyui.utils.storage import NonStrictManifestStaticFilesStorage


@override_settings(STATIC_URL="/static/", DEBUG=False)
class TestNonStrictManifestStaticFilesStorage(TestCase):
    def setUp(self):
        self.storage = NonStrictManifestStaticFilesStorage()

    def test_hashed_name_returns_original_on_missing_file(self):
        name = "nonexistent.css"
        result = self.storage.hashed_name(name)
        self.assertEqual(result, name)

    def test_hashed_name_returns_hashed_name_when_parent_succeeds(self):
        with patch.object(
            ManifestStaticFilesStorage,
            "hashed_name",
            return_value="test.a1b2c3d4.css",
        ) as mock_hashed_name:
            result = self.storage.hashed_name("test.css")
            self.assertEqual(result, "test.a1b2c3d4.css")
            mock_hashed_name.assert_called_once_with("test.css", None, None)

    def test_hashed_name_returns_original_when_parent_raises_value_error(self):
        with patch.object(
            ManifestStaticFilesStorage,
            "hashed_name",
            side_effect=ValueError,
        ):
            result = self.storage.hashed_name("broken.css")
            self.assertEqual(result, "broken.css")

    def test_url_returns_original_when_name_absent_from_manifest(self):
        name = "absent.css"
        result = self.storage.url(name)
        self.assertEqual(result, "/static/absent.css")
