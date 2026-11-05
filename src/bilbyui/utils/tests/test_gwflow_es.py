from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.gwflow_es import _parse_portal_bool


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestParsePortalBool(BilbyTestCase):
    def test_truthy_strings(self):
        for value in ("true", "1", "yes"):
            with self.subTest(value=value):
                self.assertTrue(_parse_portal_bool(value))

    def test_case_insensitive_truthy_strings(self):
        for value in ("TRUE", "Yes", "yEs", " 1 ", "YES"):
            with self.subTest(value=value):
                self.assertTrue(_parse_portal_bool(value))

    def test_falsy_strings(self):
        for value in ("false", "0", "no", "on", "off", ""):
            with self.subTest(value=value):
                self.assertFalse(_parse_portal_bool(value))

    def test_non_bool_non_str_falls_back_to_bool(self):
        self.assertFalse(_parse_portal_bool(0))
        self.assertTrue(_parse_portal_bool(1))

    def test_real_bool_passthrough(self):
        self.assertIs(_parse_portal_bool(True), True)
        self.assertIs(_parse_portal_bool(False), False)
