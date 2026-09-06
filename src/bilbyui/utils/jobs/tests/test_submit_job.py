import json
from unittest import mock
from unittest.mock import patch

import requests
import responses
from django.conf import settings
from django.test import override_settings

from bilbyui.tests.test_utils import silence_errors
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.submit_job import submit_job

JOB_URL = f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/"
USER_ID = 1
PARAMS = {"name": "test-job"}


@override_settings(ALLOW_HTTP_LEAKS=True, CLUSTERS=["default", "another"])
class TestSubmitJob(BilbyTestCase):
    def setUp(self):
        self.create_user(id=1)
        self.responses = responses.RequestsMock()
        self.responses.start()
        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

    def test_submit_job_success(self):
        self.responses.add(
            responses.POST,
            JOB_URL,
            body=json.dumps({"jobId": 42}),
            status=200,
        )

        result = submit_job(USER_ID, {"foo": "bar"}, cluster=settings.CLUSTERS[0])

        self.assertEqual(result, {"jobId": 42})
        body = json.loads(self.responses.calls[0].request.body)
        self.assertEqual(body["cluster"], settings.CLUSTERS[0])
        self.assertEqual(body["parameters"], json.dumps({"foo": "bar"}))

    @silence_errors
    def test_invalid_cluster(self):
        with self.assertRaises(ValueError) as ctx:
            submit_job(USER_ID, PARAMS, "not_real")

        self.assertIn("cluster 'not_real' is not one of", str(ctx.exception))

    def test_default_cluster_fallback(self):
        self.responses.add(
            responses.POST,
            JOB_URL,
            body=json.dumps({"jobId": 99}),
            status=200,
        )

        result = submit_job(USER_ID, PARAMS, None)

        self.assertEqual(result, {"jobId": 99})
        body = json.loads(self.responses.calls[0].request.body)
        self.assertEqual(body["cluster"], "default")

    def test_successful_submission(self):
        self.responses.add(
            responses.POST,
            JOB_URL,
            body=json.dumps({"jobId": 4321}),
            status=200,
        )

        result = submit_job(USER_ID, PARAMS, "another")

        self.assertEqual(result, {"jobId": 4321})
        body = json.loads(self.responses.calls[0].request.body)
        self.assertEqual(body["cluster"], "another")
        self.assertEqual(json.loads(body["parameters"]), PARAMS)

    @silence_errors
    def test_non_200_response(self):
        self.responses.add(responses.POST, JOB_URL, body=b"error", status=500)

        with self.assertRaises(RuntimeError) as ctx:
            submit_job(USER_ID, PARAMS, "default")

        self.assertIn("Job controller returned 500", str(ctx.exception))

    @silence_errors
    def test_malformed_response(self):
        self.responses.add(responses.POST, JOB_URL, body=json.dumps(None), status=200)

        with self.assertRaises(RuntimeError) as ctx:
            submit_job(USER_ID, PARAMS, "default")

        self.assertIn("malformed response", str(ctx.exception))

    @silence_errors
    @patch("bilbyui.utils.jobs.submit_job.requests.request")
    def test_request_exception(self, mock_request):
        mock_request.side_effect = requests.ConnectionError("connection refused")

        with self.assertRaises(RuntimeError) as ctx:
            submit_job(USER_ID, PARAMS, "default")

        self.assertEqual(str(ctx.exception), "Error submitting job: connection refused")


@override_settings(ALLOW_HTTP_LEAKS=True, CLUSTERS=["default", "another"])
class TestSubmitJobWithMockedRequest(BilbyTestCase):
    def setUp(self):
        self.create_user(id=1)

    @mock.patch("bilbyui.utils.jobs.submit_job._make_job_controller_request")
    def test_default_cluster_selection(self, mock_request):
        mock_request.return_value = {"jobId": 42}

        result = submit_job(USER_ID, PARAMS, None)

        self.assertEqual(result, {"jobId": 42})
        self.assertEqual(mock_request.call_args.kwargs["data"]["cluster"], settings.CLUSTERS[0])

    @silence_errors
    @mock.patch("bilbyui.utils.jobs.submit_job._make_job_controller_request")
    def test_invalid_cluster_raises_value_error(self, mock_request):
        with self.assertRaises(ValueError) as ctx:
            submit_job(USER_ID, PARAMS, "not_real")

        self.assertIn("cluster 'not_real' is not one of", str(ctx.exception))
        mock_request.assert_not_called()

    @silence_errors
    @mock.patch("bilbyui.utils.jobs.submit_job._make_job_controller_request")
    def test_request_exception_becomes_runtime_error(self, mock_request):
        mock_request.side_effect = requests.RequestException("boom")

        with self.assertRaises(RuntimeError) as ctx:
            submit_job(USER_ID, PARAMS, "default")

        self.assertEqual(str(ctx.exception), "Error submitting job: boom")

    @silence_errors
    @mock.patch("bilbyui.utils.jobs.submit_job._make_job_controller_request")
    def test_malformed_non_dict_response_raises_runtime_error(self, mock_request):
        mock_request.return_value = ["not", "a", "dict"]

        with self.assertRaises(RuntimeError) as ctx:
            submit_job(USER_ID, PARAMS, "default")

        self.assertIn("malformed response", str(ctx.exception))

    @mock.patch("bilbyui.utils.jobs.submit_job._make_job_controller_request")
    def test_success_returns_job_id(self, mock_request):
        mock_request.return_value = {"jobId": 7}

        result = submit_job(USER_ID, PARAMS, "default")

        self.assertEqual(result, {"jobId": 7})
