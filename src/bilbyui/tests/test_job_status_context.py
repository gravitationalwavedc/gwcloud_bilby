from unittest import mock

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob
from bilbyui.status import JobStatus
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _get_job_status_context


class TestGetJobStatusContext(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ini = create_test_ini_string({"detectors": "['H1']"})

    def setUp(self):
        self.authenticate()

    def test_uploaded_job_returns_completed_status(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="uploaded_job",
            description="uploaded",
            job_type=BilbyJobType.UPLOADED,
            ini_string=self.ini,
        )

        context = _get_job_status_context(job, self.user)

        self.assertEqual(context["status_name"], "Completed")
        self.assertEqual(context["status_badge_class"], "primary")
        self.assertEqual(context["status_date"], job.last_updated)

    def test_external_job_returns_completed_status(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="external_job",
            description="external",
            job_type=BilbyJobType.EXTERNAL,
            ini_string=self.ini,
        )

        context = _get_job_status_context(job, self.user)

        self.assertEqual(context["status_name"], "Completed")
        self.assertEqual(context["status_badge_class"], "primary")
        self.assertEqual(context["status_date"], job.last_updated)

    def test_missing_job_controller_id_returns_unknown(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="no_controller",
            description="no controller",
            job_controller_id=None,
            ini_string=self.ini,
        )

        context = _get_job_status_context(job, self.user)

        self.assertEqual(context["status_name"], "Unknown")
        self.assertEqual(context["status_badge_class"], "dark")
        self.assertEqual(context["status_date"], job.last_updated)

    @mock.patch("bilbyui.views.request_job_filter", return_value=(True, []))
    def test_empty_job_controller_response_returns_unknown(self, mock_filter):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="controller_job",
            description="with controller",
            job_controller_id=42,
            ini_string=self.ini,
        )

        context = _get_job_status_context(job, self.user)

        self.assertEqual(context["status_name"], "Unknown")
        self.assertEqual(context["status_badge_class"], "dark")
        mock_filter.assert_called_once_with(self.user.id, ids=[42])

    @mock.patch("bilbyui.views.request_job_filter")
    def test_running_job_returns_status_from_controller(self, mock_filter):
        timestamp = "2020-01-01 12:00:00 UTC"
        mock_filter.return_value = (
            True,
            [{"id": 99, "history": [{"state": JobStatus.RUNNING, "timestamp": timestamp}]}],
        )
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="running_job",
            description="running",
            job_controller_id=99,
            ini_string=self.ini,
        )

        context = _get_job_status_context(job, self.user)

        self.assertEqual(context["status_name"], "Running")
        self.assertEqual(context["status_badge_class"], "info")
        self.assertEqual(context["status_date"], timestamp)

    @mock.patch("bilbyui.views.request_job_filter")
    def test_error_job_uses_danger_badge(self, mock_filter):
        timestamp = "2021-06-15 08:30:00 UTC"
        mock_filter.return_value = (
            True,
            [{"id": 77, "history": [{"state": JobStatus.ERROR, "timestamp": timestamp}]}],
        )
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="error_job",
            description="error",
            job_controller_id=77,
            ini_string=self.ini,
        )

        context = _get_job_status_context(job, self.user)

        self.assertEqual(context["status_name"], "Error")
        self.assertEqual(context["status_badge_class"], "danger")
        self.assertEqual(context["status_date"], timestamp)
