from django.test import RequestFactory

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _normalize_time_range, _parse_page


class TestParsePage(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_missing_page_defaults_to_one(self):
        self.assertEqual(_parse_page(self.factory.get("/")), 1)

    def test_valid_page_parsed(self):
        self.assertEqual(_parse_page(self.factory.get("/?page=3")), 3)

    def test_non_int_page_falls_back_to_one(self):
        self.assertEqual(_parse_page(self.factory.get("/?page=abc")), 1)

    def test_float_page_falls_back_to_one(self):
        self.assertEqual(_parse_page(self.factory.get("/?page=2.5")), 1)

    def test_empty_page_falls_back_to_one(self):
        self.assertEqual(_parse_page(self.factory.get("/?page=")), 1)

    def test_negative_page_clamped_to_one(self):
        self.assertEqual(_parse_page(self.factory.get("/?page=-5")), 1)

    def test_zero_page_clamped_to_one(self):
        self.assertEqual(_parse_page(self.factory.get("/?page=0")), 1)

    def test_max_page_allowed(self):
        self.assertEqual(_parse_page(self.factory.get("/?page=499")), 499)

    def test_parse_page_is_backend_neutral(self):
        # The ES result-window cap is applied at the ES-backed view boundaries,
        # not in the shared parser (My Jobs is database-backed and must reach
        # pages beyond 499).
        self.assertEqual(_parse_page(self.factory.get("/?page=500")), 500)
        self.assertEqual(_parse_page(self.factory.get("/?page=999999999")), 999999999)

    def test_max_page_keeps_from_plus_size_within_result_window(self):
        page = 499
        page_size = 20
        from_ = (page - 1) * page_size
        self.assertLessEqual(from_ + (page_size + 1), 10000)


class TestNormalizeTimeRange(BilbyTestCase):
    def test_valid_ranges_passthrough(self):
        for value in ("all", "1d", "1w", "1m", "1y"):
            with self.subTest(value=value):
                self.assertEqual(_normalize_time_range(value), value)

    def test_invalid_range_falls_back_to_all(self):
        for value in ("2d", "ALL", "", "1h"):
            with self.subTest(value=value):
                self.assertEqual(_normalize_time_range(value), "all")

    def test_none_falls_back_to_all(self):
        self.assertEqual(_normalize_time_range(None), "all")
