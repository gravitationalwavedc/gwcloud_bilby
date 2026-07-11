import datetime
from unittest import mock

from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _get_job_status_context


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestGetJobStatusContext(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Test job",
            description="A test job",
            job_controller_id=10001,
            private=False,
            ini_string="label = Test job\ndetectors = ['H1']",
        )

    def test_uploaded_job_returns_completed(self):
        self.job.job_type = BilbyJobType.UPLOADED
        self.job.last_updated = datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)
        self.job.save()

        result = _get_job_status_context(self.job, self.user)

        self.assertEqual(result["status_name"], "Completed")
        self.assertEqual(result["status_badge_class"], "primary")
        self.assertEqual(result["status_date"], self.job.last_updated)

    def test_external_job_returns_completed(self):
        self.job.job_type = BilbyJobType.EXTERNAL
        self.job.last_updated = datetime.datetime(2024, 6, 15, 8, 30, 0, tzinfo=datetime.UTC)
        self.job.save()

        result = _get_job_status_context(self.job, self.user)

        self.assertEqual(result["status_name"], "Completed")
        self.assertEqual(result["status_badge_class"], "primary")
        self.assertEqual(result["status_date"], self.job.last_updated)

    def test_missing_job_controller_id_returns_unknown(self):
        self.job.job_controller_id = None
        self.job.save()

        result = _get_job_status_context(self.job, self.user)

        self.assertEqual(result["status_name"], "Unknown")
        self.assertEqual(result["status_badge_class"], "dark")
        self.assertEqual(result["status_date"], self.job.last_updated)

    @mock.patch("bilbyui.views.request_job_filter", return_value=(True, []))
    def test_empty_filter_result_returns_unknown(self, mock_filter):
        result = _get_job_status_context(self.job, self.user)

        self.assertEqual(result["status_name"], "Unknown")
        self.assertEqual(result["status_badge_class"], "dark")
        self.assertEqual(result["status_date"], self.job.last_updated)
        mock_filter.assert_called_once_with(self.user.id, ids=[10001])

    @mock.patch(
        "bilbyui.views.request_job_filter",
        return_value=(True, [{"history": [{"state": 500, "timestamp": "2024-03-01 10:00:00 UTC"}]}]),
    )
    def test_successful_status_fetch(self, mock_filter):
        result = _get_job_status_context(self.job, self.user)

        self.assertEqual(result["status_name"], "Completed")
        self.assertEqual(result["status_badge_class"], "primary")
        self.assertEqual(result["status_date"], "2024-03-01 10:00:00 UTC")
