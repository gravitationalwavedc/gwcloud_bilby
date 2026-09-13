from decimal import Decimal

from bilbyui.schema import _parse_file_size
from bilbyui.tests.testcases import BilbyTestCase


class TestParseFileSize(BilbyTestCase):
    def test_parse_file_size_numeric_string_returns_decimal(self):
        self.assertEqual(_parse_file_size("123"), Decimal("123"))

    def test_parse_file_size_int_returns_decimal(self):
        self.assertEqual(_parse_file_size(123), Decimal("123"))

    def test_parse_file_size_decimal_returns_decimal(self):
        self.assertEqual(_parse_file_size(Decimal("123.45")), Decimal("123.45"))

    def test_parse_file_size_non_numeric_string_returns_none(self):
        self.assertIsNone(_parse_file_size("not-a-size"))

    def test_parse_file_size_none_returns_none(self):
        self.assertIsNone(_parse_file_size(None))

    def test_parse_file_size_object_raising_type_error_returns_none(self):
        class RaisingObject:
            def __str__(self):
                raise TypeError("boom")

        self.assertIsNone(_parse_file_size(RaisingObject()))
