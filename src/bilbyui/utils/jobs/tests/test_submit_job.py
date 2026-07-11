from unittest.mock import patch

import requests
from django.conf import settings
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.submit_job import submit_job


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestSubmitJob(BilbyTestCase):
    @patch("bilbyui.utils.jobs.submit_job.requests.request", side_effect=requests.RequestException("connection failed"))
    def test_submit_job_request_exception(self, mock_request):
        with self.assertRaises(Exception) as ctx:
            submit_job(1234, {"foo": "bar"}, cluster=settings.CLUSTERS[0])

        self.assertIn("Error submitting job", str(ctx.exception))
        mock_request.assert_called_once()
