import json
from unittest.mock import patch

import requests
import responses
from django.conf import settings
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.submit_job import submit_job

BASE_URL = settings.GWCLOUD_JOB_CONTROLLER_API_URL


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestSubmitJob(BilbyTestCase):
    def setUp(self):
        self.responses = responses.RequestsMock()
        self.responses.start()
        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

    def test_submit_job_success(self):
        self.responses.add(
            responses.POST,
            f"{BASE_URL}/job/",
            body=json.dumps({"jobId": 42}),
            status=200,
        )

        result = submit_job(1234, {"foo": "bar"}, cluster=settings.CLUSTERS[0])

        self.assertEqual(result, {"jobId": 42})
        body = json.loads(self.responses.calls[0].request.body)
        self.assertEqual(body["cluster"], settings.CLUSTERS[0])
        self.assertEqual(body["parameters"], json.dumps({"foo": "bar"}))

    @patch("bilbyui.utils.jobs.submit_job.requests.request", side_effect=requests.RequestException("connection failed"))
    def test_submit_job_request_exception(self, mock_request):
        with self.assertRaises(Exception) as ctx:
            submit_job(1234, {"foo": "bar"}, cluster=settings.CLUSTERS[0])

        self.assertIn("Error submitting job", str(ctx.exception))
        mock_request.assert_called_once()

    def test_submit_job_invalid_cluster(self):
        with self.assertRaises(Exception) as ctx:
            submit_job(1234, {"foo": "bar"}, cluster="not-a-real-cluster")

        self.assertIn("Error submitting job", str(ctx.exception))
