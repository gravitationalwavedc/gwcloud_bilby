"""
Comprehensive tests for cbcflow_ingest script.

Tests cover:
- Git operations with SSH keys
- SQLite export and querying
- File downloads from job controller
- GWCloud job uploads
- Error handling and edge cases
"""

import json
import logging
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import responses
from parameterized import parameterized

import cbcflow_ingest

# Disable logging during tests
logger = logging.getLogger("cbcflow_ingest")
while logger.hasHandlers():
    logger.removeHandler(logger.handlers[0])

# Use test configuration
cbcflow_ingest.DB_PATH = ":memory:"
cbcflow_ingest.GWCLOUD_TOKEN = "TEST_TOKEN"
cbcflow_ingest.ENDPOINT = "https://test-gwcloud/graphql"
cbcflow_ingest.JOB_CONTROLLER_JWT_SECRET = "TEST_SECRET"
cbcflow_ingest.JOB_CONTROLLER_API_URL = "https://test-jobcontroller/api"
cbcflow_ingest.SSH_KEY_PATH = "/tmp/test_key"
cbcflow_ingest.LIBRARIES_DIR = "/tmp/libraries"
cbcflow_ingest.SQLITE_DIR = "/tmp/sqlite_exports"


class TestGitOperations(unittest.TestCase):
    """Test git clone and update operations."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.repo_path = Path(self.temp_dir) / "test_repo"
        self.ssh_key = "/tmp/test_ssh_key"

    @patch("subprocess.run")
    def test_clone_repo_success(self, mock_run):
        """Test successful git clone."""
        mock_run.return_value = Mock(returncode=0)

        result = cbcflow_ingest.clone_or_update_repo(
            "git@test.org:repo.git", self.repo_path, self.ssh_key
        )

        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 1)
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "git")
        self.assertEqual(args[1], "clone")

    @patch("subprocess.run")
    def test_update_existing_repo(self, mock_run):
        """Test updating existing repository."""
        # Create the repo directory
        self.repo_path.mkdir(parents=True)

        mock_run.return_value = Mock(returncode=0)

        result = cbcflow_ingest.clone_or_update_repo(
            "git@test.org:repo.git", self.repo_path, self.ssh_key
        )

        self.assertTrue(result)
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "git")
        self.assertEqual(args[1], "pull")

    @patch("subprocess.run")
    def test_clone_repo_failure(self, mock_run):
        """Test git clone failure."""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(
            1, "git", stderr="Authentication failed"
        )

        result = cbcflow_ingest.clone_or_update_repo(
            "git@test.org:repo.git", self.repo_path, self.ssh_key
        )

        self.assertFalse(result)

    @patch("subprocess.run")
    def test_ssh_key_in_git_command(self, mock_run):
        """Test that SSH key is passed to git command."""
        mock_run.return_value = Mock(returncode=0)

        cbcflow_ingest.clone_or_update_repo(
            "git@test.org:repo.git", self.repo_path, self.ssh_key
        )

        # Check environment variable was set
        env = mock_run.call_args[1]["env"]
        self.assertIn("GIT_SSH_COMMAND", env)
        self.assertIn(self.ssh_key, env["GIT_SSH_COMMAND"])


class TestSQLiteExport(unittest.TestCase):
    """Test SQLite export functionality."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.library_path = Path(self.temp_dir) / "test_library"
        self.output_db = Path(self.temp_dir) / "test.db"
        self.library_path.mkdir(parents=True)

    @patch("subprocess.run")
    def test_export_success(self, mock_run):
        """Test successful SQLite export."""
        mock_run.return_value = Mock(returncode=0, stdout="Export complete")

        result = cbcflow_ingest.export_library_to_sqlite(
            self.library_path, self.output_db
        )

        self.assertTrue(result)
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "cbcflow_export_sqlite")
        self.assertIn(str(self.output_db), args)
        self.assertIn(str(self.library_path), args)

    @patch("subprocess.run")
    def test_export_failure(self, mock_run):
        """Test SQLite export failure."""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(
            1, "cbcflow_export_sqlite", stderr="Export failed"
        )

        result = cbcflow_ingest.export_library_to_sqlite(
            self.library_path, self.output_db
        )

        self.assertFalse(result)


