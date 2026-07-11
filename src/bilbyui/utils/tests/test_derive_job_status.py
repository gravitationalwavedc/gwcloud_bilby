import datetime

from django.test import override_settings

from bilbyui.status import JobStatus
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.derive_job_status import derive_job_status


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestDeriveJobStatus(BilbyTestCase):
    def test_empty_history_returns_draft(self):
        status_number, status_name, status_date = derive_job_status([])

        self.assertEqual(status_number, JobStatus.DRAFT)
        self.assertEqual(status_name, "Unknown")
        self.assertIsNone(status_date)

    def test_single_history_item(self):
        history = [
            {
                "timestamp": "2024-01-01 10:00:00.000000 UTC",
                "state": JobStatus.RUNNING,
            }
        ]

        status_number, status_name, status_date = derive_job_status(history)

        self.assertEqual(status_number, JobStatus.RUNNING)
        self.assertEqual(status_name, "Running")
        self.assertEqual(status_date, datetime.datetime(2024, 1, 1, 10, 0, 0, 0))

    def test_latest_state_selected_by_timestamp(self):
        history = [
            {
                "timestamp": "2024-01-01 09:00:00.000000 UTC",
                "state": JobStatus.QUEUED,
            },
            {
                "timestamp": "2024-01-01 12:00:00.000000 UTC",
                "state": JobStatus.COMPLETED,
            },
            {
                "timestamp": "2024-01-01 10:00:00.000000 UTC",
                "state": JobStatus.RUNNING,
            },
        ]

        status_number, status_name, status_date = derive_job_status(history)

        self.assertEqual(status_number, JobStatus.COMPLETED)
        self.assertEqual(status_name, "Completed")
        self.assertEqual(status_date, datetime.datetime(2024, 1, 1, 12, 0, 0, 0))
