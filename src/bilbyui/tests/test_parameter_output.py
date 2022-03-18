import random
import string
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model

from bilbyui.models import BilbyJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.gen_parameter_output import to_dec, generate_parameter_output

User = get_user_model()


def rand_int(start, end):
    return random.randrange(start, end, 1)


def rand_float(start, end, places=4):
    return Decimal(str(round(random.uniform(start, end), places)))


def rand_string(num_chars):
    return ''.join(random.choices(string.ascii_lowercase + string.ascii_uppercase + string.digits, k=num_chars))


class TestJobSubmission(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user, True)

    @patch("bilbyui.models.submit_job")
    def test_generate_parameter_output(self, mock_api_call):
        # Try randomly generating 100 jobs
        for job_index in range(100):
            mock_api_call.return_value = {'jobId': job_index + 10}

            params = {
                "input": {
                    "params": {
                        "details": {
                            "name": rand_string(20),
                            "description": rand_string(128),
                            "private": True,
                        },
                        # "calibration": None,
                        "data": {
                            "dataChoice": random.choice(["real", "simulated"]),
                            "triggerTime": str(to_dec(float(rand_float(1126200000, 118200000)))),
                            "channels": {
                                "hanfordChannel": random.choice(["GWOSC", "GDS-CALIB_STRAIN"]),
                                "livingstonChannel": random.choice(["GWOSC", "GDS-CALIB_STRAIN"]),
                                "virgoChannel": random.choice(["GWOSC", "Hrec_hoft_16384Hz"]),
                            }
                        },
                        "detector": {
                            "hanford": True,
                            "hanfordMinimumFrequency": str(to_dec(float(rand_float(10, 900)))),
                            "hanfordMaximumFrequency": str(to_dec(float(rand_float(1000, 20000)))),
                            "livingston": random.choice([True, False]),
                            "livingstonMinimumFrequency": str(to_dec(float(rand_float(10, 900)))),
                            "livingstonMaximumFrequency": str(to_dec(float(rand_float(1000, 20000)))),
                            "virgo": random.choice([True, False]),
                            "virgoMinimumFrequency": str(to_dec(float(rand_float(10, 900)))),
                            "virgoMaximumFrequency": str(to_dec(float(rand_float(1000, 20000)))),
                            "duration": random.choice(["4", "8", "16", "32", "64", "128"]),
                            "samplingFrequency": random.choice(["512", "1024", "2048", "4096", "8192", "16384"])
                        },
                        # "injection": {},
                        # "likelihood": {},
                        "prior": {
                            "priorDefault": random.choice(["4s", "8s", "16s", "32s", "64s", "128s"])
                        },
                        # "postProcessing": {},
                        "sampler": {
                            "nlive": rand_int(100, 10000),
                            "nact": rand_int(1, 100),
                            "maxmcmc": rand_int(1000, 10000),
                            "walks": rand_int(100, 10000),
                            "dlogz": str(to_dec(float(rand_float(0.1, 1)))),
                            "cpus": rand_int(1, 32),
                            "samplerChoice": "dynesty"
                        },
                        "waveform": {
                            "model": random.choice([None, "binaryNeutronStar", "binaryBlackHole"])
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

            self.assertTrue('jobId' in response.data['newBilbyJob']['result'])

            job_id = response.data['newBilbyJob']['result']['jobId']

            response = self.client.execute(f"""
                query {{
                    bilbyJob(id:"{job_id}"){{
                        id
                        name
                        userId
                        description
                        jobControllerId
                        private
                        params {{
                            details {{
                                name
                                description
                                private
                            }}
                            data {{
                                dataChoice
                                triggerTime
                                channels {{
                                    hanfordChannel
                                    livingstonChannel
                                    virgoChannel
                                }}
                            }}
                            detector {{
                                hanford
                                hanfordMinimumFrequency
                                hanfordMaximumFrequency
                                livingston
                                livingstonMinimumFrequency
                                livingstonMaximumFrequency
                                virgo
                                virgoMinimumFrequency
                                virgoMaximumFrequency
                                duration
                                samplingFrequency
                            }}
                            prior {{
                                priorDefault
                            }}
                            sampler {{
                                nlive
                                nact
                                maxmcmc
                                walks
                                dlogz
                                cpus
                                samplerChoice
                            }}
                            waveform {{
                                model
                            }}
                        }}
                    }}
                }}
                """
                                           )

            min_vals = [
                Decimal(params['input']['params']['detector']['hanfordMinimumFrequency'])
            ]

            max_vals = [
                Decimal(params['input']['params']['detector']['hanfordMaximumFrequency'])
            ]

            if params['input']['params']['detector']['livingston']:
                min_vals.append(Decimal(params['input']['params']['detector']['livingstonMinimumFrequency']))
                max_vals.append(Decimal(params['input']['params']['detector']['livingstonMaximumFrequency']))

            if params['input']['params']['detector']['virgo']:
                min_vals.append(Decimal(params['input']['params']['detector']['virgoMinimumFrequency']))
                max_vals.append(Decimal(params['input']['params']['detector']['virgoMaximumFrequency']))

            if not params['input']['params']['detector']['livingston']:
                params['input']['params']['data']['channels']['livingstonChannel'] = None
                params['input']['params']['detector']['livingstonMinimumFrequency'] = str(min(min_vals))
                params['input']['params']['detector']['livingstonMaximumFrequency'] = str(max(max_vals))

            if not params['input']['params']['detector']['virgo']:
                params['input']['params']['data']['channels']['virgoChannel'] = None
                params['input']['params']['detector']['virgoMinimumFrequency'] = str(min(min_vals))
                params['input']['params']['detector']['virgoMaximumFrequency'] = str(max(max_vals))

            if not params['input']['params']['waveform']['model']:
                params['input']['params']['waveform']['model'] = 'binaryBlackHole'

            expected = {
                "bilbyJob": {
                    "id": job_id,
                    "name": params['input']['params']['details']['name'],
                    "userId": 1,
                    "description": params['input']['params']['details']['description'],
                    "jobControllerId": job_index + 10,
                    "private": params['input']['params']['details']['private'],
                    "params": params['input']['params']
                }
            }

            self.assertDictEqual(
                expected, response.data, "bilbyJob query returned unexpected data."
            )

    def test_invalid_outdir_output(self):
        # There are invalid outdirs which can crash the viewing of jobs, so we need to check that the outdir is
        # correctly sanitized

        # Start with creating a job with an invalid outdir (".")
        job = BilbyJob.objects.create(user_id=self.user.id)
        job.ini_string = """detectors=['H1']
trigger-time=12345678
outdir=."""
        job.save()

        # Generate the output params - bilby will raise an exception if outdir=. is not sanitized
        generate_parameter_output(job)

    def test_sampler_parsing_output(self):
        # There is a case where parsing of sampler arguments broke because some dict values were strings representing a
        # word rather than a parsable decimal number. We need to check that that case can successfully be parsed.

        # Case: sampler-kwargs={'queue_size': 4, 'nlive': 2000, 'sample': 'rwalk', 'walks': 100, 'n_check_point': 2000,
        # 'nact': 10, 'npool': 4}
        # Because "'sample': 'rwalk'" isn't parsable as a decimal

        # Start with creating a job with the test case
        job = BilbyJob.objects.create(user_id=self.user.id)
        job.ini_string = """detectors=['H1']
trigger-time=12345678
outdir=./
sampler=dynesty
sampler-kwargs={'queue_size': 4, 'nlive': 2000, 'sample': 'rwalk', 'walks': 100, 'n_check_point': 2000, 'nact': 10, 'npool': 4}""" # noqa
        job.save()

        # Generate the output params - bilby will raise an exception if the decimal parser isn't updated to handle the
        # case of 'sample': 'rwalk'
        generate_parameter_output(job)
