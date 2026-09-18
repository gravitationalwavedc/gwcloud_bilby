import unittest
from unittest.mock import MagicMock

from gwflow_ingest import resolve_libraries
from libraries import normalise_libraries


class TestResolveLibraries(unittest.TestCase):
    """Direct unit tests for ``resolve_libraries``.

    Asserts the documented return contract: a list of normalised library
    names to set, ``[]`` to clear libraries (no current version), and
    ``None`` to leave libraries unchanged (endpoint failure / malformed
    data). The portal client is mocked so each branch is exercised in
    isolation.
    """

    def _client(self, versions):
        client = MagicMock()
        client.get_versions.return_value = versions
        return client

    def test_get_versions_raising_returns_none(self):
        client = MagicMock()
        client.get_versions.side_effect = Exception("versions down")
        self.assertIsNone(resolve_libraries(client, "S1"))

    def test_non_list_versions_returns_none(self):
        client = self._client("malformed")
        self.assertIsNone(resolve_libraries(client, "S1"))

    def test_no_current_version_returns_empty(self):
        client = self._client([{"is_current": False, "libraries": ["bilby"]}])
        self.assertEqual(resolve_libraries(client, "S1"), [])

    def test_multiple_current_versions_uses_first(self):
        client = self._client(
            [
                {"is_current": True, "libraries": ["bilby"]},
                {"is_current": True, "libraries": ["gwpy"]},
            ]
        )
        self.assertEqual(resolve_libraries(client, "S1"), ["bilby"])

    def test_malformed_libraries_returns_none(self):
        for shape in (None, "bilby", 42, {"a": 1}, True):
            client = self._client([{"is_current": True, "libraries": shape}])
            self.assertIsNone(resolve_libraries(client, "S1"))

    def test_missing_libraries_member_returns_none(self):
        client = self._client([{"is_current": True}])
        self.assertIsNone(resolve_libraries(client, "S1"))

    def test_normalise_path_returns_list(self):
        client = self._client([{"is_current": True, "libraries": ["  bilby  ", "bilby", "gwpy"]}])
        self.assertEqual(resolve_libraries(client, "S1"), ["bilby", "gwpy"])


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
