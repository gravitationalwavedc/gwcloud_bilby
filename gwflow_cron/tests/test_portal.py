import unittest
from unittest.mock import patch

import responses

from portal import PortalClient


class TestPortalClient(unittest.TestCase):
    def setUp(self):
        self.base_url = "https://cbcflow.example.com"
        self.token = "test-token"
        self.client = PortalClient(self.base_url, self.token)

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
        # Verify page 1 sorting
        self.assertEqual(rows[0]["sname"], "S260101a")
        self.assertEqual(rows[1]["sname"], "S260102b")
        self.assertEqual(rows[2]["sname"], "S260103c")

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
                    {"sname": "S260102b"},
                ],
                "next": None,
            },
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


if __name__ == "__main__":
    unittest.main()
