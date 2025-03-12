import json
from tempfile import TemporaryDirectory

import responses
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import (
    silence_errors,
    create_test_ini_string,
    create_test_upload_data,
)
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.request_file_list import request_file_list

User = get_user_model()


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestRequestFileListNotUploaded(BilbyTestCase):
    def setUp(self):
        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

        self.job = BilbyJob.objects.create(user_id=1234, ini_string="detectors=['H1']")

    @silence_errors
    def test_request_file_list_not_uploaded(self):
        # Set up responses before any call to request
        # See https://github.com/getsentry/responses/pull/375
        self.responses.add(
            responses.PATCH,
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/",
            status=400,
        )

        return_result = [
            {"path": "/a", "isDir": True, "fileSize": 0},
            {"path": "/a/path", "isDir": True, "fileSize": 0},
            {"path": "/a/path/here2.txt", "isDir": False, "fileSize": 12345},
            {"path": "/a/path/here3.txt", "isDir": False, "fileSize": 123456},
            {"path": "/a/path/here4.txt", "isDir": False, "fileSize": 1234567},
        ]
        self.responses.add(
            responses.PATCH,
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/",
            body=json.dumps({"files": return_result}),
            status=200,
        )

        # Test job not submitted
        self.job.job_controller_id = None
        self.job.save()

        result = request_file_list(self.job, ".", True, self.job.user_id)

        self.assertEqual(result, (False, "Job not submitted"))

        # Test submitted job, invalid return code
        self.job.job_controller_id = 4321
        self.job.save()

        result = request_file_list(self.job, ".", True, self.job.user_id)

        self.assertEqual(result, (False, "Error getting job file list"))

        # Test submitted job, successful return
        self.job.job_controller_id = 4321
        self.job.save()

        result = request_file_list(self.job, ".", True, self.job.user_id)

        self.assertEqual(result, (True, return_result))


@override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
class TestRequestFileListUploaded(BilbyTestCase):
    def setUp(self):
        self.authenticate()

        token = self.get_upload_token()

        # Create a new uploaded bilby job
        test_name = "myjob"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            {"label": test_name, "detectors": "['H1']", "outdir": "./"}, True
        )

        test_file = SimpleUploadedFile(
            name="test.tar.gz",
            content=create_test_upload_data(test_ini_string, test_name),
            content_type="application/gzip",
        )

        test_input = {
            "uploadToken": token,
            "details": {"description": test_description, "private": test_private},
            "jobFile": None,
        }

        test_files = {"input.jobFile": test_file}

        self.file_query(
            """
                mutation JobUploadMutation($input: UploadBilbyJobMutationInput!) {
                  uploadBilbyJob(input: $input) {
                    result {
                      jobId
                    }
                  }
                }
            """,
            input_data=test_input,
            files=test_files,
        )

        self.job = BilbyJob.objects.all().last()

    def test_request_file_list_uploaded(self):
        # Test "this file really sits under the working directory"
        result = request_file_list(self.job, "../test/", True, self.job.user_id)
        self.assertEqual(result, (False, "Files do not exist"))

        result = request_file_list(
            self.job, "../../../../../../../../../bin/bash", True, self.job.user_id
        )
        self.assertEqual(result, (False, "Files do not exist"))

        result = request_file_list(self.job, "../data/", True, self.job.user_id)
        self.assertEqual(result, (False, "Files do not exist"))

        result = request_file_list(
            self.job, "./data/../../test/", True, self.job.user_id
        )
        self.assertEqual(result, (False, "Files do not exist"))

        result = request_file_list(self.job, "./data", True, self.job.user_id)
        self.assertEqual(result[0], True)

        result = request_file_list(self.job, "./result/../data", True, self.job.user_id)
        self.assertEqual(result[0], True)

        # Test "the path exists"
        result = request_file_list(
            self.job, "./data_not_exist/", True, self.job.user_id
        )
        self.assertEqual(result, (False, "Files do not exist"))

        result = request_file_list(self.job, "data_not_exist", True, self.job.user_id)
        self.assertEqual(result, (False, "Files do not exist"))

        result = request_file_list(self.job, "./data/not_exist", True, self.job.user_id)
        self.assertEqual(result, (False, "Files do not exist"))

        result = request_file_list(self.job, "data", True, self.job.user_id)
        self.assertEqual(result[0], True)

        result = request_file_list(self.job, "./result", True, self.job.user_id)
        self.assertEqual(result[0], True)

        # Test "the path is a directory"
        result = request_file_list(
            self.job, "myjob_config_complete.ini", True, self.job.user_id
        )
        self.assertEqual(result, (False, "Files do not exist"))

        result = request_file_list(
            self.job,
            "data/H1_myjob_generation_frequency_domain_data.png",
            True,
            self.job.user_id,
        )
        self.assertEqual(result, (False, "Files do not exist"))

        result = request_file_list(self.job, "results_page", True, self.job.user_id)
        self.assertEqual(result[0], True)

        # Test recursive file list
        result = request_file_list(self.job, "", True, self.job.user_id)
        self.assertTrue(
            len(list(filter(lambda x: "overview.html" in x["path"], result[1])))
        )

        # Test non-recursive file list
        result = request_file_list(self.job, "", False, self.job.user_id)
        self.assertFalse(
            len(list(filter(lambda x: "overview.html" in x["path"], result[1])))
        )

        result = request_file_list(self.job, "results_page", True, self.job.user_id)
        self.assertTrue(
            len(list(filter(lambda x: "overview.html" in x["path"], result[1])))
        )
