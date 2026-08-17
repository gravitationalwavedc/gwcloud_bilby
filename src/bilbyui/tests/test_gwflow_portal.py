import requests
import responses
from django.core.cache import caches
from django.test import TestCase, override_settings

from bilbyui.utils import gwflow_portal

PORTAL_URL = "https://portal.example.com"
PORTAL_TOKEN = "test-token-uuid"

SUPEREVENT_PATH = "/api/v1/superevents/S230601ag/"


@override_settings(CBCFLOW_PORTAL_URL=PORTAL_URL, CBCFLOW_PORTAL_TOKEN=PORTAL_TOKEN)
class TestGWFlowPortalClient(TestCase):
    def setUp(self):
        caches["default"].clear()

    @responses.activate
    def test_live_response_cached(self):
        payload = {"sname": "S230601ag", "foo": "bar"}
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json=payload, status=200)

        data, state = gwflow_portal.get_superevent("S230601ag")

        self.assertEqual(state, "live")
        self.assertEqual(data, payload)
        self.assertEqual(caches["default"].get("gwflow:se:S230601ag"), payload)

    @responses.activate
    def test_stale_on_failure_with_cache(self):
        payload = {"sname": "S230601ag"}
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json=payload, status=200)
        gwflow_portal.get_superevent("S230601ag")

        responses.reset()
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", status=500)

        data, state = gwflow_portal.get_superevent("S230601ag")

        self.assertEqual(state, "stale")
        self.assertEqual(data, payload)
        self.assertEqual(len(responses.calls), 0)

    @responses.activate
    def test_stale_on_connection_error_with_cache(self):
        payload = {"sname": "S230601ag"}
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json=payload, status=200)
        gwflow_portal.get_superevent("S230601ag")

        responses.reset()
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", body=requests.ConnectionError("boom"))

        data, state = gwflow_portal.get_superevent("S230601ag")

        self.assertEqual(state, "stale")
        self.assertEqual(data, payload)

    @responses.activate
    def test_down_on_failure_without_cache(self):
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", status=500)

        data, state = gwflow_portal.get_superevent("S230601ag")

        self.assertEqual(state, "down")
        self.assertIsNone(data)

    @responses.activate
    def test_down_on_connection_error_without_cache(self):
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", body=requests.ConnectionError("boom"))

        data, state = gwflow_portal.get_superevent("S230601ag")

        self.assertEqual(state, "down")
        self.assertIsNone(data)

    @responses.activate
    def test_down_on_non_json_200_response_without_cache(self):
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", body="<html>proxy error</html>", status=200)

        data, state = gwflow_portal.get_superevent("S230601ag")

        self.assertEqual(state, "down")
        self.assertIsNone(data)

    @responses.activate
    def test_unconfigured_settings_logs_warning(self):
        with override_settings(CBCFLOW_PORTAL_URL=None, CBCFLOW_PORTAL_TOKEN=None):
            with self.assertLogs("bilbyui.utils.gwflow_portal", level="WARNING") as cm:
                data, state = gwflow_portal.get_superevent("S230601ag")

        self.assertEqual(state, "down")
        self.assertIsNone(data)
        self.assertIn("not configured", cm.output[0])

    @responses.activate
    def test_cache_hit_within_ttl_no_http_call(self):
        payload = {"sname": "S230601ag"}
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json=payload, status=200)
        gwflow_portal.get_superevent("S230601ag")

        data, state = gwflow_portal.get_superevent("S230601ag")

        self.assertEqual(state, "stale")
        self.assertEqual(data, payload)
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_cache_clear_forces_http_call(self):
        payload = {"sname": "S230601ag"}
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json=payload, status=200)
        gwflow_portal.get_superevent("S230601ag")

        caches["default"].clear()
        gwflow_portal.get_superevent("S230601ag")

        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    def test_authorization_header_raw_token(self):
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json={}, status=200)

        gwflow_portal.get_superevent("S230601ag")

        self.assertEqual(responses.calls[0].request.headers["Authorization"], PORTAL_TOKEN)

    @responses.activate
    def test_wrapper_urls_and_cache_keys(self):
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json={}, status=200)
        responses.add(responses.GET, f"{PORTAL_URL}/api/v1/superevents/S230601ag/versions/", json={}, status=200)
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/superevents/S230601ag/versions/abc123/",
            json={},
            status=200,
        )

        gwflow_portal.get_superevent("S230601ag")
        gwflow_portal.get_versions("S230601ag")
        gwflow_portal.get_version("S230601ag", "abc123")

        self.assertEqual(len(responses.calls), 3)
        self.assertEqual(responses.calls[0].request.url, f"{PORTAL_URL}{SUPEREVENT_PATH}")
        self.assertEqual(responses.calls[1].request.url, f"{PORTAL_URL}/api/v1/superevents/S230601ag/versions/")
        self.assertEqual(responses.calls[2].request.url, f"{PORTAL_URL}/api/v1/superevents/S230601ag/versions/abc123/")
        self.assertIn("gwflow:se:S230601ag", caches["default"])
        self.assertIn("gwflow:versions:S230601ag", caches["default"])
        self.assertIn("gwflow:version:S230601ag:abc123", caches["default"])
