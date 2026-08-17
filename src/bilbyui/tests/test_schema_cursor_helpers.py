from graphql_relay.node.node import to_global_id

from bilbyui.schema import _pad_result_for_cursor, _parse_after_cursor
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
