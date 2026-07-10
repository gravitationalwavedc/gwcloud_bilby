from decimal import Decimal

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.gen_parameter_output import to_dec


class TestToDec(BilbyTestCase):
    def test_returns_decimal_unchanged(self):
        value = Decimal("1.25")
        self.assertIs(to_dec(value), value)

    def test_returns_none_for_none(self):
        self.assertIsNone(to_dec(None))

    def test_parses_numeric_string(self):
        self.assertEqual(to_dec("3.14"), Decimal("3.14"))

    def test_returns_non_numeric_string_unchanged(self):
        self.assertEqual(to_dec("not-a-number"), "not-a-number")

    def test_converts_fractional_float(self):
        self.assertEqual(to_dec(1.5), Decimal("1.5"))

    def test_converts_whole_float_to_integer_decimal(self):
        self.assertEqual(to_dec(2.0), Decimal(2))

    def test_converts_whole_int(self):
        self.assertEqual(to_dec(42), Decimal(42))
