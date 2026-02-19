import logging
import sqlite3
import unittest
from unittest.mock import patch

import responses

import gwosc_ingest

logger = logging.getLogger("gwosc_ingest")
while logger.hasHandlers():
    logger.removeHandler(logger.handlers[0])

# Use test configuration
gwosc_ingest.DB_PATH = ":memory:"
gwosc_ingest.GWCLOUD_TOKEN = "VALID"
gwosc_ingest.AUTH_ENDPOINT = "https://authendpoint/graphql"
gwosc_ingest.ENDPOINT = "https://bilby/graphql"


class GWOSCTestBase(unittest.TestCase):
    """Shared setUp and HTTP-response helpers for gwosc_ingest tests."""

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con_patch = patch("sqlite3.connect", lambda x: self.con)

    # ---- single-event helpers ------------------------------------------------

    def add_allevents_response(self, events=None):
        """Register the allevents JSON endpoint.

        If *events* is ``None`` a single ``GW000001_123456`` event is returned.
        Pass a dict to customise.
        """
        if events is None:
            events = {
                "GW000001_123456": {
                    "commonName": "GW000001_123456",
                    "catalog.shortName": "GWTC-3-confident",
                    "jsonurl": "https://test.org/GW000001_123456.json",
                }
            }
        responses.add(
            responses.GET,
            "https://gwosc.org/eventapi/json/allevents",
            json={"events": events},
        )

    def add_event_response(
        self,
        event_name="GW000001_123456",
        common_name=None,
        catalog_shortname="GWTC-3-confident",
        data_url="https://test.org/GW000001.h5",
    ):  # noqa: E501
        if common_name is None:
            common_name = event_name
        responses.add(
            responses.GET,
            f"https://test.org/{event_name}.json",
            json={
                "events": {
                    event_name: {
                        "commonName": common_name,
                        "catalog.shortName": catalog_shortname,
                        "GPS": 1729400000,
                        "gracedb_id": "S123456z",
                        "parameters": {
                            "AAAAA": {
                                "is_preferred": True,
                                "data_url": data_url,
                            }
                        },
                    }
                }
            },
        )

    def add_file_response(self, filename="good.h5", url_path="GW000001.h5"):
        with open(f"test_fixtures/{filename}", "rb") as f:
            h5data = f.read()
        responses.add(responses.GET, f"https://test.org/{url_path}", h5data)

    # ---- multi-event helpers -------------------------------------------------

    def add_two_events_allevents_response(self):
        """Register allevents with GW000001_123456 and GW000002_654321."""
        self.add_allevents_response(
            {
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
            }
        )

    def add_second_event_response(self):
        self.add_event_response(
            event_name="GW000002_654321",
            data_url="https://test.org/GW000002.h5",
        )

    def add_second_file_response(self, filename="good.h5"):
        self.add_file_response(filename=filename, url_path="GW000002.h5")

    # ---- SQLite assertion helpers -------------------------------------------

    def get_completed_jobs(self):
        cur = self.con.cursor()
        return cur.execute("SELECT * FROM completed_jobs").fetchall()

    def get_job_errors(self):
        cur = self.con.cursor()
        return cur.execute("SELECT * FROM job_errors").fetchall()

    # ---- SQLite seeding helpers ---------------------------------------------

    def seed_job_error(self, job_id, failure_count, last_error="seeded error"):
        """Insert a pre-existing job_errors row, creating tables if needed."""
        with self.con_patch:
            cur = self.con.cursor()
            gwosc_ingest.create_table(cur)
            gwosc_ingest.create_job_errors_table(cur)
            cur.execute(
                "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error)"
                " VALUES (?, ?, CURRENT_TIMESTAMP, ?)",
                (job_id, failure_count, last_error),
            )
            self.con.commit()