class TestSQLiteQuerying(unittest.TestCase):
    """Test querying SQLite database for completed PE jobs."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        self._create_test_database()

    def _create_test_database(self):
        """Create a test database with sample data."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Create tables
        cursor.execute(
            """
            CREATE TABLE superevents (
                id INTEGER PRIMARY KEY,
                sname TEXT
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE superevents_parameterestimation (
                id INTEGER PRIMARY KEY,
                superevents_id INTEGER,
                status TEXT
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE superevents_parameterestimation_results (
                id INTEGER PRIMARY KEY,
                superevents_parameterestimation_id INTEGER,
                uid TEXT,
                inferencesoftware TEXT,
                waveformapproximant TEXT,
                reviewstatus TEXT,
                runstatus TEXT,
                resultfile_id INTEGER,
                configfile_id INTEGER,
                deprecated INTEGER
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE linkedfiles (
                id INTEGER PRIMARY KEY,
                path TEXT,
                md5sum TEXT
            )
        """
        )

        # Insert test data
        cursor.execute("INSERT INTO superevents VALUES (1, 'S240525p')")
        cursor.execute("INSERT INTO superevents VALUES (2, 'S231113bw')")

        cursor.execute(
            "INSERT INTO superevents_parameterestimation VALUES (1, 1, 'complete')"
        )
        cursor.execute(
            "INSERT INTO superevents_parameterestimation VALUES (2, 2, 'complete')"
        )

        cursor.execute(
            """
            INSERT INTO superevents_parameterestimation_results 
            VALUES (1, 1, 'online', 'bilby', 'IMRPhenomXPHM', 'pass', 'complete', 1, 2, 0)
        """
        )

        cursor.execute(
            """
            INSERT INTO superevents_parameterestimation_results 
            VALUES (2, 2, 'offline', 'bilby', 'IMRPhenomPv2', 'ongoing', 'complete', 3, 4, 0)
        """
        )

        cursor.execute(
            """
            INSERT INTO superevents_parameterestimation_results 
            VALUES (3, 2, 'deprecated-run', 'bilby', 'IMRPhenomD', 'pass', 'complete', 5, 6, 1)
        """
        )

        cursor.execute(
            "INSERT INTO linkedfiles VALUES (1, 'CIT:/home/pe/result1.hdf5', 'abc123')"
        )
        cursor.execute(
            "INSERT INTO linkedfiles VALUES (2, 'CIT:/home/pe/config1.ini', 'def456')"
        )
        cursor.execute(
            "INSERT INTO linkedfiles VALUES (3, 'CIT:/home/pe/result2.hdf5', 'ghi789')"
        )
        cursor.execute(
            "INSERT INTO linkedfiles VALUES (4, 'CIT:/home/pe/config2.ini', 'jkl012')"
        )
        cursor.execute(
            "INSERT INTO linkedfiles VALUES (5, 'CIT:/home/pe/result3.hdf5', 'mno345')"
        )
        cursor.execute(
            "INSERT INTO linkedfiles VALUES (6, 'CIT:/home/pe/config3.ini', 'pqr678')"
        )

        conn.commit()
        conn.close()

    def test_query_completed_jobs(self):
        """Test querying for completed PE jobs."""
        jobs = cbcflow_ingest.query_completed_pe_jobs(self.db_path)

        # Should return 2 jobs (deprecated job excluded)
        self.assertEqual(len(jobs), 2)

        # Check first job
        self.assertEqual(jobs[0]["sname"], "S240525p")
        self.assertEqual(jobs[0]["uid"], "online")
        self.assertEqual(jobs[0]["result_file_path"], "CIT:/home/pe/result1.hdf5")

        # Check second job
        self.assertEqual(jobs[1]["sname"], "S231113bw")
        self.assertEqual(jobs[1]["uid"], "offline")

    def test_query_filters_deprecated(self):
        """Test that deprecated jobs are filtered out."""
        jobs = cbcflow_ingest.query_completed_pe_jobs(self.db_path)

        # Should not include deprecated job
        uids = [job["uid"] for job in jobs]
        self.assertNotIn("deprecated-run", uids)

    def test_query_empty_database(self):
        """Test querying empty database."""
        empty_db = Path(self.temp_dir) / "empty.db"
        conn = sqlite3.connect(str(empty_db))
        cursor = conn.cursor()

        # Create tables but no data
        cursor.execute("CREATE TABLE superevents (id INTEGER PRIMARY KEY, sname TEXT)")
        cursor.execute(
            """
            CREATE TABLE superevents_parameterestimation (
                id INTEGER, superevents_id INTEGER, status TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE superevents_parameterestimation_results (
                id INTEGER, superevents_parameterestimation_id INTEGER,
                uid TEXT, runstatus TEXT, deprecated INTEGER, resultfile_id INTEGER
            )
        """
        )
        cursor.execute("CREATE TABLE linkedfiles (id INTEGER, path TEXT)")
        conn.commit()
        conn.close()

        jobs = cbcflow_ingest.query_completed_pe_jobs(empty_db)
        self.assertEqual(len(jobs), 0)


