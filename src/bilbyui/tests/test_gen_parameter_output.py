from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.models import BilbyJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.types import JobParameterOutput
from bilbyui.utils.gen_parameter_output import generate_parameter_output, to_dec

User = get_user_model()
INI_BASE = (
    "trigger-time=12345678\n"
    "outdir=./\n"
    "duration=4\n"
    "sampling-frequency=2048\n"
    "prior-file=4s\n"
    "sampler=dynesty\n"
    "nlive=1024\n"
    "frequency-domain-source-model=lal_binary_black_hole\n"
)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestGenerateParameterOutput(BilbyTestCase):
    def setUp(self):
        self.user, _ = User.objects.update_or_create(
            id=1, defaults={"name": "buffy summers", "primary_email": "slayer@gmail.com"}
        )

    def _make_job(self, ini_string, name="test-job"):
        return BilbyJob.objects.create(
            user_id=self.user.id, name=name, description="test", private=False, ini_string=ini_string
        )

    def test_to_dec(self):
        self.assertIsNone(to_dec(None))
        self.assertEqual(to_dec(Decimal("3.14")), Decimal("3.14"))
        self.assertEqual(to_dec("42"), Decimal(42))
        self.assertEqual(to_dec(42), Decimal(42))
        self.assertEqual(to_dec(3.14), Decimal("3.14"))
        self.assertEqual(to_dec("hello"), "hello")

    def test_basic_job(self):
        job = self._make_job(
            "detectors=['H1', 'L1', 'V1']\n" + INI_BASE + "sampler-kwargs={'nlive': 1024, 'sample': 'rwalk'}\n"
        )
        r = generate_parameter_output(job)
        self.assertIsInstance(r, JobParameterOutput)
        self.assertEqual(r.details.name, "test-job")
        self.assertEqual(r.data.data_choice, "real")
        self.assertEqual(r.data.trigger_time, Decimal(12345678))
        self.assertIsNone(r.data.channels.hanford_channel)
        self.assertEqual(r.detector.duration, Decimal(4))
        self.assertEqual(r.detector.sampling_frequency, Decimal(2048))
        self.assertTrue(r.detector.hanford)
        self.assertTrue(r.detector.livingston)
        self.assertTrue(r.detector.virgo)
        self.assertEqual(r.prior.prior_default, "4s")
        self.assertEqual(r.sampler.sampler_choice, "dynesty")
        self.assertEqual(r.sampler.nlive, Decimal(1024))
        self.assertEqual(r.sampler.sample, "rwalk")
        self.assertEqual(r.waveform.model, "binaryBlackHole")

    def test_outdir_dot(self):
        job = self._make_job("detectors=['H1']\n" + INI_BASE.replace("outdir=./", "outdir=.\n"))
        self.assertEqual(generate_parameter_output(job).data.data_choice, "real")

    def test_simulated(self):
        job = self._make_job("detectors=['H1']\n" + INI_BASE + "n-simulation=1\n")
        self.assertEqual(generate_parameter_output(job).data.data_choice, "simulated")

    def test_single_detector(self):
        r = generate_parameter_output(self._make_job("detectors=['H1']\n" + INI_BASE))
        self.assertTrue(r.detector.hanford)
        self.assertFalse(r.detector.livingston)
        self.assertFalse(r.detector.virgo)
        self.assertEqual(r.detector.hanford_minimum_frequency, Decimal(20))
        self.assertEqual(r.detector.hanford_maximum_frequency, Decimal(1024))

    def test_waveform_models(self):
        for i, (model, expected) in enumerate(
            [
                ("lal_binary_neutron_star", "binaryNeutronStar"),
                ("some_custom_model", "unknown"),
            ]
        ):
            job = self._make_job(
                "detectors=['H1']\n"
                + INI_BASE.replace(
                    "frequency-domain-source-model=lal_binary_black_hole",
                    f"frequency-domain-source-model={model}",
                )
            )
            job.name = f"test-waveform-{i}"
            job.save()
            self.assertEqual(generate_parameter_output(job).waveform.model, expected)

    def test_generation_seed(self):
        job = self._make_job("detectors=['H1']\n" + INI_BASE + "generation-seed=12345\n")
        r = generate_parameter_output(job)
        self.assertIsNotNone(r.details)
        self.assertEqual(r.data.data_choice, "real")

    def test_sampler_kwargs(self):
        job = self._make_job(
            "detectors=['H1']\n" + INI_BASE + "sampler-kwargs={'sample': 'rwalk', 'nlive': 2000, 'walks': 100}\n"
        )
        r = generate_parameter_output(job)
        self.assertEqual(r.sampler.sample, "rwalk")
        self.assertEqual(r.sampler.nlive, Decimal(2000))
        self.assertEqual(r.sampler.walks, Decimal(100))

    def test_channel_dict(self):
        job = self._make_job(
            "detectors=['H1', 'L1', 'V1']\n"
            + INI_BASE
            + "channel-dict={'H1': 'GDS-CALIB_STRAIN', 'L1': 'GDS-CALIB_STRAIN', 'V1': 'Hrec_hoft_16384Hz'}\n"
        )
        r = generate_parameter_output(job)
        self.assertEqual(r.data.channels.hanford_channel, "GDS-CALIB_STRAIN")
        self.assertEqual(r.data.channels.livingston_channel, "GDS-CALIB_STRAIN")
        self.assertEqual(r.data.channels.virgo_channel, "Hrec_hoft_16384Hz")

    def test_prior_sanitization(self):
        job = self._make_job("detectors=['H1']\n" + INI_BASE)
        self.assertEqual(generate_parameter_output(job).prior.prior_default, "4s")
        job.name = "test-prior-custom"
        job.ini_string = "detectors=['H1']\n" + INI_BASE.replace("prior-file=4s", "prior-file=/custom/path/prior.prior")
        job.save()
        self.assertIsNone(generate_parameter_output(job).prior.prior_default)
