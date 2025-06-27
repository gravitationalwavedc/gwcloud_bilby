import logging
import unittest
from unittest.mock import patch, call
import responses
import sqlite3
from collections import namedtuple
from gwdc_python.exceptions import GWDCUnknownException

import gwosc_ingest

logger = logging.getLogger("gwosc_ingest")
while logger.hasHandlers():
    logger.removeHandler(logger.handlers[0])

# Use test configuration
gwosc_ingest.DB_PATH = ":memory:"
gwosc_ingest.GWCLOUD_TOKEN = "VALID"
gwosc_ingest.AUTH_ENDPOINT = "https://authendpoint/graphql"
gwosc_ingest.ENDPOINT = "https://bilby/graphql"


@unittest.mock.patch("gwosc_ingest.GWCloud", autospec=True)
class TestGWOSCCron(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con_patch = patch("sqlite3.connect", lambda x: self.con)

    def add_allevents_response(self):
        responses.add(
            responses.GET,
            "https://gwosc.org/eventapi/json/allevents",
            json={
                "events": {
                    "GW000001_123456": {
                        "commonName": "GW000001_123456",
                        "catalog.shortName": "GWTC-3-confident",
                        "jsonurl": "https://test.org/GW000001_123456.json",
                    }
                }
            },
        )

    def add_event_response(self):
        responses.add(
            responses.GET,
            "https://test.org/GW000001_123456.json",
            json={
                "events": {
                    "GW000001_123456": {
                        "commonName": "GW000001_123456",
                        "catalog.shortName": "GWTC-3-confident",
                        "GPS": 1729400000,
                        "gracedb_id": "S123456z",
                        "parameters": {
                            "AAAAA": {
                                "is_preferred": True,
                                "data_url": "https://test.org/GW000001.h5",
                            }
                        },
                    }
                }
            },
        )

    def add_file_response(self, filename="good.h5", url_path="GW000001.h5"):
        # make the file available for download
        with open(f"test_fixtures/{filename}", "rb") as f:
            h5data = f.read()
        responses.add(responses.GET, f"https://test.org/{url_path}", h5data)

    @responses.activate
    def test_normal(self, gwc):
        """Assuming a normal h5 file with 1 config, does it save it to bilby correctly"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response()

        # Do the thing, Zhu Li
        with self.con_patch:
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001_123456--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        self.assertEqual(row["success"], 1)
        self.assertEqual(row["reason"], "completed_submit")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")

    @responses.activate
    def test_none_found(self, gwc):
        """Assuming a valid h5 file with no valid configs (ini parameters), it should not create a bilby job"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response("no_configs.h5")

        # Do the thing, Zhu Li
        with self.con_patch:
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_not_called()

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        # better not have
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["reason"], "completed_submit")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")

    @responses.activate
    def test_no_preferred(self, gwc):
        """Assuming there are no is_preferred parameters, does it not save anything"""
        self.add_allevents_response()
        responses.add(
            responses.GET,
            "https://test.org/GW000001_123456.json",
            json={
                "events": {
                    "GW000001_123456": {
                        "commonName": "GW000001_123456",
                        "catalog.shortName": "GWTC-3-confident",
                        "GPS": 1729400000,
                        "gracedb_id": "S123456z",
                        "parameters": {
                            "AAAAA": {
                                "is_preferred": False,
                                "data_url": "https://test.org/GW000001.h5",
                            },
                            "BBBBB": {
                                "is_preferred": False,
                                "data_url": "https://test.org/GW000002.h5",
                            },
                        },
                    }
                }
            },
        )

        # Do[n't do] the thing, Zhu Li
        with (
            self.con_patch,
            self.assertRaises(SystemExit),
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_not_called()

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        # better not have
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["reason"], "no preferred job")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")

        # does it tell us why it failed?
        self.assertIn("Unable to find preferred job", logs.output[0])

    @responses.activate
    def test_too_many_preferred(self, gwc):
        """More than 1 preferred h5 file found"""
        self.add_allevents_response()
        responses.add(
            responses.GET,
            "https://test.org/GW000001_123456.json",
            json={
                "events": {
                    "GW000001_123456": {
                        "commonName": "GW000001_123456",
                        "catalog.shortName": "GWTC-3-confident",
                        "GPS": 1729400000,
                        "gracedb_id": "S123456z",
                        "parameters": {
                            "AAAAA": {
                                "is_preferred": True,
                                "data_url": "https://test.org/GW000001.h5",
                            },
                            "BBBBB": {
                                "is_preferred": True,
                                "data_url": "https://test.org/GW000002.h5",
                            },
                        },
                    }
                }
            },
        )

        # Do[n't do] the thing, Zhu Li
        with (
            self.con_patch,
            self.assertRaises(SystemExit),
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_not_called()

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        # better not have
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["reason"], "no preferred job")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")

        # does it tell us why it failed?
        self.assertIn("Unable to find preferred job", logs.output[0])

    @responses.activate
    def test_download_allevents_error(self, gwc):
        """What happens if any part of the download process fails due to external problems?
        Specifically,
            - Downloading the allevents json
        """
        responses.add(
            responses.GET,
            "https://gwosc.org/eventapi/json/allevents",
            json={"error": True},
            status=500,
        )

        # Do[n't do] the thing, Zhu Li
        with (
            self.con_patch,
            self.assertRaises(SystemExit),
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_not_called()

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        # better not have
        self.assertEqual(len(sqlite_rows), 0)

        # does it tell us why it failed?
        self.assertIn("Unable to fetch allevents json", logs.output[0])

    @responses.activate
    def test_download_specific_event_error(self, gwc):
        """What happens if any part of the download process fails due to external problems?
        Specifically,
            - Downloading the specific event json
        """
        self.add_allevents_response()
        responses.add(
            responses.GET,
            "https://test.org/GW000001_123456.json",
            json={"error": True},
            status=500,
        )

        # Do[n't do] the thing, Zhu Li
        with (
            self.con_patch,
            self.assertRaises(SystemExit),
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_not_called()

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        # better not have
        self.assertEqual(len(sqlite_rows), 0)

        # does it tell us why it failed?
        self.assertIn("Unable to fetch event json", logs.output[0])

    @responses.activate
    def test_download_h5_error(self, gwc):
        """What happens if any part of the download process fails due to external problems?
        Specifically,
            - The h5 file is missing
        """
        self.add_allevents_response()
        self.add_event_response()

        # make the file _un_available for download
        responses.add(responses.GET, "https://test.org/GW000001.h5", status=404)

        # Do[n't do] the thing, Zhu Li
        # Also mock stderr so it doesn't dump the exception to test output
        with (
            self.con_patch,
            self.assertRaises(SystemExit),
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_not_called()

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        # better not have
        self.assertEqual(len(sqlite_rows), 0)

        # does it tell us why it failed?
        self.assertIn("Downloading https://test.org/GW000001.h5 failed", logs.output[0])

    @responses.activate
    def test_creates_event_id(self, gwc):
        """If a job has a valid event_id we haven't encountered before, create one"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response()

        # Do the thing, Zhu Li
        with self.con_patch:
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001_123456--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        # Did it create a new event_id
        gwc.return_value.create_event_id.assert_called_once_with(
            "GW000001_123456", 1729400000, "S123456z"
        )

        # Has it set the event id on the job?
        gwc.return_value.upload_external_job.return_value.set_event_id.assert_called_once_with(
            gwc.return_value.create_event_id.return_value
        )

    @responses.activate
    def test_doesnt_create_event_id(self, gwc):
        """If a job has a valid event_id that already exists, behave normally"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response()

        # mock that this event_id is already in the DB
        event_id = namedtuple("event_id", ["event_id"])
        specific_event_id = event_id("GW000001_123456")
        gwc.return_value.get_all_event_ids.return_value = [specific_event_id]

        # Do the thing, Zhu Li
        with self.con_patch:
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001_123456--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        # Did it _not_ create a new event_id
        gwc.return_value.create_event_id.assert_not_called()

        # Has it set the event id on the job?
        gwc.return_value.upload_external_job.return_value.set_event_id.assert_called_once_with(
            specific_event_id
        )

    @responses.activate
    def test_invalid_event_id(self, gwc):
        """If a file does not have a valid event ID, don't create one"""
        # We add these manually instead of using the helper functions because the helper
        # functions have implcit valid event IDs
        responses.add(
            responses.GET,
            "https://gwosc.org/eventapi/json/allevents",
            json={
                "events": {
                    "GW000001": {
                        "commonName": "GW000001",
                        "catalog.shortName": "GWTC-3-confident",
                        "jsonurl": "https://test.org/GW000001.json",
                    }
                }
            },
        )
        responses.add(
            responses.GET,
            "https://test.org/GW000001.json",
            json={
                "events": {
                    "GW000001": {
                        "commonName": "GW000001",
                        "catalog.shortName": "GWTC-3-confident",
                        "GPS": 1729400000,
                        "gracedb_id": "S123456z",
                        "parameters": {
                            "AAAAA": {
                                "is_preferred": True,
                                "data_url": "https://test.org/GW000001.h5",
                            }
                        },
                    }
                }
            },
        )
        # make the file available for download
        with open("test_fixtures/good.h5", "rb") as f:
            h5data = f.read()
        responses.add(responses.GET, "https://test.org/GW000001.h5", h5data)

        # Do the thing, Zhu Li
        with self.con_patch:
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        # Did it _not_ create a new event_id
        gwc.return_value.create_event_id.assert_not_called()

        # Has it set the event id on the job?
        gwc.return_value.upload_external_job.return_value.set_event_id.assert_not_called()

    @responses.activate
    def test_dont_duplicate_jobs(self, gwc):
        """If a file already has a matching bilbyJob, deal with it"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response()

        # Pretend that the job has already been created
        gwc.return_value.upload_external_job.side_effect = GWDCUnknownException(
            "Duplicate job"
        )

        # Do the thing, Zhu Li
        # Also mock stderr so it doesn't dump the exception to test output
        with self.con_patch, self.assertLogs(level=logging.ERROR) as logs:
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001_123456--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        # better not have
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["reason"], "completed_submit")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")

        self.assertIn("Failed to create BilbyJob", logs.output[0])

    @responses.activate
    def test_multiple_bilbyjobs(self, gwc):
        """If a h5 file contains multiple config_files, create multiple bilbyJobs"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response("multiple_configs.h5")

        # Do the thing, Zhu Li
        with self.con_patch:
            gwosc_ingest.check_and_download()

        # has the job completed?
        calls = [
            call(
                "GW000001_123456--IMRPhenom",
                "IMRPhenom",
                False,
                "VALID=good",
                "https://test.org/GW000001.h5",
            ),
            call(
                "GW000001_123456--IMRPhenom2ElectricBoogaloo",
                "IMRPhenom2ElectricBoogaloo",
                False,
                "VALID=good",
                "https://test.org/GW000001.h5",
            ),
        ]
        gwc.return_value.upload_external_job.assert_has_calls(calls, any_order=True)

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        # better not have
        self.assertEqual(row["success"], 1)
        self.assertEqual(row["reason"], "completed_submit")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")

    @responses.activate
    def test_skip_if_present(self, gwc):
        """If a job is already in sqlite, skip it"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response()

        # Add the 'job history' to sqlite
        self.con.row_factory = sqlite3.Row
        cur = self.con.cursor()
        gwosc_ingest.create_table(cur)
        "CREATE TABLE IF NOT EXISTS completed_jobs (job_id TEXT PRIMARY KEY, success BOOLEAN, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, reason TEXT, reason_data TEXT, catalog_shortname TEXT,common_name, all_succeeded INT, none_succeeded INT, is_latest_version BOOLEAN)"  # noqa
        cur.execute(
            "INSERT INTO completed_jobs (job_id, success, reason, reason_data, catalog_shortname, common_name, all_succeeded, none_succeeded, is_latest_version ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "GW000001_123456",
                True,
                "completed_submit",
                "",
                "GWTC-3-confident",
                "GW000001_123456",
                1,
                0,
                1,
            ),
        )

        # Do the thing, Zhu Li
        with (
            self.con_patch,
            self.assertRaises(SystemExit),
            self.assertLogs(level=logging.INFO) as logs,
        ):
            gwosc_ingest.check_and_download()

        # Has it made a record of this job in sqlite?
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000001_123456")
        self.assertEqual(sqlite_rows[0]["success"], 1)

        # Did it tell us why it did nothing?
        self.assertIn("Nothing to do 😊", logs.output[-1])

    @responses.activate
    def test_no_dataurl(self, gwc):
        """If a preferred job doesn't contain a dataurl, skip it"""
        self.add_allevents_response()
        responses.add(
            responses.GET,
            "https://test.org/GW000001_123456.json",
            json={
                "events": {
                    "GW000001_123456": {
                        "commonName": "GW000001_123456",
                        "catalog.shortName": "GWTC-3-confident",
                        "GPS": 1729400000,
                        "gracedb_id": "S123456z",
                        "parameters": {
                            "AAAAA": {
                                "is_preferred": True,
                                "data_url": "",
                            }
                        },
                    }
                }
            },
        )

        # Do the thing, Zhu Li
        with (
            self.con_patch,
            self.assertRaises(SystemExit),
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_not_called()

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["reason"], "no dataurl")
        self.assertEqual(row["is_latest_version"], -1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")

        # Did it tell us why it failed?
        self.assertIn("does not contain a dataurl", logs.output[0])

    def test_bad_ini(self, gwc):
        """If an ini file is invalid, skip it"""
        # If an ini file is bad, an exception is returned by GWCloud when submitting the job.
        # Thus, this test is identical to TestGWOSCCron.test_dont_duplicate_jobs
        pass

    @responses.activate
    def test_colon_name(self, gwc):
        """If a job name contains weird characters, make it safe for SLURM (even though these
        jobs aren't submitted to slurm, it's easier to ensure that ALL jobs comply with those
        requirements rather than have special checks for external jobs)"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response("colon.h5")

        # Do the thing, Zhu Li
        with self.con_patch:
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001_123456--IMRPhenom-Test-3",
            "IMRPhenom:Test~3",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        self.assertEqual(row["success"], 1)
        self.assertEqual(row["reason"], "completed_submit")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")

    @responses.activate
    def test_bad_h5(self, gwc):
        """If a h5 file contains a top level key that _isn't_ a group, do we fail safely"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response("bad.h5")

        # Do the thing, Zhu Li
        with self.con_patch:
            gwosc_ingest.check_and_download()

        # did it not attempt to add a job
        gwc.return_value.upload_external_job.assert_not_called()

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["reason"], "completed_submit")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")

    @responses.activate
    def test_special_symbols_event(self, gwc):
        """If the event json contains symbols which can't be in a bilby job name, do we handle it safely"""
        responses.add(
            responses.GET,
            "https://gwosc.org/eventapi/json/allevents",
            json={
                "events": {
                    "GW000001.123456": {
                        "commonName": "GW000001.123456",
                        "jsonurl": "https://test.org/GW000001.123456.json",
                    }
                }
            },
        )
        responses.add(
            responses.GET,
            "https://test.org/GW000001.123456.json",
            json={
                "events": {
                    "GW000001.123456": {
                        "commonName": "GW000001.123456",
                        "catalog.shortName": "GWTC-3-confident",
                        "GPS": 1729400000,
                        "gracedb_id": "S123456z",
                        "parameters": {
                            "AAAAA": {
                                "is_preferred": True,
                                "data_url": "https://test.org/GW000001.h5",
                            }
                        },
                    }
                }
            },
        )
        self.add_file_response()

        # Do the thing, Zhu Li
        with self.con_patch:
            gwosc_ingest.check_and_download()

        # has the job completed?
        # and is it saved under a bilby-safe name?
        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001-123456--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        # Has it made a record of this job in sqlite?
        # and is it saved under the original event ID in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001.123456")
        self.assertEqual(row["success"], 1)
        self.assertEqual(row["reason"], "completed_submit")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001.123456")
