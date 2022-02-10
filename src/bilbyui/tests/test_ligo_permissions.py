from unittest.mock import patch

from django.contrib.auth import get_user_model
from graphql_relay.node.node import from_global_id

from bilbyui.models import BilbyJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.tests.test_utils import create_test_ini_string, silence_errors

User = get_user_model()


class TestBilbyLigoPermissions(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

        self.params = {
            "input": {
                "params": {
                    "details": {
                        "name": "test job for GW12345",
                        "description": "Test description 1234",
                        "private": True,
                    },
                    # "calibration": None,
                    "data": {
                        "dataChoice": "real",
                        "triggerTime": "1126259462.391",
                        "channels": {
                            "hanfordChannel": "GWOSC",
                            "livingstonChannel": "GWOSC",
                            "virgoChannel": "GWOSC"
                        }
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
                        "samplingFrequency": "512"
                    },
                    # "injection": {},
                    # "likelihood": {},
                    "prior": {
                        "priorDefault": "4s"
                    },
                    # "postProcessing": {},
                    "sampler": {
                        "nlive": "1000.0",
                        "nact": "10.0",
                        "maxmcmc": "5000.0",
                        "walks": "1000.0",
                        "dlogz": "0.1",
                        "cpus": "1",
                        "samplerChoice": "dynesty"
                    },
                    "waveform": {
                        "model": None
                    }
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

        self.expected_one = {
            'newBilbyJob': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjE='
                }
            }
        }

        self.expected_none = {
            'newBilbyJob': None
        }

        patcher = patch("bilbyui.views.submit_job")
        self.addCleanup(patcher.stop)
        self.mock_api_call = patcher.start()
        self.mock_api_call.return_value = {'jobId': 4321}

    @silence_errors
    def test_non_ligo_user_with_gwosc(self):

        self.client.authenticate(self.user, is_ligo=False)

        response = self.client.execute(self.query, self.params)

        self.assertDictEqual(
            self.expected_one, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # Check that the job is marked as not proprietary
        self.assertFalse(BilbyJob.objects.all().last().is_ligo_job)

    @silence_errors
    def test_ligo_user_with_gwosc(self):
        self.client.authenticate(self.user, is_ligo=True)

        response = self.client.execute(self.query, self.params)

        self.assertDictEqual(
            self.expected_one, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # Check that the job is marked as not proprietary
        self.assertFalse(BilbyJob.objects.all().last().is_ligo_job)

    @silence_errors
    def test_non_ligo_user_with_non_gwosc(self):
        self.client.authenticate(self.user, is_ligo=False)

        for detector, channel in [
            ('hanfordChannel', 'GDS-CALIB_STRAIN'),
            ('livingstonChannel', 'GDS-CALIB_STRAIN'),
            ('virgoChannel', 'Hrec_hoft_16384Hz'),
            # Also check invalid (Non GWOSC channels)
            ('hanfordChannel', 'testchannel1'),
            ('livingstonChannel', 'imnotarealchannel'),
            ('virgoChannel', 'GWOSc'),
        ]:
            self.params['input']['params']['data']['channels'][detector] = channel

            response = self.client.execute(self.query, self.params)

            self.assertDictEqual(
                self.expected_none, response.data, "create bilbyJob mutation returned unexpected data."
            )

            self.assertEqual(
                response.errors[0].message,
                'Non-LIGO members may only run real jobs on GWOSC channels'
            )

            self.assertFalse(BilbyJob.objects.all().exists())

            self.params['input']['params']['data']['channels'][detector] = "GWOSC"

    @silence_errors
    def test_ligo_user_with_non_gwosc(self):
        # Now if the channels are proprietary, the ligo user should be able to create jobs
        self.client.authenticate(self.user, is_ligo=True)

        for detector, channel in [
            ('hanfordChannel', 'GDS-CALIB_STRAIN'),
            ('livingstonChannel', 'GDS-CALIB_STRAIN'),
            ('virgoChannel', 'Hrec_hoft_16384Hz')
        ]:
            self.params['input']['params']['data']['channels'][detector] = channel

            response = self.client.execute(self.query, self.params)

            self.assertTrue('jobId' in response.data['newBilbyJob']['result'])

            _, job_id = from_global_id(response.data['newBilbyJob']['result']['jobId'])

            # Check that the job is marked as proprietary
            job = BilbyJob.objects.all().last()
            self.assertTrue(job.is_ligo_job)
            job.delete()

            self.params['input']['params']['data']['channels'][detector] = "GWOSC"


class TestIniBilbyLigoPermissions(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

        self.params = {
            "input": {
                "params": {
                    "details": {
                        "name": "test job for GW12345",
                        "description": "Test description 1234",
                        "private": True,
                    },
                    "iniString": {
                        "iniString": None
                    }
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

        self.expected_one = {
            'newBilbyJobFromIniString': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjE='
                }
            }
        }

        self.expected_none = {
            'newBilbyJobFromIniString': None
        }

        patcher = patch("bilbyui.views.submit_job")
        self.addCleanup(patcher.stop)
        self.mock_api_call = patcher.start()
        self.mock_api_call.return_value = {'jobId': 4321}

    @silence_errors
    def test_non_ligo_user_with_gwosc(self):
        # Test checks that a LIGO user does not create a LIGO job if the data is real and channels are GWOSC
        self.client.authenticate(self.user, is_ligo=False)

        ini_string = create_test_ini_string(config_dict={
            "n-simulation": 0,
            "channel-dict": {'H1': 'GWOSC', 'L1': 'GWOSC'}
        }, complete=True)

        self.params['input']['params']['iniString']['iniString'] = ini_string

        response = self.client.execute(self.query, self.params)

        self.assertDictEqual(
            self.expected_one, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # Check that the job is marked as not proprietary
        self.assertFalse(BilbyJob.objects.all().last().is_ligo_job)

    @silence_errors
    def test_ligo_user_with_gwosc(self):
        # This test checks that a non LIGO user can still create non LIGO jobs
        self.client.authenticate(self.user, is_ligo=True)

        ini_string = create_test_ini_string(config_dict={
            "n-simulation": 0,
            "channel-dict": {'H1': 'GWOSC', 'L1': 'GWOSC'}
        }, complete=True)

        self.params['input']['params']['iniString']['iniString'] = ini_string

        response = self.client.execute(self.query, self.params)

        self.assertDictEqual(
            self.expected_one, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # Check that the job is marked as not proprietary
        self.assertFalse(BilbyJob.objects.all().last().is_ligo_job)

    @silence_errors
    def test_non_ligo_user_with_non_gwosc(self):
        # Test checks that non-LIGO user cannot create real jobs with non-GWOSC channels, nor with invalid channels
        # Now if the channels are proprietary, the non-ligo user should not be able to create jobs
        self.client.authenticate(self.user, is_ligo=False)

        for channel_dict in [
            {'H1': 'GDS-CALIB_STRAIN', 'L1': 'GWOSC', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'GDS-CALIB_STRAIN', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'GWOSC', 'V1': 'Hrec_hoft_16384Hz'},
            # Also check invalid channels
            {'H1': 'testchannel1', 'L1': 'GWOSC', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'imnotarealchannel', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'GWOSC', 'V1': 'GWOSc'},
        ]:
            ini_string = create_test_ini_string({'n-simulation': 0, 'channel-dict': channel_dict}, True)
            self.params['input']['params']['iniString']['iniString'] = ini_string

            response = self.client.execute(self.query, self.params)

            self.assertDictEqual(
                self.expected_none, response.data, "create bilbyJob mutation returned unexpected data."
            )

            self.assertEqual(
                response.errors[0].message,
                'Non-LIGO members may only run real jobs on GWOSC channels'
            )

            self.assertFalse(BilbyJob.objects.all().exists())

    @silence_errors
    def test_ligo_user_with_non_gwosc(self):
        # Test that LIGO users can make jobs with proprietary channels
        # Now if the channels are proprietary, the ligo user should be able to create jobs
        self.client.authenticate(self.user, is_ligo=True)

        for channel_dict in [
            {'H1': 'GDS-CALIB_STRAIN', 'L1': 'GWOSC', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'GDS-CALIB_STRAIN', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'GWOSC', 'V1': 'Hrec_hoft_16384Hz'},
        ]:
            ini_string = create_test_ini_string({'n-simulation': 0, 'channel-dict': channel_dict}, True)
            self.params['input']['params']['iniString']['iniString'] = ini_string

            response = self.client.execute(self.query, self.params)

            self.assertTrue('jobId' in response.data['newBilbyJobFromIniString']['result'])

            # Check that the job is marked as proprietary
            job = BilbyJob.objects.all().last()
            self.assertTrue(job.is_ligo_job)
            job.delete()
