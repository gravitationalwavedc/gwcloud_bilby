import json

import responses
from django.conf import settings
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.submit_job import _make_job_controller_request

USER_ID = 1
BASE_URL = settings.GWCLOUD_JOB_CONTROLLER_API_URL


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestMakeJobControllerRequest(BilbyTestCase):
    def setUp(self):
        self.responses = responses.RequestsMock()
        self.responses.start()
        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

    def test_get_request_success(self):
        self.responses.add(
            responses.GET,
            f"{BASE_URL}/status/",
            body=json.dumps({"jobs": []}),
            status=200,
        )

        result = _make_job_controller_request("GET", f"{BASE_URL}/status/", USER_ID)

        self.assertEqual(result, {"jobs": []})
        self.assertIn("Authorization", self.responses.calls[0].request.headers)

    def test_post_request_with_data(self):
        self.responses.add(
            responses.POST,
            f"{BASE_URL}/job/",
            body=json.dumps({"jobId": 42}),
            status=200,
        )

        data = {"parameters": "{}", "cluster": "default"}
        result = _make_job_controller_request("POST", f"{BASE_URL}/job/", USER_ID, data=data)

        self.assertEqual(result, {"jobId": 42})
        body = json.loads(self.responses.calls[0].request.body)
        self.assertEqual(body, data)

    def test_non_200_response_raises(self):
        self.responses.add(
            responses.GET,
            f"{BASE_URL}/status/",
            body=b"error",
            status=500,
        )

        with self.assertRaises(Exception) as ctx:
            _make_job_controller_request("GET", f"{BASE_URL}/status/", USER_ID)

        self.assertIn("Job controller returned 500", str(ctx.exception))