class TestFileDownload(unittest.TestCase):
    """Test file download from CIT cluster."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_path = Path(self.temp_dir) / "downloaded_file.hdf5"

    @responses.activate
    def test_download_success(self):
        """Test successful file download via HTTPS."""
        test_content = b"test file content"
        
        # Mock HTTPS download from ldas-jobs.ligo.caltech.edu
        responses.add(
            responses.GET,
            "https://ldas-jobs.ligo.caltech.edu/~pe.o4/O4b/S240525p/online/bilby/final_result/result.hdf5",
            body=test_content,
            status=200,
        )

        result = cbcflow_ingest.download_file_from_cit(
            "CIT:/home/pe.o4/public_html/O4b/S240525p/online/bilby/final_result/result.hdf5",
            output_path=self.output_path
        )

        self.assertTrue(result)
        self.assertTrue(self.output_path.exists())
        with open(self.output_path, "rb") as f:
            self.assertEqual(f.read(), test_content)

    def test_download_non_public_file_failure(self):
        """Test that non-public files return error."""
        result = cbcflow_ingest.download_file_from_cit(
            "CIT:/home/private/file.hdf5",
            output_path=self.output_path
        )

        self.assertFalse(result)
        self.assertFalse(self.output_path.exists())

    @responses.activate
    def test_download_file_failure(self):
        """Test file download failure."""
        responses.add(
            responses.GET,
            "https://ldas-jobs.ligo.caltech.edu/~pe.o4/test.hdf5",
            body="Not Found",
            status=404,
        )

        result = cbcflow_ingest.download_file_from_cit(
            "CIT:/home/pe.o4/public_html/test.hdf5",
            output_path=self.output_path
        )

        self.assertFalse(result)

    def test_download_parse_cit_path(self):
        """Test parsing CIT: prefix from file path."""
        with patch("requests.get") as mock_get:
            mock_get.return_value.__enter__.return_value.status_code = 200
            mock_get.return_value.__enter__.return_value.iter_content.return_value = [
                b"test"
            ]
            mock_get.return_value.__enter__.return_value.raise_for_status = lambda: None

            cbcflow_ingest.download_file_from_cit(
                "CIT:/home/pe.o4/public_html/test.hdf5",
                output_path=self.output_path,
            )

            # Check that the URL was correctly constructed
            call_url = mock_get.call_args[0][0]
            self.assertEqual(call_url, "https://ldas-jobs.ligo.caltech.edu/~pe.o4/test.hdf5")


class TestGWCloudUpload(unittest.TestCase):
    """Test uploading jobs to GWCloud."""

    def setUp(self):
        self.mock_gwc = MagicMock()
        self.temp_dir = tempfile.mkdtemp()
        self.files_dir = Path(self.temp_dir) / "files"
        self.files_dir.mkdir(parents=True)

    def test_upload_job_success(self):
        """Test successful job upload."""
        mock_job = MagicMock()
        mock_job.id = 12345
        self.mock_gwc.upload_external_job.return_value = mock_job

        job_info = {
            "sname": "S240525p",
            "uid": "online",
            "waveformapproximant": "IMRPhenomXPHM",
            "inferencesoftware": "bilby",
            "result_file_path": "CIT:/home/pe.o4/result.hdf5",
            "reviewstatus": "pass",
        }

        job_id = cbcflow_ingest.upload_job_to_gwcloud(
            self.mock_gwc, job_info, "test-library", self.files_dir
        )

        self.assertEqual(job_id, 12345)
        self.mock_gwc.upload_external_job.assert_called_once()

        # Check the arguments
        call_kwargs = self.mock_gwc.upload_external_job.call_args[1]
        self.assertEqual(call_kwargs["name"], "S240525p--online--test-library")
        self.assertTrue(call_kwargs["is_ligo_job"])
        self.assertIn("IMRPhenomXPHM", call_kwargs["ini_string"])
        self.assertIn("bilby", call_kwargs["ini_string"])

    def test_upload_job_failure(self):
        """Test job upload failure."""
        self.mock_gwc.upload_external_job.side_effect = Exception("API Error")

        job_info = {
            "sname": "S240525p",
            "uid": "online",
            "result_file_path": "CIT:/home/pe.o4/result.hdf5",
        }

        job_id = cbcflow_ingest.upload_job_to_gwcloud(
            self.mock_gwc, job_info, "test-library", self.files_dir
        )

        self.assertIsNone(job_id)

    def test_job_name_sanitization(self):
        """Test that job names are properly sanitized."""
        mock_job = MagicMock()
        mock_job.id = 12345
        self.mock_gwc.upload_external_job.return_value = mock_job

        job_info = {
            "sname": "S240525p",
            "uid": "bilby/IMRPhenomXPHM/online",
            "result_file_path": "CIT:/home/pe.o4/result.hdf5",
        }

        cbcflow_ingest.upload_job_to_gwcloud(
            self.mock_gwc, job_info, "test-library", self.files_dir
        )

        call_kwargs = self.mock_gwc.upload_external_job.call_args[1]
        # Slashes should be replaced with dashes
        self.assertEqual(call_kwargs["name"], "S240525p--bilby-IMRPhenomXPHM-online--test-library")


class TestTrackingDatabase(unittest.TestCase):
    """Test tracking database functionality."""

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.cur = self.con.cursor()

    def test_create_tracking_table(self):
        """Test creating tracking table."""
        cbcflow_ingest.create_tracking_table(self.cur)

        # Check that table was created
        self.cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='processed_jobs'"
        )
        result = self.cur.fetchone()
        self.assertIsNotNone(result)

    def test_insert_processed_job(self):
        """Test inserting a processed job record."""
        cbcflow_ingest.create_tracking_table(self.cur)

        self.cur.execute(
            """
            INSERT INTO processed_jobs 
            (job_uid, sname, library_name, success, reason, gwcloud_job_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            ("test-uid", "S240525p", "o4a", True, "completed", 12345),
        )
        self.con.commit()

        # Query the record
        self.cur.execute("SELECT * FROM processed_jobs WHERE job_uid = 'test-uid'")
        result = self.cur.fetchone()

        self.assertIsNotNone(result)
        self.assertEqual(result[1], "S240525p")
        self.assertEqual(result[2], "o4a")
        self.assertEqual(result[3], 1)  # Boolean True as INTEGER


