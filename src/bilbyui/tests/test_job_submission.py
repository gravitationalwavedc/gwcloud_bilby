import json
from ast import literal_eval
from unittest.mock import patch

import responses
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test.utils import override_settings

from bilbyui.models import IniKeyValue, BilbyJob
from bilbyui.tests.test_utils import compare_ini_kvs, silence_errors
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


class TestJobSubmission(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)

        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

    @patch("bilbyui.views.submit_job")
    def test_simulated_job(self, mock_api_call):
        mock_api_call.return_value = {'jobId': 4321}

        params = {
            "input": {
                "params": {
                    "details": {
                        "name": "test job for GW12345",
                        "description": "Test description 1234",
                        "private": True,
                    },
                    # "calibration": None,
                    "data": {
                        "dataChoice": "simulated",
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

        response = self.client.execute(
            """
            mutation NewJobMutation($input: BilbyJobMutationInput!) {
              newBilbyJob(input: $input) {
                result {
                  jobId
                }
              }
            }
            """,
            params
        )

        expected = {
            'newBilbyJob': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjE='
                }
            }
        }

        self.assertDictEqual(
            expected, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # And should create all k/v's with default values
        job = BilbyJob.objects.all().last()
        compare_ini_kvs(self, job, job.ini_string)

        _params = params["input"]["params"]

        self.assertEqual(job.name, _params['details']['name'])
        self.assertEqual(job.description, _params['details']['description'])
        self.assertEqual(job.private, _params['details']['private'])

        # Double check that the k/v's were correctly created
        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="trigger_time").value,
            json.dumps(_params['data']['triggerTime'])
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="gaussian_noise").value,
            json.dumps(True)
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="n_simulation").value,
            json.dumps(1)
        )

        self.assertDictEqual(
            literal_eval(json.loads(IniKeyValue.objects.get(job=job, key="channel_dict").value)),
            {'H1': 'GWOSC', 'L1': 'GWOSC'}
        )

        self.assertEqual(
            sorted(json.loads(IniKeyValue.objects.get(job=job, key="detectors").value)),
            sorted(["'H1'", "'L1'"])
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="duration").value,
            json.dumps(float(_params['detector']['duration']))
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="sampling_frequency").value,
            json.dumps(float(_params['detector']['samplingFrequency']))
        )

        self.assertDictEqual(
            literal_eval(json.loads(IniKeyValue.objects.get(job=job, key="maximum_frequency").value)),
            {'H1': '1024', 'L1': '1024'}
        )

        self.assertDictEqual(
            literal_eval(json.loads(IniKeyValue.objects.get(job=job, key="minimum_frequency").value)),
            {'H1': '20', 'L1': '20'}
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="label").value,
            json.dumps(_params['details']['name'])
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="prior_file").value,
            json.dumps(_params['prior']['priorDefault'])
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="sampler").value,
            json.dumps(_params['sampler']['samplerChoice'])
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="frequency_domain_source_model").value,
            json.dumps("lal_binary_black_hole")
        )

    @patch("bilbyui.views.submit_job")
    def test_real_job(self, mock_api_call):
        mock_api_call.return_value = {'jobId': 4321}

        params = {
            "input": {
                "params": {
                    "details": {
                        "name": "real test job for GW12345",
                        "description": "real Test description 1234",
                        "private": True,
                    },
                    # "calibration": None,
                    "data": {
                        "dataChoice": "real",
                        "triggerTime": "1126259562.391",
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

        response = self.client.execute(
            """
            mutation NewJobMutation($input: BilbyJobMutationInput!) {
              newBilbyJob(input: $input) {
                result {
                  jobId
                }
              }
            }
            """,
            params
        )

        expected = {
            'newBilbyJob': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjE='
                }
            }
        }

        self.assertDictEqual(
            expected, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # And should create all k/v's with default values
        job = BilbyJob.objects.all().last()
        compare_ini_kvs(self, job, job.ini_string)

        _params = params["input"]["params"]

        self.assertEqual(job.name, _params['details']['name'])
        self.assertEqual(job.description, _params['details']['description'])
        self.assertEqual(job.private, _params['details']['private'])

        # Double check that the k/v's were correctly created
        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="trigger_time").value,
            json.dumps(_params['data']['triggerTime'])
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="gaussian_noise").value,
            json.dumps(False)
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="n_simulation").value,
            json.dumps(0)
        )

        self.assertDictEqual(
            literal_eval(json.loads(IniKeyValue.objects.get(job=job, key="channel_dict").value)),
            {'H1': 'GWOSC', 'L1': 'GWOSC'}
        )

        self.assertEqual(
            sorted(json.loads(IniKeyValue.objects.get(job=job, key="detectors").value)),
            sorted(["'H1'", "'L1'"])
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="duration").value,
            json.dumps(float(_params['detector']['duration']))
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="sampling_frequency").value,
            json.dumps(float(_params['detector']['samplingFrequency']))
        )

        self.assertDictEqual(
            literal_eval(json.loads(IniKeyValue.objects.get(job=job, key="maximum_frequency").value)),
            {'H1': '1024', 'L1': '1024'}
        )

        self.assertDictEqual(
            literal_eval(json.loads(IniKeyValue.objects.get(job=job, key="minimum_frequency").value)),
            {'H1': '20', 'L1': '20'}
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="label").value,
            json.dumps(_params['details']['name'])
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="prior_file").value,
            json.dumps(_params['prior']['priorDefault'])
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="sampler").value,
            json.dumps(_params['sampler']['samplerChoice'])
        )

        self.assertEqual(
            IniKeyValue.objects.get(job=job, key="frequency_domain_source_model").value,
            json.dumps("lal_binary_black_hole")
        )

    @silence_errors
    @override_settings(CLUSTERS=['default', 'another'])
    def test_cluster_submission(self):
        return_result = {'jobId': 1122}

        self.responses.add(
            responses.POST,
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/",
            body=json.dumps(return_result),
            status=200
        )

        params = {
            "input": {
                "params": {
                    "details": {
                        "name": "test job for GW12345",
                        "description": "Test description 1122",
                        "private": True,
                    },
                    # "calibration": None,
                    "data": {
                        "dataChoice": "simulated",
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

        mut = """
            mutation NewJobMutation($input: BilbyJobMutationInput!) {
              newBilbyJob(input: $input) {
                result {
                  jobId
                }
              }
            }
            """

        # First test no cluster - this should default to 'default'
        response = self.client.execute(mut, params)

        expected = {
            'newBilbyJob': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjE='
                }
            }
        }

        self.assertDictEqual(
            expected, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # Check the job controller id was set as expected
        job = BilbyJob.objects.all().last()
        self.assertEqual(job.job_controller_id, 1122)

        # Check that the correct cluster was used in the request
        r = json.loads(self.responses.calls[0].request.body)
        self.assertEqual(r['cluster'], 'default')

        job.delete()

        # Next test default cluster uses the default cluster
        params['input']['params']['details']['cluster'] = 'default'
        response = self.client.execute(mut, params)

        expected = {
            'newBilbyJob': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjI='
                }
            }
        }

        self.assertDictEqual(
            expected, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # Check that the correct cluster was used in the request
        r = json.loads(self.responses.calls[1].request.body)
        self.assertEqual(r['cluster'], 'default')

        BilbyJob.objects.all().last().delete()

        # Next test "another" cluster
        params['input']['params']['details']['cluster'] = 'another'
        response = self.client.execute(mut, params)

        expected = {
            'newBilbyJob': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjM='
                }
            }
        }

        self.assertDictEqual(
            expected, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # Check that the correct cluster was used in the request
        r = json.loads(self.responses.calls[2].request.body)
        self.assertEqual(r['cluster'], 'another')

        BilbyJob.objects.all().last().delete()

        # Finally test invalid clusters are rejected cluster
        params['input']['params']['details']['cluster'] = 'not_real'
        response = self.client.execute(mut, params)

        self.assertEqual(
            response.errors[0].message, "Error submitting job, cluster 'not_real' is not one of [default another]"
        )
