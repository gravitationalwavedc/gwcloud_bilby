from datetime import timedelta

from django.utils import timezone

from bilbyui.models import BilbyJob
from bilbyui.services.jobs import _apply_search_filter, _apply_time_range_filter
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestApplySearchFilter(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.matching_job = BilbyJob.objects.create(
            user_id=1,
            name="alpha_job",
            description="contains beta text",
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.other_job = BilbyJob.objects.create(
            user_id=1,
            name="gamma_job",
            description="unrelated",
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def test_empty_search_returns_all(self):
        qs = BilbyJob.objects.all()
        filtered = _apply_search_filter(qs, "")
        self.assertEqual(filtered.count(), qs.count())

    def test_search_matches_name(self):
        matches = _apply_search_filter(BilbyJob.objects.all(), "alpha")
        self.assertEqual(list(matches), [self.matching_job])

    def test_search_matches_description(self):
        matches = _apply_search_filter(BilbyJob.objects.all(), "beta")
        self.assertEqual(list(matches), [self.matching_job])

    def test_search_no_match_returns_empty(self):
        matches = _apply_search_filter(BilbyJob.objects.all(), "no-such-term")
        self.assertEqual(list(matches), [])


class TestApplyTimeRangeFilter(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.recent_job = BilbyJob.objects.create(
            user_id=1,
            name="recent_job",
            description="recent",
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        BilbyJob.objects.filter(pk=cls.recent_job.pk).update(last_updated=now - timedelta(hours=1))

        cls.old_job = BilbyJob.objects.create(
            user_id=1,
            name="old_job",
            description="old",
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        BilbyJob.objects.filter(pk=cls.old_job.pk).update(last_updated=now - timedelta(days=40))

        cls.recent_job.refresh_from_db()
        cls.old_job.refresh_from_db()

    def test_all_time_range_returns_unfiltered_queryset(self):
        qs = BilbyJob.objects.all()
        self.assertQuerySetEqual(_apply_time_range_filter(qs, "all"), qs.order_by("pk"))

    def test_one_day_filter_excludes_old_jobs(self):
        matches = _apply_time_range_filter(BilbyJob.objects.all(), "1d")
        self.assertEqual(list(matches), [self.recent_job])

    def test_one_week_filter_excludes_old_jobs(self):
        matches = _apply_time_range_filter(BilbyJob.objects.all(), "1w")
        self.assertEqual(list(matches), [self.recent_job])

    def test_one_month_filter_excludes_old_jobs(self):
        matches = _apply_time_range_filter(BilbyJob.objects.all(), "1m")
        self.assertEqual(list(matches), [self.recent_job])

    def test_one_year_filter_includes_recent_jobs(self):
        matches = _apply_time_range_filter(BilbyJob.objects.all(), "1y")
        self.assertEqual(set(matches), {self.recent_job, self.old_job})

    def test_custom_field_name(self):
        now = timezone.now()
        BilbyJob.objects.filter(pk=self.recent_job.pk).update(creation_time=now - timedelta(hours=1))
        BilbyJob.objects.filter(pk=self.old_job.pk).update(creation_time=now - timedelta(days=40))
        self.recent_job.refresh_from_db()
        self.old_job.refresh_from_db()

        matches = _apply_time_range_filter(BilbyJob.objects.all(), "1d", field_name="creation_time")
        self.assertEqual(list(matches), [self.recent_job])

    def test_invalid_time_range_raises(self):
        with self.assertRaisesMessage(Exception, "Unexpected timeRange value invalid"):
            _apply_time_range_filter(BilbyJob.objects.all(), "invalid")
