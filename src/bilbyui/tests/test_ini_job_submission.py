import json
from unittest.mock import patch

import responses
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test.utils import override_settings

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import compare_ini_kvs, create_test_ini_string, silence_errors
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


class TestIniJobSubmission(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user, is_ligo=True)

        self.mutation = """
            mutation NewIniJobMutation($input: BilbyJobFromIniStringMutationInput!) {
              newBilbyJobFromIniString(input: $input) {
                result {
                  jobId
                }
              }
            }
        """

        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

    @patch("bilbyui.models.submit_job")
    def test_ini_job_submission(self, mock_api_call):
        self.client.authenticate(self.user, is_ligo=True)

        mock_api_call.return_value = {"jobId": 4321}
        test_name = "Test_Name"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string({"label": test_name, "detectors": "['H1']"})

        test_input = {
            "input": {
                "params": {
                    "details": {"name": test_name, "description": test_description, "private": test_private},
                    "iniString": {"iniString": test_ini_string},
                }
            }
        }

        response = self.client.execute(self.mutation, test_input)

        expected = {"newBilbyJobFromIniString": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjE="}}}

        self.assertDictEqual(expected, response.data, "create bilbyJob mutation returned unexpected data.")

        # And should create all k/v's with default values
        job = BilbyJob.objects.all().last()
        compare_ini_kvs(self, job, test_ini_string)

        self.assertEqual(job.name, test_name)
        self.assertEqual(job.description, test_description)
        self.assertEqual(job.private, test_private)

        # Check that ini labels are correctly set to the job name passed to the job details
        test_name = "Test_Name1"
        test_ini_string = create_test_ini_string({"label": "Not the real job name", "detectors": "['H1']"})

        test_input = {
            "input": {
                "params": {
                    "details": {"name": test_name, "description": test_description, "private": test_private},
                    "iniString": {"iniString": test_ini_string},
                }
            }
        }

        response = self.client.execute(self.mutation, test_input)

        expected = {"newBilbyJobFromIniString": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjI="}}}

        self.assertDictEqual(expected, response.data, "create bilbyJob mutation returned unexpected data.")

        # And should create all k/v's with default values
        job = BilbyJob.objects.all().first()
        compare_ini_kvs(self, job, job.ini_string)

        self.assertEqual(job.name, test_name)
        self.assertEqual(job.description, test_description)
        self.assertEqual(job.private, test_private)

    @silence_errors
    @override_settings(CLUSTERS=["default", "another"])
    @override_settings(ALLOW_HTTP_LEAKS=True)
    def test_cluster_submission(self):
        self.client.authenticate(self.user, is_ligo=True)

        return_result = {"jobId": 1122}

        self.responses.add(
            responses.POST,
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/",
            body=json.dumps(return_result),
            status=200,
        )

        test_name = "Test_Name"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string({"label": test_name, "detectors": "['H1']"})

        test_input = {
            "input": {
                "params": {
                    "details": {"name": test_name, "description": test_description, "private": test_private},
                    "iniString": {"iniString": test_ini_string},
                }
            }
        }

        # First test no cluster - this should default to 'default'
        response = self.client.execute(self.mutation, test_input)

        expected = {"newBilbyJobFromIniString": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjE="}}}

        self.assertDictEqual(expected, response.data, "create bilbyJob mutation returned unexpected data.")

        # Check the job controller id was set as expected
        job = BilbyJob.objects.all().last()
        self.assertEqual(job.job_controller_id, 1122)

        # Check that the correct cluster was used in the request
        r = json.loads(self.responses.calls[0].request.body)
        self.assertEqual(r["cluster"], "default")

        job.delete()

        # Next test default cluster uses the default cluster
        test_input["input"]["params"]["details"]["cluster"] = "default"
        response = self.client.execute(self.mutation, test_input)

        expected = {"newBilbyJobFromIniString": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjI="}}}

        self.assertDictEqual(expected, response.data, "create bilbyJob mutation returned unexpected data.")

        # Check that the correct cluster was used in the request
        r = json.loads(self.responses.calls[1].request.body)
        self.assertEqual(r["cluster"], "default")

        BilbyJob.objects.all().last().delete()

        # Next test "another" cluster
        test_input["input"]["params"]["details"]["cluster"] = "another"
        response = self.client.execute(self.mutation, test_input)

        expected = {"newBilbyJobFromIniString": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjM="}}}

        self.assertDictEqual(expected, response.data, "create bilbyJob mutation returned unexpected data.")

        # Check that the correct cluster was used in the request
        r = json.loads(self.responses.calls[2].request.body)
        self.assertEqual(r["cluster"], "another")

        BilbyJob.objects.all().last().delete()

        # Finally test invalid clusters are rejected cluster
        test_input["input"]["params"]["details"]["cluster"] = "not_real"
        response = self.client.execute(self.mutation, test_input)

        self.assertEqual(
            response.errors[0].message, "Error submitting job, cluster 'not_real' is not one of [default another]"
        )


class TestIniJobSubmissionNameValidation(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)

        self.mutation = """
            mutation NewIniJobMutation($input: BilbyJobFromIniStringMutationInput!) {
              newBilbyJobFromIniString(input: $input) {
                result {
                  jobId
                }
              }
            }
        """

    @silence_errors
    def test_invalid_job_name_symbols(self):
        test_name = "Test_Name$"

        test_ini_string = create_test_ini_string({"label": test_name, "detectors": "['H1']"})

        test_input = {
            "input": {
                "params": {
                    "details": {"name": test_name, "description": "a description", "private": True},
                    "iniString": {"iniString": test_ini_string},
                }
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertDictEqual(
            {"newBilbyJobFromIniString": None}, response.data, "create bilbyJob mutation returned unexpected data."
        )

        self.assertEqual(response.errors[0].message, "Job name must not contain any spaces or special characters.")

    @silence_errors
    def test_invalid_job_name_too_long(self):
        test_name = "a" * 50

        test_ini_string = create_test_ini_string({"label": test_name, "detectors": "['H1']"})

        test_input = {
            "input": {
                "params": {
                    "details": {"name": test_name, "description": "a description", "private": True},
                    "iniString": {"iniString": test_ini_string},
                }
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertDictEqual(
            {"newBilbyJobFromIniString": None}, response.data, "create bilbyJob mutation returned unexpected data."
        )

        self.assertEqual(response.errors[0].message, "Job name must be less than 30 characters long.")

    @silence_errors
    def test_invalid_job_name_too_short(self):
        test_name = "a"

        test_ini_string = create_test_ini_string({"label": test_name, "detectors": "['H1']"})

        test_input = {
            "input": {
                "params": {
                    "details": {"name": test_name, "description": "a description", "private": True},
                    "iniString": {"iniString": test_ini_string},
                }
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertDictEqual(
            {"newBilbyJobFromIniString": None}, response.data, "create bilbyJob mutation returned unexpected data."
        )

        self.assertEqual(response.errors[0].message, "Job name must be at least 5 characters long.")
