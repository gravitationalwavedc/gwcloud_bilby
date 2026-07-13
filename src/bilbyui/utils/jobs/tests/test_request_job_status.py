import json
from unittest import mock

import responses
from django.conf import settings
from django.test import override_settings

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.request_job_status import request_job_status


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestRequestJobStatus(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Status job",
            description="A job to check status",
            job_controller_id=10001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Status job"}),
        )

    def test_returns_unknown_when_not_submitted(self):
        draft_job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Draft job",
            description="Not yet submitted",
            job_controller_id=None,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Draft job"}),
        )

        status, message = request_job_status(draft_job)

        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(message, "Job not submitted")

    @mock.patch("bilbyui.utils.jobs.request_job_status._make_job_controller_request")
    def test_returns_ok_on_success(self, make_request):
        history = [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}]
        make_request.return_value = [{"history": history}]

        status, result = request_job_status(self.job)

        self.assertEqual(status, "OK")
        self.assertEqual(result, history)
        make_request.assert_called_once_with(
            "GET",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?jobIds={self.job.job_controller_id}",
            self.user.id,
        )

    @mock.patch("bilbyui.utils.jobs.request_job_status._make_job_controller_request")
    def test_uses_explicit_user_id(self, make_request):
        make_request.return_value = [{"history": []}]

        request_job_status(self.job, user_id=42)

        make_request.assert_called_once_with(
            "GET",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?jobIds={self.job.job_controller_id}",
            42,
        )

    @mock.patch("bilbyui.utils.jobs.request_job_status._make_job_controller_request")
    def test_returns_unknown_on_error(self, make_request):
        make_request.side_effect = Exception("controller unavailable")

        status, message = request_job_status(self.job)

        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(message, "Error getting job status")

    def test_request_job_status_with_responses(self):
        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

        status_url = f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?jobIds=4321"
        self.responses.add(responses.GET, status_url, status=400)

        history = [{"status": 30, "timestamp": "2020-01-01T00:00:00Z"}]
        self.responses.add(
            responses.GET,
            status_url,
            body=json.dumps([{"id": 4321, "history": history}]),
            status=200,
        )

        # Test job not submitted
        self.job.job_controller_id = None
        self.job.save()

        result = request_job_status(self.job)

        self.assertEqual(result, ("UNKNOWN", "Job not submitted"))

        # Test submitted job, invalid return code
        self.job.job_controller_id = 4321
        self.job.save()

        result = request_job_status(self.job)

        self.assertEqual(result, ("UNKNOWN", "Error getting job status"))

        # Test submitted job, successful return
        result = request_job_status(self.job)

        self.assertEqual(result, ("OK", history))
