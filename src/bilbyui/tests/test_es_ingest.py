import json
from io import StringIO
from unittest import mock

import requests
from django.core.management import call_command
from django.db import DatabaseError
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, GWFlowJob, IniKeyValue
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class _MockResponse:
    def __init__(self, payload, status_code):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


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

    def test_es_ingest_drops_bilby_index_before_ingesting(self):
        out = StringIO()
        with mock.patch("bilbyui.management.commands.es_ingest.get_es_client") as mock_get_es:
            mock_es = mock_get_es.return_value
            with override_settings(IGNORE_ELASTIC_SEARCH=False):
                with mock.patch.object(BilbyJob, "save", autospec=True):
                    call_command("es_ingest", stdout=out)

        mock_es.indices.delete.assert_called_once_with(
            index="gwcloud-bilbyjob",
            ignore_unavailable=True,
        )
        self.assertIn("Ingestion complete: 3 succeeded, 0 failed", out.getvalue())

    def test_es_ingest_skips_index_drop_when_es_ignored(self):
        out = StringIO()
        with mock.patch("bilbyui.management.commands.es_ingest.get_es_client") as mock_get_es:
            with mock.patch.object(BilbyJob, "save", autospec=True):
                call_command("es_ingest", stdout=out)

        mock_get_es.assert_not_called()
        self.assertIn("Ingestion complete: 3 succeeded, 0 failed", out.getvalue())

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

    def test_es_ingest_gwflow_missing_settings_returns_cleanly(self):
        out = StringIO()
        with mock.patch("bilbyui.management.commands.es_ingest.requests.get") as mock_get:
            with override_settings(CBCFLOW_PORTAL_URL=None, CBCFLOW_PORTAL_TOKEN=None):
                call_command("es_ingest", "--gwflow", stdout=out, stderr=out)

        mock_get.assert_not_called()
        output = out.getvalue()
        self.assertIn("CBCFLOW_PORTAL_URL and CBCFLOW_PORTAL_TOKEN must be set", output)
        self.assertNotIn("GWFlow ingestion complete", output)
        self.assertNotIn("Error during gwflow ingestion loop", output)

    def _run_gwflow(self, fake_get):
        out = StringIO()
        with mock.patch("bilbyui.management.commands.es_ingest.requests.get", side_effect=fake_get):
            with override_settings(
                CBCFLOW_PORTAL_URL="https://portal.example.com",
                CBCFLOW_PORTAL_TOKEN="token",
            ):
                call_command("es_ingest", "--gwflow", stdout=out, stderr=out)
        return out.getvalue()

    def _list_page(self, results, next_url=None):
        return _MockResponse({"results": results, "next": next_url}, 200)

    def test_es_ingest_gwflow_paginates_across_multiple_pages(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        GWFlowJob.objects.create(sname="S230601ah", user=self.user)

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page(
                    [{"sname": "S230601ag"}], "https://portal.example.com/api/v1/superevents/?page=2"
                )
            if url.endswith("/api/v1/superevents/?page=2"):
                return self._list_page([{"sname": "S230601ah"}])
            if url.endswith("/api/v1/superevents/S230601ag/") or url.endswith("/api/v1/superevents/S230601ah/"):
                return _MockResponse({}, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("GWFlow ingestion complete: 2 succeeded", output)
        self.assertNotIn("Error during gwflow ingestion loop", output)

    def test_es_ingest_gwflow_non_200_list_response_stops(self):
        def fake_get(url, headers=None, timeout=None):
            return _MockResponse({}, 500)

        output = self._run_gwflow(fake_get)
        self.assertIn("Failed to fetch superevents list from portal: HTTP 500", output)
        self.assertNotIn("Error during gwflow ingestion loop", output)

    def test_es_ingest_gwflow_detail_request_exception_skips(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S230601ag"}])
            if url.endswith("/api/v1/superevents/S230601ag/"):
                raise requests.RequestException("connection refused")
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("portal detail request failed", output)
        self.assertIn("GWFlow ingestion complete: 0 succeeded, 0 skipped, 1 failed", output)

    def test_es_ingest_gwflow_detail_non_200_skips(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S230601ag"}])
            if url.endswith("/api/v1/superevents/S230601ag/"):
                return _MockResponse({}, 404)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("portal detail returned HTTP 404", output)
        self.assertIn("GWFlow ingestion complete: 0 succeeded, 0 skipped, 1 failed", output)

    def test_es_ingest_gwflow_detail_invalid_json_skips(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S230601ag"}])
            if url.endswith("/api/v1/superevents/S230601ag/"):
                return _MockResponse(ValueError("No JSON object could be decoded"), 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("portal detail returned invalid JSON", output)
        self.assertIn("GWFlow ingestion complete: 0 succeeded, 0 skipped, 1 failed", output)

    def test_es_ingest_gwflow_no_matching_local_job_skips(self):
        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S230601ag"}])
            if url.endswith("/api/v1/superevents/S230601ag/"):
                return _MockResponse({}, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("no matching local GWFlowJob record found", output)
        self.assertIn("GWFlow ingestion complete: 0 succeeded, 1 skipped, 0 failed", output)

    def test_es_ingest_gwflow_non_list_results_stops(self):
        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return _MockResponse({"foo": "bar"}, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("Unexpected portal response shape", output)
        self.assertNotIn("Error during gwflow ingestion loop", output)

    def test_es_ingest_gwflow_item_without_sname_skipped(self):
        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"foo": "bar"}])
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("GWFlow ingestion complete: 0 succeeded, 0 skipped, 0 failed", output)
        self.assertNotIn("Error during gwflow ingestion loop", output)

    def test_es_ingest_gwflow_unexpected_exception_stops(self):
        def fake_get(url, headers=None, timeout=None):
            raise ValueError("boom")

        output = self._run_gwflow(fake_get)
        self.assertIn("Error during gwflow ingestion loop", output)
        self.assertIn("boom", output)

    def test_handle_bilby_backfills_gwosc_job_with_version_suffix(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="GW150914-v4--IMRPhenomD",
            description="Historical GWOSC job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        IniKeyValue.objects.create(
            job=job,
            key="trigger_time",
            value=json.dumps("1126259462.42"),
            index=0,
            processed=True,
        )

        out = StringIO()
        call_command("es_ingest", stdout=out)

        job.refresh_from_db()
        self.assertIsNotNone(job.event_id)
        self.assertEqual(job.event_id.event_id, "GW150914")
        self.assertAlmostEqual(job.event_id.gps_time, 1126259462.42)

    def test_handle_bilby_backfills_gwflow_child_via_bilby_jobs(self):
        event = EventID.objects.create(
            event_id="GW190425",
            gps_time=1239082262.22,
            is_ligo_event=False,
        )
        parent_gwflow = GWFlowJob.objects.create(
            sname="S190425z",
            user=self.user,
            event_id=event,
        )
        child = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Child_PE_GWFlow",
            description="Child Bilby job",
            private=False,
            gwflow_job=parent_gwflow,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        self.assertIsNone(child.event_id)

        out = StringIO()
        call_command("es_ingest", stdout=out)

        child.refresh_from_db()
        self.assertEqual(child.event_id, event)

    def test_handle_gwflow_selects_state_preferred(self):
        gwflow_job = GWFlowJob.objects.create(
            sname="S200105ae",
            user=self.user,
            event_id=None,
            ligo_only=False,
        )

        detail_payload = {
            "GraceDB": {
                "Events": [
                    {"UID": "G000001", "state": "neighbor", "GPSTime": 1262272818.0},
                    {"UID": "G000002", "state": "neighbor", "GPSTime": 1262272819.0},
                    {"UID": "G000003", "state": "neighbor", "GPSTime": 1262272820.0},
                    {"UID": "G000004", "state": "preferred", "GPSTime": 1262272821.5},
                ]
            }
        }

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S200105ae"}])
            if url.endswith("/api/v1/superevents/S200105ae/"):
                return _MockResponse(detail_payload, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("GWFlow ingestion complete: 1 succeeded", output)

        gwflow_job.refresh_from_db()
        self.assertIsNotNone(gwflow_job.event_id)
        self.assertEqual(gwflow_job.event_id.event_id, "G000004")
        self.assertEqual(gwflow_job.event_id.trigger_id, "S200105ae")
        self.assertAlmostEqual(gwflow_job.event_id.gps_time, 1262272821.5)
        self.assertFalse(gwflow_job.event_id.is_ligo_event)

    def test_handle_gwflow_inspects_raw_payload_for_gracedb(self):
        gwflow_job = GWFlowJob.objects.create(
            sname="S200115j",
            user=self.user,
            event_id=None,
            ligo_only=True,
        )

        detail_payload = {
            "raw_payload": {
                "gracedb": {
                    "preferred_event_uid": "G000005",
                    "events": [
                        {"uid": "G000005", "gps_time": "1263172181.28"},
                    ],
                }
            }
        }

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S200115j"}])
            if url.endswith("/api/v1/superevents/S200115j/"):
                return _MockResponse(detail_payload, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("GWFlow ingestion complete: 1 succeeded", output)

        gwflow_job.refresh_from_db()
        self.assertIsNotNone(gwflow_job.event_id)
        self.assertEqual(gwflow_job.event_id.event_id, "G000005")
        self.assertEqual(gwflow_job.event_id.trigger_id, "S200115j")
        self.assertAlmostEqual(gwflow_job.event_id.gps_time, 1263172181.28)
        self.assertTrue(gwflow_job.event_id.is_ligo_event)

    def test_handle_gwflow_cascades_to_children_via_bilby_jobs(self):
        # 1. Unlinked parent that gets resolved during ingestion
        parent1 = GWFlowJob.objects.create(sname="S200219ac", user=self.user, event_id=None)
        child1 = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Child1_Unlinked_Parent",
            gwflow_job=parent1,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

        # 2. Pre-linked parent with existing EventID
        existing_event = EventID.objects.create(event_id="GW200224", gps_time=1266624018.0)
        parent2 = GWFlowJob.objects.create(sname="S200224a", user=self.user, event_id=existing_event)
        child2 = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Child2_Prelinked_Parent",
            gwflow_job=parent2,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

        self.assertIsNone(child1.event_id)
        self.assertIsNone(child2.event_id)

        detail_payload1 = {
            "GraceDB": {
                "preferred_event": "G000010",
                "Events": [{"UID": "G000010", "GPSTime": 1266105618.0}],
            }
        }
        detail_payload2 = {}

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S200219ac"}, {"sname": "S200224a"}])
            if url.endswith("/api/v1/superevents/S200219ac/"):
                return _MockResponse(detail_payload1, 200)
            if url.endswith("/api/v1/superevents/S200224a/"):
                return _MockResponse(detail_payload2, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("GWFlow ingestion complete: 2 succeeded", output)

        parent1.refresh_from_db()
        child1.refresh_from_db()
        child2.refresh_from_db()

        self.assertIsNotNone(parent1.event_id)
        self.assertEqual(parent1.event_id.event_id, "G000010")
        self.assertEqual(child1.event_id, parent1.event_id)
        self.assertEqual(child2.event_id, existing_event)

    def test_handle_gwflow_individual_error_does_not_abort_loop(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        GWFlowJob.objects.create(sname="S230601ah", user=self.user)

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page(
                    [{"sname": "S230601ag"}],
                    "https://portal.example.com/api/v1/superevents/?page=2",
                )
            if url.endswith("/api/v1/superevents/?page=2"):
                return self._list_page([{"sname": "S230601ah"}])
            if url.endswith("/api/v1/superevents/S230601ag/") or url.endswith("/api/v1/superevents/S230601ah/"):
                return _MockResponse({}, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        def fail_on_first(job, metadata):
            if job.sname == "S230601ag":
                raise RuntimeError("Failed to update ES for S230601ag")

        with mock.patch(
            "bilbyui.management.commands.es_ingest.gwflow_elastic_search_update",
            side_effect=fail_on_first,
        ):
            output = self._run_gwflow(fake_get)

        self.assertIn("GWFlow ingestion complete: 1 succeeded, 0 skipped, 1 failed", output)
        self.assertIn("✗ GWFlowJob", output)
        self.assertIn("✓ GWFlowJob", output)
        self.assertIn("Failed to update ES for S230601ag", output)

    def test_handle_bilby_backfills_gwflow_child_via_trigger_id_fallback(self):
        event = EventID.objects.create(
            event_id="GW190426",
            trigger_id="S190426c",
            gps_time=1239082262.22,
            is_ligo_event=False,
        )
        parent_gwflow = GWFlowJob.objects.create(
            sname="S190426c",
            user=self.user,
            event_id=None,
        )
        child = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Child_PE_Fallback_Trigger",
            description="Child Bilby job",
            private=False,
            gwflow_job=parent_gwflow,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        self.assertIsNone(child.event_id)

        out = StringIO()
        call_command("es_ingest", stdout=out)

        child.refresh_from_db()
        self.assertEqual(child.event_id, event)

    def test_handle_bilby_backfills_gwosc_job_raw_float_string(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="GW170817-v1--TaylorF2",
            description="Historical GWOSC raw float job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        IniKeyValue.objects.create(
            job=job,
            key="trigger_time",
            value="1187008882.43",
            index=0,
            processed=False,
        )

        out = StringIO()
        call_command("es_ingest", stdout=out)

        job.refresh_from_db()
        self.assertIsNotNone(job.event_id)
        self.assertEqual(job.event_id.event_id, "GW170817")
        self.assertAlmostEqual(job.event_id.gps_time, 1187008882.43)

    def test_handle_gwflow_matches_preferred_uid(self):
        gwflow_job = GWFlowJob.objects.create(
            sname="S190814bv",
            user=self.user,
            event_id=None,
        )

        detail_payload = {
            "GraceDB": {
                "preferred_event": "G000002",
                "Events": [
                    {"UID": "G000001", "GPSTime": 1249852257.0},
                    {"UID": "G000002", "GPSTime": 1249852258.12},
                ],
            }
        }

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S190814bv"}])
            if url.endswith("/api/v1/superevents/S190814bv/"):
                return _MockResponse(detail_payload, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("GWFlow ingestion complete: 1 succeeded", output)

        gwflow_job.refresh_from_db()
        self.assertIsNotNone(gwflow_job.event_id)
        self.assertEqual(gwflow_job.event_id.event_id, "G000002")
        self.assertAlmostEqual(gwflow_job.event_id.gps_time, 1249852258.12)

    def test_handle_gwflow_preferred_uid_without_events_list(self):
        gwflow_job = GWFlowJob.objects.create(
            sname="S190910d",
            user=self.user,
            event_id=None,
        )

        detail_payload = {
            "GraceDB": {
                "preferred_event_uid": "G000003",
                "preferred_event_gps": 1252150000.5,
            }
        }

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S190910d"}])
            if url.endswith("/api/v1/superevents/S190910d/"):
                return _MockResponse(detail_payload, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("GWFlow ingestion complete: 1 succeeded", output)

        gwflow_job.refresh_from_db()
        self.assertIsNotNone(gwflow_job.event_id)
        self.assertEqual(gwflow_job.event_id.event_id, "G000003")
        self.assertAlmostEqual(gwflow_job.event_id.gps_time, 1252150000.5)

    def test_handle_gwflow_invalid_gps_falls_back_to_default(self):
        gwflow_job = GWFlowJob.objects.create(
            sname="S190915a",
            user=self.user,
            event_id=None,
        )

        detail_payload = {
            "GraceDB": {
                "preferred_event_uid": "G000004",
                "preferred_event_gps": "invalid-gps",
            }
        }

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S190915a"}])
            if url.endswith("/api/v1/superevents/S190915a/"):
                return _MockResponse(detail_payload, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("GWFlow ingestion complete: 1 succeeded", output)

        gwflow_job.refresh_from_db()
        self.assertIsNotNone(gwflow_job.event_id)
        self.assertEqual(gwflow_job.event_id.event_id, "G000004")
        self.assertAlmostEqual(gwflow_job.event_id.gps_time, 1126259462.391)

    def test_handle_gwflow_reconciles_is_ligo_event_and_trigger_id_on_existing_event(self):
        existing_event = EventID.objects.create(
            event_id="G000007",
            gps_time=1262272821.5,
            is_ligo_event=False,
            trigger_id=None,
        )
        gwflow_job = GWFlowJob.objects.create(
            sname="S200116a",
            user=self.user,
            event_id=None,
            ligo_only=True,
        )

        detail_payload = {
            "GraceDB": {
                "preferred_event": "G000007",
                "Events": [{"UID": "G000007", "GPSTime": 1262272821.5}],
            }
        }

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S200116a"}])
            if url.endswith("/api/v1/superevents/S200116a/"):
                return _MockResponse(detail_payload, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("GWFlow ingestion complete: 1 succeeded", output)

        gwflow_job.refresh_from_db()
        existing_event.refresh_from_db()
        self.assertEqual(gwflow_job.event_id, existing_event)
        self.assertTrue(existing_event.is_ligo_event)
        self.assertEqual(existing_event.trigger_id, "S200116a")

    def test_handle_gwflow_ignores_malformed_chosen_uid(self):
        gwflow_job = GWFlowJob.objects.create(
            sname="S200117a",
            user=self.user,
            event_id=None,
        )

        detail_payload = {
            "GraceDB": {
                "preferred_event": "INVALID-UID-12345",
                "Events": [{"UID": "INVALID-UID-12345", "GPSTime": 1262272821.5}],
            }
        }

        def fake_get(url, headers=None, timeout=None):
            if url.endswith("/api/v1/superevents/?page=1"):
                return self._list_page([{"sname": "S200117a"}])
            if url.endswith("/api/v1/superevents/S200117a/"):
                return _MockResponse(detail_payload, 200)
            raise AssertionError(f"Unexpected URL: {url}")

        output = self._run_gwflow(fake_get)
        self.assertIn("GWFlow ingestion complete: 1 succeeded", output)

        gwflow_job.refresh_from_db()
        self.assertIsNone(gwflow_job.event_id)
        self.assertFalse(EventID.objects.filter(event_id="INVALID-UID-12345").exists())
