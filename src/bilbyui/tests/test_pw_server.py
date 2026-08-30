from unittest.mock import patch

from bilbyui.tests.e2e import pw_server
from bilbyui.tests.testcases import BilbyTestCase


class CheckNodeAvailableTestCase(BilbyTestCase):
    """Deterministic unit tests for ``_check_node_available`` (no real node)."""

    def _run_check(self, stdout="", returncode=0, stderr=""):
        result = pw_server.subprocess.CompletedProcess(
            args=["node", "--version"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
        with patch.object(pw_server.subprocess, "run", return_value=result):
            pw_server._check_node_available()

    def test_node_22_passes(self):
        self._run_check(stdout="v22.14.0\n")

    def test_node_20_passes(self):
        self._run_check(stdout="v20.11.1\n")

    def test_node_18_raises_with_found_version(self):
        with self.assertRaisesRegex(RuntimeError, "18.20.4"):
            self._run_check(stdout="v18.20.4\n")

    def test_node_16_raises(self):
        with self.assertRaisesRegex(RuntimeError, "16.20.2"):
            self._run_check(stdout="v16.20.2\n")

    def test_missing_node_raises(self):
        with patch.object(
            pw_server.subprocess,
            "run",
            side_effect=FileNotFoundError("node not found"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Node.js 20 or later"):
                pw_server._check_node_available()

    def test_failed_command_raises(self):
        with patch.object(
            pw_server.subprocess,
            "run",
            side_effect=pw_server.subprocess.CalledProcessError(returncode=127, cmd=["node", "--version"]),
        ):
            with self.assertRaisesRegex(RuntimeError, "Node.js 20 or later"):
                pw_server._check_node_available()

    def test_malformed_output_raises(self):
        with self.assertRaisesRegex(RuntimeError, "Node.js 20 or later"):
            self._run_check(stdout="garbage\n")

    def test_output_without_v_prefix_parses(self):
        self._run_check(stdout="22.14.0\n")

    def test_empty_output_raises(self):
        with self.assertRaisesRegex(RuntimeError, "Node.js 20 or later"):
            self._run_check(stdout="")
