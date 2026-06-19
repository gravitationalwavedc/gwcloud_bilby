from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class TestProductionSettings(SimpleTestCase):
    def test_production_settings_configures_proxy_csrf(self):
        path = Path(settings.BASE_DIR) / "gw_bilby" / "production-settings.py"
        content = path.read_text()

        self.assertIn('SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")', content)
        self.assertIn('"https://gwcloud.org.au"', content)
        self.assertIn("CSRF_TRUSTED_ORIGINS", content)
