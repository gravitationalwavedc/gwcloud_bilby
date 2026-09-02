from django.test import RequestFactory

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _normalize_time_range, _parse_page, _resolve_page


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


class TestResolvePage(BilbyTestCase):
    def test_service_down_passthrough(self):
        result = {"state": "down"}

        def fetch(page):
            self.fail("fetch must not be called when service is down")

        resolved, page = _resolve_page(result, 3, 20, fetch)
        self.assertIs(resolved, result)
        self.assertEqual(page, 3)

    def test_in_range_page_noop(self):
        result = {"state": "up", "total": 100}

        def fetch(page):
            self.fail("fetch must not be called for an in-range page")

        resolved, page = _resolve_page(result, 2, 20, fetch)
        self.assertIs(resolved, result)
        self.assertEqual(page, 2)

    def test_out_of_range_page_clamped_and_refetched(self):
        result = {"state": "up", "total": 41}
        fetched = []

        def fetch(page):
            fetched.append(page)
            return {"state": "up", "total": 41}

        resolved, page = _resolve_page(result, 99, 20, fetch)
        self.assertEqual(page, 3)
        self.assertEqual(fetched, [3])
        self.assertIsNot(resolved, result)

    def test_zero_page_size_defaults_to_one_page(self):
        result = {"state": "up", "total": 100}
        fetched = []

        def fetch(page):
            fetched.append(page)
            return {"state": "up", "total": 100}

        resolved, page = _resolve_page(result, 5, 0, fetch)
        self.assertEqual(page, 1)
        self.assertEqual(fetched, [1])
        self.assertIsNot(resolved, result)
