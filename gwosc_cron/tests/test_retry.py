import logging
import unittest
from unittest.mock import patch

import responses

import gwosc_ingest
from tests.base import GWOSCTestBase


@unittest.mock.patch("gwosc_ingest.GWCloud", autospec=True)
class TestRetryLogic(GWOSCTestBase):
    """Tests for per-event failure tracking, retry skip, and max-retries logic."""

    # ---- single-event failure recording ------------------------------------

    @responses.activate
    def test_h5_failure_records_job_error(self, gwc):
        """H5 404 → job_errors row with failure_count=1, no completed_jobs row."""
        self.add_allevents_response()
        self.add_event_response()
        responses.add(responses.GET, "https://test.org/GW000001.h5", status=404)

        with self.con_patch, self.assertLogs(level=logging.ERROR):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        self.assertEqual(len(self.get_completed_jobs()), 0)

        error_rows = self.get_job_errors()
        self.assertEqual(len(error_rows), 1)
        self.assertEqual(error_rows[0]["job_id"], "GW000001_123456")
        self.assertEqual(error_rows[0]["failure_count"], 1)
        self.assertIn("Downloading", error_rows[0]["last_error"])

    @responses.activate
    def test_event_json_failure_records_job_error(self, gwc):
        """Event JSON non-200 → job_errors row with failure_count=1, no completed_jobs row."""
        self.add_allevents_response()
        responses.add(
            responses.GET,
            "https://test.org/GW000001_123456.json",
            json={"error": True},
            status=500,
        )

        with self.con_patch, self.assertLogs(level=logging.ERROR):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()
        self.assertEqual(len(self.get_completed_jobs()), 0)

        error_rows = self.get_job_errors()
        self.assertEqual(len(error_rows), 1)
        self.assertEqual(error_rows[0]["job_id"], "GW000001_123456")
        self.assertEqual(error_rows[0]["failure_count"], 1)
        self.assertIn("Unable to fetch event json", error_rows[0]["last_error"])

    # ---- failure count increments ------------------------------------------

    @responses.activate
    def test_failure_count_increments(self, gwc):
        """Running twice with same H5 404 → failure_count=2 on second run."""
        self.add_allevents_response()
        self.add_event_response()
        responses.add(responses.GET, "https://test.org/GW000001.h5", status=404)

        with self.con_patch, self.assertLogs(level=logging.ERROR):
            gwosc_ingest.check_and_download()

        error_rows = self.get_job_errors()
        self.assertEqual(error_rows[0]["failure_count"], 1)

        # Second run — re-register the same HTTP mocks
        responses.reset()
        self.add_allevents_response()
        self.add_event_response()
        responses.add(responses.GET, "https://test.org/GW000001.h5", status=404)

        with self.con_patch, self.assertLogs(level=logging.ERROR):
            gwosc_ingest.check_and_download()

        error_rows = self.get_job_errors()
        self.assertEqual(len(error_rows), 1)
        self.assertEqual(error_rows[0]["failure_count"], 2)

    # ---- threshold boundary tests ------------------------------------------

    @responses.activate
    def test_failure_below_threshold_still_retried(self, gwc):
        """Pre-seed failure_count=23 — event should still be retried, and on success, uploaded."""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response()

        # Pre-seed job_errors at threshold - 1
        with self.con_patch:
            self.con.row_factory = None
            cur = self.con.cursor()
            gwosc_ingest.create_table(cur)
            gwosc_ingest.create_job_errors_table(cur)
            cur.execute(
                "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error) VALUES (?, ?, CURRENT_TIMESTAMP, ?)",  # noqa: E501
                ("GW000001_123456", gwosc_ingest.MAX_RETRY_ATTEMPTS - 1, "previous error"),
            )
            self.con.commit()
            self.con.row_factory = __import__("sqlite3").Row

        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_called_once()

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000001_123456")
        self.assertEqual(sqlite_rows[0]["success"], 1)
        self.assertEqual(sqlite_rows[0]["reason"], "completed_submit")

    @responses.activate
    def test_failure_at_threshold_marks_broken(self, gwc):
        """Pre-seed failure_count=24 → completed_jobs written with reason=max_retries_exceeded, no upload."""
        self.add_allevents_response()

        # Pre-seed job_errors at threshold
        with self.con_patch:
            self.con.row_factory = None
            cur = self.con.cursor()
            gwosc_ingest.create_table(cur)
            gwosc_ingest.create_job_errors_table(cur)
            cur.execute(
                "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error) VALUES (?, ?, CURRENT_TIMESTAMP, ?)",  # noqa: E501
                ("GW000001_123456", gwosc_ingest.MAX_RETRY_ATTEMPTS, "download failed"),
            )
            self.con.commit()
            self.con.row_factory = __import__("sqlite3").Row

        with self.con_patch, self.assertLogs(level=logging.ERROR):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000001_123456")
        self.assertEqual(sqlite_rows[0]["success"], 0)
        self.assertEqual(sqlite_rows[0]["reason"], "max_retries_exceeded")
        self.assertIn("download failed", sqlite_rows[0]["reason_data"])

    # ---- skip-to-next tests ------------------------------------------------

    @responses.activate
    def test_skip_to_next_on_h5_failure(self, gwc):
        """Two events: first H5 404, second succeeds → second uploaded, first gets failure_count=1."""
        self.add_two_events_allevents_response()
        self.add_event_response()  # GW000001_123456
        self.add_second_event_response()  # GW000002_654321

        # First event H5 fails
        responses.add(responses.GET, "https://test.org/GW000001.h5", status=404)
        # Second event H5 succeeds
        self.add_second_file_response()

        with self.con_patch, self.assertLogs(level=logging.ERROR):
            gwosc_ingest.check_and_download()

        # Second event should have been uploaded
        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000002_654321--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000002.h5",
        )

        # First event: job_errors row, no completed_jobs
        error_rows = self.get_job_errors()
        self.assertEqual(len(error_rows), 1)
        self.assertEqual(error_rows[0]["job_id"], "GW000001_123456")
        self.assertEqual(error_rows[0]["failure_count"], 1)

        # Second event: completed_jobs row
        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000002_654321")
        self.assertEqual(sqlite_rows[0]["success"], 1)

    @responses.activate
    def test_skip_to_next_on_event_json_failure(self, gwc):
        """Two events: first event JSON 500, second succeeds → second uploaded."""
        self.add_two_events_allevents_response()

        # First event JSON fails
        responses.add(
            responses.GET,
            "https://test.org/GW000001_123456.json",
            json={"error": True},
            status=500,
        )
        # Second event succeeds
        self.add_second_event_response()
        self.add_second_file_response()

        with self.con_patch, self.assertLogs(level=logging.ERROR):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000002_654321--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000002.h5",
        )

        # First event: job_errors row
        error_rows = self.get_job_errors()
        self.assertEqual(len(error_rows), 1)
        self.assertEqual(error_rows[0]["job_id"], "GW000001_123456")

        # Second event: completed
        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000002_654321")

    @responses.activate
    def test_max_retries_continues_to_next_event(self, gwc):
        """First at failure_count=24, second succeeds → first marked broken, second uploaded."""
        self.add_two_events_allevents_response()
        self.add_second_event_response()
        self.add_second_file_response()

        # Pre-seed first event at max retries
        with self.con_patch:
            self.con.row_factory = None
            cur = self.con.cursor()
            gwosc_ingest.create_table(cur)
            gwosc_ingest.create_job_errors_table(cur)
            cur.execute(
                "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error) VALUES (?, ?, CURRENT_TIMESTAMP, ?)",  # noqa: E501
                ("GW000001_123456", gwosc_ingest.MAX_RETRY_ATTEMPTS, "persistent failure"),
            )
            self.con.commit()
            self.con.row_factory = __import__("sqlite3").Row

        with self.con_patch, self.assertLogs(level=logging.ERROR):
            gwosc_ingest.check_and_download()

        # Second event uploaded
        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000002_654321--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000002.h5",
        )

        # Both in completed_jobs
        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 2)
        # First: marked broken
        broken = [r for r in sqlite_rows if r["job_id"] == "GW000001_123456"][0]
        self.assertEqual(broken["success"], 0)
        self.assertEqual(broken["reason"], "max_retries_exceeded")
        # Second: successful
        success = [r for r in sqlite_rows if r["job_id"] == "GW000002_654321"][0]
        self.assertEqual(success["success"], 1)
        self.assertEqual(success["reason"], "completed_submit")

    # ---- transient recovery ------------------------------------------------

    @responses.activate
    def test_transient_recovery(self, gwc):
        """Pre-seed failure_count=3, event succeeds this run → uploaded normally."""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response()

        # Pre-seed some failures
        with self.con_patch:
            self.con.row_factory = None
            cur = self.con.cursor()
            gwosc_ingest.create_table(cur)
            gwosc_ingest.create_job_errors_table(cur)
            cur.execute(
                "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error) VALUES (?, ?, CURRENT_TIMESTAMP, ?)",  # noqa: E501
                ("GW000001_123456", 3, "temporary glitch"),
            )
            self.con.commit()
            self.con.row_factory = __import__("sqlite3").Row

        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_called_once()

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000001_123456")
        self.assertEqual(sqlite_rows[0]["success"], 1)
        self.assertEqual(sqlite_rows[0]["reason"], "completed_submit")

    # ---- all-failing scenario ----------------------------------------------

    @responses.activate
    def test_all_events_failing(self, gwc):
        """Two events, both H5 404 → neither in completed_jobs, both get failure_count++."""
        self.add_two_events_allevents_response()
        self.add_event_response()
        self.add_second_event_response()

        # Both H5 files fail
        responses.add(responses.GET, "https://test.org/GW000001.h5", status=404)
        responses.add(responses.GET, "https://test.org/GW000002.h5", status=404)

        with self.con_patch, self.assertLogs(level=logging.ERROR):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        # No completed jobs
        self.assertEqual(len(self.get_completed_jobs()), 0)

        # Both have job_errors entries
        error_rows = self.get_job_errors()
        self.assertEqual(len(error_rows), 2)
        error_ids = {r["job_id"] for r in error_rows}
        self.assertEqual(error_ids, {"GW000001_123456", "GW000002_654321"})
        for row in error_rows:
            self.assertEqual(row["failure_count"], 1)

    # ---- mix scenario: broken + transient + success ------------------------

    @responses.activate
    def test_mix_broken_transient_success(self, gwc):
        """Three events: first at max retries (marked broken), second H5 404
        (incremented), third succeeds → all handled correctly in one run."""
        events = {
            "GW000001_123456": {
                "commonName": "GW000001_123456",
                "catalog.shortName": "GWTC-3-confident",
                "jsonurl": "https://test.org/GW000001_123456.json",
            },
            "GW000002_654321": {
                "commonName": "GW000002_654321",
                "catalog.shortName": "GWTC-3-confident",
                "jsonurl": "https://test.org/GW000002_654321.json",
            },
            "GW000003_111111": {
                "commonName": "GW000003_111111",
                "catalog.shortName": "GWTC-3-confident",
                "jsonurl": "https://test.org/GW000003_111111.json",
            },
        }
        self.add_allevents_response(events)

        # Second event: event JSON + H5 404
        self.add_event_response(event_name="GW000002_654321", data_url="https://test.org/GW000002.h5")
        responses.add(responses.GET, "https://test.org/GW000002.h5", status=404)

        # Third event: success
        self.add_event_response(event_name="GW000003_111111", data_url="https://test.org/GW000003.h5")
        self.add_file_response(url_path="GW000003.h5")

        # Pre-seed first event at max retries
        with self.con_patch:
            self.con.row_factory = None
            cur = self.con.cursor()
            gwosc_ingest.create_table(cur)
            gwosc_ingest.create_job_errors_table(cur)
            cur.execute(
                "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error) VALUES (?, ?, CURRENT_TIMESTAMP, ?)",  # noqa: E501
                ("GW000001_123456", gwosc_ingest.MAX_RETRY_ATTEMPTS, "permanently broken"),
            )
            self.con.commit()
            self.con.row_factory = __import__("sqlite3").Row

        with self.con_patch, self.assertLogs(level=logging.ERROR):
            gwosc_ingest.check_and_download()

        # Third event uploaded
        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000003_111111--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000003.h5",
        )

        # Completed jobs: first (broken) and third (success)
        sqlite_rows = self.get_completed_jobs()
        completed_ids = {r["job_id"] for r in sqlite_rows}
        self.assertEqual(completed_ids, {"GW000001_123456", "GW000003_111111"})

        broken = [r for r in sqlite_rows if r["job_id"] == "GW000001_123456"][0]
        self.assertEqual(broken["reason"], "max_retries_exceeded")
        self.assertEqual(broken["success"], 0)

        success = [r for r in sqlite_rows if r["job_id"] == "GW000003_111111"][0]
        self.assertEqual(success["reason"], "completed_submit")
        self.assertEqual(success["success"], 1)

        # Second event: job_errors incremented
        error_rows = self.get_job_errors()
        second_errors = [r for r in error_rows if r["job_id"] == "GW000002_654321"]
        self.assertEqual(len(second_errors), 1)
        self.assertEqual(second_errors[0]["failure_count"], 1)
