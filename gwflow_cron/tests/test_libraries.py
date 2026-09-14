import unittest

from libraries import normalise_libraries


class TestNormaliseLibraries(unittest.TestCase):
    """Parity tests for ``normalise_libraries``.

    These assert the exact expected values, mirroring the semantics of
    ``bilbyui.utils.gwflow_version.normalise_libraries``: drop non-strings,
    strip whitespace, drop blanks, case-sensitively dedupe, preserve
    first-seen order, and return [] for None.
    """

    def test_none_returns_empty(self):
        self.assertEqual(normalise_libraries(None), [])

    def test_empty_list(self):
        self.assertEqual(normalise_libraries([]), [])

    def test_drops_non_strings(self):
        self.assertEqual(
            normalise_libraries(["bilby", 123, None, 4.5, ["x"], {"a": 1}, True, b"bytes"]),
            ["bilby"],
        )

    def test_strips_whitespace(self):
        self.assertEqual(
            normalise_libraries(["  bilby  ", "\tbilby_pipe\n", "  "]),
            ["bilby", "bilby_pipe"],
        )

    def test_drops_blank_strings(self):
        self.assertEqual(
            normalise_libraries(["bilby", "", "   ", "\t\n", "bilby_pipe"]),
            ["bilby", "bilby_pipe"],
        )

    def test_case_sensitive_dedupe(self):
        self.assertEqual(
            normalise_libraries(["bilby", "Bilby", "BILBY", "bilby"]),
            ["bilby", "Bilby", "BILBY"],
        )

    def test_dedupe_preserves_first_seen_order(self):
        self.assertEqual(
            normalise_libraries(["a", "b", "a", "c", "b", "d"]),
            ["a", "b", "c", "d"],
        )

    def test_dedupe_after_trimming(self):
        self.assertEqual(
            normalise_libraries(["  a  ", "a", " b ", "b"]),
            ["a", "b"],
        )

    def test_representative_combined_input(self):
        raw = ["bilby", "", "  bilby_pipe  ", None, 42, "bilby", "Bilby", "   ", "bilby_pipe"]
        self.assertEqual(normalise_libraries(raw), ["bilby", "bilby_pipe", "Bilby"])

    def test_preserves_original_order_of_distinct_values(self):
        self.assertEqual(
            normalise_libraries(["z", "y", "x", "z"]),
            ["z", "y", "x"],
        )


if __name__ == "__main__":
    unittest.main()
