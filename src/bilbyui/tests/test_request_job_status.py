from unittest import mock

from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.request_job_status import request_job_status


class FakeJob:
    def __init__(self, job_id, job_controller_id, user_id):
        self.id = job_id
        self.job_controller_id = job_controller_id
        self.user_id = user_id


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestRequestJobStatus(BilbyTestCase):
    def test_no_job_controller_id(self):
        job = FakeJob(1, None, 1)
        status, detail = request_job_status(job)
        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(detail, "Job not submitted")

    def test_success(self):
        job = FakeJob(2, 42, 1)
        with mock.patch("bilbyui.utils.jobs.request_job_status._make_job_controller_request") as mocked:
            mocked.return_value = [{"history": "some_history"}]
            status, detail = request_job_status(job)
        self.assertEqual(status, "OK")
        self.assertEqual(detail, "some_history")

    def test_exception(self):
        job = FakeJob(3, 42, 1)
        with mock.patch("bilbyui.utils.jobs.request_job_status._make_job_controller_request") as mocked:
            mocked.side_effect = Exception("boom")
            status, detail = request_job_status(job)
        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(detail, "Error getting job status")
