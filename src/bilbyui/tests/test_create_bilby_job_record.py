from types import SimpleNamespace

from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob, Label
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.ini_utils import bilby_ini_string_to_args
from bilbyui.views import _create_bilby_job_record


def _args_from_ini(config):
    return bilby_ini_string_to_args(create_test_ini_string(config).encode("utf-8"))


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestCreateBilbyJobRecord(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user(id=1)
        self.details = SimpleNamespace(description="test description", private=False)

    def test_creates_job_record_with_normal_fields(self):
        args = _args_from_ini(
            {
                "label": "myjob",
                "detectors": "['H1']",
                "trigger-time": "1.0",
                "n-simulation": "0",
            }
        )

        job = _create_bilby_job_record(self.user, self.details, args, BilbyJobType.NORMAL)

        self.assertEqual(job.user, self.user)
        self.assertEqual(job.name, "myjob")
        self.assertEqual(job.description, "test description")
        self.assertFalse(job.private)
        self.assertEqual(job.job_type, BilbyJobType.NORMAL)
        self.assertFalse(job.is_ligo_job)
        self.assertEqual(BilbyJob.objects.count(), 1)

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_embargoed_job_marked_as_ligo_job(self):
        args = _args_from_ini(
            {
                "label": "myjob",
                "detectors": "['H1']",
                "trigger-time": "2.0",
                "n-simulation": "0",
            }
        )

        job = _create_bilby_job_record(self.user, self.details, args, BilbyJobType.NORMAL)

        self.assertTrue(job.is_ligo_job)

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_simulated_job_not_marked_as_ligo_job(self):
        args = _args_from_ini(
            {
                "label": "myjob",
                "detectors": "['H1']",
                "trigger-time": "2.0",
                "n-simulation": "1",
            }
        )

        job = _create_bilby_job_record(self.user, self.details, args, BilbyJobType.NORMAL)

        self.assertFalse(job.is_ligo_job)

    @override_settings(GWOSC_INGEST_USER=1)
    def test_gwosc_ingest_user_gets_official_label(self):
        args = _args_from_ini(
            {
                "label": "myjob",
                "detectors": "['H1']",
                "trigger-time": "1.0",
                "n-simulation": "0",
            }
        )

        job = _create_bilby_job_record(self.user, self.details, args, BilbyJobType.NORMAL)

        self.assertEqual(list(job.labels.values_list("name", flat=True)), ["Official"])

    @override_settings(GWOSC_INGEST_USER=2)
    def test_regular_user_gets_no_official_label(self):
        args = _args_from_ini(
            {
                "label": "myjob",
                "detectors": "['H1']",
                "trigger-time": "1.0",
                "n-simulation": "0",
            }
        )

        job = _create_bilby_job_record(self.user, self.details, args, BilbyJobType.NORMAL)

        self.assertEqual(job.labels.count(), 0)

    @override_settings(GWOSC_INGEST_USER=1)
    def test_gwosc_ingest_user_without_official_label_does_not_crash(self):
        Label.objects.filter(name="Official").delete()
        args = _args_from_ini(
            {
                "label": "myjob",
                "detectors": "['H1']",
                "trigger-time": "1.0",
                "n-simulation": "0",
            }
        )

        job = _create_bilby_job_record(self.user, self.details, args, BilbyJobType.NORMAL)

        self.assertEqual(job.labels.count(), 0)

    def test_ini_string_is_passed_through(self):
        args = _args_from_ini(
            {
                "label": "myjob",
                "detectors": "['H1']",
                "trigger-time": "1.0",
                "n-simulation": "0",
            }
        )
        custom_ini = create_test_ini_string(
            {
                "label": "customjob",
                "detectors": "['L1']",
                "trigger-time": "1.0",
                "n-simulation": "0",
            }
        )

        job = _create_bilby_job_record(
            self.user,
            self.details,
            args,
            BilbyJobType.NORMAL,
            ini_string=custom_ini,
        )

        self.assertEqual(job.ini_string, custom_ini)
