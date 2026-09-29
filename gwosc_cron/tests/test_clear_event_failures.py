import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

import gwosc_ingest
from clear_event_failures import clear_event_failures


class TestClearEventFailures(unittest.TestCase):
    """Unit tests for the clear_event_failures function."""

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.cur = self.con.cursor()
        gwosc_ingest.create_table(self.cur)
        gwosc_ingest.create_job_errors_table(self.cur)

    def tearDown(self):
        self.con.close()

    def test_deletes_event_id_failures_from_job_errors(self):
        self.cur.execute(
            "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error) "
            "VALUES (?, ?, CURRENT_TIMESTAMP, ?)",
            ("GW150914", 5, "Failed to create event_id for GW150914"),
        )
        self.cur.execute(
            "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error) "
            "VALUES (?, ?, CURRENT_TIMESTAMP, ?)",
            ("GW170817", 3, "Error creating EventID record"),
        )
        self.cur.execute(
            "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error) "
            "VALUES (?, ?, CURRENT_TIMESTAMP, ?)",
            ("GW190425_081805", 2, "Network timeout during download"),
        )
        self.con.commit()

        clear_event_failures(self.con, self.cur)

        rows = self.cur.execute("SELECT job_id, last_error FROM job_errors").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["job_id"], "GW190425_081805")
        self.assertEqual(rows[0]["last_error"], "Network timeout during download")

    def test_deletes_event_id_failures_from_completed_jobs_max_retries(self):
        self.cur.execute(
            "INSERT INTO completed_jobs (job_id, common_name, catalog_shortname, success, reason, is_latest_version, reason_data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "GW150914",
                "GW150914",
                "GWTC-1-confident",
                0,
                "max_retries_exceeded",
                1,
                "Failed to create event_id for GW150914",
            ),
        )
        self.cur.execute(
            "INSERT INTO completed_jobs (job_id, common_name, catalog_shortname, success, reason, is_latest_version, reason_data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "GW170817",
                "GW170817",
                "GWTC-1-confident",
                0,
                "max_retries_exceeded",
                1,
                "Invalid EventID trigger",
            ),
        )
        self.cur.execute(
            "INSERT INTO completed_jobs (job_id, common_name, catalog_shortname, success, reason, is_latest_version, reason_data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "GW190814",
                "GW190814",
                "GWTC-2",
                0,
                "max_retries_exceeded",
                1,
                "Download failed after retries",
            ),
        )
        self.cur.execute(
            "INSERT INTO completed_jobs (job_id, common_name, catalog_shortname, success, reason, is_latest_version, reason_data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "GW200105",
                "GW200105",
                "GWTC-3",
                1,
                "completed_submit",
                1,
                "event_id created",
            ),
        )
        self.con.commit()

        clear_event_failures(self.con, self.cur)

        rows = self.cur.execute("SELECT job_id, reason, reason_data FROM completed_jobs ORDER BY job_id").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["job_id"], "GW190814")
        self.assertEqual(rows[0]["reason"], "max_retries_exceeded")
        self.assertEqual(rows[1]["job_id"], "GW200105")
        self.assertEqual(rows[1]["reason"], "completed_submit")

    def test_retains_unrelated_errors_and_jobs(self):
        self.cur.execute(
            "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error) "
            "VALUES (?, ?, CURRENT_TIMESTAMP, ?)",
            ("NETWORK_ERROR_JOB", 1, "Connection refused: https://gwosc.org"),
        )
        self.cur.execute(
            "INSERT INTO completed_jobs (job_id, common_name, catalog_shortname, success, reason, is_latest_version, reason_data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "NETWORK_ERROR_JOB",
                "NETWORK_ERROR_JOB",
                "GWTC-3",
                0,
                "max_retries_exceeded",
                1,
                "Connection refused: https://gwosc.org",
            ),
        )
        self.con.commit()

        clear_event_failures(self.con, self.cur)

        err_rows = self.cur.execute("SELECT * FROM job_errors").fetchall()
        self.assertEqual(len(err_rows), 1)
        self.assertEqual(err_rows[0]["job_id"], "NETWORK_ERROR_JOB")

        comp_rows = self.cur.execute("SELECT * FROM completed_jobs").fetchall()
        self.assertEqual(len(comp_rows), 1)
        self.assertEqual(comp_rows[0]["job_id"], "NETWORK_ERROR_JOB")

    def test_commits_transaction(self):
        mock_con = MagicMock()
        mock_cur = MagicMock()
        clear_event_failures(mock_con, mock_cur)
        self.assertEqual(mock_cur.execute.call_count, 2)
        mock_con.commit.assert_called_once()


class TestClearEventFailuresCLI(unittest.TestCase):
    """Integration tests for clear_event_failures CLI execution."""

    def test_cli_missing_db_path_exits_with_error(self):
        env = {k: v for k, v in os.environ.items() if k != "DB_PATH"}
        env["PYTHONPATH"] = "."
        result = subprocess.run(
            [sys.executable, "clear_event_failures.py"],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: DB_PATH is not set in local.py or environment.", result.stderr)

    def test_cli_with_db_path_clears_failures(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            db_path = tmp.name
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            gwosc_ingest.create_table(cur)
            gwosc_ingest.create_job_errors_table(cur)
            cur.execute(
                "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error) "
                "VALUES (?, ?, CURRENT_TIMESTAMP, ?)",
                ("GW150914", 24, "Failed to create event_id for GW150914"),
            )
            cur.execute(
                "INSERT INTO completed_jobs (job_id, common_name, catalog_shortname, success, reason, is_latest_version, reason_data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "GW150914",
                    "GW150914",
                    "GWTC-1-confident",
                    0,
                    "max_retries_exceeded",
                    1,
                    "Failed to create event_id for GW150914",
                ),
            )
            con.commit()
            con.close()

            env = dict(os.environ)
            env["DB_PATH"] = db_path
            env["PYTHONPATH"] = "."
            result = subprocess.run(
                [sys.executable, "clear_event_failures.py"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn(f"Connecting to {db_path}...", result.stdout)
            self.assertIn("Event failures successfully cleared.", result.stdout)

            # Verify that records were deleted in the db file
            verify_con = sqlite3.connect(db_path)
            verify_cur = verify_con.cursor()
            err_count = verify_cur.execute("SELECT count(*) FROM job_errors").fetchone()[0]
            comp_count = verify_cur.execute("SELECT count(*) FROM completed_jobs").fetchone()[0]
            verify_con.close()
            self.assertEqual(err_count, 0)
            self.assertEqual(comp_count, 0)