class TestProcessLibrary(unittest.TestCase):
    """Test processing a complete library."""

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.cur = self.con.cursor()
        cbcflow_ingest.create_tracking_table(self.cur)
        self.mock_gwc = MagicMock()

    @patch("cbcflow_ingest.clone_or_update_repo")
    @patch("cbcflow_ingest.export_library_to_sqlite")
    @patch("cbcflow_ingest.query_completed_pe_jobs")
    @patch("cbcflow_ingest.upload_job_to_gwcloud")
    def test_process_library_success(
        self, mock_upload, mock_query, mock_export, mock_clone
    ):
        """Test successful library processing."""
        mock_clone.return_value = True
        mock_export.return_value = True
        mock_query.return_value = [
            {
                "uid": "test-job-1",
                "sname": "S240525p",
                "result_file_path": "CIT:/home/pe/test.hdf5",
            }
        ]
        mock_upload.return_value = 12345

        library_config = {
            "name": "test-library",
            "url": "git@test.org:test.git",
        }

        successful, failed = cbcflow_ingest.process_library(
            library_config, self.mock_gwc, self.cur, self.con
        )

        self.assertEqual(successful, 1)
        self.assertEqual(failed, 0)

        # Check that job was recorded in tracking database
        self.cur.execute("SELECT * FROM processed_jobs WHERE job_uid = 'test-job-1'")
        result = self.cur.fetchone()
        self.assertIsNotNone(result)

    @patch("cbcflow_ingest.clone_or_update_repo")
    def test_process_library_git_failure(self, mock_clone):
        """Test library processing with git failure."""
        mock_clone.return_value = False

        library_config = {
            "name": "test-library",
            "url": "git@test.org:test.git",
        }

        successful, failed = cbcflow_ingest.process_library(
            library_config, self.mock_gwc, self.cur, self.con
        )

        self.assertEqual(successful, 0)
        self.assertEqual(failed, 0)

    @patch("cbcflow_ingest.clone_or_update_repo")
    @patch("cbcflow_ingest.export_library_to_sqlite")
    @patch("cbcflow_ingest.query_completed_pe_jobs")
    def test_process_library_filters_processed_jobs(
        self, mock_query, mock_export, mock_clone
    ):
        """Test that already processed jobs are filtered out."""
        mock_clone.return_value = True
        mock_export.return_value = True
        mock_query.return_value = [
            {
                "uid": "already-processed",
                "sname": "S240525p",
                "result_file_path": "CIT:/home/pe/test.hdf5",
            },
            {
                "uid": "new-job",
                "sname": "S231113bw",
                "result_file_path": "CIT:/home/pe/test2.hdf5",
            },
        ]

        # Mark first job as already processed
        self.cur.execute(
            """
            INSERT INTO processed_jobs (job_uid, sname, library_name, success, reason)
            VALUES (?, ?, ?, ?, ?)
        """,
            ("already-processed", "S240525p", "test-library", True, "completed"),
        )
        self.con.commit()

        library_config = {
            "name": "test-library",
            "url": "git@test.org:test.git",
        }

        with patch("cbcflow_ingest.upload_job_to_gwcloud") as mock_upload:
            mock_upload.return_value = 12345

            successful, failed = cbcflow_ingest.process_library(
                library_config, self.mock_gwc, self.cur, self.con
            )

            # Should only process 1 job (the new one)
            self.assertEqual(successful, 1)
            # Only one job should be uploaded
            self.assertEqual(mock_upload.call_count, 1)


class TestJobNameFixing(unittest.TestCase):
    """Test job name sanitization."""

    def test_fix_job_name_basic(self):
        """Test basic job name fixing."""
        result = cbcflow_ingest.fix_job_name("S240525p--online")
        self.assertEqual(result, "S240525p--online")

    def test_fix_job_name_with_slashes(self):
        """Test fixing job names with slashes."""
        result = cbcflow_ingest.fix_job_name("S240525p/bilby/online")
        self.assertEqual(result, "S240525p-bilby-online")

    def test_fix_job_name_with_special_chars(self):
        """Test fixing job names with special characters."""
        result = cbcflow_ingest.fix_job_name("S240525p@test#123")
        self.assertEqual(result, "S240525p-test-123")

    def test_fix_job_name_preserves_case(self):
        """Test that case is preserved."""
        result = cbcflow_ingest.fix_job_name("S240525p--IMRPhenomXPHM")
        self.assertEqual(result, "S240525p--IMRPhenomXPHM")


if __name__ == "__main__":
    unittest.main()
