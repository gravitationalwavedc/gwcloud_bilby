import fcntl
import tempfile
from pathlib import Path
from unittest.mock import patch

import gwflow_ingest
import settings
from tests.base import GWFlowTestBase


class TestLockingAndExecution(GWFlowTestBase):
    def test_run_success(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with patch.object(settings, "DB_PATH", tmp.name):
                res = gwflow_ingest.run([])
                self.assertEqual(res, 0)

    def test_backfill_flag(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with patch.object(settings, "DB_PATH", tmp.name):
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
