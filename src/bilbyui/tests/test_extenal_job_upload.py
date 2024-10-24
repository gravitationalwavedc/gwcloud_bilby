from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob, ExternalBilbyJob
from bilbyui.tests.test_utils import create_test_ini_string, compare_ini_kvs, silence_errors
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


class TestExternalJobUpload(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="bill", first_name="bill", last_name="nye")
        self.client.authenticate(self.user, is_ligo=True)

        self.mutation = """
            mutation ExternalJobUploadMutation($input: UploadExternalBilbyJobMutationInput!) {
              uploadExternalBilbyJob(input: $input) {
                result {
                  jobId
                }
              }
            }
        """

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_external_job_upload_unauthorised_user(self):
        # Test user not logged in
        self.client.authenticate(None)

        test_name = "Test Name"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            {
                "label": test_name,
            }
        )

        test_input = {
            "input": {
                "details": {"name": test_name, "description": test_description, "private": test_private},
                "iniFile": test_ini_string,
                "resultUrl": "https://www.example.com/",
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertEqual(response.errors[0].message, "You do not have permission to perform this action")

        self.assertDictEqual({"uploadExternalBilbyJob": None}, response.data)

        self.assertFalse(BilbyJob.objects.all().exists())
        self.assertFalse(ExternalBilbyJob.objects.all().exists())

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_external_job_upload_success(self):
        test_name = "myjob"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string({"label": test_name}, True)

        test_input = {
            "input": {
                "details": {"name": test_name, "description": test_description, "private": test_private},
                "iniFile": test_ini_string,
                "resultUrl": "https://www.example.com/",
            }
        }

        response = self.client.execute(self.mutation, test_input)

        expected = {"uploadExternalBilbyJob": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjE="}}}

        self.assertDictEqual(expected, response.data)

        # And should create all k/v's with default values
        job = BilbyJob.objects.all().last()
        compare_ini_kvs(self, job, test_ini_string)

        self.assertEqual(job.name, test_name)
        self.assertEqual(job.description, test_description)
        self.assertEqual(job.private, test_private)
        self.assertEqual(job.job_type, BilbyJobType.EXTERNAL)

        # Check that the external job record was created
        self.assertEqual(ExternalBilbyJob.objects.filter(job=job, url=test_input["input"]["resultUrl"]).count(), 1)

    @override_settings(GWOSC_INGEST_USER=1)
    def test_gwosc_ingest_upload(self):
        test_name = "myjob"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string({"label": test_name}, True)

        test_input = {
            "input": {
                "details": {"name": test_name, "description": test_description, "private": test_private},
                "iniFile": test_ini_string,
                "resultUrl": "https://www.example.com/",
            }
        }

        response = self.client.execute(self.mutation, test_input)

        expected = {"uploadExternalBilbyJob": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjE="}}}

        self.assertDictEqual(expected, response.data)

        job = BilbyJob.objects.all().last()

        # It should add the "Official" label if it was added by the GWOSC_INGEST_USER
        self.assertEqual(job.labels.first().name, "Official")

    @override_settings(GWOSC_INGEST_USER=3)
    def test_not_gwosc_ingest_upload(self):
        test_name = "myjob"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string({"label": test_name}, True)

        test_input = {
            "input": {
                "details": {"name": test_name, "description": test_description, "private": test_private},
                "iniFile": test_ini_string,
                "resultUrl": "https://www.example.com/",
            }
        }

        response = self.client.execute(self.mutation, test_input)

        expected = {"uploadExternalBilbyJob": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjE="}}}

        self.assertDictEqual(expected, response.data)

        job = BilbyJob.objects.all().last()

        # It should _not_ add the "Official" label (or any label) if it was _not_ added by the GWOSC_INGEST_USER
        self.assertEqual(job.labels.count(), 0)


class TestExternalJobUploadLigoPermissions(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        test_private = True
        self.mutation = """
            mutation ExternalJobUploadMutation($input: UploadExternalBilbyJobMutationInput!) {
              uploadExternalBilbyJob(input: $input) {
                result {
                  jobId
                }
              }
            }
        """

        self.params = {
            "input": {
                "details": {"name": "test_name", "description": "test_description", "private": test_private},
                "iniFile": None,
                "resultUrl": "https://www.example.com/",
            }
        }

        self.expected_one = {"uploadExternalBilbyJob": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjE="}}}

        self.expected_none = {"uploadExternalBilbyJob": None}

    @silence_errors
    def test_non_ligo_user_with_gwosc(self):
        # Test checks that a LIGO user does not create a LIGO job if the data is real and channels are GWOSC
        self.client.authenticate(self.user, is_ligo=False)

        ini_string = create_test_ini_string(
            config_dict={"label": "testjob", "n-simulation": 0, "channel-dict": {"H1": "GWOSC", "L1": "GWOSC"}},
            complete=True,
        )

        self.params["input"]["iniFile"] = ini_string
        response = self.client.execute(self.mutation, self.params)

        self.assertDictEqual(self.expected_one, response.data, "create bilbyJob mutation returned unexpected data.")

        # Check that the job is marked as not proprietary
        self.assertFalse(BilbyJob.objects.all().last().is_ligo_job)

    @silence_errors
    def test_ligo_user_with_gwosc(self):
        # This test checks that a non LIGO user can still create non LIGO jobs
        self.client.authenticate(self.user, is_ligo=True)

        ini_string = create_test_ini_string(
            config_dict={"label": "testjob", "n-simulation": 0, "channel-dict": {"H1": "GWOSC", "L1": "GWOSC"}},
            complete=True,
        )

        self.params["input"]["iniFile"] = ini_string
        response = self.client.execute(self.mutation, self.params)

        self.assertDictEqual(self.expected_one, response.data, "create bilbyJob mutation returned unexpected data.")

        # Check that the job is marked as not proprietary
        self.assertFalse(BilbyJob.objects.all().last().is_ligo_job)

    @silence_errors
    def test_ligo_user_with_non_gwosc(self):
        # Test that LIGO users can make jobs with proprietary channels
        # Now if the channels are proprietary, the ligo user should be able to create jobs
        self.client.authenticate(self.user, is_ligo=True)

        for channel_dict in [
            {"H1": "GDS-CALIB_STRAIN", "L1": "GWOSC", "V1": "GWOSC"},
            {"H1": "GWOSC", "L1": "GDS-CALIB_STRAIN", "V1": "GWOSC"},
            {"H1": "GWOSC", "L1": "GWOSC", "V1": "Hrec_hoft_16384Hz"},
        ]:
            ini_string = create_test_ini_string(
                {"label": "testjob", "n-simulation": 0, "channel-dict": channel_dict}, complete=True
            )

            self.params["input"]["iniFile"] = ini_string
            response = self.client.execute(self.mutation, self.params)

            self.assertTrue("jobId" in response.data["uploadExternalBilbyJob"]["result"])

            # Check that the job is marked as proprietary
            job = BilbyJob.objects.all().last()
            self.assertFalse(job.is_ligo_job)
            job.delete()
