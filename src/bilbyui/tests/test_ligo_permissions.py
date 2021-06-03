from unittest.mock import patch

from django.test import TestCase
from munch import DefaultMunch

from bilbyui.models import BilbyJob
from bilbyui.views import create_bilby_job
from gw_bilby.jwt_tools import GWCloudUser


class TestBilbyLigoPermissions(TestCase):
    @patch("bilbyui.views.submit_job")
    def test_gwosc_channel_permissions(self, mock_api_call):
        mock_api_call.return_value = {'jobId': 4321}

        payload = {
            "start": {
                "name": "Untitled",
                "description": "A good description is specific, unique, and memorable.",
                "private": False
            },
            "data": {
                "data_type": "real",
                "data_choice": "real",
                "signal_duration": "4",
                "sampling_frequency": "512",
                "trigger_time": "1126259462.391",
                "hanford": True,
                "hanford_minimum_frequency": "20",
                "hanford_maximum_frequency": "1024",
                "hanford_channel": "GWOSC",
                "livingston": False,
                "livingston_minimum_frequency": "20",
                "livingston_maximum_frequency": "1024",
                "livingston_channel": "GWOSC",
                "virgo": False,
                "virgo_minimum_frequency": "20",
                "virgo_maximum_frequency": "1024",
                "virgo_channel": "GWOSC"
            },
            "signal": {
                "mass1": "30",
                "mass2": "25",
                "luminosity_distance": "2000",
                "psi": "0.4",
                "iota": "2.659",
                "phase": "1.3",
                "merger_time": "1126259642.413",
                "ra": "1.375",
                "dec": "-1.2108",
                "signal_choice": "skip",
                "signal_model": "none"
            },
            "sampler": {
                "nlive": "1000",
                "nact": "10",
                "maxmcmc": "5000",
                "walks": "1000",
                "dlogz": "0.1",
                "cpus": "1",
                "sampler_choice": "dynesty"
            },
            "prior": {
                "prior_choice": "4s"
            }
        }

        payload = DefaultMunch.fromDict(payload)

        user = GWCloudUser('billy')
        user.user_id = 1234
        user.is_ligo = True

        # First call should be successful for all users, since we're using GWOSC channels
        job_id = create_bilby_job(
            user, payload.start, payload.data, payload.signal, payload.prior, payload.sampler
        )
        # Check that the job is marked as public
        self.assertFalse(BilbyJob.objects.get(id=job_id).is_ligo_job)

        BilbyJob.objects.all().delete()
        user.is_ligo = False
        job_id = create_bilby_job(
            user, payload.start, payload.data, payload.signal, payload.prior, payload.sampler
        )
        # Check that the job is marked as public
        self.assertFalse(BilbyJob.objects.get(id=job_id).is_ligo_job)

        # Now if the channels are proprietary, the non-ligo user should not be able to create jobs
        for detector in [
            ('hanford_channel', 'GDS-CALIB_STRAIN'),
            ('livingston_channel', 'GDS-CALIB_STRAIN'),
            ('virgo_channel', 'Hrec_hoft_16384Hz'),
            # Also check invalid (Non GWOSC channels)
            ('hanford_channel', 'testchannel1'),
            ('livingston_channel', 'imnotarealchannel'),
            ('virgo_channel', 'GWOSc'),
        ]:
            payload.data[detector[0]] = detector[1]
            with self.assertRaises(Exception):
                BilbyJob.objects.all().delete()
                create_bilby_job(
                    user, payload.start, payload.data, payload.signal, payload.prior, payload.sampler
                )

            payload.data[detector[0]] = "GWOSC"

        BilbyJob.objects.all().delete()

        # Now if the channels are proprietary, the ligo user should be able to create jobs
        user.is_ligo = True
        for detector in [
            ('hanford_channel', 'GDS-CALIB_STRAIN'),
            ('livingston_channel', 'GDS-CALIB_STRAIN'),
            ('virgo_channel', 'Hrec_hoft_16384Hz')
        ]:
            payload.data[detector[0]] = detector[1]
            BilbyJob.objects.all().delete()
            job_id = create_bilby_job(
                user, payload.start, payload.data, payload.signal, payload.prior, payload.sampler
            )
            # Check that the job is marked as proprietary
            self.assertTrue(BilbyJob.objects.get(id=job_id).is_ligo_job)

            payload.data[detector[0]] = "GWOSC"

        BilbyJob.objects.all().delete()
