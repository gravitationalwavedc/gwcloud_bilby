from unittest import mock

import requests
from django.conf import settings
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.request_job_filter import request_job_filter


class TestRequestJobFilter(BilbyTestCase):
    @override_settings(ALLOW_HTTP_LEAKS=True)
    @mock.patch("bilbyui.utils.jobs.request_job_filter._make_job_controller_request")
    def test_success_path_with_ids(self, make_request):
        result = [{"id": 1}, {"id": 2}]
        make_request.return_value = result

        status, jobs = request_job_filter(42, ids=[1, 2])

        self.assertEqual(status, "OK")
        self.assertEqual(jobs, result)
        make_request.assert_called_once()
        args, _ = make_request.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(args[1], f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?jobIds=1,2")
        self.assertEqual(args[2], 42)

    @override_settings(ALLOW_HTTP_LEAKS=True)
    @mock.patch("bilbyui.utils.jobs.request_job_filter._make_job_controller_request")
    def test_ids_none_omits_job_ids(self, make_request):
        make_request.return_value = []

        status, jobs = request_job_filter(42)

        self.assertEqual(status, "OK")
        self.assertEqual(jobs, [])
        make_request.assert_called_once()
        args, _ = make_request.call_args
        self.assertNotIn("jobIds=", args[1])

    @override_settings(ALLOW_HTTP_LEAKS=True)
    @mock.patch("bilbyui.utils.jobs.request_job_filter._make_job_controller_request")
    def test_non_list_response_returns_unknown(self, make_request):
        make_request.return_value = {"id": 1}

        status, jobs = request_job_filter(42, ids=[1])

        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(jobs, [])

    @override_settings(ALLOW_HTTP_LEAKS=True)
    @mock.patch("bilbyui.utils.jobs.request_job_filter._make_job_controller_request")
    def test_request_exception_returns_unknown(self, make_request):
        make_request.side_effect = requests.RequestException("boom")

        status, jobs = request_job_filter(42, ids=[1])

        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(jobs, [])
