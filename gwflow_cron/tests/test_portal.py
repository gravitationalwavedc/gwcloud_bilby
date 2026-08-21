import unittest
from unittest.mock import patch

import requests
import responses

from portal import PortalClient


class TestPortalClient(unittest.TestCase):
    def setUp(self):
        self.base_url = "https://cbcflow.example.com"
        self.token = "test-token"
        self.client = PortalClient(self.base_url, self.token)

    def test_init_without_trailing_slash_and_token(self):
        c = PortalClient("https://cbcflow.example.com", token="")
        self.assertEqual(c.base_url, "https://cbcflow.example.com/")

    @responses.activate
    def test_iter_changed_pagination_and_sorting(self):
        url1 = f"{self.base_url}/api/v1/superevents/?ordering=commit_timestamp%2Csname&commit_timestamp__gte=2026-01-01T00%3A00%3A00Z&page_size=50"
        url2 = f"{self.base_url}/api/v1/superevents/?page=2"

        responses.add(
            responses.GET,
            url1,
            json={
                "results": [
                    {"sname": "S260102b", "commit_timestamp": "2026-01-02T12:00:00Z"},
                    {"sname": "S260101a", "commit_timestamp": "2026-01-01T10:00:00Z"},
                ],
                "next": url2,
            },
            status=200,
        )
        responses.add(
            responses.GET,
            url2,
            json={
                "results": [
                    {"sname": "S260103c", "commit_timestamp": "2026-01-03T15:00:00Z"},
                ],
                "next": None,
            },
            status=200,
        )

        rows = list(self.client.iter_changed(since="2026-01-01T00:00:00Z"))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["sname"], "S260101a")
        self.assertEqual(rows[1]["sname"], "S260102b")
        self.assertEqual(rows[2]["sname"], "S260103c")

    @responses.activate
    def test_iter_changed_list_format(self):
        url = f"{self.base_url}/api/v1/superevents/?ordering=commit_timestamp%2Csname&page_size=50"
        responses.add(
            responses.GET,
            url,
            json=[
                {"sname": "S260101a", "commit_timestamp": "2026-01-01T10:00:00Z"},
            ],
            status=200,
        )
        rows = list(self.client.iter_changed())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sname"], "S260101a")

    @responses.activate
    def test_iter_changed_skips_non_list_results_and_continues(self):
        url1 = f"{self.base_url}/api/v1/superevents/?ordering=commit_timestamp%2Csname&page_size=50"
        url2 = f"{self.base_url}/api/v1/superevents/?page=2"

        responses.add(
            responses.GET,
            url1,
            json={"results": None, "next": url2},
            status=200,
        )
        responses.add(
            responses.GET,
            url2,
            json={
                "results": [{"sname": "S260101a", "commit_timestamp": "2026-01-01T10:00:00Z"}],
                "next": None,
            },
            status=200,
        )

        rows = list(self.client.iter_changed())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sname"], "S260101a")

    @responses.activate
    def test_get_superevent(self):
        sname = "S260101a"
        url = f"{self.base_url}/api/v1/superevents/{sname}/"
        responses.add(
            responses.GET,
            url,
            json={"sname": sname, "raw_payload": {"test": 123}},
            status=200,
        )

        detail = self.client.get_superevent(sname)
        self.assertEqual(detail["sname"], sname)
        self.assertEqual(detail["raw_payload"]["test"], 123)

    @responses.activate
    def test_iter_current_snames(self):
        url = f"{self.base_url}/api/v1/superevents/"
        responses.add(
            responses.GET,
            url,
            json={
                "results": [
                    {"sname": "S260101a"},
                    "S260102b",
                ],
                "next": None,
            },
            status=200,
        )

        snames = list(self.client.iter_current_snames())
        self.assertEqual(snames, ["S260101a", "S260102b"])

    @responses.activate
    def test_iter_current_snames_list_format(self):
        url = f"{self.base_url}/api/v1/superevents/"
        responses.add(
            responses.GET,
            url,
            json=["S260101a", {"sname": "S260102b"}],
            status=200,
        )
        snames = list(self.client.iter_current_snames())
        self.assertEqual(snames, ["S260101a", "S260102b"])

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retry_on_5xx_server_error(self, mock_sleep):
        url = f"{self.base_url}/api/v1/superevents/S260101a/"
        responses.add(responses.GET, url, status=500)
        responses.add(responses.GET, url, status=500)
        responses.add(
            responses.GET,
            url,
            json={"sname": "S260101a", "ok": True},
            status=200,
        )

        detail = self.client.get_superevent("S260101a")
        self.assertTrue(detail["ok"])
        self.assertEqual(len(responses.calls), 3)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retry_max_attempts_exceeded(self, mock_sleep):
        url = f"{self.base_url}/api/v1/superevents/S_FAIL/"
        responses.add(responses.GET, url, status=500)
        responses.add(responses.GET, url, status=500)
        responses.add(responses.GET, url, status=500)

        with self.assertRaises(requests.RequestException):
            self.client.get_superevent("S_FAIL")

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_4xx_raises_immediately_without_retry(self, mock_sleep):
        url = f"{self.base_url}/api/v1/superevents/S_GONE/"
        responses.add(responses.GET, url, status=404)

        with self.assertRaises(requests.HTTPError):
            self.client.get_superevent("S_GONE")
        self.assertEqual(len(responses.calls), 1)
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
