import subprocess
from unittest import TestCase
from unittest.mock import patch

from scheduler.slurm import SlurmScheduler


class TestSlurmSubmit(TestCase):
    def setUp(self):
        self.scheduler = SlurmScheduler()

    @patch(
        "scheduler.slurm.subprocess.check_output",
        return_value=b"Submitted batch job 12345\n",
    )
    def test_submit_success(self, check_output_mock):
        result = self.scheduler.submit("script.sh", "/a/working/directory")

        self.assertEqual(result, 12345)
        check_output_mock.assert_called_once_with(
            "cd /a/working/directory && sbatch script.sh", shell=True, timeout=30
        )

    @patch(
        "scheduler.slurm.subprocess.check_output",
        side_effect=subprocess.CalledProcessError(1, "sbatch"),
    )
    def test_submit_called_process_error(self, check_output_mock):
        result = self.scheduler.submit("script.sh", "/a/working/directory")

        self.assertIsNone(result)

    @patch(
        "scheduler.slurm.subprocess.check_output",
        side_effect=subprocess.TimeoutExpired("sbatch", 30),
    )
    def test_submit_timeout(self, check_output_mock):
        result = self.scheduler.submit("script.sh", "/a/working/directory")

        self.assertIsNone(result)

    @patch("scheduler.slurm.subprocess.check_output", return_value=b"not a number\n")
    def test_submit_malformed_output_value_error(self, check_output_mock):
        result = self.scheduler.submit("script.sh", "/a/working/directory")

        self.assertIsNone(result)

    @patch("scheduler.slurm.subprocess.check_output", return_value=b"\n")
    def test_submit_malformed_output_index_error(self, check_output_mock):
        result = self.scheduler.submit("script.sh", "/a/working/directory")

        self.assertIsNone(result)
