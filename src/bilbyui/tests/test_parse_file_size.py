from decimal import Decimal

from bilbyui.schema import _parse_file_size
from bilbyui.tests.testcases import BilbyTestCase


class TestParseFileSize(BilbyTestCase):
    def test_valid_numeric_string_returns_decimal(self):
        self.assertEqual(_parse_file_size("42"), Decimal("42"))

    def test_not_a_number_returns_none(self):
        self.assertIsNone(_parse_file_size("not-a-number"))

    def test_none_returns_none(self):
        self.assertIsNone(_parse_file_size(None))

    def test_list_returns_none(self):
        self.assertIsNone(_parse_file_size(["42"]))

    def test_object_returns_none(self):
        self.assertIsNone(_parse_file_size(object()))
