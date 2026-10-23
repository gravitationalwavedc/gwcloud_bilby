from datetime import UTC, datetime
from unittest import mock

import requests
import responses
from django.core.cache import caches
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils import gwflow_portal

PORTAL_URL = "https://portal.example.com"
PORTAL_TOKEN = "test-token-uuid"
SNAME = "S230601ag"
SUPEREVENT_PATH = f"/api/v1/superevents/{SNAME}/"
VERSION_PATH = f"/api/v1/superevents/{SNAME}/versions/7/"
DIFF_PATH = f"/api/v1/superevents/{SNAME}/diff/?baseline=3&selected=7"


def canonical_detail(**overrides):
    payload = {
        "sname": SNAME,
        "libraries": ["cbc-workflow-o4a"],
        "version_number": 7,
        "record_timestamp": "2026-08-10T12:00:00Z",
        "commit_sha": "abc123",
        "is_current": True,
        "analyses": [],
        "detector_configurations": [],
        "gracedb_events": [],
        "catalog_connections": [],
        "raw_payload": {"GraceDB": {"Events": [{"gpstime": 1234567890.5}]}},
    }
    payload.update(overrides)
    return payload


@override_settings(CBCFLOW_PORTAL_URL=PORTAL_URL, CBCFLOW_PORTAL_TOKEN=PORTAL_TOKEN)
class TestGWFlowPortalClient(BilbyTestCase):
    def setUp(self):
        caches["default"].clear()

    @responses.activate
    def test_get_version_integer_uses_canonical_route(self):
        payload = canonical_detail()
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/superevents/{SNAME}/versions/7/",
            json=payload,
            status=200,
        )

        self.assertEqual(gwflow_portal.get_version(SNAME, 7), (payload, "live"))
        self.assertEqual(
            responses.calls[0].request.url,
            f"{PORTAL_URL}/api/v1/superevents/{SNAME}/versions/7/",
        )

    @responses.activate
    def test_get_version_sha_resolves_to_summary_version_number(self):
        sha = "0123456789abcdef"
        payload = canonical_detail(commit_sha=sha, version_number=12)
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/superevents/{SNAME}/versions/?page=1",
            json={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [{"commit_sha": sha, "version_number": 12}],
            },
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/superevents/{SNAME}/versions/12/",
            json=payload,
            status=200,
        )

        self.assertEqual(gwflow_portal.get_version(SNAME, sha), (payload, "live"))
        self.assertEqual(
            [call.request.url for call in responses.calls],
            [
                f"{PORTAL_URL}/api/v1/superevents/{SNAME}/versions/?page=1",
                f"{PORTAL_URL}/api/v1/superevents/{SNAME}/versions/12/",
            ],
        )

    @responses.activate
    def test_get_version_unknown_sha_fails_without_sha_detail_request(self):
        sha = "unknown-sha"
        responses.add(
            responses.GET,
            f"{PORTAL_URL}/api/v1/superevents/{SNAME}/versions/?page=1",
            json={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [{"commit_sha": "known-sha", "version_number": 13}],
            },
            status=200,
        )

        self.assertEqual(gwflow_portal.get_version(SNAME, sha), (None, "failed"))
        self.assertEqual(len(responses.calls), 1)
        self.assertNotIn(
            f"/versions/{sha}/",
            responses.calls[0].request.url,
        )

    @responses.activate
    def test_live_response_cached(self):
        payload = canonical_detail()
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json=payload, status=200)

        data, state = gwflow_portal.get_superevent(SNAME)

        self.assertEqual(state, "live")
        self.assertEqual(data, payload)
        self.assertEqual(caches["default"].get(f"gwflow:se:{SNAME}"), payload)

    @responses.activate
    def test_cache_hit_within_ttl_returns_stale_without_http(self):
        payload = canonical_detail()
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json=payload, status=200)

        gwflow_portal.get_superevent(SNAME)
        data, state = gwflow_portal.get_superevent(SNAME)

        self.assertEqual((data, state), (payload, "stale"))
        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(gwflow_portal.CACHE_TTL, 60 * 10)

    @responses.activate
    def test_cache_clear_forces_http_call(self):
        payload = canonical_detail()
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json=payload, status=200)

        gwflow_portal.get_superevent(SNAME)
        caches["default"].clear()
        gwflow_portal.get_superevent(SNAME)

        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    def test_raw_payload_null_passthrough_live(self):
        payload = canonical_detail(raw_payload=None)
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json=payload, status=200)

        data, state = gwflow_portal.get_superevent(SNAME)

        self.assertEqual(state, "live")
        self.assertIsNone(data["raw_payload"])

    @responses.activate
    def test_raw_payload_null_passthrough_stale(self):
        payload = canonical_detail(raw_payload=None)
        responses.add(responses.GET, f"{PORTAL_URL}{VERSION_PATH}", json=payload, status=200)

        gwflow_portal.get_version(SNAME, 7)
        data, state = gwflow_portal.get_version(SNAME, 7)

        self.assertEqual(state, "stale")
        self.assertIsNone(data["raw_payload"])
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_empty_canonical_collections_are_valid(self):
        payload = canonical_detail()
        responses.add(responses.GET, f"{PORTAL_URL}{VERSION_PATH}", json=payload, status=200)

        data, state = gwflow_portal.get_version(SNAME, 7)

        self.assertEqual((data, state), (payload, "live"))

    @responses.activate
    def test_populated_canonical_collections_are_valid(self):
        payload = canonical_detail(
            analyses=[{"pipeline": "bilby"}],
            detector_configurations=[{"detector": "H1"}],
            gracedb_events=[{"uid": "G123"}],
            catalog_connections=[{"catalog": "GWTC"}],
        )
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json=payload, status=200)

        data, state = gwflow_portal.get_superevent(SNAME)

        self.assertEqual((data, state), (payload, "live"))

    def _assert_version_collection_is_malformed(self, field, value):
        with responses.RequestsMock() as mocked:
            mocked.add(
                responses.GET,
                f"{PORTAL_URL}{VERSION_PATH}",
                json=canonical_detail(**{field: value}),
                status=200,
            )
            with self.assertLogs(
                "bilbyui.utils.gwflow_portal",
                level="ERROR",
            ) as logs:
                data, state = gwflow_portal.get_version(SNAME, 7)

        self.assertEqual((data, state), (None, "malformed"))
        self.assertIn(VERSION_PATH, "\n".join(logs.output))
        self.assertIn(SNAME, "\n".join(logs.output))

    def test_null_analyses_is_malformed(self):
        self._assert_version_collection_is_malformed("analyses", None)

    def test_null_detector_configurations_is_malformed(self):
        self._assert_version_collection_is_malformed(
            "detector_configurations",
            None,
        )

    def test_null_gracedb_events_is_malformed(self):
        self._assert_version_collection_is_malformed("gracedb_events", None)

    def test_null_catalog_connections_is_malformed(self):
        self._assert_version_collection_is_malformed(
            "catalog_connections",
            None,
        )

    def test_non_array_analyses_is_malformed(self):
        self._assert_version_collection_is_malformed(
            "analyses",
            {"unexpected": "object"},
        )

    def test_non_array_detector_configurations_is_malformed(self):
        self._assert_version_collection_is_malformed(
            "detector_configurations",
            {"unexpected": "object"},
        )

    def test_non_array_gracedb_events_is_malformed(self):
        self._assert_version_collection_is_malformed(
            "gracedb_events",
            {"unexpected": "object"},
        )

    def test_non_array_catalog_connections_is_malformed(self):
        self._assert_version_collection_is_malformed(
            "catalog_connections",
            {"unexpected": "object"},
        )

    def test_new_detail_root_types_are_validated(self):
        invalid_values = (
            ("sname", ""),
            ("sname", 123),
            ("record_timestamp", ""),
            ("record_timestamp", None),
            ("commit_sha", "   "),
            ("commit_sha", []),
            ("libraries", {}),
            ("version_number", "7"),
            ("version_number", True),
            ("is_current", 1),
            ("raw_payload", []),
        )
        for field, value in invalid_values:
            with self.subTest(field=field, value=value):
                self._assert_version_collection_is_malformed(field, value)

    @responses.activate
    def test_string_is_current_is_accepted(self):
        payload = canonical_detail(is_current="true")
        responses.add(
            responses.GET,
            f"{PORTAL_URL}{VERSION_PATH}",
            json=payload,
            status=200,
        )

        self.assertEqual(
            gwflow_portal.get_version(SNAME, 7),
            (payload, "live"),
        )

    @responses.activate
    def test_absent_raw_payload_is_accepted(self):
        payload = canonical_detail()
        del payload["raw_payload"]
        responses.add(
            responses.GET,
            f"{PORTAL_URL}{VERSION_PATH}",
            json=payload,
            status=200,
        )

        self.assertEqual(
            gwflow_portal.get_version(SNAME, 7),
            (payload, "live"),
        )

    @responses.activate
    def test_missing_required_root_field_rejected_with_context(self):
        payload = canonical_detail()
        del payload["commit_sha"]
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", json=payload, status=200)

        with self.assertLogs("bilbyui.utils.gwflow_portal", level="ERROR") as logs:
            data, state = gwflow_portal.get_superevent(SNAME)

        self.assertEqual((data, state), (None, "malformed"))
        output = "\n".join(logs.output)
        self.assertIn(SUPEREVENT_PATH, output)
        self.assertIn(SNAME, output)
        self.assertNotIn(f"gwflow:se:{SNAME}", caches["default"])

    @responses.activate
    def test_authorization_header_and_timeout_are_unchanged(self):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}{SUPEREVENT_PATH}",
            json=canonical_detail(),
            status=200,
        )

        with mock.patch("bilbyui.utils.gwflow_portal.requests.get", wraps=requests.get) as request_get:
            gwflow_portal.get_superevent(SNAME)

        self.assertEqual(responses.calls[0].request.headers["Authorization"], PORTAL_TOKEN)
        self.assertEqual(request_get.call_args.kwargs["timeout"], 10)

    @responses.activate
    def test_wrapper_urls_and_cache_keys(self):
        versions_path = f"/api/v1/superevents/{SNAME}/versions/"
        page_1_url = f"{PORTAL_URL}{versions_path}?page=1"
        page_2_url = f"{PORTAL_URL}{versions_path}?page=2"
        first = {"commit_sha": "first", "version_number": 1}
        second = {"commit_sha": "second", "version_number": 2}
        third = {"commit_sha": "third", "version_number": 3}
        responses.add(
            responses.GET,
            f"{PORTAL_URL}{SUPEREVENT_PATH}",
            json=canonical_detail(),
            status=200,
        )
        responses.add(
            responses.GET,
            page_1_url,
            json={
                "count": 3,
                "next": page_2_url,
                "previous": None,
                "results": [first, second],
            },
            status=200,
        )
        responses.add(
            responses.GET,
            page_2_url,
            json={
                "count": 3,
                "next": None,
                "previous": page_1_url,
                "results": [third],
            },
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PORTAL_URL}{VERSION_PATH}",
            json=canonical_detail(),
            status=200,
        )

        gwflow_portal.get_superevent(SNAME)
        versions, state = gwflow_portal.get_versions(SNAME)
        gwflow_portal.get_version(SNAME, 7)

        self.assertEqual((versions, state), ([first, second, third], "live"))
        self.assertEqual(
            [call.request.url for call in responses.calls],
            [
                f"{PORTAL_URL}{SUPEREVENT_PATH}",
                page_1_url,
                page_2_url,
                f"{PORTAL_URL}{VERSION_PATH}",
            ],
        )
        self.assertEqual(
            sum(call.request.url == page_1_url for call in responses.calls),
            1,
        )
        self.assertEqual(
            sum(call.request.url == page_2_url for call in responses.calls),
            1,
        )
        self.assertIn(f"gwflow:se:{SNAME}", caches["default"])
        self.assertEqual(
            caches["default"].get(f"gwflow:versions:{SNAME}"),
            [first, second, third],
        )
        self.assertIn(f"gwflow:version:{SNAME}:7", caches["default"])

    def test_resolve_current_version_uses_record_timestamp(self):
        summary = {
            "is_current": True,
            "commit_sha": "abc123",
            "version_number": 4,
            "record_timestamp": "2026-08-10T12:00:00Z",
            "commit_timestamp": "1999-01-01T00:00:00Z",
        }
        detail = canonical_detail()

        with (
            mock.patch.object(gwflow_portal, "get_versions", return_value=([summary], "live")),
            mock.patch.object(gwflow_portal, "get_version", return_value=(detail, "live")),
            mock.patch.object(
                gwflow_portal,
                "_gwflow_trigger_time_from_metadata",
                return_value=1234567890.5,
            ),
        ):
            result = gwflow_portal.resolve_current_version(SNAME)

        self.assertTrue(result.available)
        self.assertEqual(
            result.current_history_timestamp,
            datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
        )

    def test_resolve_current_version_with_null_raw_payload_is_unavailable(self):
        summary = {
            "is_current": True,
            "commit_sha": "abc123",
            "version_number": 4,
            "record_timestamp": "2026-08-10T12:00:00Z",
        }
        detail = canonical_detail(raw_payload=None)

        with (
            mock.patch.object(gwflow_portal, "get_versions", return_value=([summary], "live")),
            mock.patch.object(gwflow_portal, "get_version", return_value=(detail, "live")),
        ):
            result = gwflow_portal.resolve_current_version(SNAME)

        self.assertFalse(result.available)
        self.assertEqual(result.reason, "detail has no usable finite trigger time")

    def test_resolve_current_version_does_not_fall_back_to_commit_timestamp(self):
        summary = {
            "is_current": True,
            "commit_sha": "abc123",
            "version_number": 5,
            "commit_timestamp": "2026-08-10 12:00:00 UTC",
        }

        with mock.patch.object(
            gwflow_portal,
            "get_versions",
            return_value=([summary], "live"),
        ):
            result = gwflow_portal.resolve_current_version(SNAME)

        self.assertFalse(result.available)
        self.assertEqual(result.reason, "current summary has no usable record_timestamp")

    @responses.activate
    def test_versions_rejects_cross_origin_next(self):
        page_1_url = f"{PORTAL_URL}/api/v1/superevents/{SNAME}/versions/?page=1"
        responses.add(
            responses.GET,
            page_1_url,
            json={
                "count": 2,
                "next": "https://attacker.example/versions/?page=2",
                "previous": None,
                "results": [{"commit_sha": "first", "version_number": 9}],
            },
            status=200,
        )

        self.assertEqual(
            gwflow_portal.get_versions(SNAME),
            (None, "malformed"),
        )
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_versions_rejects_cyclic_next(self):
        page_1_url = f"{PORTAL_URL}/api/v1/superevents/{SNAME}/versions/?page=1"
        responses.add(
            responses.GET,
            page_1_url,
            json={
                "count": 1,
                "next": page_1_url,
                "previous": None,
                "results": [{"commit_sha": "first", "version_number": 10}],
            },
            status=200,
        )

        self.assertEqual(
            gwflow_portal.get_versions(SNAME),
            (None, "malformed"),
        )
        self.assertEqual(len(responses.calls), 1)

    def test_versions_envelope_requires_exact_keys_and_types(self):
        valid = {
            "count": 0,
            "next": None,
            "previous": None,
            "results": [],
        }
        invalid_envelopes = []
        for field in valid:
            missing = valid.copy()
            del missing[field]
            invalid_envelopes.append(missing)
        unexpected = valid.copy()
        unexpected["extra"] = True
        invalid_envelopes.extend(
            [
                unexpected,
                {**valid, "count": True},
                {**valid, "count": "0"},
                {**valid, "next": 2},
                {**valid, "previous": False},
                {**valid, "results": {}},
            ]
        )

        for envelope in invalid_envelopes:
            with self.subTest(envelope=envelope), responses.RequestsMock() as mocked:
                mocked.add(
                    responses.GET,
                    f"{PORTAL_URL}/api/v1/superevents/{SNAME}/versions/?page=1",
                    json=envelope,
                    status=200,
                )
                self.assertEqual(
                    gwflow_portal.get_versions(SNAME),
                    (None, "malformed"),
                )
                caches["default"].clear()

    def test_versions_cache_hit_returns_flattened_list_as_stale(self):
        flattened = [
            {"commit_sha": "first", "version_number": 6},
            {"commit_sha": "second", "version_number": 7},
        ]
        caches["default"].set(
            f"gwflow:versions:{SNAME}",
            flattened,
            gwflow_portal.CACHE_TTL,
        )

        with responses.RequestsMock() as mocked:
            self.assertEqual(
                gwflow_portal.get_versions(SNAME),
                (flattened, "stale"),
            )
            self.assertEqual(len(mocked.calls), 0)


