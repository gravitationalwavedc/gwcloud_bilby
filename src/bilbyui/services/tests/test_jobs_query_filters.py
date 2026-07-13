from datetime import timedelta

from django.utils import timezone

from bilbyui.models import BilbyJob
from bilbyui.services.jobs import _apply_search_filter, _apply_time_range_filter
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestApplySearchFilter(BilbyTestCase):
    def setUp(self):
        self.create_user(id=1)

    @classmethod
    def setUpTestData(cls):
        cls.create_user(id=1, name="buffy summers")
        cls.match_name = BilbyJob.objects.create(
            user_id=1,
            name="gw_search_match",
            description="unrelated",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.match_description = BilbyJob.objects.create(
            user_id=1,
            name="other_job",
            description="contains gw_search_match token",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.no_match = BilbyJob.objects.create(
            user_id=1,
            name="third_job",
            description="nothing here",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def test_empty_search_returns_all_jobs(self):
        qs = BilbyJob.objects.all()
        self.assertQuerySetEqual(
            _apply_search_filter(qs, ""),
            qs.order_by("pk"),
            ordered=False,
        )

    def test_search_matches_name(self):
        qs = BilbyJob.objects.all()
        result = _apply_search_filter(qs, "gw_search_match")
        self.assertEqual(set(result.values_list("pk", flat=True)), {self.match_name.pk, self.match_description.pk})

    def test_search_matches_description(self):
        qs = BilbyJob.objects.filter(pk=self.match_description.pk)
        result = _apply_search_filter(qs, "gw_search_match")
        self.assertEqual(list(result.values_list("pk", flat=True)), [self.match_description.pk])


class TestApplyTimeRangeFilter(BilbyTestCase):
    def setUp(self):
        self.create_user(id=1)

    @classmethod
    def setUpTestData(cls):
        cls.create_user(id=1, name="buffy summers")
        cls.recent_job = BilbyJob.objects.create(
            user_id=1,
            name="recent_job",
            description="recent",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.old_job = BilbyJob.objects.create(
            user_id=1,
            name="old_job",
            description="old",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        BilbyJob.objects.filter(pk=cls.old_job.pk).update(
            last_updated=timezone.now() - timedelta(days=40),
        )

    def test_all_time_range_returns_unchanged_queryset(self):
        qs = BilbyJob.objects.all()
        self.assertQuerySetEqual(_apply_time_range_filter(qs, "all"), qs.order_by("pk"), ordered=False)

    def test_one_day_filter_excludes_old_jobs(self):
        qs = BilbyJob.objects.all()
        result = _apply_time_range_filter(qs, "1d")
        self.assertEqual(list(result.values_list("pk", flat=True)), [self.recent_job.pk])

    def test_one_week_filter_excludes_old_jobs(self):
        qs = BilbyJob.objects.all()
        result = _apply_time_range_filter(qs, "1w")
        self.assertEqual(list(result.values_list("pk", flat=True)), [self.recent_job.pk])

    def test_one_month_filter_excludes_old_jobs(self):
        qs = BilbyJob.objects.all()
        result = _apply_time_range_filter(qs, "1m")
        self.assertEqual(list(result.values_list("pk", flat=True)), [self.recent_job.pk])

    def test_one_year_filter_includes_recent_jobs(self):
        qs = BilbyJob.objects.all()
        result = _apply_time_range_filter(qs, "1y")
        self.assertEqual(set(result.values_list("pk", flat=True)), {self.recent_job.pk, self.old_job.pk})

    def test_invalid_time_range_raises(self):
        with self.assertRaisesMessage(Exception, "Unexpected timeRange value invalid"):
            _apply_time_range_filter(BilbyJob.objects.all(), "invalid")

    def test_custom_field_name(self):
        BilbyJob.objects.filter(pk=self.old_job.pk).update(
            creation_time=timezone.now() - timedelta(days=2),
        )
        qs = BilbyJob.objects.all()
        result = _apply_time_range_filter(qs, "1d", field_name="creation_time")
        self.assertEqual(list(result.values_list("pk", flat=True)), [self.recent_job.pk])
