import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

import settings
from scheduler.scheduler import EScheduler
from scheduler.status import JobStatus


class TestStatus(TestCase):
    def setUp(self):
        sys.path.append(str(Path(__file__).parent / "misc"))

    def tearDown(self):
        sys.path = sys.path[:-1]

    @patch("_bundledb.get_job_by_id")
    def test_status_job_doesnt_exist(self, get_job_by_id_mock):
        get_job_by_id_mock.side_effect = Mock(return_value=None)

        from core.status import status

        result = status({"scheduler_id": 1234})

        self.assertEqual(
            result["status"],
            [{"what": "system", "status": 400, "info": "Job does not exist. Perhaps it failed to start?"}],
        )
        self.assertEqual(result["complete"], True)

    @patch("_bundledb.get_job_by_id")
    def test_status_missing_scheduler_id(self, get_job_by_id_mock):
        get_job_by_id_mock.side_effect = Mock(return_value=None)

        from core.status import status

        result = status({})

        self.assertEqual(
            result["status"],
            [{"what": "system", "status": 400, "info": "Job does not exist. Perhaps it failed to start?"}],
        )
        self.assertEqual(result["complete"], True)
        get_job_by_id_mock.assert_called_once_with(None)

    @patch("_bundledb.get_job_by_id")
    def test_status_non_dict_details(self, get_job_by_id_mock):
        from core.status import status

        result = status("not-a-dict")

        self.assertEqual(
            result["status"],
            [{"what": "system", "status": 400, "info": "Invalid job details payload"}],
        )
        self.assertEqual(result["complete"], True)
        get_job_by_id_mock.assert_not_called()

    @patch("_bundledb.get_job_by_id")
    @patch.object(settings, "scheduler", "unknown")
    def test_status_unknown_scheduler(self, get_job_by_id_mock):
        db_job = {"submit_id": 1234, "working_directory": "a/working/directory", "submit_directory": "submit"}

        get_job_by_id_mock.side_effect = Mock(return_value=db_job)

        details = {"scheduler_id": 1234}

        from core.status import status

        result = status(details)

        self.assertIsNone(result)

    @patch("_bundledb.create_or_update_job")
    @patch("_bundledb.get_job_by_id")
    @patch("os.path.exists")
    @patch("scheduler.slurm.SlurmScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_status_slurm_submit_running(self, status_mock, path_exists_mock, get_job_by_id_mock, update_job_mock):
        path_exists_mock.side_effect = Mock(return_value=False)

        db_job = {
            "submit_id": 4321,
            "working_directory": "a/test/working/directory",
            "submit_directory": "a/submit/directory/",
        }

        get_job_by_id_mock.side_effect = Mock(return_value=db_job)

        details = {"scheduler_id": 1234}

        from core.status import status

        status_mock.side_effect = Mock(return_value=(JobStatus.SUBMITTED, JobStatus.display_name(JobStatus.SUBMITTED)))

        result = status(details)

        # Job has only one step that is submitted, and job is not completed
        self.assertEqual(result["status"], [{"what": "submit", "status": 30, "info": "Submitted"}])
        self.assertEqual(result["complete"], False)

        status_mock.side_effect = Mock(return_value=(JobStatus.RUNNING, JobStatus.display_name(JobStatus.RUNNING)))

        result = status(details)

        # Job has only one step that is running, and job is not completed
        self.assertEqual(result["status"], [{"what": "submit", "status": 50, "info": "Running"}])
        self.assertEqual(result["complete"], False)

        # Update job (To remove the submit_id) should never have been called
        self.assertEqual(update_job_mock.call_count, 0)

        status_mock.side_effect = Mock(return_value=(None, None))

        result = status(details)

        # An undeterminable status should not crash and should keep polling
        self.assertEqual(result["status"], [{"what": "submit", "status": None, "info": None}])
        self.assertEqual(result["complete"], False)

        # Update job (To remove the submit_id) should never have been called
        self.assertEqual(update_job_mock.call_count, 0)

    @patch("_bundledb.delete_job")
    @patch("_bundledb.create_or_update_job")
    @patch("_bundledb.get_job_by_id")
    @patch("os.path.exists")
    @patch("scheduler.slurm.SlurmScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_status_slurm_submit_error(
        self, status_mock, path_exists_mock, get_job_by_id_mock, update_job_mock, delete_job_mock
    ):
        path_exists_mock.side_effect = Mock(return_value=False)

        db_job = {
            "submit_id": 4321,
            "working_directory": "a/test/working/directory",
            "submit_directory": "a/submit/directory/",
        }

        get_job_by_id_mock.side_effect = Mock(return_value=db_job)

        details = {"scheduler_id": 1234}

        from core.status import status

        status_mock.side_effect = Mock(return_value=(JobStatus.ERROR, JobStatus.display_name(JobStatus.ERROR)))

        result = status(details)

        # Job has only one step that is error, and job is completed
        self.assertEqual(result["status"], [{"what": "submit", "status": 400, "info": "Error"}])
        self.assertEqual(result["complete"], True)

        # Delete should have been called
        self.assertEqual(delete_job_mock.call_count, 1)
        self.assertEqual(update_job_mock.call_count, 0)

    @patch("_bundledb.create_or_update_job")
    @patch("_bundledb.get_job_by_id")
    @patch("os.path.exists")
    @patch("scheduler.slurm.SlurmScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_status_slurm_submit_success(self, status_mock, path_exists_mock, get_job_by_id_mock, update_job_mock):
        path_exists_mock.side_effect = Mock(return_value=False)

        db_job = {
            "submit_id": 4321,
            "working_directory": "a/test/working/directory",
            "submit_directory": "a/submit/directory/",
        }

        get_job_by_id_mock.side_effect = Mock(return_value=db_job)

        details = {"scheduler_id": 1234}

        from core.status import status

        status_mock.side_effect = Mock(return_value=(JobStatus.COMPLETED, JobStatus.display_name(JobStatus.COMPLETED)))

        result = status(details)

        # Job has only one step that is error, and job is completed
        self.assertEqual(result["status"], [{"what": "submit", "status": 500, "info": "Completed"}])
        self.assertEqual(result["complete"], False)

        # Delete should have been called and the submit_id key should no longer exist in the job record
        self.assertEqual(update_job_mock.call_count, 1)
        self.assertDictEqual(
            update_job_mock.call_args[0][0],
            {"working_directory": "a/test/working/directory", "submit_directory": "a/submit/directory/"},
        )

    @patch("_bundledb.delete_job")
    @patch("_bundledb.get_job_by_id")
    @patch("os.path.exists")
    @patch("scheduler.slurm.SlurmScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_status_slurm(self, status_mock, path_exists_mock, get_job_by_id_mock, delete_job_mock):
        path_exists_mock.side_effect = Mock(return_value=True)

        with TemporaryDirectory() as tmpdir:
            db_job = {"working_directory": str(tmpdir), "submit_directory": ""}

            get_job_by_id_mock.side_effect = Mock(return_value=db_job)

            details = {"scheduler_id": 1234}

            with open(os.path.join(tmpdir, "slurm_ids"), "w") as f:
                f.writelines(["jid0 12345\n", "jid1 54321\n"])
                f.flush()

            from core.status import status

            job_status_values = []
            job_status_count = 0

            def job_status_mock(*args, **kwargs):
                nonlocal job_status_count
                job_status_count += 1

                return job_status_values[job_status_count - 1], JobStatus.display_name(
                    job_status_values[job_status_count - 1]
                )

            status_mock.side_effect = job_status_mock

            job_status_values = [JobStatus.QUEUED, JobStatus.QUEUED]

            result = status(details)

            self.assertEqual(
                result["status"],
                [
                    {"status": 500, "what": "submit", "info": "Completed"},
                    {"status": 40, "what": "jid0", "info": "Queued"},
                    {"status": 40, "what": "jid1", "info": "Queued"},
                ],
            )
            self.assertEqual(result["complete"], False)
            self.assertEqual(delete_job_mock.call_count, 0)

            job_status_count = 0
            job_status_values = [JobStatus.RUNNING, JobStatus.QUEUED]

            result = status(details)

            self.assertEqual(
                result["status"],
                [
                    {"status": 500, "what": "submit", "info": "Completed"},
                    {"status": 50, "what": "jid0", "info": "Running"},
                    {"status": 40, "what": "jid1", "info": "Queued"},
                ],
            )
            self.assertEqual(result["complete"], False)
            self.assertEqual(delete_job_mock.call_count, 0)

            job_status_count = 0
            job_status_values = [JobStatus.COMPLETED, JobStatus.QUEUED]

            result = status(details)

            self.assertEqual(
                result["status"],
                [
                    {"status": 500, "what": "submit", "info": "Completed"},
                    {"status": 500, "what": "jid0", "info": "Completed"},
                    {"status": 40, "what": "jid1", "info": "Queued"},
                ],
            )
            self.assertEqual(result["complete"], False)
            self.assertEqual(delete_job_mock.call_count, 0)

            job_status_count = 0
            job_status_values = [JobStatus.COMPLETED, JobStatus.RUNNING]

            result = status(details)

            self.assertEqual(
                result["status"],
                [
                    {"status": 500, "what": "submit", "info": "Completed"},
                    {"status": 500, "what": "jid0", "info": "Completed"},
                    {"status": 50, "what": "jid1", "info": "Running"},
                ],
            )
            self.assertEqual(result["complete"], False)
            self.assertEqual(delete_job_mock.call_count, 0)

            job_status_count = 0
            job_status_values = [JobStatus.COMPLETED, JobStatus.COMPLETED]

            result = status(details)

            self.assertEqual(
                result["status"],
                [
                    {"status": 500, "what": "submit", "info": "Completed"},
                    {"status": 500, "what": "jid0", "info": "Completed"},
                    {"status": 500, "what": "jid1", "info": "Completed"},
                ],
            )
            self.assertEqual(result["complete"], True)
            self.assertEqual(delete_job_mock.call_count, 1)

            job_status_count = 0
            job_status_values = [JobStatus.WALL_TIME_EXCEEDED, JobStatus.CANCELLED]

            result = status(details)

            self.assertEqual(
                result["status"],
                [
                    {"status": 500, "what": "submit", "info": "Completed"},
                    {"status": 401, "what": "jid0", "info": "Wall Time Exceeded"},
                    {"status": 70, "what": "jid1", "info": "Cancelled"},
                ],
            )
            self.assertEqual(result["complete"], True)
            self.assertEqual(delete_job_mock.call_count, 2)

            job_status_count = 0
            job_status_values = [JobStatus.COMPLETED, JobStatus.CANCELLED]

            result = status(details)

            self.assertEqual(
                result["status"],
                [
                    {"status": 500, "what": "submit", "info": "Completed"},
                    {"status": 500, "what": "jid0", "info": "Completed"},
                    {"status": 70, "what": "jid1", "info": "Cancelled"},
                ],
            )
            self.assertEqual(result["complete"], True)
            self.assertEqual(delete_job_mock.call_count, 3)

            job_status_count = 0
            job_status_values = [JobStatus.COMPLETED, JobStatus.ERROR]

            result = status(details)

            self.assertEqual(
                result["status"],
                [
                    {"status": 500, "what": "submit", "info": "Completed"},
                    {"status": 500, "what": "jid0", "info": "Completed"},
                    {"status": 400, "what": "jid1", "info": "Error"},
                ],
            )
            self.assertEqual(result["complete"], True)
            self.assertEqual(delete_job_mock.call_count, 4)

    @patch("_bundledb.delete_job")
    @patch("_bundledb.get_job_by_id")
    @patch("scheduler.slurm.SlurmScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_status_slurm_slurm_ids_is_directory(self, status_mock, get_job_by_id_mock, delete_job_mock):
        with TemporaryDirectory() as tmpdir:
            os.mkdir(os.path.join(tmpdir, "slurm_ids"))

            db_job = {"working_directory": str(tmpdir), "submit_directory": ""}

            get_job_by_id_mock.side_effect = Mock(return_value=db_job)

            details = {"scheduler_id": 1234}

            from core.status import status

            result = status(details)

            # A corrupted job directory where slurm_ids is a directory should not crash and should keep polling
            self.assertEqual(result["status"], [{"status": 500, "what": "submit", "info": "Completed"}])
            self.assertEqual(result["complete"], False)
            self.assertEqual(status_mock.call_count, 0)
            self.assertEqual(delete_job_mock.call_count, 0)

    @patch("_bundledb.delete_job")
    @patch("_bundledb.get_job_by_id")
    @patch("scheduler.slurm.SlurmScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_status_slurm_no_submit_directory(self, status_mock, get_job_by_id_mock, delete_job_mock):
        db_job = {"working_directory": "a/working/directory", "submit_id": 1234}

        get_job_by_id_mock.side_effect = Mock(return_value=db_job)

        details = {"scheduler_id": 1234}

        from core.status import status

        result = status(details)

        self.assertEqual(
            result["status"],
            [
                {"status": 400, "what": "submit", "info": "Job has no submit directory"},
            ],
        )
        self.assertEqual(result["complete"], True)
        self.assertEqual(status_mock.call_count, 0)
        self.assertEqual(delete_job_mock.call_count, 0)

    @patch("_bundledb.delete_job")
    @patch("_bundledb.get_job_by_id")
    @patch("scheduler.slurm.SlurmScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_status_slurm_no_working_directory(self, status_mock, get_job_by_id_mock, delete_job_mock):
        db_job = {"submit_directory": "submit"}

        get_job_by_id_mock.side_effect = Mock(return_value=db_job)

        details = {"scheduler_id": 1234}

        from core.status import status

        result = status(details)

        self.assertEqual(
            result["status"],
            [
                {"status": 400, "what": "submit", "info": "Job has no working directory"},
            ],
        )
        self.assertEqual(result["complete"], True)
        self.assertEqual(status_mock.call_count, 0)
        self.assertEqual(delete_job_mock.call_count, 0)

    @patch("_bundledb.delete_job")
    @patch("_bundledb.get_job_by_id")
    @patch("scheduler.slurm.SlurmScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_status_slurm_none_submit_directory(self, status_mock, get_job_by_id_mock, delete_job_mock):
        db_job = {"submit_directory": None, "working_directory": "a/working/directory", "submit_id": 1234}

        get_job_by_id_mock.side_effect = Mock(return_value=db_job)

        details = {"scheduler_id": 1234}

        from core.status import status

        result = status(details)

        self.assertEqual(
            result["status"],
            [
                {"status": 400, "what": "submit", "info": "Job has no submit directory"},
            ],
        )
        self.assertEqual(result["complete"], True)
        self.assertEqual(status_mock.call_count, 0)
        self.assertEqual(delete_job_mock.call_count, 0)

    @patch("_bundledb.delete_job")
    @patch("_bundledb.get_job_by_id")
    @patch("scheduler.slurm.SlurmScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_status_slurm_none_working_directory(self, status_mock, get_job_by_id_mock, delete_job_mock):
        db_job = {"working_directory": None, "submit_directory": "submit"}

        get_job_by_id_mock.side_effect = Mock(return_value=db_job)

        details = {"scheduler_id": 1234}

        from core.status import status

        result = status(details)

        self.assertEqual(
            result["status"],
            [
                {"status": 400, "what": "submit", "info": "Job has no working directory"},
            ],
        )
        self.assertEqual(result["complete"], True)
        self.assertEqual(status_mock.call_count, 0)
        self.assertEqual(delete_job_mock.call_count, 0)

    @patch("_bundledb.delete_job")
    @patch("_bundledb.get_job_by_id")
    @patch("scheduler.condor.CondorScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.CONDOR)
    def test_status_condor_no_submit_id(self, status_mock, get_job_by_id_mock, delete_job_mock):
        db_job = {"working_directory": "a/working/directory", "submit_directory": "submit"}

        get_job_by_id_mock.side_effect = Mock(return_value=db_job)

        details = {"scheduler_id": 1234}

        from core.status import status

        result = status(details)

        self.assertEqual(
            result["status"],
            [
                {"status": 400, "what": "submit", "info": "Job has no submit id"},
            ],
        )
        self.assertEqual(result["complete"], True)
        self.assertEqual(status_mock.call_count, 0)
        self.assertEqual(delete_job_mock.call_count, 0)

    @patch("_bundledb.delete_job")
    @patch("_bundledb.get_job_by_id")
    @patch("scheduler.condor.CondorScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.CONDOR)
    def test_status_condor(self, status_mock, get_job_by_id_mock, delete_job_mock):
        db_job = {"submit_id": 1234, "working_directory": "a/working/directory", "submit_directory": "submit"}

        get_job_by_id_mock.side_effect = Mock(return_value=db_job)

        details = {"scheduler_id": 1234}

        from core.status import status

        job_status_result = None

        def job_status_mock(*args, **kwargs):
            return job_status_result, JobStatus.display_name(job_status_result)

        status_mock.side_effect = job_status_mock

        job_status_result = JobStatus.QUEUED

        result = status(details)

        self.assertEqual(
            result["status"],
            [
                {"status": 40, "what": "submit", "info": "Queued"},
            ],
        )
        self.assertEqual(result["complete"], False)
        self.assertEqual(delete_job_mock.call_count, 0)

        job_status_result = None

        result = status(details)

        # An undeterminable status should not crash and should keep polling
        self.assertEqual(
            result["status"],
            [
                {"status": None, "what": "submit", "info": "Unknown"},
            ],
        )
        self.assertEqual(result["complete"], False)
        self.assertEqual(delete_job_mock.call_count, 0)

        job_status_result = JobStatus.RUNNING

        result = status(details)

        self.assertEqual(
            result["status"],
            [
                {"status": 50, "what": "submit", "info": "Running"},
            ],
        )
        self.assertEqual(result["complete"], False)
        self.assertEqual(delete_job_mock.call_count, 0)

        job_status_result = JobStatus.COMPLETED

        result = status(details)

        self.assertEqual(
            result["status"],
            [
                {"status": 500, "what": "submit", "info": "Completed"},
            ],
        )
        self.assertEqual(result["complete"], True)
        self.assertEqual(delete_job_mock.call_count, 1)

        job_status_result = JobStatus.ERROR

        result = status(details)

        self.assertEqual(
            result["status"],
            [
                {"status": 400, "what": "submit", "info": "Error"},
            ],
        )
        self.assertEqual(result["complete"], True)
        self.assertEqual(delete_job_mock.call_count, 2)

        job_status_result = JobStatus.OUT_OF_MEMORY

        result = status(details)

        self.assertEqual(
            result["status"],
            [
                {"status": 402, "what": "submit", "info": "Out of Memory"},
            ],
        )
        self.assertEqual(result["complete"], True)
        self.assertEqual(delete_job_mock.call_count, 3)


class TestSlurmStatusDirect(TestCase):
    def setUp(self):
        sys.path.append(str(Path(__file__).parent / "misc"))

    def tearDown(self):
        sys.path = sys.path[:-1]

    @patch("_bundledb.delete_job")
    def test_slurm_status_missing_submit_directory(self, delete_job_mock):
        from core.status import slurm_status

        result = slurm_status({"working_directory": "a/working/directory"})

        self.assertEqual(
            result["status"],
            [{"status": 400, "what": "submit", "info": "Job has no submit directory"}],
        )
        self.assertEqual(result["complete"], True)
        self.assertEqual(delete_job_mock.call_count, 0)

    @patch("_bundledb.delete_job")
    def test_slurm_status_missing_working_directory(self, delete_job_mock):
        from core.status import slurm_status

        result = slurm_status({"submit_directory": "submit"})

        self.assertEqual(
            result["status"],
            [{"status": 400, "what": "submit", "info": "Job has no working directory"}],
        )
        self.assertEqual(result["complete"], True)
        self.assertEqual(delete_job_mock.call_count, 0)

    @patch("_bundledb.delete_job")
    def test_slurm_status_sid_file_not_a_file(self, delete_job_mock):
        with TemporaryDirectory() as tmpdir:
            from core.status import slurm_status

            result = slurm_status({"working_directory": str(tmpdir), "submit_directory": "submit"})

            # A missing slurm_ids file should not crash and should keep polling
            self.assertEqual(
                result["status"],
                [{"status": 500, "what": "submit", "info": "Completed"}],
            )
            self.assertEqual(result["complete"], False)
            self.assertEqual(delete_job_mock.call_count, 0)

    @patch("_bundledb.delete_job")
    @patch("scheduler.slurm.SlurmScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_slurm_status_per_job_error(self, status_mock, delete_job_mock):
        with TemporaryDirectory() as tmpdir:
            os.mkdir(os.path.join(tmpdir, "submit"))

            with open(os.path.join(tmpdir, "submit", "slurm_ids"), "w") as f:
                f.writelines(["jid0 12345\n"])
                f.flush()

            from core.status import slurm_status

            status_mock.side_effect = Mock(return_value=(JobStatus.ERROR, JobStatus.display_name(JobStatus.ERROR)))

            result = slurm_status({"working_directory": str(tmpdir), "submit_directory": "submit"})

            # A per-job error marks the job as complete and removes it from the database
            self.assertEqual(
                result["status"],
                [
                    {"status": 500, "what": "submit", "info": "Completed"},
                    {"status": 400, "what": "jid0", "info": "Error"},
                ],
            )
            self.assertEqual(result["complete"], True)
            self.assertEqual(delete_job_mock.call_count, 1)

    @patch("_bundledb.delete_job")
    @patch("scheduler.slurm.SlurmScheduler.status")
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_slurm_status_completed(self, status_mock, delete_job_mock):
        with TemporaryDirectory() as tmpdir:
            os.mkdir(os.path.join(tmpdir, "submit"))

            with open(os.path.join(tmpdir, "submit", "slurm_ids"), "w") as f:
                f.writelines(["jid0 12345\n"])
                f.flush()

            from core.status import slurm_status

            status_mock.side_effect = Mock(return_value=(JobStatus.COMPLETED, JobStatus.display_name(JobStatus.COMPLETED)))

            result = slurm_status({"working_directory": str(tmpdir), "submit_directory": "submit"})

            # A completed job is marked complete and removed from the database
            self.assertEqual(
                result["status"],
                [
                    {"status": 500, "what": "submit", "info": "Completed"},
                    {"status": 500, "what": "jid0", "info": "Completed"},
                ],
            )
            self.assertEqual(result["complete"], True)
            self.assertEqual(delete_job_mock.call_count, 1)
