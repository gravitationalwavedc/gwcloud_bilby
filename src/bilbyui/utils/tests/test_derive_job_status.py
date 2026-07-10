import datetime

from django.test import override_settings

from bilbyui.status import JobStatus
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.derive_job_status import derive_job_status


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestDeriveJobStatus(BilbyTestCase):
    def test_empty_history_returns_draft(self):
        state, display, timestamp = derive_job_status([])

        self.assertEqual(state, JobStatus.DRAFT)
        self.assertEqual(display, "Unknown")
        self.assertIsNone(timestamp)

    def test_returns_latest_history_entry(self):
        history = [
            {"timestamp": "2020-01-01 10:00:00.123456 UTC", "state": JobStatus.QUEUED},
            {"timestamp": "2020-01-01 12:00:00.123456 UTC", "state": JobStatus.RUNNING},
            {"timestamp": "2020-01-01 11:00:00.123456 UTC", "state": JobStatus.SUBMITTED},
        ]

        state, display, timestamp = derive_job_status(history)

        self.assertEqual(state, JobStatus.RUNNING)
        self.assertEqual(display, "Running")
        self.assertEqual(
            timestamp,
            datetime.datetime.strptime("2020-01-01 12:00:00.123456 UTC", "%Y-%m-%d %H:%M:%S.%f UTC"),
        )

    def test_single_entry(self):
        history = [
            {"timestamp": "2020-01-01 10:00:00.123456 UTC", "state": JobStatus.COMPLETED},
        ]

        state, display, timestamp = derive_job_status(history)

        self.assertEqual(state, JobStatus.COMPLETED)
        self.assertEqual(display, "Completed")
        self.assertIsNotNone(timestamp)
