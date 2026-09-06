from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from graphql import GraphQLError

from bilbyui.models import BilbyJob, EventID
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import create_bilby_job


def _make_params(**overrides):
    params = SimpleNamespace(
        details=SimpleNamespace(
            name="test_job",
            description="test description",
            private=True,
            cluster="default",
        ),
        data=SimpleNamespace(
            trigger_time="1126259462.391",
            data_choice="simulated",
            channels=None,
            event_id=None,
        ),
        detector=SimpleNamespace(
            hanford=True,
            hanford_minimum_frequency="20",
            hanford_maximum_frequency="1024",
            livingston=True,
            livingston_minimum_frequency="20",
            livingston_maximum_frequency="1024",
            virgo=False,
            virgo_minimum_frequency="20",
            virgo_maximum_frequency="1024",
            duration="4",
            sampling_frequency="512",
        ),
        prior=SimpleNamespace(prior_default="4s"),
        sampler=SimpleNamespace(
            nlive=1000,
            nact=10,
            maxmcmc=5000,
            walks=1000,
            dlogz=0.1,
            cpus=1,
            sampler_choice="dynesty",
        ),
        waveform=SimpleNamespace(model=None),
    )
    for key, value in overrides.items():
        setattr(params, key, value)
    return params


class TestCreateBilbyJob(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user(id=1)

    @patch.object(BilbyJob, "submit")
    def test_success_path_creates_and_submits_job(self, mock_submit):
        job = create_bilby_job(self.user, _make_params())

        self.assertEqual(BilbyJob.objects.count(), 1)
        self.assertEqual(job.user, self.user)
        self.assertEqual(job.name, "test_job")
        self.assertEqual(job.description, "test description")
        self.assertTrue(job.private)
        self.assertFalse(job.is_ligo_job)
        self.assertIsNone(job.event_id)
        mock_submit.assert_called_once()

    @override_settings(EMBARGO_START_TIME=1.0)
    def test_embargoed_real_job_rejected_for_non_ligo_user(self):
        params = _make_params()
        params.data.data_choice = "real"
        params.data.trigger_time = "2.0"

        with self.assertRaises(GraphQLError) as ex:
            create_bilby_job(self.user, params)

        self.assertEqual(str(ex.exception), "Only LIGO users may run real jobs on embargoed LIGO data")
        self.assertEqual(BilbyJob.objects.count(), 0)

    def test_invalid_job_name_raises_value_error(self):
        params = _make_params()
        params.details.name = "a"

        with self.assertRaises(ValueError) as ex:
            create_bilby_job(self.user, params)

        self.assertEqual(str(ex.exception), "Job name must be at least 5 characters long.")
        self.assertEqual(BilbyJob.objects.count(), 0)

    def test_event_id_not_found_raises_graphql_error(self):
        params = _make_params()
        params.data.event_id = "GW123456_123456"

        with self.assertRaises(GraphQLError) as ex:
            create_bilby_job(self.user, params)

        self.assertEqual(str(ex.exception), "Event ID 'GW123456_123456' not found.")
        self.assertEqual(BilbyJob.objects.count(), 0)

    @patch.object(BilbyJob, "submit")
    def test_success_path_with_existing_event_id(self, mock_submit):
        EventID.create(event_id="GW123456_123456", gps_time=1234.1234)

        params = _make_params()
        params.data.event_id = "GW123456_123456"

        job = create_bilby_job(self.user, params)

        self.assertEqual(BilbyJob.objects.count(), 1)
        self.assertEqual(job.event_id.event_id, "GW123456_123456")
        mock_submit.assert_called_once()
