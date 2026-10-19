import unittest
from unittest.mock import Mock, patch

import requests
import responses

from portal import PortalClient, PortalMalformedResponseError


class TestPortalClient(unittest.TestCase):
    def setUp(self):
        self.base_url = "https://cbcflow.example.com"
        self.token = "test-token"
        self.client = PortalClient(self.base_url, self.token)

    @staticmethod
    def envelope(results, *, count=None, next_url=None, previous=None):
        return {
            "count": len(results) if count is None else count,
            "next": next_url,
            "previous": previous,
            "results": results,
        }

    @staticmethod
    def detail(sname="S260101a", raw_payload=None):
        return {
            "sname": sname,
            "libraries": ["bilby"],
            "version_number": 4,
            "record_timestamp": "2026-01-04T10:00:00Z",
            "commit_sha": "abc123",
            "is_current": True,
            "analyses": [],
            "detector_configurations": [],
            "gracedb_events": [],
            "catalog_connections": [],
            "raw_payload": raw_payload,
        }

    def test_init_preserves_authorisation_header_and_normalises_base_url(self):
        self.assertEqual(self.client.base_url, f"{self.base_url}/")
        self.assertEqual(
            self.client.session.headers["Authorization"],
            self.token,
        )

        client_without_token = PortalClient(self.base_url, token="")
        self.assertNotIn("Authorization", client_without_token.session.headers)

    @responses.activate
    def test_iter_changed_traverses_three_pages_once_in_server_order(self):
        first_url = f"{self.base_url}/api/v1/superevents/?page=1"
        second_url = f"{self.base_url}/api/v1/superevents/?page=2"
        third_url = f"{self.base_url}/api/v1/superevents/?page=3"
        rows_by_page = [
            [
                {
                    "sname": "S260101a",
                    "record_timestamp": "2026-01-03T10:00:00Z",
                    "version_number": 3,
                },
                {
                    "sname": "S260102b",
                    "record_timestamp": "2026-01-01T10:00:00Z",
                    "version_number": 1,
                },
            ],
            [
                {
                    "sname": "S260103c",
                    "record_timestamp": "2026-01-02T10:00:00Z",
                    "version_number": 2,
                }
            ],
            [
                {
                    "sname": "S260104d",
                    "record_timestamp": "2025-12-31T10:00:00Z",
                    "version_number": 4,
                }
            ],
        ]
        for url, results, next_url, previous in (
            (first_url, rows_by_page[0], second_url, None),
            (second_url, rows_by_page[1], third_url, first_url),
            (third_url, rows_by_page[2], None, second_url),
        ):
            responses.add(
                responses.GET,
                url,
                json=self.envelope(
                    results,
                    count=4,
                    next_url=next_url,
                    previous=previous,
                ),
                status=200,
            )

        actual = list(self.client.iter_changed())

        self.assertEqual(actual, [row for page in rows_by_page for row in page])
        self.assertEqual(
            [call.request.url for call in responses.calls],
            [first_url, second_url, third_url],
        )
        self.assertEqual(len(responses.calls), 3)

    @responses.activate
    def test_iter_changed_filters_since_client_side_without_reordering(self):
        first_url = f"{self.base_url}/api/v1/superevents/?page=1"
        since = "2026-01-02T00:00:00Z"
        newer = {
            "sname": "S260101a",
            "record_timestamp": "2026-01-03T10:00:00Z",
            "version_number": 3,
        }
        older = {
            "sname": "S260102b",
            "record_timestamp": "2026-01-01T10:00:00Z",
            "version_number": 1,
        }
        boundary = {
            "sname": "S260103c",
            "record_timestamp": since,
            "version_number": 2,
        }
        responses.add(
            responses.GET,
            first_url,
            json=self.envelope([newer, older, boundary]),
            status=200,
        )

        actual = list(self.client.iter_changed(since=since))

        self.assertEqual(actual, [newer, boundary])
        self.assertEqual(
            [call.request.url for call in responses.calls],
            [first_url],
        )
        self.assertNotIn("timestamp", responses.calls[0].request.url)

    @responses.activate
    def test_collection_rejects_self_referential_next_url(self):
        url = f"{self.base_url}/api/v1/superevents/"
        responses.add(
            responses.GET,
            url,
            json=self.envelope([], next_url=url),
            status=200,
        )

        with self.assertRaises(PortalMalformedResponseError) as caught:
            list(self.client._iter_pages(url))

        self.assertIn("cycle", caught.exception.reason)
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_collection_rejects_cross_origin_next_url(self):
        url = f"{self.base_url}/api/v1/superevents/"
        responses.add(
            responses.GET,
            url,
            json=self.envelope(
                [],
                next_url="https://attacker.example/api/v1/superevents/?page=2",
            ),
            status=200,
        )

        with self.assertRaises(PortalMalformedResponseError) as caught:
            list(self.client._iter_pages(url))

        self.assertIn("portal origin", caught.exception.reason)
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_collection_rejects_legacy_bare_list(self):
        url = f"{self.base_url}/api/v1/superevents/"
        responses.add(
            responses.GET,
            url,
            json=[{"sname": "S260101a"}],
            status=200,
        )

        with self.assertRaises(PortalMalformedResponseError) as caught:
            list(self.client._iter_pages(url))

        self.assertEqual(caught.exception.endpoint, url)
        self.assertEqual(
            caught.exception.correlation_context,
            (url, None, "list"),
        )

    @responses.activate
    def test_collection_rejects_non_list_results_without_following_next(self):
        first_url = f"{self.base_url}/api/v1/superevents/"
        second_url = f"{self.base_url}/api/v1/superevents/?page=2"
        responses.add(
            responses.GET,
            first_url,
            json={
                "count": 1,
                "next": second_url,
                "previous": None,
                "results": None,
            },
            status=200,
        )
        responses.add(
            responses.GET,
            second_url,
            json=self.envelope([{"sname": "S260101a"}]),
            status=200,
        )

        with self.assertRaises(PortalMalformedResponseError):
            list(self.client._iter_pages(first_url))

        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_collection_requires_exact_envelope_fields(self):
        url = f"{self.base_url}/api/v1/superevents/"
        malformed_envelopes = (
            {
                "count": 0,
                "next": None,
                "results": [],
            },
            {
                "count": 0,
                "next": None,
                "previous": None,
                "results": [],
                "legacy": True,
            },
            {
                "count": "0",
                "next": None,
                "previous": None,
                "results": [],
            },
            {
                "count": 0,
                "next": 2,
                "previous": None,
                "results": [],
            },
            {
                "count": 0,
                "next": None,
                "previous": 1,
                "results": [],
            },
        )

        for body in malformed_envelopes:
            with self.subTest(body=body):
                responses.reset()
                responses.add(
                    responses.GET,
                    url,
                    json=body,
                    status=200,
                )
                with self.assertRaises(PortalMalformedResponseError):
                    list(self.client._iter_pages(url))

    @responses.activate
    def test_list_non_json_logs_and_raises_with_correlation_context(self):
        url = f"{self.base_url}/api/v1/superevents/?page=1"
        responses.add(
            responses.GET,
            url,
            body="<html>proxy error</html>",
            status=200,
            content_type="text/html",
        )

        with self.assertLogs("gwflow_ingest.portal", level="ERROR") as logs:
            with self.assertRaises(PortalMalformedResponseError) as caught:
                list(self.client.iter_changed())

        self.assertEqual(caught.exception.endpoint, url.split("?")[0])
        self.assertEqual(
            caught.exception.correlation_context,
            (url.split("?")[0], None, "list"),
        )
        log_text = "\n".join(logs.output)
        self.assertIn(url.split("?")[0], log_text)
        self.assertIn("correlation_context", log_text)
        self.assertIn("'list'", log_text)

    @responses.activate
    def test_get_superevent_accepts_empty_arrays_and_null_raw_payload(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/"
        expected = self.detail(sname, raw_payload=None)
        responses.add(responses.GET, url, json=expected, status=200)

        actual = self.client.get_superevent(sname)

        self.assertEqual(actual, expected)
        self.assertIsNone(actual["raw_payload"])
        self.assertEqual(responses.calls[0].request.url, url)

    @responses.activate
    def test_get_superevent_passes_object_raw_payload_through(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/"
        payload = {"GraceDB": {"gpstime": 1234567890.5}}
        expected = self.detail(sname, raw_payload=payload)
        responses.add(responses.GET, url, json=expected, status=200)

        actual = self.client.get_superevent(sname)

        self.assertEqual(actual["raw_payload"], payload)

    @responses.activate
    def test_get_superevent_accepts_string_is_current(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/"
        body = self.detail(sname)
        body["is_current"] = "true"
        responses.add(responses.GET, url, json=body, status=200)

        self.assertEqual(self.client.get_superevent(sname)["is_current"], "true")

    @responses.activate
    def test_get_superevent_rejects_invalid_required_detail_roots(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/"
        malformed_fields = (
            ("sname", ""),
            ("record_timestamp", None),
            ("commit_sha", 123),
            ("libraries", None),
            ("version_number", "4"),
            ("version_number", True),
            ("is_current", 1),
        )

        for field, value in malformed_fields:
            with self.subTest(field=field, value=value):
                responses.reset()
                body = self.detail(sname)
                body[field] = value
                responses.add(responses.GET, url, json=body, status=200)

                with self.assertRaises(PortalMalformedResponseError) as caught:
                    self.client.get_superevent(sname)

                self.assertIn(field, caught.exception.reason)

    @responses.activate
    def test_get_superevent_rejects_null_or_non_array_collections(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/"
        collection_fields = (
            "analyses",
            "detector_configurations",
            "gracedb_events",
            "catalog_connections",
        )

        for field in collection_fields:
            for malformed_value in (None, {}, "not-an-array"):
                with self.subTest(field=field, value=malformed_value):
                    responses.reset()
                    body = self.detail(sname)
                    body[field] = malformed_value
                    responses.add(
                        responses.GET,
                        url,
                        json=body,
                        status=200,
                    )

                    with self.assertRaises(PortalMalformedResponseError) as caught:
                        self.client.get_superevent(sname)

                    self.assertEqual(caught.exception.endpoint, url)
                    self.assertEqual(
                        caught.exception.correlation_context,
                        (url, sname, "current-detail"),
                    )
                    self.assertIn(field, caught.exception.reason)

    @responses.activate
    def test_get_superevent_rejects_missing_required_collection(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/"
        body = self.detail(sname)
        del body["analyses"]
        responses.add(responses.GET, url, json=body, status=200)

        with self.assertRaises(PortalMalformedResponseError):
            self.client.get_superevent(sname)

    @responses.activate
    def test_get_superevent_rejects_invalid_raw_payload_type(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/"
        body = self.detail(sname)
        body["raw_payload"] = []
        responses.add(responses.GET, url, json=body, status=200)

        with self.assertRaises(PortalMalformedResponseError):
            self.client.get_superevent(sname)

    @responses.activate
    def test_get_superevent_non_json_logs_and_raises_with_context(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/"
        responses.add(
            responses.GET,
            url,
            body="<html>proxy error</html>",
            status=200,
            content_type="text/html",
        )

        with self.assertLogs("gwflow_ingest.portal", level="ERROR") as logs:
            with self.assertRaises(PortalMalformedResponseError) as caught:
                self.client.get_superevent(sname)

        self.assertEqual(caught.exception.endpoint, url)
        self.assertEqual(
            caught.exception.correlation_context,
            (url, sname, "current-detail"),
        )
        self.assertIn(url, "\n".join(logs.output))
        self.assertIn(sname, "\n".join(logs.output))

    @responses.activate
    def test_get_versions_canonical_one_page_preserves_server_order(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/versions/"
        expected = [
            {
                "version_number": 7,
                "record_timestamp": "2026-01-07T10:00:00Z",
                "commit_sha": "sha7",
                "is_current": True,
            },
            {
                "version_number": 5,
                "record_timestamp": "2026-01-05T10:00:00Z",
                "commit_sha": "sha5",
                "is_current": False,
            },
        ]
        responses.add(
            responses.GET,
            url,
            json=self.envelope(expected),
            status=200,
        )

        self.assertEqual(self.client.get_versions(sname), expected)
        self.assertEqual(responses.calls[0].request.url, url)

    @responses.activate
    def test_get_versions_follows_next_exactly_once(self):
        sname = "S260101a"
        first_url = f"{self.base_url}/api/v1/superevents/{sname}/versions/"
        second_url = f"{first_url}?page=2"
        first = {
            "version_number": 2,
            "record_timestamp": "2026-01-02T10:00:00Z",
            "commit_sha": "sha2",
            "is_current": True,
        }
        second = {
            "version_number": 1,
            "record_timestamp": "2026-01-01T10:00:00Z",
            "commit_sha": "sha1",
            "is_current": False,
        }
        responses.add(
            responses.GET,
            first_url,
            json=self.envelope(
                [first],
                count=2,
                next_url=second_url,
            ),
            status=200,
        )
        responses.add(
            responses.GET,
            second_url,
            json=self.envelope(
                [second],
                count=2,
                previous=first_url,
            ),
            status=200,
        )

        self.assertEqual(
            self.client.get_versions(sname),
            [first, second],
        )
        self.assertEqual(
            [call.request.url for call in responses.calls],
            [first_url, second_url],
        )

    @responses.activate
    def test_get_versions_rejects_bare_list(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/versions/"
        responses.add(
            responses.GET,
            url,
            json=[{"version_number": 1}],
            status=200,
        )

        with self.assertRaises(PortalMalformedResponseError):
            self.client.get_versions(sname)

    @responses.activate
    def test_get_versions_rejects_non_list_results(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/versions/"
        responses.add(
            responses.GET,
            url,
            json={
                "count": 1,
                "next": None,
                "previous": None,
                "results": {},
            },
            status=200,
        )

        with self.assertRaises(PortalMalformedResponseError):
            self.client.get_versions(sname)

    @responses.activate
    def test_get_versions_non_json_logs_and_raises_with_context(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/versions/"
        responses.add(
            responses.GET,
            url,
            body="<html>proxy error</html>",
            status=200,
            content_type="text/html",
        )

        with self.assertLogs("gwflow_ingest.portal", level="ERROR") as logs:
            with self.assertRaises(PortalMalformedResponseError) as caught:
                self.client.get_versions(sname)

        self.assertEqual(caught.exception.endpoint, url)
        self.assertEqual(
            caught.exception.correlation_context,
            (url, sname, "versions"),
        )
        self.assertIn(url, "\n".join(logs.output))
        self.assertIn(sname, "\n".join(logs.output))

    @responses.activate
    def test_iter_changed_rejects_row_missing_record_timestamp_with_context(self):
        endpoint = f"{self.base_url}/api/v1/superevents/"
        responses.add(
            responses.GET,
            endpoint,
            json=self.envelope([{"sname": "S260101a"}]),
            status=200,
        )

        with self.assertRaises(PortalMalformedResponseError) as caught:
            list(self.client.iter_changed())

        self.assertEqual(caught.exception.endpoint, endpoint)
        self.assertEqual(
            caught.exception.correlation_context,
            (endpoint, "S260101a", "changed"),
        )

    @responses.activate
    def test_iter_changed_rejects_non_dict_row(self):
        endpoint = f"{self.base_url}/api/v1/superevents/"
        responses.add(
            responses.GET,
            endpoint,
            json=self.envelope(["not-an-object"]),
            status=200,
        )

        with self.assertRaises(PortalMalformedResponseError) as caught:
            list(self.client.iter_changed())

        self.assertEqual(caught.exception.endpoint, endpoint)
        self.assertEqual(caught.exception.reason, "result row must be an object")

    @responses.activate
    def test_iter_current_snames_skips_and_logs_malformed_rows(self):
        first_url = f"{self.base_url}/api/v1/superevents/"
        second_url = f"{first_url}?page=2"
        responses.add(
            responses.GET,
            first_url,
            json=self.envelope(
                [
                    {"sname": "S260101a"},
                    "raw-sensitive-row-contents",
                    {},
                    {"sname": None},
                ],
                count=5,
                next_url=second_url,
            ),
            status=200,
        )
        responses.add(
            responses.GET,
            second_url,
            json=self.envelope(
                [{"sname": "S260103c"}],
                count=5,
                previous=first_url,
            ),
            status=200,
        )

        with self.assertLogs("gwflow_ingest.portal", level="ERROR") as logs:
            snames = list(self.client.iter_current_snames())

        self.assertEqual(snames, ["S260101a", "S260103c"])
        self.assertEqual(len(logs.output), 3)
        self.assertTrue(all("Skipping malformed current-sname row" in line for line in logs.output))
        joined_logs = "\n".join(logs.output)
        self.assertNotIn("raw-sensitive-row-contents", joined_logs)
        self.assertIn("row_type=str", joined_logs)
        self.assertIn("row_keys=[]", joined_logs)
        self.assertIn("row_keys=['sname']", joined_logs)
        self.assertEqual(
            [call.request.url for call in responses.calls],
            [first_url, second_url],
        )

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_each_4xx_class_raises_without_retry(self, mock_sleep):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                responses.reset()
                mock_sleep.reset_mock()
                url = f"{self.base_url}/api/v1/superevents/S_STATUS_{status}/"
                responses.add(responses.GET, url, status=status)

                with self.assertRaises(requests.HTTPError):
                    self.client.get_superevent(f"S_STATUS_{status}")

                self.assertEqual(len(responses.calls), 1)
                mock_sleep.assert_not_called()

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_5xx_retries_then_succeeds(self, mock_sleep):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/"
        responses.add(responses.GET, url, status=500)
        responses.add(responses.GET, url, status=502)
        responses.add(
            responses.GET,
            url,
            json=self.detail(sname),
            status=200,
        )

        result = self.client.get_superevent(sname)

        self.assertEqual(result["sname"], sname)
        self.assertEqual(len(responses.calls), 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_exhausted_5xx_retry_raises(self, mock_sleep):
        sname = "S_FAIL"
        url = f"{self.base_url}/api/v1/superevents/{sname}/"
        responses.add(responses.GET, url, status=500)
        responses.add(responses.GET, url, status=502)
        responses.add(responses.GET, url, status=503)

        with self.assertRaises(requests.HTTPError):
            self.client.get_superevent(sname)

        self.assertEqual(len(responses.calls), 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("time.sleep", return_value=None)
    def test_timeout_is_retried_then_propagated(self, mock_sleep):
        self.client.session.request = Mock(side_effect=requests.Timeout("portal timed out"))
        url = f"{self.base_url}/api/v1/superevents/S_TIMEOUT/"

        with self.assertRaises(requests.Timeout):
            self.client.get_superevent("S_TIMEOUT")

        self.assertEqual(self.client.session.request.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        for call in self.client.session.request.call_args_list:
            self.assertEqual(call.kwargs["timeout"], 10)
            self.assertEqual(call.args, ("GET", url))

    @patch("time.sleep", return_value=None)
    def test_request_preserves_ten_second_timeout(self, mock_sleep):
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        self.client.session.request = Mock(return_value=response)
        url = f"{self.base_url}/api/v1/superevents/"

        actual = self.client._request_with_retry(
            "GET",
            url,
            params={"page": 1},
        )

        self.assertIs(actual, response)
        self.client.session.request.assert_called_once_with(
            "GET",
            url,
            timeout=10,
            params={"page": 1},
        )
        mock_sleep.assert_not_called()

    def test_get_versions_is_only_versions_method(self):
        self.assertTrue(hasattr(self.client, "get_versions"))
        self.assertFalse(hasattr(self.client, "get_superevent_versions"))

    def test_portal_source_has_no_legacy_timestamp_or_version_key_reads(self):
        from pathlib import Path

        source = Path(__file__).parents[1].joinpath("portal.py").read_text()
        self.assertNotRegex(
            source,
            r"""(?:\[|\.get\()\s*["']commit_timestamp["']""",
        )
        self.assertNotRegex(
            source,
            r"""(?:\[|\.get\()\s*["']version["']""",
        )


if __name__ == "__main__":
    unittest.main()
