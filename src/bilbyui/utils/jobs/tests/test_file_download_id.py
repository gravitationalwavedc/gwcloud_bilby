import json
import logging

import responses
from django.conf import settings
from django.test import override_settings

from bilbyui.models import BilbyJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.request_file_download_id import request_file_download_id, request_file_download_ids


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestFileDownloadIds(BilbyTestCase):
    def setUp(self):
        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

        self.job = BilbyJob.objects.create(user_id=1234, ini_string="detectors=['H1']")

    def test_request_file_download_id(self):
        try:
            logging.disable(logging.CRITICAL)

            # Set up responses before any call to request
            # See https://github.com/getsentry/responses/pull/375
            self.responses.add(responses.POST, f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/", status=400)

            return_result = "val1"
            self.responses.add(
                responses.POST,
                f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/",
                body=json.dumps({"fileIds": [return_result]}),
                status=200,
            )

            # Test job not submitted
            self.job.job_controller_id = None
            self.job.save()

            result = request_file_download_id(self.job, "test_path")

            self.assertEqual(result, (False, "Job not submitted"))

            # Test submitted job, invalid return code
            self.job.job_controller_id = 4321
            self.job.save()

            result = request_file_download_id(self.job, "test_path")

            self.assertEqual(result, (False, "Error getting job file download url"))

            # Test submitted job, successful return
            self.job.job_controller_id = 4321
            self.job.save()

            result = request_file_download_id(self.job, "test_path")

            self.assertEqual(result, (True, return_result))
        finally:
            logging.disable(logging.NOTSET)

    def test_request_file_download_ids(self):
        try:
            logging.disable(logging.CRITICAL)

            # Set up responses before any call to request
            # See https://github.com/getsentry/responses/pull/375
            self.responses.add(responses.POST, f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/", status=400)

            return_result = ["val1", "val2", "val3"]
            self.responses.add(
                responses.POST,
                f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/",
                body=json.dumps({"fileIds": return_result}),
                status=200,
            )

            # Test job not submitted
            self.job.job_controller_id = None
            self.job.save()

            result = request_file_download_ids(self.job, "test_path")

            self.assertEqual(result, (False, "Job not submitted"))

            # Test submitted job, invalid return code
            self.job.job_controller_id = 4321
            self.job.save()

            result = request_file_download_ids(self.job, "test_path")

            self.assertEqual(result, (False, "Error getting job file download url"))

            # Test submitted job, successful return
            self.job.job_controller_id = 4321
            self.job.save()

            result = request_file_download_ids(self.job, "test_path")

            self.assertEqual(result, (True, return_result))
        finally:
            logging.disable(logging.NOTSET)
