from unittest import mock

from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.request_file_download_id import (
    request_file_download_id,
    request_file_download_ids,
)


class TestRequestFileDownloadIds(BilbyTestCase):
    def setUp(self):
        self.authenticate()

    def _make_job(self, job_controller_id):
        return BilbyJob.objects.create(
            user_id=self.user.id,
            name="TestDownloadIds",
            description="job for download ids",
            job_controller_id=job_controller_id,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
            job_type=BilbyJobType.NORMAL,
        )

    @override_settings(ALLOW_HTTP_LEAKS=True)
    def test_not_submitted_returns_error(self):
        job = self._make_job(None)
        success, result = request_file_download_ids(job, ["/a", "/b"])
        self.assertFalse(success)
        self.assertEqual(result, "Job not submitted")

    @override_settings(ALLOW_HTTP_LEAKS=True)
    @mock.patch("bilbyui.utils.jobs.request_file_download_id._make_job_controller_request")
    def test_success_path(self, make_request):
        make_request.return_value = {"fileIds": ["id1", "id2"]}

        job = self._make_job(7)
        success, result = request_file_download_ids(job, ["/a", "/b"], user_id=42)
        self.assertTrue(success)
        self.assertEqual(result, ["id1", "id2"])
        make_request.assert_called_once()
        args, kwargs = make_request.call_args
        self.assertEqual(args[2], 42)
        self.assertEqual(kwargs["data"]["jobId"], 7)
        self.assertEqual(kwargs["data"]["paths"], ["/a", "/b"])

    @override_settings(ALLOW_HTTP_LEAKS=True)
    @mock.patch("bilbyui.utils.jobs.request_file_download_id._make_job_controller_request")
    def test_exception_path(self, make_request):
        make_request.side_effect = Exception("boom")

        job = self._make_job(9)
        success, result = request_file_download_ids(job, ["/a"])
        self.assertFalse(success)
        self.assertEqual(result, "Error getting job file download id")

    @override_settings(ALLOW_HTTP_LEAKS=True)
    @mock.patch("bilbyui.utils.jobs.request_file_download_id.request_file_download_ids")
    def test_singular_success_and_failure(self, request_ids):
        job = self._make_job(11)

        request_ids.return_value = (True, ["the-id"])
        success, result = request_file_download_id(job, "/a")
        self.assertTrue(success)
        self.assertEqual(result, "the-id")

        request_ids.return_value = (False, "some error")
        success, result = request_file_download_id(job, "/a")
        self.assertFalse(success)
        self.assertEqual(result, "some error")
