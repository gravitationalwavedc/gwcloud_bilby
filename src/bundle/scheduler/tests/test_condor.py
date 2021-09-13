import htcondor
import os
from mock import patch
from scheduler.condor import CondorScheduler
from scheduler.status import JobStatus
from tempfile import TemporaryDirectory
from unittest import TestCase


mock_from_dag_args = None
mock_from_dag_kwargs = None
mock_from_dag_result = None
mock_submit_args = None
mock_submit_kwargs = None
mock_submit_result = None


def mock_from_dag(*args, **kwargs):
    global mock_from_dag_args, mock_from_dag_kwargs
    mock_from_dag_args = args
    mock_from_dag_kwargs = kwargs
    return mock_from_dag_result


class MockSubmit:
    def submit(self, *args, **kwargs):
        global mock_submit_args, mock_submit_kwargs
        mock_submit_args = args
        mock_submit_kwargs = kwargs
        return mock_submit_result


class TestCondor(TestCase):
    def setUp(self):
        self.maxDiff = None

    @patch("htcondor.Submit.from_dag", side_effect=mock_from_dag)
    @patch("htcondor.Schedd", side_effect=MockSubmit)
    def test_submit_success(self, *args, **kwargs):
        class Result:
            def cluster(self):
                return 1234

        global mock_submit_result, mock_from_dag_result
        mock_from_dag_result = ['OK']
        mock_submit_result = Result()

        sched = CondorScheduler()
        result = sched.submit("test_script_path", "a/working/directory")

        self.assertEqual(result, 1234)
        self.assertEqual(mock_from_dag_args, ("test_script_path", {'force': True}))
        self.assertEqual(mock_submit_args, (mock_from_dag_result,))
        self.assertEqual(mock_submit_kwargs, {'count': 1})

    @patch("htcondor.Submit.from_dag", autospec=True)
    def test_submit_failure(self, from_dag_mock):
        from_dag_mock.side_effect = Exception()

        sched = CondorScheduler()
        result = sched.submit("test_script_path_failure", "a/working/directory")

        self.assertEqual(result, None)
        self.assertEqual(from_dag_mock.call_count, 5)

    def test_status_no_error_no_parallel(self):
        sched = CondorScheduler()

        log_name = 'completed_no_error_no_parallel.submit.nodes.log'

        jel = htcondor.JobEventLog(
            os.path.join(
                os.path.dirname(__file__),
                'data',
                log_name
            )
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

            for _ in range(7):
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

    def test_status_cancelled_no_parallel(self):
        sched = CondorScheduler()

        log_name = 'cancelled_no_parallel.submit.nodes.log'

        jel = htcondor.JobEventLog(
            os.path.join(
                os.path.dirname(__file__),
                'data',
                log_name
            )
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

            for _ in range(5):
                write_next_event()
                self.assertEqual(
                    sched.status(None, details),
                    (JobStatus.RUNNING, "Job is running")
                )

            write_next_event()
            self.assertEqual(
                sched.status(None, details),
                (JobStatus.CANCELLED, "Job has been aborted")
            )

    def test_status_no_error_parallel(self):
        sched = CondorScheduler()

        log_name = 'completed_no_error_parallel.submit.nodes.log'

        jel = htcondor.JobEventLog(
            os.path.join(
                os.path.dirname(__file__),
                'data',
                log_name
            )
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

            for _ in range(26):
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

    def test_status_error_no_parallel(self):
        sched = CondorScheduler()

        log_name = 'error_no_parallel.submit.nodes.log'

        jel = htcondor.JobEventLog(
            os.path.join(
                os.path.dirname(__file__),
                'data',
                log_name
            )
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

            for _ in range(7):
                write_next_event()
                self.assertEqual(
                    sched.status(None, details),
                    (JobStatus.RUNNING, "Job is running")
                )

            write_next_event()
            self.assertEqual(
                sched.status(None, details),
                (JobStatus.ERROR, "Job terminated with return value 1")
            )

    def test_status_error_short(self):
        sched = CondorScheduler()

        log_name = 'error_short.submit.nodes.log'

        jel = htcondor.JobEventLog(
            os.path.join(
                os.path.dirname(__file__),
                'data',
                log_name
            )
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

            write_next_event()
            self.assertEqual(
                sched.status(None, details),
                (JobStatus.RUNNING, "Job is running")
            )

            write_next_event()
            self.assertEqual(
                sched.status(None, details),
                (JobStatus.ERROR, "Job terminated with return value 1")
            )
