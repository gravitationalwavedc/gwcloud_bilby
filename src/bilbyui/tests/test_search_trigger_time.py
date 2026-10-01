import unittest

from bilbyui.utils.search_trigger_time import max_finite_time


class TestMaxFiniteTime(unittest.TestCase):
    def test_returns_none_without_finite_numeric_value(self):
        rejected_values = [
            True,
            False,
            "123.4",
            "not-a-number",
            float("nan"),
            float("inf"),
            float("-inf"),
        ]

        self.assertIsNone(max_finite_time([]))
        self.assertIsNone(max_finite_time([None, None]))
        self.assertIsNone(max_finite_time(rejected_values))

    def test_returns_maximum_finite_numeric_value(self):
        result = max_finite_time([-12, 4.5, 9, 3.25])

        self.assertEqual(result, 9.0)
        self.assertIsInstance(result, float)

    def test_retains_zero_and_negative_values(self):
        self.assertEqual(max_finite_time([-8, -2.5]), -2.5)
        self.assertEqual(max_finite_time([-8, 0, -2.5]), 0.0)

    def test_valid_finite_value_wins_mixed_input(self):
        values = [
            None,
            True,
            False,
            "21",
            "not-a-number",
            float("nan"),
            float("inf"),
            float("-inf"),
            -4,
            12.5,
        ]

        self.assertEqual(max_finite_time(values), 12.5)
