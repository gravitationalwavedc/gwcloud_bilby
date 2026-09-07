from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob
from bilbyui.services.jobs import _apply_time_range_filter, _time_range_to_timedelta
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TimeRangeToTimedeltaTestCase(BilbyTestCase):
    def test_one_day(self):
        self.assertEqual(_time_range_to_timedelta("1d"), timedelta(days=1))

    def test_one_week(self):
        self.assertEqual(_time_range_to_timedelta("1w"), timedelta(days=7))

    def test_one_month(self):
        self.assertEqual(_time_range_to_timedelta("1m"), timedelta(days=31))

    def test_one_year(self):
        self.assertEqual(_time_range_to_timedelta("1y"), timedelta(days=365))

    def test_invalid_time_range_raises_value_error(self):
        with self.assertRaises(ValueError):
            _time_range_to_timedelta("2d")


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class ApplyTimeRangeFilterTestCase(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ini = create_test_ini_string({"detectors": "['H1']"})

    def setUp(self):
        self.authenticate()

    def _make_job(self, name, last_updated):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name=name,
            description="Test description",
            ini_string=self.ini,
            job_type=BilbyJobType.NORMAL,
            job_controller_id=None,
        )
        # auto_now/auto_now_add would overwrite the timestamps on save, so set
        # them via the queryset to exercise the time-window branch with a known
        # timestamp.
        BilbyJob.objects.filter(pk=job.pk).update(
            last_updated=last_updated,
            creation_time=last_updated,
        )
        return job

    def test_all_returns_queryset_unchanged(self):
        qs = BilbyJob.objects.all()
        result = _apply_time_range_filter(qs, "all")

        self.assertIs(result, qs)

    def test_time_window_includes_recent_jobs(self):
        self._make_job("recent", timezone.now())
        self._make_job("stale", timezone.now() - timedelta(days=10))

        qs = _apply_time_range_filter(BilbyJob.objects.all(), "1d")

        names = set(qs.values_list("name", flat=True))
        self.assertIn("recent", names)
        self.assertNotIn("stale", names)

    def test_custom_field_name(self):
        self._make_job("recent", timezone.now())
        self._make_job("stale", timezone.now() - timedelta(days=10))

        qs = _apply_time_range_filter(BilbyJob.objects.all(), "1d", field_name="creation_time")

        names = set(qs.values_list("name", flat=True))
        self.assertIn("recent", names)
        self.assertNotIn("stale", names)
