from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings

from graphql_relay.node.node import from_global_id

from bilbyui.models import BilbyJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.tests.test_utils import create_test_ini_string, silence_errors

User = get_user_model()

MOCK_EMBARGO_START_TIME = 1128678900.4


class TestBilbyEmbargoPermissions(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

        self.params = {
            "input": {
                "params": {
                    "details": {
                        "name": "test_job_for_GW12345",
                        "description": "Test description 1234",
                        "private": True,
                    },
                    # "calibration": None,
                    "data": {
                        "dataChoice": "real",
                        "triggerTime": "1126259462.391",
                        "channels": {"hanfordChannel": "GWOSC", "livingstonChannel": "GWOSC", "virgoChannel": "GWOSC"},
                    },
                    "detector": {
                        "hanford": True,
                        "hanfordMinimumFrequency": "20",
                        "hanfordMaximumFrequency": "1024",
                        "livingston": True,
                        "livingstonMinimumFrequency": "20",
                        "livingstonMaximumFrequency": "1024",
                        "virgo": False,
                        "virgoMinimumFrequency": "20",
                        "virgoMaximumFrequency": "1024",
                        "duration": "4",
                        "samplingFrequency": "512",
                    },
                    # "injection": {},
                    # "likelihood": {},
                    "prior": {"priorDefault": "4s"},
                    # "postProcessing": {},
                    "sampler": {
                        "nlive": "1000.0",
                        "nact": "10.0",
                        "maxmcmc": "5000.0",
                        "walks": "1000.0",
                        "dlogz": "0.1",
                        "cpus": "1",
                        "samplerChoice": "dynesty",
                    },
                    "waveform": {"model": None},
                }
            }
        }

        self.query = """
            mutation NewJobMutation($input: BilbyJobMutationInput!) {
                newBilbyJob(input: $input) {
                    result {
                        jobId
                    }
                }
            }
        """

        self.expected_none = {"newBilbyJob": None}

        patcher = patch("bilbyui.models.submit_job")
        self.addCleanup(patcher.stop)
        self.mock_api_call = patcher.start()
        self.mock_api_call.return_value = {"jobId": 4321}

    def set_trigger_time_and_data_choice(self, trigger_time, data_choice):
        self.params["input"]["params"]["data"]["triggerTime"] = trigger_time
        self.params["input"]["params"]["data"]["dataChoice"] = data_choice

    @silence_errors
    @override_settings(EMBARGO_START_TIME=MOCK_EMBARGO_START_TIME)
    def test_non_ligo_user_embargo(self):
        self.client.authenticate(self.user, is_ligo=False)

        for trigger_time, data_choice in [
            (str(MOCK_EMBARGO_START_TIME + 1), "simulated"),
            (str(MOCK_EMBARGO_START_TIME - 1), "real"),
            (str(MOCK_EMBARGO_START_TIME - 1), "simulated"),
        ]:
            self.set_trigger_time_and_data_choice(trigger_time, data_choice)
            response = self.client.execute(self.query, self.params)

            self.assertResponseHasNoErrors(response, "mutation should not have returned errors due to embargo")
            self.assertEqual(BilbyJob.objects.count(), 1)

            self.assertTrue("jobId" in response.data["newBilbyJob"]["result"])

            _, job_id = from_global_id(response.data["newBilbyJob"]["result"]["jobId"])

            # Check job_id maps to correct job
            job = BilbyJob.objects.get(pk=job_id)
            job.delete()

        self.set_trigger_time_and_data_choice(str(MOCK_EMBARGO_START_TIME + 1), "real")
        response = self.client.execute(self.query, self.params)

        self.assertDictEqual(self.expected_none, response.data, "create bilbyJob mutation returned unexpected data.")

        self.assertResponseHasErrors(response, "mutation should have returned errors due to embargo")

        # Check that no job was created
        self.assertFalse(BilbyJob.objects.all().exists())

    @silence_errors
    @override_settings(EMBARGO_START_TIME=MOCK_EMBARGO_START_TIME)
    def test_ligo_user_embargo(self):
        self.client.authenticate(self.user, is_ligo=True)

        for trigger_time, data_choice in [
            (str(MOCK_EMBARGO_START_TIME + 1), "real"),
            (str(MOCK_EMBARGO_START_TIME + 1), "simulated"),
            (str(MOCK_EMBARGO_START_TIME - 1), "real"),
            (str(MOCK_EMBARGO_START_TIME - 1), "simulated"),
        ]:
            self.set_trigger_time_and_data_choice(trigger_time, data_choice)
            response = self.client.execute(self.query, self.params)

            self.assertResponseHasNoErrors(response, "mutation should not have returned errors due to embargo")
            self.assertEqual(BilbyJob.objects.count(), 1)

            self.assertTrue("jobId" in response.data["newBilbyJob"]["result"])

            _, job_id = from_global_id(response.data["newBilbyJob"]["result"]["jobId"])

            # Check job_id maps to correct job
            job = BilbyJob.objects.get(pk=job_id)
            job.delete()


class TestIniBilbyEmbargoPermissions(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

        self.params = {
            "input": {
                "params": {
                    "details": {
                        "name": "test_job_for_GW12345",
                        "description": "Test description 1234",
                        "private": True,
                    },
                    "iniString": {"iniString": None},
                }
            }
        }

        self.query = """
            mutation NewJobMutation($input: BilbyJobFromIniStringMutationInput!) {
                newBilbyJobFromIniString(input: $input) {
                    result {
                        jobId
                    }
                }
            }
        """

        self.expected_none = {"newBilbyJobFromIniString": None}

        patcher = patch("bilbyui.models.submit_job")
        self.addCleanup(patcher.stop)
        self.mock_api_call = patcher.start()
        self.mock_api_call.return_value = {"jobId": 4321}

    @silence_errors
    @override_settings(EMBARGO_START_TIME=MOCK_EMBARGO_START_TIME)
    def test_non_ligo_user_embargo(self):
        # Test checks that a LIGO user does not create a LIGO job if the data is real and channels are GWOSC
        self.client.authenticate(self.user, is_ligo=False)

        for trigger_time, n_simulation in [
            (MOCK_EMBARGO_START_TIME + 1, 1),
            (MOCK_EMBARGO_START_TIME - 1, 0),
            (MOCK_EMBARGO_START_TIME - 1, 1),
            ('GW151226', 1),
            ('GW150914', 0),
            ('GW150914', 1),
        ]:
            ini_string = create_test_ini_string(
                config_dict={"trigger-time": trigger_time, "n-simulation": n_simulation}, complete=True
            )
            self.params["input"]["params"]["iniString"]["iniString"] = ini_string

            response = self.client.execute(self.query, self.params)

            self.assertResponseHasNoErrors(response, "mutation should not have returned errors due to embargo")
            self.assertEqual(BilbyJob.objects.count(), 1)

            self.assertTrue("jobId" in response.data["newBilbyJobFromIniString"]["result"])

            _, job_id = from_global_id(response.data["newBilbyJobFromIniString"]["result"]["jobId"])

            # Check job_id maps to correct job
            job = BilbyJob.objects.get(pk=job_id)
            job.delete()

        for trigger_time, n_simulation in [
            (MOCK_EMBARGO_START_TIME + 1, 0),
            ('GW151226', 0),
        ]:
            ini_string = create_test_ini_string(
                config_dict={"trigger-time": trigger_time, "n-simulation": n_simulation}, complete=True
            )
            self.params["input"]["params"]["iniString"]["iniString"] = ini_string
            response = self.client.execute(self.query, self.params)

            self.assertDictEqual(
                self.expected_none,
                response.data,
                "create bilbyJob mutation returned unexpected data."
            )

            self.assertResponseHasErrors(response, "mutation should have returned errors due to embargo")

            # Check that no job was created
            self.assertFalse(BilbyJob.objects.all().exists())

    @silence_errors
    @override_settings(EMBARGO_START_TIME=MOCK_EMBARGO_START_TIME)
    def test_ligo_user_embargo(self):
        # Test checks that a LIGO user does not create a LIGO job if the data is real and channels are GWOSC
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
            ini_string = create_test_ini_string(
                config_dict={"trigger-time": trigger_time, "n-simulation": n_simulation}, complete=True
            )
            self.params["input"]["params"]["iniString"]["iniString"] = ini_string

            response = self.client.execute(self.query, self.params)

            self.assertResponseHasNoErrors(response, "mutation should not have returned errors due to embargo")
            self.assertEqual(BilbyJob.objects.count(), 1)

            self.assertTrue("jobId" in response.data["newBilbyJobFromIniString"]["result"])

            _, job_id = from_global_id(response.data["newBilbyJobFromIniString"]["result"]["jobId"])

            # Check job_id maps to correct job
            job = BilbyJob.objects.get(pk=job_id)
            job.delete()
