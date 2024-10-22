from io import StringIO
from requests.exceptions import HTTPError
import unittest
from unittest.mock import patch
import responses
import sqlite3
from collections import namedtuple

import gwosc_ingest

# Use test configuration
gwosc_ingest.DB_PATH=":memory:"
gwosc_ingest.GWCLOUD_TOKEN="VALID"
gwosc_ingest.AUTH_ENDPOINT="https://authendpoint/graphql"
gwosc_ingest.ENDPOINT="https://bilby/graphql"

@unittest.mock.patch("gwosc_ingest.GWCloud", autospec=True)
class TestGWOSCCron(unittest.TestCase):
    def setUp(self) -> None:
        self.con = sqlite3.connect(":memory:")
        gwosc_ingest.sqlite3.connect = lambda x: self.con
        pass

    @responses.activate
    def test_normal(self, gwc):
        """Assuming a normal h5 file with 1 config, does it save it to bilby correctly"""
        responses.add(responses.GET, "https://gwosc.org/eventapi/json/allevents", json={
            "events": {
                "GW000001": {
                    "jsonurl": "https://test.org/GW000001.json"
                }
            }
        })
        responses.add(responses.GET, "https://test.org/GW000001.json", json={
            "events": {
                "GW000001": {
                    "commonName": "GW000001",
                    "GPS": 1729400000,
                    "gracedb_id": "S123456z",
                    "parameters": {
                        "AAAAA": {
                            "is_preferred": True,
                            "data_url": "https://test.org/GW000001.h5",
                        }
                    }
                }
            }
        })

        # make the file available for download
        with open("text_fixtures/good.h5", 'rb') as f:
            h5data = f.read()
        responses.add(responses.GET, "https://test.org/GW000001.h5", h5data)


        stdout = StringIO()
        # Do the thing, Zhu Li
        with patch('sys.stdout', new = stdout):
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_called_once_with('GW000001--IMRPhenom', 'IMRPhenom', False, 'VALID=good', 'https://test.org/GW000001.h5')

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000001")
        self.assertEqual(sqlite_rows[0]["success"], 1)


    @responses.activate
    def test_none_found(self, gwc):
        """Assuming a valid h5 file with no valid configs, does it not save it to bilby correctly"""
        responses.add(responses.GET, "https://gwosc.org/eventapi/json/allevents", json={
            "events": {
                "GW000001": {
                    "jsonurl": "https://test.org/GW000001.json"
                }
            }
        })
        responses.add(responses.GET, "https://test.org/GW000001.json", json={
            "events": {
                "GW000001": {
                    "commonName": "GW000001",
                    "GPS": 1729400000,
                    "gracedb_id": "S123456z",
                    "parameters": {
                        "AAAAA": {
                            "is_preferred": True,
                            "data_url": "https://test.org/GW000001.h5",
                        }
                    }
                }
            }
        })

        # make the file available for download
        with open("text_fixtures/no_configs.h5", 'rb') as f:
            h5data = f.read()
        responses.add(responses.GET, "https://test.org/GW000001.h5", h5data)

        stdout = StringIO()
        # Do the thing, Zhu Li
        with patch('sys.stdout', new = stdout):
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_not_called()

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000001")
        # better not have
        self.assertEqual(sqlite_rows[0]["success"], 0)


    @responses.activate
    def test_no_preferred(self, gwc):
        """Assuming there are no is_preferred parameters, does it not save anything"""
        responses.add(responses.GET, "https://gwosc.org/eventapi/json/allevents", json={
            "events": {
                "GW000001": {
                    "jsonurl": "https://test.org/GW000001.json"
                }
            }
        })
        responses.add(responses.GET, "https://test.org/GW000001.json", json={
            "events": {
                "GW000001": {
                    "commonName": "GW000001",
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
                    }
                }
            }
        })

        # make the file available for download
        with open("text_fixtures/no_configs.h5", 'rb') as f:
            h5data = f.read()
        responses.add(responses.GET, "https://test.org/GW000001.h5", h5data)

        stdout = StringIO()
        # Do[n't do] the thing, Zhu Li
        with self.assertRaises(SystemExit):
            with patch('sys.stdout', new = stdout):
                gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_not_called()


        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000001")
        # better not have
        self.assertEqual(sqlite_rows[0]["success"], 0)

        # does it tell us why it failed?
        self.assertIn("Unable to find preferred job", stdout.getvalue())

    @responses.activate
    def test_too_many_preferred(self, gwc):
        """More than 1 preferred h5 file found"""
        responses.add(responses.GET, "https://gwosc.org/eventapi/json/allevents", json={
            "events": {
                "GW000001": {
                    "jsonurl": "https://test.org/GW000001.json"
                }
            }
        })
        responses.add(responses.GET, "https://test.org/GW000001.json", json={
            "events": {
                "GW000001": {
                    "commonName": "GW000001",
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
                    }
                }
            }
        })

        # make the file available for download
        with open("text_fixtures/no_configs.h5", 'rb') as f:
            h5data = f.read()
        responses.add(responses.GET, "https://test.org/GW000001.h5", h5data)

        stdout = StringIO()
        # Do[n't do] the thing, Zhu Li
        with self.assertRaises(SystemExit):
            with patch('sys.stdout', new = stdout):
                gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_not_called()


        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000001")
        # better not have
        self.assertEqual(sqlite_rows[0]["success"], 0)

        # does it tell us why it failed?
        self.assertIn("Unable to find preferred job", stdout.getvalue())

    @responses.activate
    def test_download_allevents_error(self, gwc):
        """What happens if any part of the download process fails due to external problems?
        Specifically,
            - Downloading the allevents json
            - Downloading the specific event json
            - Downloading the h5 file
        """
        responses.add(responses.GET, "https://gwosc.org/eventapi/json/allevents", json={
            "error": True
        }, status=500)
        
        stdout = StringIO()
        # Do[n't do] the thing, Zhu Li
        with self.assertRaises(SystemExit):
            with patch('sys.stdout', new = stdout):
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
        self.assertIn("Unable to fetch allevents json", stdout.getvalue())


    @responses.activate
    def test_download_specific_event_error(self, gwc):
        """What happens if any part of the download process fails due to external problems?
        Specifically,
            - Downloading the specific event json
        """
        responses.add(responses.GET, "https://gwosc.org/eventapi/json/allevents", json={
            "events": {
                "GW000001": {
                    "jsonurl": "https://test.org/GW000001.json"
                }
            }
        })
        responses.add(responses.GET, "https://test.org/GW000001.json", json={
            "error": True
        }, status=500)
        
        stdout = StringIO()
        # Do[n't do] the thing, Zhu Li
        with self.assertRaises(SystemExit):
            with patch('sys.stdout', new = stdout):
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
        self.assertIn("Unable to fetch event json", stdout.getvalue())

    @responses.activate
    def test_download_h5_error(self, gwc):
        """What happens if any part of the download process fails due to external problems?
        Specifically,
            - The h5 file is missing
        """
        responses.add(responses.GET, "https://gwosc.org/eventapi/json/allevents", json={
            "events": {
                "GW000001": {
                    "jsonurl": "https://test.org/GW000001.json"
                }
            }
        })
        responses.add(responses.GET, "https://test.org/GW000001.json", json={
            "events": {
                "GW000001": {
                    "commonName": "GW000001",
                    "GPS": 1729400000,
                    "gracedb_id": "S123456z",
                    "parameters": {
                        "AAAAA": {
                            "is_preferred": True,
                            "data_url": "https://test.org/GW000001.h5",
                        },
                    }
                }
            }
        })

        # make the file _un_available for download
        responses.add(responses.GET, "https://test.org/GW000001.h5", status=404)
        
        stdout = StringIO()
        # Do[n't do] the thing, Zhu Li
        with self.assertRaises(HTTPError):
            with patch('sys.stdout', new = stdout):
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
        self.assertIn("Downloading https://test.org/GW000001.h5 failed", stdout.getvalue())

    @responses.activate
    def test_creates_event_id(self, gwc):
        """If a file has a valid event_id we haven't encountered before, create one"""
        responses.add(responses.GET, "https://gwosc.org/eventapi/json/allevents", json={
            "events": {
                "GW000001_123456": {
                    "jsonurl": "https://test.org/GW000001_123456.json"
                }
            }
        })
        responses.add(responses.GET, "https://test.org/GW000001_123456.json", json={
            "events": {
                "GW000001_123456": {
                    "commonName": "GW000001_123456",
                    "GPS": 1729400000,
                    "gracedb_id": "S123456z",
                    "parameters": {
                        "AAAAA": {
                            "is_preferred": True,
                            "data_url": "https://test.org/GW000001_123456.h5",
                        }
                    }
                }
            }
        })

        # make the file available for download
        with open("text_fixtures/good.h5", 'rb') as f:
            h5data = f.read()
        responses.add(responses.GET, "https://test.org/GW000001_123456.h5", h5data)


        stdout = StringIO()
        # Do the thing, Zhu Li
        with patch('sys.stdout', new = stdout):
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_called_once_with('GW000001_123456--IMRPhenom', 'IMRPhenom', False, 'VALID=good', 'https://test.org/GW000001_123456.h5')

        # Did it create a new event_id
        gwc.return_value.create_event_id.assert_called_once_with("GW000001_123456", 1729400000, "S123456z")

        # Has it set the event id on the job?
        gwc.return_value.upload_external_job.return_value.set_event_id.assert_called_once_with(
            gwc.return_value.create_event_id.return_value
        )

    @responses.activate
    def test_doesnt_create_event_id(self, gwc):
        """If a file has a valid event_id that exists, behave normally"""
        responses.add(responses.GET, "https://gwosc.org/eventapi/json/allevents", json={
            "events": {
                "GW000001_123456": {
                    "jsonurl": "https://test.org/GW000001_123456.json"
                }
            }
        })
        responses.add(responses.GET, "https://test.org/GW000001_123456.json", json={
            "events": {
                "GW000001_123456": {
                    "commonName": "GW000001_123456",
                    "GPS": 1729400000,
                    "gracedb_id": "S123456z",
                    "parameters": {
                        "AAAAA": {
                            "is_preferred": True,
                            "data_url": "https://test.org/GW000001_123456.h5",
                        }
                    }
                }
            }
        })

        # mock that this event_id is already in the DB
        event_id = namedtuple('event_id', ['event_id'])
        specific_event_id = event_id("GW000001_123456")
        gwc.return_value.get_all_event_ids.return_value = [specific_event_id]

        # make the file available for download
        with open("text_fixtures/good.h5", 'rb') as f:
            h5data = f.read()
        responses.add(responses.GET, "https://test.org/GW000001_123456.h5", h5data)


        stdout = StringIO()
        # Do the thing, Zhu Li
        with patch('sys.stdout', new = stdout):
            gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_called_once_with('GW000001_123456--IMRPhenom', 'IMRPhenom', False, 'VALID=good', 'https://test.org/GW000001_123456.h5')

        # Did it _not_ create a new event_id
        gwc.return_value.create_event_id.assert_not_called()

        # Has it set the event id on the job?
        gwc.return_value.upload_external_job.return_value.set_event_id.assert_called_once_with(
            specific_event_id
        )

    def test_dont_duplicate_jobs(self, gwc):
        """If a file already has a matching bilbyJob, deal with it"""
        pass

    def test_multiple_bilbyjobs(self, gwc):
        """If a h5 file contains multiple config_files, create multiple bilbyJobs"""
        pass

    def test_skip_if_present(self, gwc):
        """If a job is already in sqlite, skip it"""
        pass

    def test_no_dataurl(self, gwc):
        """If a preferred job doesn't contain a dataurl, skip it"""
        pass

    # need to test that the bilby server adds the official tag when a job is submitted by the GWOSC_INGEST_USER
        

# What do we need to test
# - Can download a file and store it in the database
# - Can download a file and _not_ store it in the database (but save a failed job in sqlite)
# - What if the downloaded file is unavailable?
# - Creates a event_id if none is found
# - Doesn't create an event_id if one is already present
# - Doesn't create a BilbyJob if one is already present
# - Creates multiple bilbyJobs if the h5 file has multiple potential bilbyJobs
# - Skips a job if one is already present in sqlite

