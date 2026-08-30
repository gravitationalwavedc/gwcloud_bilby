from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import DatabaseError
from django.test import override_settings

from bilbyui.models import BilbyJob, GWFlowJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestEsIngestCommand(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        for i in range(3):
            BilbyJob.objects.create(
                user_id=cls.user.id,
                name=f"Test_Job_{i}",
                description="Test job description",
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

    def test_es_ingest_success(self):
        out = StringIO()
        with mock.patch.object(BilbyJob, "save", autospec=True) as mock_save:
            call_command("es_ingest", stdout=out)

        self.assertEqual(mock_save.call_count, 3)
        output = out.getvalue()
        self.assertIn("Ingestion complete: 3 succeeded, 0 failed", output)
        self.assertIn("✓ Job", output)

    def test_es_ingest_error(self):
        out = StringIO()
        with mock.patch.object(BilbyJob, "save", autospec=True, side_effect=DatabaseError("boom")):
            call_command("es_ingest", stdout=out)

        output = out.getvalue()
        self.assertIn("Ingestion complete: 0 succeeded, 3 failed", output)
        self.assertIn("✗ Job", output)
        self.assertIn("boom", output)

    def test_es_ingest_continues_after_non_database_error(self):
        out = StringIO()
        with mock.patch.object(BilbyJob, "save", autospec=True, side_effect=[ValueError("bad detectors"), None, None]):
            call_command("es_ingest", stdout=out)

        output = out.getvalue()
        self.assertIn("Ingestion complete: 2 succeeded, 1 failed", output)
        self.assertIn("✗ Job", output)
        self.assertIn("bad detectors", output)

    def test_es_ingest_gwflow_non_dict_item_does_not_abort(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        class MockResponse:
            def __init__(self, payload, status_code):
                self._payload = payload
                self.status_code = status_code

            def json(self):
                return self._payload

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return MockResponse({"results": ["S230601ag"], "next": None}, 200)
            if url.endswith("/api/v1/superevents/S230601ag/"):
                return MockResponse({}, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        out = StringIO()
        with mock.patch("bilbyui.management.commands.es_ingest.requests.get", side_effect=fake_get):
            with override_settings(
                CBCFLOW_PORTAL_URL="https://portal.example.com",
                CBCFLOW_PORTAL_TOKEN="token",
            ):
                call_command("es_ingest", "--gwflow", stdout=out)

        output = out.getvalue()
        self.assertIn("GWFlow ingestion complete: 1 succeeded", output)
        self.assertNotIn("Error during gwflow ingestion loop", output)

    def test_es_ingest_gwflow_invalid_list_json_stops_cleanly(self):
        class MockResponse:
            def __init__(self, status_code):
                self.status_code = status_code

            def json(self):
                raise ValueError("No JSON object could be decoded")

        def fake_get(url, headers=None, timeout=None):
            return MockResponse(200)

        out = StringIO()
        with mock.patch("bilbyui.management.commands.es_ingest.requests.get", side_effect=fake_get):
            with override_settings(
                CBCFLOW_PORTAL_URL="https://portal.example.com",
                CBCFLOW_PORTAL_TOKEN="token",
            ):
                call_command("es_ingest", "--gwflow", stdout=out)

        output = out.getvalue()
        self.assertIn("invalid JSON", output)
        self.assertNotIn("Error during gwflow ingestion loop", output)
