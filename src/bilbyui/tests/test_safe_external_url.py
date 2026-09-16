from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _safe_external_url


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestSafeExternalUrl(BilbyTestCase):
    def test_plain_http_url_is_returned_unchanged(self):
        self.assertEqual(_safe_external_url("http://example.com/results.tar.gz"), "http://example.com/results.tar.gz")

    def test_plain_https_url_is_returned_unchanged(self):
        self.assertEqual(_safe_external_url("https://example.com/results.tar.gz"), "https://example.com/results.tar.gz")

    def test_javascript_scheme_is_sanitised(self):
        self.assertEqual(_safe_external_url("javascript:alert(1)"), "")

    def test_data_scheme_is_sanitised(self):
        self.assertEqual(_safe_external_url("data:text/html,<script>alert(1)</script>"), "")

    def test_ftp_scheme_is_sanitised(self):
        self.assertEqual(_safe_external_url("ftp://example.com/results.tar.gz"), "")

    def test_protocol_relative_url_is_sanitised(self):
        self.assertEqual(_safe_external_url("//example.com/results.tar.gz"), "")

    def test_empty_value_is_sanitised(self):
        self.assertEqual(_safe_external_url(""), "")

    def test_none_value_is_sanitised(self):
        self.assertEqual(_safe_external_url(None), "")
