import logging

from django.test import SimpleTestCase

from bilbyui.utils.search_trigger_time import max_finite_time, normalize_trigger

logger = logging.getLogger(__name__)


def normalize_source_row(row_id, raw):
    normalized = normalize_trigger(raw)
    if normalized is None:
        logger.warning("rejected trigger source row_id=%s", row_id)
    return normalized


class NormalizeTriggerTests(SimpleTestCase):
    def test_finite_ints_and_floats(self):
        cases = (
            (123, 123.0),
            (-7, -7.0),
            (123.5, 123.5),
            (0, 0.0),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_trigger(raw), expected)

    def test_numeric_strings_are_trimmed(self):
        cases = (
            (" 123.5 ", 123.5),
            ("\t-7\n", -7.0),
            ("0", 0.0),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_trigger(raw), expected)

    def test_json_numbers_and_numeric_strings(self):
        cases = (
            ("1.25", 1.25),
            ("1e3", 1000.0),
            ('"123.5"', 123.5),
            ('"  -2.5  "', -2.5),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_trigger(raw), expected)

    def test_null_empty_whitespace_malformed_and_containers_are_rejected(self):
        rejected = (
            None,
            "null",
            '"null"',
            "",
            " \t\n ",
            "not-a-number",
            "{malformed",
            "[]",
            "{}",
            "[123]",
            '{"value": 123}',
        )
        for raw in rejected:
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_trigger(raw))

    def test_booleans_are_rejected_before_numeric_handling(self):
        for raw in (True, False, "true", "false"):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_trigger(raw))

    def test_non_finite_and_overflow_values_are_rejected(self):
        rejected = (
            float("nan"),
            float("inf"),
            float("-inf"),
            "NaN",
            "Infinity",
            "-Infinity",
            '"NaN"',
            '"Infinity"',
            '"-Infinity"',
            "1e309",
            "-1e309",
            10**10000,
        )
        for index, raw in enumerate(rejected):
            with self.subTest(case=index, type=type(raw).__name__):
                self.assertIsNone(normalize_trigger(raw))

    def test_no_plausibility_sentinel_or_zero_rule(self):
        for raw, expected in (
            (0, 0.0),
            ("0", 0.0),
            (1126259462.391, 1126259462.391),
            ("-1", -1.0),
            ("1e100", 1e100),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_trigger(raw), expected)

    def test_caller_can_log_rejected_row_id_without_source_value(self):
        source_value = "private-malformed-trigger"
        with self.assertLogs(logger, level="WARNING") as captured:
            self.assertIsNone(normalize_source_row(4815, source_value))

        output = "\n".join(captured.output)
        self.assertIn("row_id=4815", output)
        self.assertNotIn(source_value, output)


class MaxFiniteTimeRegressionTests(SimpleTestCase):
    def test_remains_strictly_numeric_only(self):
        values = (
            "999",
            '"1000"',
            True,
            False,
            None,
            float("nan"),
            float("inf"),
            float("-inf"),
            12,
            14.5,
        )
        self.assertEqual(max_finite_time(values), 14.5)

    def test_returns_none_without_finite_numeric_input(self):
        self.assertIsNone(
            max_finite_time(
                (
                    "123.5",
                    True,
                    None,
                    float("nan"),
                    float("inf"),
                )
            )
        )

