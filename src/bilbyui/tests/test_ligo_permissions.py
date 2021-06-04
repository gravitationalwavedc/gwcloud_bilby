import logging
from unittest.mock import patch

from django.contrib.auth import get_user_model
from graphql_relay.node.node import from_global_id

from bilbyui.models import BilbyJob
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


class TestBilbyLigoPermissions(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

    @patch("bilbyui.views.submit_job")
    def test_gwosc_channel_permissions(self, mock_api_call):
        try:
            logging.disable(logging.ERROR)

            self.client.authenticate(self.user, is_ligo=True)

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

            _, job_id = from_global_id(response.data['newBilbyJob']['result']['jobId'])

            # Check that the job is marked as public
            self.assertFalse(BilbyJob.objects.all().last().is_ligo_job)

            BilbyJob.objects.all().delete()
            self.client.authenticate(self.user, is_ligo=False)

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
                        'jobId': 'QmlsYnlKb2JOb2RlOjI='
                    }
                }
            }

            self.assertDictEqual(
                expected, response.data, "create bilbyJob mutation returned unexpected data."
            )

            _, job_id = from_global_id(response.data['newBilbyJob']['result']['jobId'])

            # Check that the job is marked as public
            self.assertFalse(BilbyJob.objects.get(id=job_id).is_ligo_job)

            # Now if the channels are proprietary, the non-ligo user should not be able to create jobs
            for detector in [
                ('hanfordChannel', 'GDS-CALIB_STRAIN'),
                ('livingstonChannel', 'GDS-CALIB_STRAIN'),
                ('virgoChannel', 'Hrec_hoft_16384Hz'),
                # Also check invalid (Non GWOSC channels)
                ('hanfordChannel', 'testchannel1'),
                ('livingstonChannel', 'imnotarealchannel'),
                ('virgoChannel', 'GWOSc'),
            ]:
                params['input']['params']['data']['channels'][detector[0]] = detector[1]

                BilbyJob.objects.all().delete()

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
                    'newBilbyJob': None
                }

                self.assertDictEqual(
                    expected, response.data, "create bilbyJob mutation returned unexpected data."
                )

                self.assertEqual(
                    response.errors[0].message,
                    'Non-LIGO members may only run real jobs on GWOSC channels'
                )

                self.assertFalse(BilbyJob.objects.all().exists())

                params['input']['params']['data']['channels'][detector[0]] = "GWOSC"

            BilbyJob.objects.all().delete()

            # Now if the channels are proprietary, the ligo user should be able to create jobs
            self.client.authenticate(self.user, is_ligo=True)

            for detector in [
                ('hanfordChannel', 'GDS-CALIB_STRAIN'),
                ('livingstonChannel', 'GDS-CALIB_STRAIN'),
                ('virgoChannel', 'Hrec_hoft_16384Hz')
            ]:
                params['input']['params']['data']['channels'][detector[0]] = detector[1]
                BilbyJob.objects.all().delete()

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

                self.assertTrue('jobId' in response.data['newBilbyJob']['result'])

                _, job_id = from_global_id(response.data['newBilbyJob']['result']['jobId'])

                # Check that the job is marked as proprietary
                self.assertTrue(BilbyJob.objects.get(id=job_id).is_ligo_job)

                params['input']['params']['data']['channels'][detector[0]] = "GWOSC"

            BilbyJob.objects.all().delete()
        finally:
            logging.disable(logging.NOTSET)
