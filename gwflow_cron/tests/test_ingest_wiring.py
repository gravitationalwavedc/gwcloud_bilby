import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import gwflow_ingest
import settings
from tests.base import GWFlowTestBase


class TestParseArgs(unittest.TestCase):
    def test_default_backfill_false(self):
        parsed = gwflow_ingest.parse_args([])
        self.assertFalse(parsed.backfill)

    def test_backfill_flag_true(self):
        parsed = gwflow_ingest.parse_args(["--backfill"])
        self.assertTrue(parsed.backfill)


class TestIngestWiring(GWFlowTestBase):
    @patch("gwflow_ingest.phase_file_mirror")
    @patch("gwflow_ingest.phase_bilby_children")
    @patch("gwflow_ingest.phase_metadata")
    @patch("gwflow_ingest.JobControllerClient")
    @patch("gwflow_ingest.GWCloud")
    def test_run_constructs_clients_and_wires_to_all_phases(
        self, mock_gwc_cls, mock_jc_cls, mock_phase_metadata, mock_phase_bilby, mock_phase_file_mirror
    ):
        mock_gwc = MagicMock()
        mock_jc = MagicMock()
        mock_gwc_cls.return_value = mock_gwc
        mock_jc_cls.return_value = mock_jc

        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with (
                patch.object(settings, "DB_PATH", tmp.name),
                patch.object(settings, "GWCLOUD_TOKEN", "test-token-123"),
                patch.object(settings, "GWCLOUD_ENDPOINT", "https://custom.gwcloud.org.au/graphql"),
                patch.object(settings, "JOB_CONTROLLER_API_URL", "https://custom.jc.org.au/api"),
                patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", "test-jwt-secret"),
                patch.object(settings, "JOB_CONTROLLER_CLUSTER", "cit_cluster"),
                patch.object(settings, "JOB_CONTROLLER_BUNDLE", "test-bundle"),
            ):
                result = gwflow_ingest.run([])
                self.assertEqual(result, 0)

        # 1. Assert GWCloud construction
        mock_gwc_cls.assert_called_once_with(
            token="test-token-123",
            endpoint="https://custom.gwcloud.org.au/graphql",
        )

        # 2. Assert JobControllerClient construction
        mock_jc_cls.assert_called_once_with(
            api_url="https://custom.jc.org.au/api",
            jwt_secret="test-jwt-secret",
            user_id=0,
            cluster="cit_cluster",
            bundle="test-bundle",
        )

        # 3. Assert phase_metadata wiring
        mock_phase_metadata.assert_called_once()
        self.assertEqual(mock_phase_metadata.call_args.kwargs.get("gwc_client"), mock_gwc)
        self.assertIsNotNone(mock_phase_metadata.call_args.kwargs.get("con"))

        # 4. Assert phase_bilby_children wiring
        mock_phase_bilby.assert_called_once()
        self.assertEqual(mock_phase_bilby.call_args.kwargs.get("gwc_client"), mock_gwc)
        self.assertEqual(mock_phase_bilby.call_args.kwargs.get("jc"), mock_jc)
        self.assertIsNotNone(mock_phase_bilby.call_args.kwargs.get("con"))

        # 5. Assert phase_file_mirror wiring
        mock_phase_file_mirror.assert_called_once()
        self.assertEqual(mock_phase_file_mirror.call_args.kwargs.get("gwc_client"), mock_gwc)
        self.assertEqual(mock_phase_file_mirror.call_args.kwargs.get("jc"), mock_jc)
        self.assertIsNotNone(mock_phase_file_mirror.call_args.kwargs.get("con"))

    def test_run_fails_fast_on_missing_settings(self):
        # Missing GWCLOUD_TOKEN
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with (
                patch.object(settings, "DB_PATH", tmp.name),
                patch.object(settings, "GWCLOUD_TOKEN", None),
            ):
                with self.assertRaises(SystemExit) as cm:
                    gwflow_ingest.run([])
                self.assertEqual(cm.exception.code, 1)

        # Missing JOB_CONTROLLER_JWT_SECRET
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with (
                patch.object(settings, "DB_PATH", tmp.name),
                patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", None),
            ):
                with self.assertRaises(SystemExit) as cm:
                    gwflow_ingest.run([])
                self.assertEqual(cm.exception.code, 1)

        # Missing JOB_CONTROLLER_BUNDLE
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            with (
                patch.object(settings, "DB_PATH", tmp.name),
                patch.object(settings, "JOB_CONTROLLER_BUNDLE", ""),
            ):
                with self.assertRaises(SystemExit) as cm:
                    gwflow_ingest.run([])
                self.assertEqual(cm.exception.code, 1)

    @patch("gwflow_ingest.fetch_to_staging")
    @patch("gwflow_ingest.PortalClient")
    @patch("gwflow_ingest.JobControllerClient")
    @patch("gwflow_ingest.GWCloud")
    def test_end_to_end_mocked_run(self, mock_gwc_cls, mock_jc_cls, mock_portal_cls, mock_fetch):
        mock_gwc = MagicMock()
        mock_jc = MagicMock()
        mock_portal = MagicMock()

        mock_gwc_cls.return_value = mock_gwc
        mock_jc_cls.return_value = mock_jc
        mock_portal_cls.return_value = mock_portal

        # Portal returns 1 changed superevent
        mock_portal.iter_changed.return_value = [
            {
                "sname": "S260101a",
                "commit_timestamp": "2026-01-01T12:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha-test-123",
            }
        ]
        mock_portal.get_superevent.return_value = {
            "sname": "S260101a",
            "raw_payload": {"sname": "S260101a", "event": "GW260101"},
            "libraries": [{"name": "bilby"}],
        }
        mock_portal.iter_current_snames.return_value = ["S260101a"]
        mock_gwc.get_gwflow_job_list.return_value = []

        # File mirror queue has 1 pending file
        pending_file = SimpleNamespace(
            id="f-101",
            sname="S260101a",
            analysis_uid="uid-101",
            path="/data/file.h5",
            file_name="file.h5",
            md5_sum="hash123",
        )
        mock_gwc.get_gwflow_pending_files.return_value = [pending_file]

        with tempfile.TemporaryDirectory() as tmpdir:
            staged_file = Path(tmpdir) / "staged.h5"
            staged_file.write_bytes(b"content")
            mock_fetch.return_value = staged_file

            db_file = Path(tmpdir) / "gwflow.db"
            with (
                patch.object(settings, "DB_PATH", str(db_file)),
                patch.object(settings, "GWCLOUD_TOKEN", "token"),
                patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", "secret"),
                patch.object(settings, "JOB_CONTROLLER_BUNDLE", "bundle"),
            ):
                with self.assertLogs("gwflow_ingest", level="INFO") as log_cm:
                    result = gwflow_ingest.run([])
                    self.assertEqual(result, 0)

                log_output = "\n".join(log_cm.output)
                # Verify that no phase skipped due to missing clients
                self.assertNotIn("clients not wired (B1) - skipping", log_output)
                self.assertIn("Starting phase_metadata", log_output)
                self.assertIn("Completed phase_metadata", log_output)
                self.assertIn("Starting phase_file_mirror", log_output)
                self.assertIn("Completed phase_file_mirror", log_output)
                # Phase order: metadata -> file_mirror -> bilby_children (bilby is secondary)
                self.assertLess(
                    log_output.index("Starting phase_metadata"), log_output.index("Starting phase_file_mirror")
                )
                self.assertLess(
                    log_output.index("Starting phase_file_mirror"), log_output.index("Starting phase_bilby_children")
                )

        # Verify metadata upsert
        mock_gwc.upsert_gwflow_job.assert_called_once_with(
            sname="S260101a",
            schema_version="1.0",
            metadata={"sname": "S260101a", "event": "GW260101"},
            libraries=["bilby"],
            is_pruned=False,
            current_history_id="sha-test-123",
            current_history_timestamp="2026-01-01T12:00:00Z",
            files=[],
        )

        # Verify file upload
        mock_gwc.upload_gwflow_file.assert_called_once_with("f-101", staged_file)

    def test_phase_bilby_children_signature_accepts_args(self):
        # Verify that phase_bilby_children can be called with clients without error
        try:
            gwflow_ingest.phase_bilby_children(gwc_client=MagicMock(), jc=MagicMock(), con=self.con)
        except TypeError as e:
            self.fail(f"phase_bilby_children raised TypeError: {e}")

    @patch("gwflow_ingest.fetch_to_staging")
    @patch("gwflow_ingest.PortalClient")
    @patch("gwflow_ingest.JobControllerClient")
    @patch("gwflow_ingest.GWCloud")
    def test_end_to_end_prunes_deleted_superevents(self, mock_gwc_cls, mock_jc_cls, mock_portal_cls, mock_fetch):
        mock_gwc = MagicMock()
        mock_portal = MagicMock()
        mock_gwc_cls.return_value = mock_gwc
        mock_jc_cls.return_value = MagicMock()
        mock_portal_cls.return_value = mock_portal

        mock_portal.iter_changed.return_value = []
        mock_portal.iter_current_snames.return_value = ["S_ACTIVE"]
        mock_gwc.get_gwflow_job_list.return_value = [{"sname": "S_ACTIVE"}, {"sname": "S_DELETED"}]
        mock_gwc.get_gwflow_pending_files.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "gwflow.db"
            with (
                patch.object(settings, "DB_PATH", str(db_file)),
                patch.object(settings, "GWCLOUD_TOKEN", "token"),
                patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", "secret"),
                patch.object(settings, "JOB_CONTROLLER_BUNDLE", "bundle"),
            ):
                result = gwflow_ingest.run([])
                self.assertEqual(result, 0)

        mock_gwc.upsert_gwflow_job.assert_called_once_with(sname="S_DELETED", is_pruned=True)


if __name__ == "__main__":
    unittest.main()
