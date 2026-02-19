import fcntl
import tempfile
import unittest
from unittest.mock import patch

import gwosc_ingest


class TestSingleInstanceLock(unittest.TestCase):
    """Tests for the run() entry point's single-instance file lock."""

    def setUp(self):
        self.lock_dir = tempfile.mkdtemp()
        self.lock_path = f"{self.lock_dir}/gwosc_ingest.lock"
        self.lock_path_patch = patch.object(gwosc_ingest, "LOCK_FILE_PATH", self.lock_path)
        self.lock_path_patch.start()

    def tearDown(self):
        self.lock_path_patch.stop()
        import shutil

        shutil.rmtree(self.lock_dir, ignore_errors=True)

    def test_missing_db_path_exits(self):
        """run() exits with code 1 when DB_PATH is not configured."""
        with patch.object(gwosc_ingest, "DB_PATH", None):
            with self.assertRaises(SystemExit) as cm:
                gwosc_ingest.run()
        self.assertEqual(cm.exception.code, 1)

    @patch("gwosc_ingest.check_and_download")
    def test_lock_acquired_runs_check_and_download(self, mock_check):
        """When no other instance holds the lock, check_and_download is called."""
        gwosc_ingest.run()
        mock_check.assert_called_once()

    @patch("gwosc_ingest.check_and_download")
    def test_lock_already_held_returns_without_running(self, mock_check):
        """When the lock is already held, run() returns without calling check_and_download."""
        # Acquire the lock externally before calling run()
        lock_fd = open(self.lock_path, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            gwosc_ingest.run()
            mock_check.assert_not_called()
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    @patch("gwosc_ingest.check_and_download", side_effect=RuntimeError("boom"))
    def test_lock_released_even_if_check_raises(self, mock_check):
        """The lock is released even when check_and_download raises an exception."""
        with self.assertRaises(RuntimeError):
            gwosc_ingest.run()

        # After run() has exited (via exception), we should be able to reacquire
        # the lock, proving it was released in the finally block.
        lock_fd = open(self.lock_path, "w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fail("Lock was NOT released after check_and_download raised an exception")
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
