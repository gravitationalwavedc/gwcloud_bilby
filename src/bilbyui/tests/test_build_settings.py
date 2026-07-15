from bilbyui.tests.testcases import BilbyTestCase
from gw_bilby import build


class TestBuildSettings(BilbyTestCase):
    """Smoke test for the Docker build-time collectstatic settings module.

    build.py is only used at build time (collectstatic) and is otherwise
    unimported by the test suite, so it starts at 0% coverage. This asserts
    the values that guard the documented collectstatic intent.
    """

    def test_build_settings_values(self):
        self.assertFalse(build.DEBUG)
        self.assertEqual(build.ALLOWED_HOSTS, ["*"])

        self.assertEqual(
            build.STORAGES["staticfiles"]["BACKEND"],
            "bilbyui.utils.storage.NonStrictManifestStaticFilesStorage",
        )

        self.assertEqual(build.DATABASES["default"]["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(build.DATABASES["default"]["NAME"], ":memory:")

        self.assertEqual(build.ADACS_SSO_CLIENT_NAME, "gwcloud_bilby")
        self.assertEqual(build.ADACS_SSO_AUTH_HOST, "https://sso.adacs.org.au")
        self.assertEqual(build.ADACS_SSO_CLIENT_SECRET, "collectstatic-build-placeholder")
