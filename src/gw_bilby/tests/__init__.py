from django.conf import settings
from django.test import TestCase, override_settings


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class ProdSettingsTestCase(TestCase):
    def test_prod_settings_importable(self):
        import gw_bilby.prod  # noqa: F401

        self.assertTrue(hasattr(settings, "DEBUG"))
