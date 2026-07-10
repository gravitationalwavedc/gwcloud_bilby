import json
from datetime import UTC, datetime

import responses
from django.conf import settings
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.request_job_filter import request_job_filter

USER_ID = 1
BASE_URL = settings.GWCLOUD_JOB_CONTROLLER_API_URL


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestRequestJobFilter(BilbyTestCase):
    def setUp(self):
        self.responses = responses.RequestsMock()
        self.responses.start()
        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

    def test_success_with_ids(self):
        jobs = [{"id": 1, "history": []}]
        self.responses.add(
            responses.GET,
            f"{BASE_URL}/job/?jobIds=1,2",
            body=json.dumps(jobs),
            status=200,
        )

        status, result = request_job_filter(USER_ID, ids=[1, 2])

        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)

    def test_success_with_end_time_gt(self):
        end_time = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
        timestamp = round(end_time.timestamp())
        jobs = []
        self.responses.add(
            responses.GET,
            f"{BASE_URL}/job/?endTimeGt={timestamp}",
            body=json.dumps(jobs),
            status=200,
        )

        status, result = request_job_filter(USER_ID, end_time_gt=end_time)

        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)

    def test_success_with_ids_and_end_time_gt(self):
        end_time = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
        timestamp = round(end_time.timestamp())
        jobs = [{"id": 5}]
        self.responses.add(
            responses.GET,
            f"{BASE_URL}/job/?jobIds=5&endTimeGt={timestamp}",
            body=json.dumps(jobs),
            status=200,
        )

        status, result = request_job_filter(USER_ID, ids=[5], end_time_gt=end_time)

        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)

    def test_success_no_query_params(self):
        jobs = []
        self.responses.add(
            responses.GET,
            f"{BASE_URL}/job/?",
            body=json.dumps(jobs),
            status=200,
        )

        status, result = request_job_filter(USER_ID)

        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)

    def test_error_on_non_200_response(self):
        self.responses.add(
            responses.GET,
            f"{BASE_URL}/job/?",
            body=b"error",
            status=500,
        )

        status, result = request_job_filter(USER_ID)

        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(result, "Error getting job filter")
