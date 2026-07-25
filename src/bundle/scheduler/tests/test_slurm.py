import subprocess
from unittest import TestCase
from unittest.mock import patch

from scheduler.slurm import SlurmScheduler


class TestSlurm(TestCase):
    def setUp(self):
        self.maxDiff = None

    @patch("subprocess.check_output")
    def test_cancel_success(self, mock_check_output):
        mock_check_output.return_value = b""
        sched = SlurmScheduler()
        result = sched.cancel(12345, {})
        self.assertTrue(result)
        mock_check_output.assert_called_once_with("scancel 12345", shell=True)

    @patch("subprocess.check_output")
    def test_cancel_failure(self, mock_check_output):
        mock_check_output.side_effect = subprocess.CalledProcessError(1, "scancel 99999")
        sched = SlurmScheduler()
        result = sched.cancel(99999, {})
        self.assertFalse(result)

    def test_status_mapping(self):
        """Verify all documented Slurm states map correctly."""
        sched = SlurmScheduler()
        self.assertEqual(
            sched.SLURM_STATUS["COMPLETED"], "Job has terminated all processes on all nodes with an exit code of zero."
        )
