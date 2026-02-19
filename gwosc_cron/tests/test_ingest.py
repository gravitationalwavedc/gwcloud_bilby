import logging
import sqlite3
import unittest
from collections import namedtuple
from unittest.mock import call

import responses
from gwdc_python.exceptions import GWDCUnknownException
from parameterized import parameterized

import gwosc_ingest
from tests.base import GWOSCTestBase


@unittest.mock.patch("gwosc_ingest.GWCloud", autospec=True)
class TestGWOSCCron(GWOSCTestBase):
    @responses.activate
    def test_normal(self, gwc):
        """Assuming a normal h5 file with 1 config, does it save it to bilby correctly"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response()

        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001_123456--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        sqlite_rows = self.get_completed_jobs()
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

        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
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

        with (
            self.con_patch,
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["reason"], "no preferred job")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")
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

        with (
            self.con_patch,
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["reason"], "no preferred job")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")
        self.assertIn("Unable to find preferred job", logs.output[0])

    @responses.activate
    def test_download_allevents_error(self, gwc):
        """If the allevents endpoint fails, the script exits without writing sqlite."""
        responses.add(
            responses.GET,
            "https://gwosc.org/eventapi/json/allevents",
            json={"error": True},
            status=500,
        )

        with (
            self.con_patch,
            self.assertRaises(SystemExit),
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 0)
        self.assertIn("Unable to fetch allevents json", logs.output[0])

    @responses.activate
    def test_download_specific_event_error(self, gwc):
        """If a specific event's JSON endpoint fails, the failure is recorded in job_errors."""
        self.add_allevents_response()
        responses.add(
            responses.GET,
            "https://test.org/GW000001_123456.json",
            json={"error": True},
            status=500,
        )

        with (
            self.con_patch,
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        # No completed_jobs row — transient failure
        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 0)

        # But a job_errors row IS written
        error_rows = self.get_job_errors()
        self.assertEqual(len(error_rows), 1)
        self.assertEqual(error_rows[0]["job_id"], "GW000001_123456")
        self.assertEqual(error_rows[0]["failure_count"], 1)

        self.assertIn("Unable to fetch event json", logs.output[0])

    @responses.activate
    def test_download_h5_error(self, gwc):
        """If the H5 file download fails (e.g. 404), the failure is recorded in job_errors."""
        self.add_allevents_response()
        self.add_event_response()
        responses.add(responses.GET, "https://test.org/GW000001.h5", status=404)

        with (
            self.con_patch,
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        # No completed_jobs row — transient failure
        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 0)

        # But a job_errors row IS written
        error_rows = self.get_job_errors()
        self.assertEqual(len(error_rows), 1)
        self.assertEqual(error_rows[0]["job_id"], "GW000001_123456")
        self.assertEqual(error_rows[0]["failure_count"], 1)

        self.assertIn("Downloading https://test.org/GW000001.h5 failed", logs.output[0])

    @responses.activate
    def test_creates_event_id(self, gwc):
        """If a job has a valid event_id we haven't encountered before, create one"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response()

        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001_123456--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        gwc.return_value.create_event_id.assert_called_once_with("GW000001_123456", 1729400000, "S123456z")
        gwc.return_value.upload_external_job.return_value.set_event_id.assert_called_once_with(
            gwc.return_value.create_event_id.return_value
        )

    @responses.activate
    def test_doesnt_create_event_id(self, gwc):
        """If a job has a valid event_id that already exists, behave normally"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response()

        event_id = namedtuple("event_id", ["event_id"])
        specific_event_id = event_id("GW000001_123456")
        gwc.return_value.get_all_event_ids.return_value = [specific_event_id]

        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001_123456--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        gwc.return_value.create_event_id.assert_not_called()
        gwc.return_value.upload_external_job.return_value.set_event_id.assert_called_once_with(specific_event_id)

    @responses.activate
    def test_invalid_event_id(self, gwc):
        """If a file does not have a valid event ID, don't create one"""
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
        with open("test_fixtures/good.h5", "rb") as f:
            h5data = f.read()
        responses.add(responses.GET, "https://test.org/GW000001.h5", h5data)

        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        gwc.return_value.create_event_id.assert_not_called()
        gwc.return_value.upload_external_job.return_value.set_event_id.assert_not_called()

    @responses.activate
    def test_dont_duplicate_jobs(self, gwc):
        """If a file already has a matching bilbyJob, deal with it"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response()

        gwc.return_value.upload_external_job.side_effect = GWDCUnknownException("Duplicate job")

        with self.con_patch, self.assertLogs(level=logging.ERROR) as logs:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001_123456--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
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

        with self.con_patch:
            gwosc_ingest.check_and_download()

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

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
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
        cur.execute(
            "INSERT INTO completed_jobs (job_id, success, reason, reason_data, catalog_shortname, common_name, all_succeeded, none_succeeded, is_latest_version ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",  # noqa: E501
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

        with (
            self.con_patch,
            self.assertRaises(SystemExit),
            self.assertLogs(level=logging.INFO) as logs,
        ):
            gwosc_ingest.check_and_download()

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000001_123456")
        self.assertEqual(sqlite_rows[0]["success"], 1)
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

        with (
            self.con_patch,
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["reason"], "no dataurl")
        self.assertEqual(row["is_latest_version"], -1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")
        self.assertIn("does not contain a dataurl", logs.output[0])

    def test_bad_ini(self, gwc):
        """If an ini file is invalid, skip it"""
        # If an ini file is bad, an exception is returned by GWCloud when submitting the job.
        # Thus, this test is identical to TestGWOSCCron.test_dont_duplicate_jobs
        pass

    @responses.activate
    def test_colon_name(self, gwc):
        """If a job name contains weird characters, make it safe for SLURM"""
        self.add_allevents_response()
        self.add_event_response()
        self.add_file_response("colon.h5")

        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001_123456--IMRPhenom-Test-3",
            "IMRPhenom:Test~3",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        sqlite_rows = self.get_completed_jobs()
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

        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        sqlite_rows = self.get_completed_jobs()
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

        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001-123456--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000001.h5",
        )

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001.123456")
        self.assertEqual(row["success"], 1)
        self.assertEqual(row["reason"], "completed_submit")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001.123456")

    @parameterized.expand(["GWTC-3-marginal", "O1_O2-Preliminary", "Initial_LIGO_Virgo"])
    @responses.activate
    def test_ignored_names(self, gwc, catalog_shortname):
        """If the event is in a catalog which we ignore, then we shouldn't submit it"""
        responses.add(
            responses.GET,
            "https://gwosc.org/eventapi/json/allevents",
            json={
                "events": {
                    "GW000001_123456": {
                        "commonName": "GW000001_123456",
                        "catalog.shortName": catalog_shortname,
                        "jsonurl": "https://test.org/GW000001_123456.json",
                    }
                }
            },
        )
        responses.add(
            responses.GET,
            "https://test.org/GW000001_123456.json",
            json={
                "events": {
                    "GW000001_123456": {
                        "commonName": "GW000001_123456",
                        "catalog.shortName": catalog_shortname,
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

        with (
            self.con_patch,
            self.assertLogs(level=logging.ERROR) as logs,
        ):
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456")
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["reason"], "ignored_event")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], catalog_shortname)
        self.assertEqual(row["common_name"], "GW000001_123456")
        self.assertIn("ignored due to matching", logs.output[0])

    @responses.activate
    def test_not_latest_version(self, gwc):
        """If the event is not the latest one for that event, then we can ignore it safely"""
        responses.add(
            responses.GET,
            "https://gwosc.org/eventapi/json/allevents",
            json={
                "events": {
                    "GW000001_123456-v1": {
                        "commonName": "GW000001_123456",
                        "catalog.shortName": "GWTC-3-confident",
                        "jsonurl": "https://test.org/GW000001_123456-v1.json",
                    },
                    "GW000001_123456-v2": {
                        "commonName": "GW000001_123456",
                        "catalog.shortName": "GWTC-3-confident",
                        "jsonurl": "https://test.org/GW000001_123456-v2.json",
                    },
                }
            },
        )
        responses.add(
            responses.GET,
            "https://test.org/GW000001_123456-v1.json",
            json={
                "events": {
                    "GW000001_123456-v1": {
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
        responses.add(
            responses.GET,
            "https://test.org/GW000001_123456-v2.json",
            json={
                "events": {
                    "GW000001_123456-v2": {
                        "commonName": "GW000001_123456",
                        "catalog.shortName": "GWTC-3-confident",
                        "GPS": 1729400000,
                        "gracedb_id": "S123456z",
                        "parameters": {
                            "AAAAA": {
                                "is_preferred": True,
                                "data_url": "https://test.org/GW000002.h5",
                            }
                        },
                    }
                }
            },
        )
        self.add_file_response("bad.h5")
        self.add_file_response("good.h5", "GW000002.h5")

        # First run processes v1 (bad h5 — no configs, but still writes completed_jobs)
        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_not_called()

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 1)
        row = sqlite_rows[0]
        self.assertEqual(row["job_id"], "GW000001_123456-v1")
        self.assertEqual(row["success"], 0)
        self.assertEqual(row["reason"], "completed_submit")
        self.assertEqual(row["is_latest_version"], 0)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")

        # Second run should process v2 successfully
        with self.con_patch:
            gwosc_ingest.check_and_download()

        gwc.return_value.upload_external_job.assert_called_once_with(
            "GW000001_123456-v2--IMRPhenom",
            "IMRPhenom",
            False,
            "VALID=good",
            "https://test.org/GW000002.h5",
        )

        sqlite_rows = self.get_completed_jobs()
        self.assertEqual(len(sqlite_rows), 2)
        row = sqlite_rows[1]
        self.assertEqual(row["job_id"], "GW000001_123456-v2")
        self.assertEqual(row["success"], 1)
        self.assertEqual(row["reason"], "completed_submit")
        self.assertEqual(row["is_latest_version"], 1)
        self.assertEqual(row["catalog_shortname"], "GWTC-3-confident")
        self.assertEqual(row["common_name"], "GW000001_123456")
