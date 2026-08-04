import unittest
from unittest.mock import patch

import settings
from core.misc import get_scheduler, working_directory
from scheduler.condor import CondorScheduler
from scheduler.scheduler import EScheduler
from scheduler.slurm import SlurmScheduler


class TestMisc(unittest.TestCase):
    @patch("settings.job_directory", "/my/test/directory")
    def test_working_directory(self):
        details = {"job_id": 1234}

        self.assertEqual(
            working_directory(details),
            f"{settings.job_directory}/{str(details['job_id'])}",
        )

    @patch("settings.default_working_directory", "/my/default/directory")
    def test_working_directory_default(self):
        details = "some_file_path.hdf5"

        self.assertEqual(working_directory(details), settings.default_working_directory)

    @patch("settings.scheduler", None)
    def test_get_scheduler_slurm(self):
        with patch("settings.scheduler", EScheduler.SLURM):
            scheduler = get_scheduler()

        self.assertIsInstance(scheduler, SlurmScheduler)

    @patch("settings.scheduler", None)
    def test_get_scheduler_condor(self):
        with patch("settings.scheduler", EScheduler.CONDOR):
            scheduler = get_scheduler()

        self.assertIsInstance(scheduler, CondorScheduler)

    @patch("settings.scheduler", None)
    def test_get_scheduler_unknown(self):
        self.assertIsNone(get_scheduler())