@override_settings(CBCFLOW_PORTAL_URL=PORTAL_URL, CBCFLOW_PORTAL_TOKEN=PORTAL_TOKEN)
class TestPortalGetDirect(BilbyTestCase):
    PATH = SUPEREVENT_PATH
    CACHE_KEY = "gwflow:direct:test"

    def setUp(self):
        caches["default"].clear()

    @responses.activate
    def test_not_configured_returns_down(self):
        with override_settings(CBCFLOW_PORTAL_URL=None, CBCFLOW_PORTAL_TOKEN=None):
            with self.assertLogs("bilbyui.utils.gwflow_portal", level="WARNING") as logs:
                data, state = gwflow_portal.portal_get(
                    self.PATH,
                    cache_key=self.CACHE_KEY,
                )

        self.assertEqual((data, state), (None, "down"))
        self.assertIn("not configured", logs.output[0])

    @responses.activate
    def test_cached_returns_stale_without_http_call(self):
        payload = {"sname": SNAME}
        responses.add(responses.GET, f"{PORTAL_URL}{self.PATH}", json=payload, status=200)

        gwflow_portal.portal_get(self.PATH, cache_key=self.CACHE_KEY)
        data, state = gwflow_portal.portal_get(self.PATH, cache_key=self.CACHE_KEY)

        self.assertEqual((data, state), (payload, "stale"))
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_200_returns_live_and_caches(self):
        payload = {"sname": SNAME, "foo": "bar"}
        responses.add(responses.GET, f"{PORTAL_URL}{self.PATH}", json=payload, status=200)

        data, state = gwflow_portal.portal_get(self.PATH, cache_key=self.CACHE_KEY)

        self.assertEqual((data, state), (payload, "live"))
        self.assertEqual(caches["default"].get(self.CACHE_KEY), payload)

    @responses.activate
    @mock.patch("bilbyui.utils.gwflow_portal.time.sleep", return_value=None)
    def test_non_200_without_cache_returns_down(self, mock_sleep):
        responses.add(responses.GET, f"{PORTAL_URL}{self.PATH}", status=500)

        data, state = gwflow_portal.portal_get(self.PATH, cache_key=self.CACHE_KEY)

        self.assertEqual((data, state), (None, "down"))
        self.assertEqual(len(responses.calls), 3)
        self.assertEqual([call.args[0] for call in mock_sleep.call_args_list], [1.0, 2.0])

    @responses.activate
    @mock.patch("bilbyui.utils.gwflow_portal.time.sleep", return_value=None)
    def test_requests_exception_without_cache_returns_down(self, mock_sleep):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}{self.PATH}",
            body=requests.ConnectionError("boom"),
        )

        data, state = gwflow_portal.portal_get(self.PATH, cache_key=self.CACHE_KEY)

        self.assertEqual((data, state), (None, "down"))
        self.assertEqual(len(responses.calls), 3)
        self.assertEqual([call.args[0] for call in mock_sleep.call_args_list], [1.0, 2.0])

    @responses.activate
    def test_non_json_200_without_cache_returns_malformed(self):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}{self.PATH}",
            body="<html>proxy error</html>",
            status=200,
        )

        data, state = gwflow_portal.portal_get(
            self.PATH,
            cache_key=self.CACHE_KEY,
            sname=SNAME,
        )

        self.assertEqual((data, state), (None, "malformed"))
        self.assertIsNone(caches["default"].get(self.CACHE_KEY))

    @responses.activate
    def test_recursion_error_without_cache_returns_malformed(self):
        deeply_nested = "[" * 20000 + "]" * 20000
        responses.add(
            responses.GET,
            f"{PORTAL_URL}{self.PATH}",
            body=deeply_nested,
            status=200,
        )

        data, state = gwflow_portal.portal_get(
            self.PATH,
            cache_key=self.CACHE_KEY,
            sname=SNAME,
        )

        self.assertEqual((data, state), (None, "malformed"))
        self.assertIsNone(caches["default"].get(self.CACHE_KEY))

    @responses.activate
    def test_connection_failure_remains_down_not_malformed(self):
        responses.add(
            responses.GET,
            f"{PORTAL_URL}{self.PATH}",
            body=requests.Timeout("timed out"),
        )

        data, state = gwflow_portal.portal_get(self.PATH, cache_key=self.CACHE_KEY)

        self.assertEqual((data, state), (None, "down"))


