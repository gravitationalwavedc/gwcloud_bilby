import unittest
from unittest.mock import patch


class TestMisc(unittest.TestCase):
    @patch("settings.job_directory", "/my/test/directory")
    def test_working_directory(self):
        import settings
        from core.misc import working_directory

        details = {"job_id": 1234}

        self.assertEqual(working_directory(details), f"{settings.job_directory}/{str(details['job_id'])}")

    @patch("settings.default_working_directory", "/my/default/directory")
    def test_working_directory_default(self):
        import settings
        from core.misc import working_directory

        details = "some_file_path.hdf5"

        self.assertEqual(working_directory(details), settings.default_working_directory)

    @patch("settings.scheduler", None)
    def test_get_scheduler_slurm(self):
        from core.misc import get_scheduler
        from scheduler.scheduler import EScheduler

        with patch("settings.scheduler", EScheduler.SLURM):
            scheduler = get_scheduler()

        from scheduler.slurm import SlurmScheduler

        self.assertIsInstance(scheduler, SlurmScheduler)

    @patch("settings.scheduler", None)
    def test_get_scheduler_condor(self):
        from core.misc import get_scheduler
        from scheduler.scheduler import EScheduler

        with patch("settings.scheduler", EScheduler.CONDOR):
            scheduler = get_scheduler()

        from scheduler.condor import CondorScheduler

        self.assertIsInstance(scheduler, CondorScheduler)

    @patch("settings.scheduler", None)
    def test_get_scheduler_unknown(self):
        from core.misc import get_scheduler

        self.assertIsNone(get_scheduler())
