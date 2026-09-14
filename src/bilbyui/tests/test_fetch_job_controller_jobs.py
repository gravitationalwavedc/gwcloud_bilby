from types import SimpleNamespace
from unittest import mock

import requests
from django.conf import settings
from django.test import override_settings

from bilbyui.services.jobs import _fetch_job_controller_jobs
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.request_job_filter import request_job_filter


def _job(job_id, job_controller_id):
    return SimpleNamespace(id=job_id, job_controller_id=job_controller_id)


class TestFetchJobControllerJobs(BilbyTestCase):
    def test_empty_job_controller_ids_returns_empty(self):
        jobs = [_job(1, None), _job(2, "")]
        self.assertEqual(_fetch_job_controller_jobs(jobs, 1), {})

    @mock.patch("bilbyui.services.jobs.request_job_filter")
    def test_populated_path_returns_filtered_mapping(self, mock_request_job_filter):
        mock_request_job_filter.return_value = (
            "OK",
            [
                {"id": 42, "history": [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}]},
                {"id": 999, "history": [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}]},
            ],
        )

        jobs = [_job(10, 42), _job(11, 999)]

        result = _fetch_job_controller_jobs(jobs, 7)

        self.assertEqual(list(result.keys()), [10, 11])
        self.assertEqual(result[10]["id"], 42)
        self.assertEqual(result[11]["id"], 999)
        mock_request_job_filter.assert_called_once_with(7, ids={42, 999})

    @mock.patch("bilbyui.services.jobs.request_job_filter")
    def test_non_ok_status_returns_empty(self, mock_request_job_filter):
        mock_request_job_filter.return_value = ("UNKNOWN", [])

        jobs = [_job(10, 42)]

        self.assertEqual(_fetch_job_controller_jobs(jobs, 7), {})


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
