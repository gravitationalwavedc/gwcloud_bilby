from datetime import datetime, timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from bilbyui.models import BilbyJob
from bilbyui.services.jobs import _apply_search_filter, _apply_time_range_filter
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase

FIXED_NOW = timezone.make_aware(datetime(2025, 6, 15, 12, 0, 0))


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestJobsServiceFilters(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        ini = create_test_ini_string({"detectors": "['H1']"})
        now = FIXED_NOW

        cls.recent_job = BilbyJob.objects.create(
            user_id=1,
            name="recent_job",
            description="Recently updated job",
            private=False,
            ini_string=ini,
        )
        cls.week_old_job = BilbyJob.objects.create(
            user_id=1,
            name="week_old_job",
            description="Updated last week",
            private=False,
            ini_string=ini,
        )
        cls.year_old_job = BilbyJob.objects.create(
            user_id=1,
            name="year_old_job",
            description="Updated long ago",
            private=False,
            ini_string=ini,
        )
        cls.searchable_job = BilbyJob.objects.create(
            user_id=1,
            name="unique_alpha_name",
            description="beta description token",
            private=False,
            ini_string=ini,
        )

        BilbyJob.objects.filter(pk=cls.recent_job.pk).update(last_updated=now - timedelta(hours=6))
        BilbyJob.objects.filter(pk=cls.week_old_job.pk).update(last_updated=now - timedelta(days=5))
        BilbyJob.objects.filter(pk=cls.year_old_job.pk).update(last_updated=now - timedelta(days=200))

        cls.recent_job.refresh_from_db()
        cls.week_old_job.refresh_from_db()
        cls.year_old_job.refresh_from_db()

    def _apply_time_range(self, qs, time_range, **kwargs):
        with mock.patch("bilbyui.services.jobs.timezone.now", return_value=FIXED_NOW):
            return _apply_time_range_filter(qs, time_range, **kwargs)

    def test_apply_time_range_filter_all_returns_unchanged_queryset(self):
        qs = BilbyJob.objects.filter(pk__in=[self.recent_job.pk, self.year_old_job.pk])
        filtered = self._apply_time_range(qs, "all")
        self.assertQuerySetEqual(filtered.order_by("pk"), qs.order_by("pk"))

    def test_apply_time_range_filter_one_day(self):
        qs = BilbyJob.objects.filter(pk__in=[self.recent_job.pk, self.week_old_job.pk, self.year_old_job.pk])
        filtered = self._apply_time_range(qs, "1d")
        self.assertEqual(list(filtered), [self.recent_job])

    def test_apply_time_range_filter_one_week(self):
        qs = BilbyJob.objects.filter(pk__in=[self.recent_job.pk, self.week_old_job.pk, self.year_old_job.pk])
        filtered = self._apply_time_range(qs, "1w")
        self.assertCountEqual(list(filtered), [self.recent_job, self.week_old_job])

    def test_apply_time_range_filter_one_month(self):
        qs = BilbyJob.objects.filter(pk__in=[self.recent_job.pk, self.week_old_job.pk, self.year_old_job.pk])
        filtered = self._apply_time_range(qs, "1m")
        self.assertCountEqual(list(filtered), [self.recent_job, self.week_old_job])

    def test_apply_time_range_filter_one_year(self):
        qs = BilbyJob.objects.filter(pk__in=[self.recent_job.pk, self.week_old_job.pk, self.year_old_job.pk])
        filtered = self._apply_time_range(qs, "1y")
        self.assertCountEqual(list(filtered), [self.recent_job, self.week_old_job, self.year_old_job])

    def test_apply_time_range_filter_invalid_value_raises(self):
        qs = BilbyJob.objects.filter(pk=self.recent_job.pk)
        with mock.patch("bilbyui.services.jobs.timezone.now", return_value=FIXED_NOW):
            with self.assertRaises(Exception) as ctx:
                _apply_time_range_filter(qs, "invalid")
        self.assertIn("Unexpected timeRange value invalid", str(ctx.exception))

    def test_apply_time_range_filter_custom_field_name(self):
        BilbyJob.objects.filter(pk=self.recent_job.pk).update(creation_time=FIXED_NOW - timedelta(hours=6))
        self.recent_job.refresh_from_db()
        qs = BilbyJob.objects.filter(pk=self.recent_job.pk)
        filtered = self._apply_time_range(qs, "1d", field_name="creation_time")
        self.assertEqual(list(filtered), [self.recent_job])

    def test_apply_search_filter_empty_search_returns_unchanged_queryset(self):
        qs = BilbyJob.objects.filter(pk__in=[self.recent_job.pk, self.searchable_job.pk])
        filtered = _apply_search_filter(qs, "")
        self.assertQuerySetEqual(filtered.order_by("pk"), qs.order_by("pk"))

    def test_apply_search_filter_matches_name(self):
        qs = BilbyJob.objects.filter(pk__in=[self.recent_job.pk, self.searchable_job.pk, self.week_old_job.pk])
        filtered = _apply_search_filter(qs, "unique_alpha")
        self.assertEqual(list(filtered), [self.searchable_job])

    def test_apply_search_filter_matches_description(self):
        qs = BilbyJob.objects.filter(pk__in=[self.recent_job.pk, self.searchable_job.pk, self.week_old_job.pk])
        filtered = _apply_search_filter(qs, "beta description")
        self.assertEqual(list(filtered), [self.searchable_job])

    def test_apply_search_filter_no_match_returns_empty(self):
        qs = BilbyJob.objects.filter(pk__in=[self.recent_job.pk, self.searchable_job.pk])
        filtered = _apply_search_filter(qs, "no_such_term")
        self.assertEqual(list(filtered), [])
