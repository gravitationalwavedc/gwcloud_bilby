from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.models import BilbyJob, IniKeyValue
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import qs_embargo_filter

User = get_user_model()


class TestQsEmbargoFilter(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user(id=1, name="test user", primary_email="test@test.com")

    def _create_job(self, name, trigger_time=None, n_simulation=None):
        """Create a BilbyJob with optional IniKeyValue entries."""
        ini_config = {"detectors": "['H1']"}
        if trigger_time is not None:
            ini_config["trigger-time"] = trigger_time
        if n_simulation is not None:
            ini_config["n-simulation"] = n_simulation

        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name=name,
            description=name,
            ini_string=create_test_ini_string(ini_config),
        )
        return job

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_job_with_trigger_time_below_embargo(self):
        """Jobs with trigger_time < EMBARGO_START_TIME should be included."""
        self._create_job("early job", trigger_time=3.0, n_simulation=0)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, "early job")

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_job_with_trigger_time_above_embargo(self):
        """Jobs with trigger_time >= EMBARGO_START_TIME should be excluded."""
        self._create_job("late job", trigger_time=7.0, n_simulation=0)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 0)

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_job_with_trigger_time_equal_to_embargo(self):
        """Jobs with trigger_time == EMBARGO_START_TIME should be excluded."""
        self._create_job("boundary job", trigger_time=5.0, n_simulation=0)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 0)

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_simulated_job_included(self):
        """Simulated jobs (n_simulation > 0) should always be included."""
        self._create_job("sim job", trigger_time=10.0, n_simulation=1)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, "sim job")

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_non_simulated_late_job_excluded(self):
        """Non-simulated job with trigger_time >= EMBARGO_START_TIME should be excluded."""
        self._create_job("real late job", trigger_time=10.0, n_simulation=0)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 0)

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_simulated_job_without_trigger_time(self):
        """Simulated job without trigger_time should still be included."""
        self._create_job("sim no trigger", n_simulation=1)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, "sim no trigger")

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_mixed_jobs(self):
        """Test multiple jobs with different trigger times and simulation status."""
        self._create_job("early real", trigger_time=1.0, n_simulation=0)
        self._create_job("late real", trigger_time=10.0, n_simulation=0)
        self._create_job("early sim", trigger_time=1.0, n_simulation=1)
        self._create_job("late sim", trigger_time=10.0, n_simulation=1)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        # early real (trigger_time=1.0 < 5.0) and both sim jobs (simulated > 0) should be included
        # late real (trigger_time=10.0 >= 5.0, not simulated) should be excluded
        self.assertEqual(result.count(), 3)
        names = set(result.values_list("name", flat=True))
        self.assertEqual(names, {"early real", "early sim", "late sim"})

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_no_embargo_setting(self):
        """When EMBARGO_START_TIME is high enough, all jobs should be included."""
        self._create_job("job 1", trigger_time=1.0, n_simulation=0)
        self._create_job("job 2", trigger_time=3.0, n_simulation=0)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 2)

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_empty_queryset(self):
        """Empty queryset should return empty result."""
        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 0)

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_job_with_processed_trigger_time(self):
        """Only processed IniKeyValue entries should be considered for trigger_time."""
        job = self._create_job("processed trigger", trigger_time=1.0, n_simulation=0)

        # Add an unprocessed trigger_time entry that should be ignored
        IniKeyValue.objects.create(
            job=job,
            key="trigger_time",
            value="99.0",
            index=1,
            processed=False,
        )

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, "processed trigger")
