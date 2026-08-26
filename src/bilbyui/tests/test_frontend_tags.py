from datetime import UTC, datetime, timedelta
from datetime import timezone as dt_timezone

from django.template import Context, Template
from django.utils import timezone

from bilbyui.templatetags.frontend_tags import basename, utc_timestamp
from bilbyui.tests.testcases import BilbyTestCase


class TestUtcTimestampFilter(BilbyTestCase):
    def test_aware_utc_datetime(self):
        value = datetime(2026, 8, 20, 14, 32, 0, tzinfo=UTC)
        self.assertEqual(utc_timestamp(value), "2026-08-20 14:32 UTC")

    def test_aware_non_utc_datetime_converts_to_utc(self):
        value = datetime(2026, 8, 21, 0, 32, 0, tzinfo=dt_timezone(timedelta(hours=10)))
        # 2026-08-21 00:32+10:00 == 2026-08-20 14:32 UTC
        self.assertEqual(utc_timestamp(value), "2026-08-20 14:32 UTC")

    def test_iso_string_with_z_suffix(self):
        self.assertEqual(utc_timestamp("2026-08-20T14:32:00Z"), "2026-08-20 14:32 UTC")

    def test_iso_string_with_explicit_offset(self):
        self.assertEqual(utc_timestamp("2026-08-21T00:32:00+10:00"), "2026-08-20 14:32 UTC")

    def test_naive_datetime_assumed_utc(self):
        value = datetime(2026, 8, 20, 14, 32, 45)
        self.assertEqual(utc_timestamp(value), "2026-08-20 14:32 UTC")

    def test_none_returns_empty_string(self):
        self.assertEqual(utc_timestamp(None), "")

    def test_empty_string_returns_empty_string(self):
        self.assertEqual(utc_timestamp(""), "")

    def test_garbage_string_returns_empty_string(self):
        self.assertEqual(utc_timestamp("not-a-date"), "")

    def test_filter_registered_in_template_engine(self):
        template = Template("{% load frontend_tags %}{{ value|utc_timestamp }}")
        aware = timezone.make_aware(datetime(2026, 8, 20, 14, 32, 0), UTC)
        rendered = template.render(Context({"value": aware}))
        self.assertEqual(rendered, "2026-08-20 14:32 UTC")


class TestBasenameFilter(BilbyTestCase):
    def test_deep_path_returns_text_after_last_slash(self):
        self.assertEqual(basename("/home/buffy/bilby/O3/GW150914/output/posteriors.h5"), "posteriors.h5")

    def test_slashless_string_returned_unchanged(self):
        self.assertEqual(basename("results.h5"), "results.h5")

    def test_trailing_slash_falls_back_to_full_value(self):
        self.assertEqual(basename("/a/b/data/"), "/a/b/data/")

    def test_empty_string_returned_unchanged(self):
        self.assertEqual(basename(""), "")

    def test_none_returns_empty_string(self):
        self.assertEqual(basename(None), "")

    def test_non_string_input_coerced_via_str(self):
        self.assertEqual(basename(42), "42")

    def test_filter_registered_in_template_engine(self):
        template = Template("{% load frontend_tags %}{{ value|basename }}")
        rendered = template.render(Context({"value": "/x/y/data.h5"}))
        self.assertEqual(rendered, "data.h5")
