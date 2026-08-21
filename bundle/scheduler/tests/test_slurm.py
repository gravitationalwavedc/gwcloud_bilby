import subprocess
from unittest import TestCase
from unittest.mock import patch

from scheduler.slurm import SlurmScheduler
from scheduler.status import JobStatus


class TestSlurm(TestCase):
    def setUp(self):
        self.maxDiff = None
        self.sched = SlurmScheduler()

    def _mock_status(self, state):
        return patch(
            "scheduler.slurm.subprocess.check_output",
            return_value=f"12345|{state}\n12345.batch|{state}\n".encode(),
        )

    def test_status_completed_with_exit_code(self):
        with self._mock_status("COMPLETED 0:0"):
            self.assertEqual(
                self.sched.status(12345, None),
                (JobStatus.COMPLETED, self.sched.SLURM_STATUS["COMPLETED"]),
            )

    def test_status_failed_with_exit_code(self):
        with self._mock_status("FAILED 1:0"):
            self.assertEqual(
                self.sched.status(12345, None),
                (JobStatus.ERROR, self.sched.SLURM_STATUS["FAILED"]),
            )

    def test_status_timeout_with_exit_code(self):
        with self._mock_status("TIMEOUT 0:0"):
            self.assertEqual(
                self.sched.status(12345, None),
                (JobStatus.WALL_TIME_EXCEEDED, self.sched.SLURM_STATUS["TIMEOUT"]),
            )

    def test_status_out_of_memory_with_exit_code(self):
        with self._mock_status("OUT_OF_MEMORY 0:0"):
            self.assertEqual(
                self.sched.status(12345, None),
                (JobStatus.OUT_OF_MEMORY, self.sched.SLURM_STATUS["OUT_OF_MEMORY"]),
            )

    def test_status_cancelled_with_exit_code(self):
        with self._mock_status("CANCELLED 0:0"):
            self.assertEqual(
                self.sched.status(12345, None),
                (JobStatus.CANCELLED, self.sched.SLURM_STATUS["CANCELLED"]),
            )

    def test_status_running(self):
        with self._mock_status("RUNNING"):
            self.assertEqual(
                self.sched.status(12345, None),
                (JobStatus.RUNNING, self.sched.SLURM_STATUS["RUNNING"]),
            )

    def test_status_pending(self):
        with self._mock_status("PENDING"):
            self.assertEqual(
                self.sched.status(12345, None),
                (JobStatus.QUEUED, self.sched.SLURM_STATUS["PENDING"]),
            )

    def test_status_no_matching_job(self):
        with patch(
            "scheduler.slurm.subprocess.check_output",
            return_value=b"99999|COMPLETED 0:0\n",
        ):
            self.assertEqual(self.sched.status(12345, None), (None, None))

    def test_status_unknown_state(self):
        with self._mock_status("UNKNOWN_STATE"):
            self.assertEqual(self.sched.status(12345, None), (None, None))

    def test_status_returns_none_when_sacct_fails(self):
        sched = SlurmScheduler()

        with patch(
            "scheduler.slurm.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "sacct"),
        ):
            self.assertEqual(sched.status(1234, None), (None, None))

    @patch("scheduler.slurm.subprocess.check_output")
    def test_status_skips_malformed_line(self, check_output_mock):
        # A malformed sacct line (no `|` separator) whose first field matches the job id
        # must be skipped instead of crashing the poll with an IndexError.
        check_output_mock.return_value = b"1234\n1234|COMPLETED\n"

        sched = SlurmScheduler()
        status, info = sched.status(1234, None)

        self.assertEqual(status, JobStatus.COMPLETED)
        self.assertEqual(info, sched.SLURM_STATUS["COMPLETED"])

    @patch("scheduler.slurm.subprocess.check_output")
    def test_status_skips_non_utf8_line(self, check_output_mock):
        # A sacct line whose state field is not valid UTF-8 must be skipped instead
        # of crashing the poll with a UnicodeDecodeError.
        check_output_mock.return_value = b"1234|\xff\xfe\n1234|COMPLETED\n"

        sched = SlurmScheduler()
        status, info = sched.status(1234, None)

        self.assertEqual(status, JobStatus.COMPLETED)
        self.assertEqual(info, sched.SLURM_STATUS["COMPLETED"])

    @patch("scheduler.slurm.subprocess.check_output")
    def test_status_valid_line(self, check_output_mock):
        check_output_mock.return_value = b"1234|RUNNING\n"

        sched = SlurmScheduler()
        status, info = sched.status(1234, None)

        self.assertEqual(status, JobStatus.RUNNING)
        self.assertEqual(info, sched.SLURM_STATUS["RUNNING"])

    @patch("scheduler.slurm.subprocess.check_output")
    def test_cancel_success(self, check_output_mock):
        check_output_mock.return_value = b""

        sched = SlurmScheduler()
        result = sched.cancel(1234, None)

        self.assertTrue(result)
        check_output_mock.assert_called_once_with("scancel 1234", shell=True)

    @patch(
        "scheduler.slurm.subprocess.check_output",
        side_effect=subprocess.CalledProcessError(1, "scancel 1234"),
    )
    def test_cancel_failure(self, check_output_mock):
        sched = SlurmScheduler()
        result = sched.cancel(1234, None)

        self.assertFalse(result)
        check_output_mock.assert_called_once_with("scancel 1234", shell=True)

    @patch("scheduler.slurm.subprocess.check_output", return_value=b"")
    def test_submit_empty_output_returns_none(self, _check_output):
        sched = SlurmScheduler()
        result = sched.submit("test_script_path", "a/working/directory")

        self.assertIsNone(result)

    @patch("scheduler.slurm.subprocess.check_output", return_value=b"   \n\t")
    def test_submit_whitespace_output_returns_none(self, _check_output):
        sched = SlurmScheduler()
        result = sched.submit("test_script_path", "a/working/directory")

        self.assertIsNone(result)


class TestSlurmScheduler(TestCase):
    def test_status_cancelled_plus_transitional_state(self):
        sched = SlurmScheduler()
        with patch(
            "scheduler.slurm.subprocess.check_output",
            return_value=b"12345|CANCELLED+  \n",
        ):
            status, info = sched.status(12345, {})
        self.assertEqual(status, JobStatus.CANCELLED)
        self.assertEqual(info, "CANCELLED+")
