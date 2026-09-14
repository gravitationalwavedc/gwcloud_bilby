import unittest
from unittest.mock import MagicMock

from gwflow_ingest import resolve_libraries


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


if __name__ == "__main__":
    unittest.main()
