from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from graphql_relay.node.node import from_global_id

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string, silence_errors, create_test_upload_data
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()

MOCK_EMBARGO_START_TIME = 1128678900.4


def get_upload_token(client):
    generate_job_upload_token_mutation = """
        query GenerateBilbyJobUploadToken {
          generateBilbyJobUploadToken {
            token
          }
        }
    """

    response = client.execute(generate_job_upload_token_mutation)

    return response


class TestEmbargoJobUpload(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="bill", first_name="bill", last_name="nye")
        self.client.authenticate(self.user, is_ligo=True)

        self.mutation = """
            mutation JobUploadMutation($input: UploadBilbyJobMutationInput!) {
              uploadBilbyJob(input: $input) {
                result {
                  jobId
                }
              }
            }
        """

        self.expected_none = {"uploadBilbyJob": None}

    def upload_job(self, trigger_time, n_simulation):
        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

        test_name = "myjob"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            config_dict={
                "label": test_name,
                "trigger-time": trigger_time,
                "n-simulation": n_simulation,
                "outdir": "./"
            },
            complete=True
        )

        test_file = SimpleUploadedFile(
            name="test.tar.gz",
            content=create_test_upload_data(test_ini_string, test_name),
            content_type="application/gzip",
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {"description": test_description, "private": test_private},
                "jobFile": test_file,
            }
        }

        return self.client.execute(self.mutation, test_input)

    @silence_errors
    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name, EMBARGO_START_TIME=MOCK_EMBARGO_START_TIME)
    def test_non_ligo_user_embargo(self):
        self.client.authenticate(self.user, is_ligo=False)

        for trigger_time, n_simulation in [
            (MOCK_EMBARGO_START_TIME + 1, 1),
            (MOCK_EMBARGO_START_TIME - 1, 0),
            (MOCK_EMBARGO_START_TIME - 1, 1),
            ('GW151226', 1),
            ('GW150914', 0),
            ('GW150914', 1),
        ]:
            response = self.upload_job(trigger_time, n_simulation)

            self.assertTrue("jobId" in response.data["uploadBilbyJob"]["result"])

            _, job_id = from_global_id(response.data["uploadBilbyJob"]["result"]["jobId"])

            self.assertEqual(BilbyJob.objects.count(), 1)

            # Check job_id maps to correct job
            job = BilbyJob.objects.get(pk=job_id)
            job.delete()

        for trigger_time, n_simulation in [
            (MOCK_EMBARGO_START_TIME + 1, 0),
            ('GW151226', 0),
        ]:
            response = self.upload_job(trigger_time, n_simulation)

            self.assertDictEqual(
                self.expected_none,
                response.data,
                "create bilbyJob mutation returned unexpected data."
            )

            self.assertResponseHasErrors(response, "mutation should have returned errors due to embargo")

            # Check that no job was created
            self.assertFalse(BilbyJob.objects.all().exists())

    @silence_errors
    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name, EMBARGO_START_TIME=MOCK_EMBARGO_START_TIME)
    def test_ligo_user_embargo(self):
        self.client.authenticate(self.user, is_ligo=True)

        for trigger_time, n_simulation in [
            (MOCK_EMBARGO_START_TIME + 1, 0),
            (MOCK_EMBARGO_START_TIME + 1, 1),
            (MOCK_EMBARGO_START_TIME - 1, 0),
            (MOCK_EMBARGO_START_TIME - 1, 1),
            ('GW151226', 0),
            ('GW151226', 1),
            ('GW150914', 0),
            ('GW150914', 1),
        ]:
            response = self.upload_job(trigger_time, n_simulation)

            self.assertTrue("jobId" in response.data["uploadBilbyJob"]["result"])

            _, job_id = from_global_id(response.data["uploadBilbyJob"]["result"]["jobId"])

            self.assertEqual(BilbyJob.objects.count(), 1)

            # Check job_id maps to correct job
            job = BilbyJob.objects.get(pk=job_id)
            job.delete()
