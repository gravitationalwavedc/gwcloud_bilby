import unittest
import responses
import sqlite3

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


        # Do the thing, Zhu Li
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

        # Do the thing, Zhu Li
        gwosc_ingest.check_and_download()

        # has the job completed?
        gwc.return_value.upload_external_job.assert_not_called()

        # Has it made a record of this job in sqlite?
        cur = self.con.cursor()
        sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
        sqlite_rows = sqlite_rows.fetchall()

        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0]["job_id"], "GW000001")
        self.assertEqual(sqlite_rows[0]["success"], 0)

    def test_no_preferred(self, gwc):
        """Assuming there are no is_preferred parameters, does it not save anything"""
        pass

    def test_too_many_preferred(self, gwc):
        """More than 1 preferred h5 file found"""
        pass

    def test_download_unavailable(self, gwc):
        """What happens if any part of the download process fails?
        Specifically,
            - Downloading the allevents json
            - Downloading the specific event json
            - Downloading the h5 file
        """
        pass

    def test_creates_event_id(self, gwc):
        """If a file has a valid event_id we haven't encountered before, create one"""
        pass

    def test_doesnt_create_event_id(self, gwc):
        """If a file has a valid event_id that exists, behave normally"""
        pass

    def test_dont_duplicate_jobs(self, gwc):
        """If a file already has a matching bilbyJob, deal with it"""
        pass

    def test_multiple_bilbyjobs(self, gwc):
        """If a h5 file contains multiple config_files, create multiple bilbyJobs"""
        pass

    def test_skip_if_present(self, gwc):
        """If a job is already in sqlite, skip it"""
        pass
        

# What do we need to test
# - Can download a file and store it in the database
# - Can download a file and _not_ store it in the database (but save a failed job in sqlite)
# - What if the downloaded file is unavailable?
# - Creates a event_id if none is found
# - Doesn't create an event_id if one is already present
# - Doesn't create a BilbyJob if one is already present
# - Creates multiple bilbyJobs if the h5 file has multiple potential bilbyJobs
# - Skips a job if one is already present in sqlite

