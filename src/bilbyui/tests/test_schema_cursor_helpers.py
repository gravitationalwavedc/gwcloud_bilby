from decimal import Decimal

from graphql_relay.node.node import to_global_id

from bilbyui.schema import MAX_CURSOR_OFFSET, _pad_result_for_cursor, _parse_after_cursor, _parse_file_size
from bilbyui.tests.testcases import BilbyTestCase


class TestParseAfterCursor(BilbyTestCase):
    def test_missing_cursor_stays_none(self):
        kwargs = {}
        _parse_after_cursor(kwargs)
        self.assertIsNone(kwargs["after"])

    def test_none_cursor_stays_none(self):
        kwargs = {"after": None}
        _parse_after_cursor(kwargs)
        self.assertIsNone(kwargs["after"])

    def test_zero_offset_parsed(self):
        kwargs = {"after": to_global_id("BilbyJobNode", 0)}
        _parse_after_cursor(kwargs)
        self.assertEqual(kwargs["after"], 0)

    def test_positive_offset_parsed(self):
        kwargs = {"after": to_global_id("BilbyJobNode", 5)}
        _parse_after_cursor(kwargs)
        self.assertEqual(kwargs["after"], 5)

    def test_huge_positive_offset_capped(self):
        kwargs = {"after": to_global_id("BilbyJobNode", 10**9)}
        _parse_after_cursor(kwargs)
        self.assertEqual(kwargs["after"], MAX_CURSOR_OFFSET)
        self.assertEqual(len(_pad_result_for_cursor(kwargs["after"], ["a", "b"])), MAX_CURSOR_OFFSET + 3)

    def test_malformed_cursor_falls_back_to_none(self):
        kwargs = {"after": "not-a-valid-cursor"}
        _parse_after_cursor(kwargs)
        self.assertIsNone(kwargs["after"])

    def test_non_numeric_id_falls_back_to_none(self):
        kwargs = {"after": to_global_id("BilbyJobNode", "abc")}
        _parse_after_cursor(kwargs)
        self.assertIsNone(kwargs["after"])


class TestPadResultForCursor(BilbyTestCase):
    def test_none_cursor_returns_nodes_unpadded(self):
        self.assertEqual(_pad_result_for_cursor(None, ["a", "b"]), ["a", "b"])

    def test_zero_offset_pads_one_entry(self):
        self.assertEqual(_pad_result_for_cursor(0, ["a", "b"]), [None, "a", "b"])

    def test_positive_offset_pads_offset_plus_one(self):
        self.assertEqual(_pad_result_for_cursor(2, ["a", "b"]), [None, None, None, "a", "b"])


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

    def test_parse_file_size_list_returns_none(self):
        self.assertIsNone(_parse_file_size(["42"]))

    def test_parse_file_size_object_raising_type_error_returns_none(self):
        class RaisingObject:
            def __str__(self):
                raise TypeError("boom")

        self.assertIsNone(_parse_file_size(RaisingObject()))
