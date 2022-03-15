import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import htcondor

from scheduler.condor import CondorScheduler
from scheduler.status import JobStatus


class TestCondor(TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_regression_393(self):
        sched = CondorScheduler()

        log_name = 'dag_393.submit.nodes.log'

        jel = htcondor.JobEventLog(
            str(Path(os.path.dirname(__file__)) / 'data' / 'regression' / log_name)
        )
        events = list(jel.events(stop_after=0))

        with TemporaryDirectory() as td:
            submit_dir = os.path.join(td, 'job', 'submit')
            os.makedirs(submit_dir)
            fn = os.path.join(submit_dir, log_name)

            details = {
                'working_directory': td,
                'submit_directory': 'job/submit'
            }

            def write_next_event():
                with open(fn, "a") as f:
                    f.write(str(events.pop(0)))
                    f.write('...\n')

            write_next_event()
            self.assertEqual(
                sched.status(None, details),
                (JobStatus.QUEUED, "Job is queued")
            )

            for _ in range(10):
                write_next_event()
                self.assertEqual(
                    sched.status(None, details),
                    (JobStatus.RUNNING, "Job is running")
                )

            write_next_event()
            self.assertEqual(
                sched.status(None, details),
                (JobStatus.COMPLETED, "All job stages finished successfully")
            )

    def test_regression_393_reverse(self):
        sched = CondorScheduler()

        log_name = 'dag_393_reverse.submit.nodes.log'

        jel = htcondor.JobEventLog(
            str(Path(os.path.dirname(__file__)) / 'data' / 'regression' / log_name)
        )
        events = list(jel.events(stop_after=0))

        with TemporaryDirectory() as td:
            submit_dir = os.path.join(td, 'job', 'submit')
            os.makedirs(submit_dir)
            fn = os.path.join(submit_dir, log_name)

            details = {
                'working_directory': td,
                'submit_directory': 'job/submit'
            }

            def write_next_event():
                with open(fn, "a") as f:
                    f.write(str(events.pop(0)))
                    f.write('...\n')

            write_next_event()
            self.assertEqual(
                sched.status(None, details),
                (JobStatus.QUEUED, "Job is queued")
            )

            for _ in range(10):
                write_next_event()
                self.assertEqual(
                    sched.status(None, details),
                    (JobStatus.RUNNING, "Job is running")
                )

            write_next_event()
            self.assertEqual(
                sched.status(None, details),
                (JobStatus.COMPLETED, "All job stages finished successfully")
            )
