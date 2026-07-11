from django.test import RequestFactory, override_settings

from bilbyui.context_processors import google_analytics_id
from bilbyui.tests.testcases import BilbyTestCase


class TestGoogleAnalyticsContextProcessor(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(GOOGLE_ANALYTICS_ID="G-TEST123")
    def test_google_analytics_id_from_settings(self):
        request = self.factory.get("/")
        result = google_analytics_id(request)

        self.assertEqual(result, {"google_analytics_id": "G-TEST123"})

    @override_settings(GOOGLE_ANALYTICS_ID=None)
    def test_google_analytics_id_none_when_unset(self):
        request = self.factory.get("/")
        result = google_analytics_id(request)

        self.assertEqual(result, {"google_analytics_id": None})
