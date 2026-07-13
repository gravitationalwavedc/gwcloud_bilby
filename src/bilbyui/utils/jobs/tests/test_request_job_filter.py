import datetime
import json
import logging

import responses
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from bilbyui.utils.jobs.request_job_filter import request_job_filter


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestRequestJobFilter(SimpleTestCase):
    def setUp(self):
        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

        self.base_url = f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/"

    def test_success_no_query_params(self):
        jobs = [{"id": 1}, {"id": 2}]
        self.responses.add(
            responses.GET,
            f"{self.base_url}?",
            body=json.dumps(jobs),
            status=200,
        )

        status, result = request_job_filter(123)

        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)

    def test_error_fallback(self):
        try:
            logging.disable(logging.CRITICAL)

            self.responses.add(responses.GET, f"{self.base_url}?", status=500)

            status, result = request_job_filter(123)

            self.assertEqual(status, "UNKNOWN")
            self.assertEqual(result, "Error getting job filter")
        finally:
            logging.disable(logging.NOTSET)

    def test_query_params(self):
        jobs = [{"id": 42}]
        end_time = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)

        ids_url = f"{self.base_url}?jobIds=10,20"
        self.responses.add(responses.GET, ids_url, body=json.dumps(jobs), status=200)
        status, result = request_job_filter(123, ids=[10, 20])
        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)

        end_time_url = f"{self.base_url}?endTimeGt={round(end_time.timestamp())}"
        self.responses.add(responses.GET, end_time_url, body=json.dumps(jobs), status=200)
        status, result = request_job_filter(123, end_time_gt=end_time)
        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)

        combined_url = f"{self.base_url}?jobIds=1,2&endTimeGt={round(end_time.timestamp())}"
        self.responses.add(responses.GET, combined_url, body=json.dumps(jobs), status=200)
        status, result = request_job_filter(123, ids=[1, 2], end_time_gt=end_time)
        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)
