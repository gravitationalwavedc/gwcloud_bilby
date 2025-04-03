from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import override_settings

from graphql_relay.node.node import from_global_id

from bilbyui.models import BilbyJob, ExternalBilbyJob
from bilbyui.tests.test_utils import create_test_ini_string, silence_errors
from bilbyui.tests.testcases import BilbyTestCase
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS

User = get_user_model()

MOCK_EMBARGO_START_TIME = 1128678900.4


class TestEmbargoJobUpload(BilbyTestCase):
    def setUp(self):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])

        self.mutation_string = """
            mutation ExternalJobUploadMutation($input: UploadExternalBilbyJobMutationInput!) {
              uploadExternalBilbyJob(input: $input) {
                result {
                  jobId
                }
              }
            }
        """

        self.expected_none = {"uploadExternalBilbyJob": None}

    def upload_job(self, trigger_time, n_simulation):
        test_name = "myjob"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            config_dict={
                "label": test_name,
                "trigger-time": trigger_time,
                "n-simulation": n_simulation,
            },
            complete=True,
        )

        test_input = {
            "details": {
                "name": test_name,
                "description": test_description,
                "private": test_private,
            },
            "iniFile": test_ini_string,
            "resultUrl": "https://www.example.com/",
        }

        return self.query(self.mutation_string, input_data=test_input)

    @silence_errors
    @override_settings(
        JOB_UPLOAD_DIR=TemporaryDirectory().name,
        EMBARGO_START_TIME=MOCK_EMBARGO_START_TIME,
    )
    def test_non_ligo_user_embargo(self):
        self.authenticate()

        for trigger_time, n_simulation in [
            (MOCK_EMBARGO_START_TIME + 1, 1),
            (MOCK_EMBARGO_START_TIME - 1, 0),
            (MOCK_EMBARGO_START_TIME - 1, 1),
            ("GW151226", 1),
            ("GW150914", 0),
            ("GW150914", 1),
        ]:
            response = self.upload_job(trigger_time, n_simulation)

            self.assertTrue("jobId" in response.data["uploadExternalBilbyJob"]["result"])

            _, job_id = from_global_id(response.data["uploadExternalBilbyJob"]["result"]["jobId"])

            self.assertEqual(BilbyJob.objects.count(), 1)
            self.assertEqual(ExternalBilbyJob.objects.count(), 1)

            # Check job_id maps to correct job
            job = BilbyJob.objects.get(pk=job_id)
            job.delete()

        for trigger_time, n_simulation in [
            (MOCK_EMBARGO_START_TIME + 1, 0),
            ("GW151226", 0),
        ]:
            response = self.upload_job(trigger_time, n_simulation)
            self.assertDictEqual(
                self.expected_none,
                response.data,
                "create bilbyJob mutation returned unexpected data.",
            )

            self.assertResponseHasErrors(response, "mutation should have returned errors due to embargo")

            # Check that no job was created
            self.assertFalse(BilbyJob.objects.all().exists())
            self.assertFalse(ExternalBilbyJob.objects.all().exists())

    @silence_errors
    @override_settings(
        JOB_UPLOAD_DIR=TemporaryDirectory().name,
        EMBARGO_START_TIME=MOCK_EMBARGO_START_TIME,
    )
    def test_ligo_user_embargo(self):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])

        for trigger_time, n_simulation in [
            (MOCK_EMBARGO_START_TIME + 1, 0),
            (MOCK_EMBARGO_START_TIME + 1, 1),
            (MOCK_EMBARGO_START_TIME - 1, 0),
            (MOCK_EMBARGO_START_TIME - 1, 1),
            ("GW151226", 0),
            ("GW151226", 1),
            ("GW150914", 0),
            ("GW150914", 1),
        ]:
            response = self.upload_job(trigger_time, n_simulation)

            self.assertTrue("jobId" in response.data["uploadExternalBilbyJob"]["result"])

            _, job_id = from_global_id(response.data["uploadExternalBilbyJob"]["result"]["jobId"])

            self.assertEqual(BilbyJob.objects.count(), 1)
            self.assertEqual(ExternalBilbyJob.objects.count(), 1)

            # Check job_id maps to correct job
            job = BilbyJob.objects.get(pk=job_id)
            job.delete()
