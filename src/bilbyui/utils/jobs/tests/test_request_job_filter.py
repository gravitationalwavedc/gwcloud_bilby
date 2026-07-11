import datetime
from unittest import mock

from django.conf import settings
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.request_job_filter import request_job_filter


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestRequestJobFilter(BilbyTestCase):
    def setUp(self):
        self.authenticate()

    @mock.patch("bilbyui.utils.jobs.request_job_filter._make_job_controller_request")
    def test_returns_ok_with_job_ids(self, make_request):
        jobs = [{"jobId": 1}, {"jobId": 2}]
        make_request.return_value = jobs

        status, result = request_job_filter(self.user.id, ids=[1, 2])

        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)
        make_request.assert_called_once_with(
            "GET",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?jobIds=1,2",
            self.user.id,
        )

    @mock.patch("bilbyui.utils.jobs.request_job_filter._make_job_controller_request")
    def test_returns_ok_with_end_time_gt(self, make_request):
        jobs = [{"jobId": 3}]
        make_request.return_value = jobs
        end_time = datetime.datetime(2024, 6, 15, 12, 30, 45, tzinfo=datetime.UTC)

        status, result = request_job_filter(self.user.id, end_time_gt=end_time)

        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)
        make_request.assert_called_once_with(
            "GET",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?endTimeGt=1718454645",
            self.user.id,
        )

    @mock.patch("bilbyui.utils.jobs.request_job_filter._make_job_controller_request")
    def test_returns_ok_with_both_params(self, make_request):
        jobs = [{"jobId": 5}]
        make_request.return_value = jobs
        end_time = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)

        status, result = request_job_filter(self.user.id, ids=[5], end_time_gt=end_time)

        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)
        make_request.assert_called_once_with(
            "GET",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?jobIds=5&endTimeGt=1704067200",
            self.user.id,
        )

    @mock.patch("bilbyui.utils.jobs.request_job_filter._make_job_controller_request")
    def test_returns_unknown_on_error(self, make_request):
        make_request.side_effect = Exception("controller unavailable")

        status, message = request_job_filter(self.user.id, ids=[1])

        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(message, "Error getting job filter")

    @mock.patch("bilbyui.utils.jobs.request_job_filter._make_job_controller_request")
    def test_empty_query_string(self, make_request):
        jobs = []
        make_request.return_value = jobs

        status, result = request_job_filter(self.user.id)

        self.assertEqual(status, "OK")
        self.assertEqual(result, [])
        make_request.assert_called_once_with(
            "GET",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?",
            self.user.id,
        )

    @mock.patch("bilbyui.utils.jobs.request_job_filter._make_job_controller_request")
    def test_uses_explicit_user_id(self, make_request):
        make_request.return_value = []

        status, result = request_job_filter(42)

        self.assertEqual(status, "OK")
        make_request.assert_called_once_with(
            "GET",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?",
            42,
        )
