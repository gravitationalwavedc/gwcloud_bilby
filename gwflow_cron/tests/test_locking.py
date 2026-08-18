import fcntl
import tempfile
from pathlib import Path
from unittest.mock import patch

import gwflow_ingest
import settings
from tests.base import GWFlowTestBase


class TestLockingAndExecution(GWFlowTestBase):
    def setUp(self):
        super().setUp()
        self.patch_gwc = patch("gwflow_ingest.GWCloud")
        self.patch_jc = patch("gwflow_ingest.JobControllerClient")
        self.patch_meta = patch("gwflow_ingest.phase_metadata")
        self.patch_bilby = patch("gwflow_ingest.phase_bilby_children")
        self.patch_mirror = patch("gwflow_ingest.phase_file_mirror")
        self.mock_gwc_cls = self.patch_gwc.start()
        self.mock_jc_cls = self.patch_jc.start()
        self.mock_meta = self.patch_meta.start()
        self.mock_bilby = self.patch_bilby.start()
        self.mock_mirror = self.patch_mirror.start()

    def tearDown(self):
        self.patch_mirror.stop()
        self.patch_bilby.stop()
        self.patch_meta.stop()
        self.patch_jc.stop()
        self.patch_gwc.stop()
        super().tearDown()

    def test_run_success(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp, patch.object(settings, "DB_PATH", tmp.name):
            res = gwflow_ingest.run([])
            self.assertEqual(res, 0)

    def test_backfill_flag(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp, patch.object(settings, "DB_PATH", tmp.name):
            gwflow_ingest.run(["--backfill"])
            self.assertTrue(settings.BACKFILL)

    def test_concurrent_lock_returns_early(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            lock_path = str(Path(tmp.name).with_suffix(".lock"))
            with open(lock_path, "w") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    with patch.object(settings, "DB_PATH", tmp.name):
                        res = gwflow_ingest.run([])
                        self.assertEqual(res, 0)
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    import unittest

    unittest.main()