@override_settings(CBCFLOW_PORTAL_URL=PORTAL_URL, CBCFLOW_PORTAL_TOKEN=PORTAL_TOKEN)
class TestPortalRetryAndDiff(BilbyTestCase):
    def setUp(self):
        caches["default"].clear()

    @responses.activate
    @mock.patch("bilbyui.utils.gwflow_portal.time.sleep", return_value=None)
    def test_500_then_200_retries_and_succeeds(self, mock_sleep):
        payload = canonical_detail()
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", status=500)
        responses.add(
            responses.GET,
            f"{PORTAL_URL}{SUPEREVENT_PATH}",
            json=payload,
            status=200,
        )

        data, state = gwflow_portal.get_superevent(SNAME)

        self.assertEqual((data, state), (payload, "live"))
        self.assertEqual(len(responses.calls), 2)
        mock_sleep.assert_called_once_with(1.0)

    @responses.activate
    @mock.patch("bilbyui.utils.gwflow_portal.time.sleep", return_value=None)
    def test_exhausted_5xx_uses_cache_that_appears_during_retry(self, mock_sleep):
        payload = canonical_detail()
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", status=503)
        cache = caches["default"]
        original_get = cache.get
        calls = 0

        def cache_get(key, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return None
            return payload

        with mock.patch.object(cache, "get", side_effect=cache_get):
            data, state = gwflow_portal.get_superevent(SNAME)

        self.assertEqual((data, state), (payload, "stale"))
        self.assertEqual(len(responses.calls), 3)
        self.assertEqual([call.args[0] for call in mock_sleep.call_args_list], [1.0, 2.0])
        self.assertIsNone(original_get("unused-key"))

    @responses.activate
    @mock.patch("bilbyui.utils.gwflow_portal.time.sleep", return_value=None)
    def test_exhausted_5xx_without_cache_is_down(self, mock_sleep):
        responses.add(responses.GET, f"{PORTAL_URL}{SUPEREVENT_PATH}", status=500)

        data, state = gwflow_portal.get_superevent(SNAME)

        self.assertEqual((data, state), (None, "down"))
        self.assertEqual(len(responses.calls), 3)
        self.assertEqual([call.args[0] for call in mock_sleep.call_args_list], [1.0, 2.0])

    @responses.activate
    @mock.patch("bilbyui.utils.gwflow_portal.time.sleep", return_value=None)
    def test_4xx_with_cold_cache_is_failed_and_not_retried(self, mock_sleep):
        for status_code in (400, 401, 403, 404):
            with self.subTest(status_code=status_code):
                responses.reset()
                caches["default"].clear()
                responses.add(
                    responses.GET,
                    f"{PORTAL_URL}{SUPEREVENT_PATH}",
                    status=status_code,
                )

                data, state = gwflow_portal.get_superevent(SNAME)

                self.assertEqual((data, state), (None, "failed"))
                self.assertEqual(len(responses.calls), 1)
        mock_sleep.assert_not_called()

    @responses.activate
    @mock.patch("bilbyui.utils.gwflow_portal.time.sleep", return_value=None)
    def test_4xx_with_late_warm_cache_is_stale_and_not_retried(
        self,
        mock_sleep,
    ):
        payload = canonical_detail()
        cache = caches["default"]

        for status_code in (400, 401, 403, 404):
            with self.subTest(status_code=status_code):
                responses.reset()
                cache.clear()
                responses.add(
                    responses.GET,
                    f"{PORTAL_URL}{SUPEREVENT_PATH}",
                    status=status_code,
                )
                cache_reads = 0

                def cache_get(key, *args, **kwargs):
                    nonlocal cache_reads
                    cache_reads += 1
                    return None if cache_reads == 1 else payload

                with mock.patch.object(cache, "get", side_effect=cache_get):
                    data, state = gwflow_portal.get_superevent(SNAME)

                self.assertEqual((data, state), (payload, "stale"))
                self.assertEqual(len(responses.calls), 1)
        mock_sleep.assert_not_called()

    @responses.activate
    @mock.patch("bilbyui.utils.gwflow_portal.time.sleep", return_value=None)
    def test_versions_4xx_with_late_warm_cache_is_stale_and_not_retried(
        self,
        mock_sleep,
    ):
        flattened = [{"commit_sha": "cached", "version_number": 8}]
        cache = caches["default"]
        page_1_url = f"{PORTAL_URL}/api/v1/superevents/{SNAME}/versions/?page=1"
        responses.add(responses.GET, page_1_url, status=404)
        cache_reads = 0

        def cache_get(key, *args, **kwargs):
            nonlocal cache_reads
            cache_reads += 1
            return None if cache_reads == 1 else flattened

        with mock.patch.object(cache, "get", side_effect=cache_get):
            data, state = gwflow_portal.get_versions(SNAME)

        self.assertEqual((data, state), (flattened, "stale"))
        self.assertEqual(len(responses.calls), 1)
        mock_sleep.assert_not_called()

    @responses.activate
    def test_get_diff_golden_passthrough_url_and_cache_key(self):
        changes = [
            {
                "entity_type": "analysis",
                "operation": "modified",
                "path": ["analyses", "bilby"],
                "before": {"status": "running", "labels": ["a", "b"]},
                "after": {"status": "complete", "labels": ["b", "a"]},
            },
            {
                "entity_type": "detector_configuration",
                "operation": "added",
                "path": ["detector_configurations", "H1"],
                "after": {"detector": "H1", "channels": ["strain", "dq"]},
            },
            {
                "entity_type": "analysis",
                "operation": "removed",
                "path": ["analyses", "lalinference"],
                "before": {"pipeline": "lalinference"},
            },
        ]
        payload = {
            "sname": SNAME,
            "baseline_version": 3,
            "selected_version": 7,
            "baseline_timestamp": "2026-08-01T00:00:00Z",
            "selected_timestamp": "2026-08-10T12:00:00Z",
            "changes": changes,
        }
        responses.add(
            responses.GET,
            f"{PORTAL_URL}{DIFF_PATH}",
            json=payload,
            status=200,
        )

        data, state = gwflow_portal.get_diff(SNAME, 3, 7)

        self.assertEqual(state, "live")
        self.assertEqual(data, payload)
        self.assertEqual(data["changes"], changes)
        self.assertEqual(responses.calls[0].request.url, f"{PORTAL_URL}{DIFF_PATH}")
        self.assertEqual(
            caches["default"].get(f"gwflow:diff:{SNAME}:3:7"),
            payload,
        )

    def test_get_diff_rejects_each_missing_required_root_field(self):
        payload = {
            "sname": SNAME,
            "baseline_version": 3,
            "selected_version": 7,
            "baseline_timestamp": "2026-08-01T00:00:00Z",
            "selected_timestamp": "2026-08-10T12:00:00Z",
            "changes": [],
        }
        for field in gwflow_portal.DIFF_REQUIRED_FIELDS:
            with self.subTest(field=field), responses.RequestsMock() as mocked:
                malformed = payload.copy()
                del malformed[field]
                mocked.add(
                    responses.GET,
                    f"{PORTAL_URL}{DIFF_PATH}",
                    json=malformed,
                    status=200,
                )

                data, state = gwflow_portal.get_diff(SNAME, 3, 7)

                self.assertEqual((data, state), (None, "malformed"))
                self.assertIsNone(caches["default"].get(f"gwflow:diff:{SNAME}:3:7"))

    @responses.activate
    def test_get_diff_rejects_non_list_changes(self):
        payload = {
            "sname": SNAME,
            "baseline_version": 3,
            "selected_version": 7,
            "baseline_timestamp": "2026-08-01T00:00:00Z",
            "selected_timestamp": "2026-08-10T12:00:00Z",
            "changes": {"analysis": []},
        }
        responses.add(responses.GET, f"{PORTAL_URL}{DIFF_PATH}", json=payload, status=200)

        self.assertEqual(gwflow_portal.get_diff(SNAME, 3, 7), (None, "malformed"))

    @responses.activate
    @mock.patch("bilbyui.utils.gwflow_portal.time.sleep", return_value=None)
    def test_get_diff_malformed_is_distinct_from_down(self, mock_sleep):
        malformed = {
            "sname": SNAME,
            "baseline_version": 3,
            "selected_version": 7,
            "baseline_timestamp": "2026-08-01T00:00:00Z",
            "selected_timestamp": "2026-08-10T12:00:00Z",
            "changes": "not-a-list",
        }
        responses.add(responses.GET, f"{PORTAL_URL}{DIFF_PATH}", json=malformed, status=200)

        self.assertEqual(gwflow_portal.get_diff(SNAME, 3, 7), (None, "malformed"))

        responses.reset()
        responses.add(responses.GET, f"{PORTAL_URL}{DIFF_PATH}", status=503)

        self.assertEqual(gwflow_portal.get_diff(SNAME, 3, 7), (None, "down"))
        self.assertEqual(len(responses.calls), 3)
        self.assertEqual([call.args[0] for call in mock_sleep.call_args_list], [1.0, 2.0])
