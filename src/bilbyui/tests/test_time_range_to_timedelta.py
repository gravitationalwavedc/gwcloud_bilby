from datetime import timedelta

from django.test import override_settings

from bilbyui.services.jobs import _time_range_to_timedelta
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
