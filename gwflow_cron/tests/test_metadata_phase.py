import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
    from tests.base import GWFlowTestBase
except ImportError:
    from base import GWFlowTestBase

import settings
import state
from gwflow_ingest import gwc_known_unpruned_snames, phase_metadata


class TestMetadataPhase(GWFlowTestBase):
    def test_happy_path_delta_sync_and_watermark_advancement(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            "non_dict_row",
            {"sname": "S_MISSING_TS"},
            {
                "sname": "S260101a",
                "commit_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha1",
            },
            {
                "sname": "S260102b",
                "commit_timestamp": "2026-01-02T12:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha2",
            },
        ]
        mock_portal.get_superevent.side_effect = lambda sname: {
            "sname": sname,
            "raw_payload": {"sname": sname},
        }
        mock_portal.get_versions.return_value = [{"is_current": True, "libraries": ["bilby"]}]
        mock_portal.iter_current_snames.return_value = ["S260101a", "S260102b"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        cur = self.con.cursor()
        phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        # Assert upserts
        self.assertEqual(mock_gwc.upsert_gwflow_job.call_count, 2)
        mock_gwc.upsert_gwflow_job.assert_any_call(
            sname="S260101a",
            schema_version="1.0",
            metadata={"sname": "S260101a"},
            libraries=["bilby"],
            is_pruned=False,
            current_history_id="sha1",
            current_history_timestamp="2026-01-01T10:00:00Z",
            files=[],
        )

        # Assert state updated to latest row
        self.assertEqual(state.get_watermark(cur), "2026-01-02T12:00:00Z")
        self.assertEqual(state.get_last_sname(cur), "S260102b")

    def test_malformed_libraries_entry_is_skipped(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {
                "sname": "S_LIBS",
                "commit_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha1",
            },
        ]
        mock_portal.get_superevent.return_value = {
            "sname": "S_LIBS",
            "raw_payload": {"sname": "S_LIBS"},
        }
        mock_portal.get_versions.return_value = [
            {"is_current": True, "libraries": [None, "  ", "bilby", {"foo": "bar"}, "gwpy", 123]}
        ]
        mock_portal.iter_current_snames.return_value = ["S_LIBS"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        mock_gwc.upsert_gwflow_job.assert_called_once_with(
            sname="S_LIBS",
            schema_version="1.0",
            metadata={"sname": "S_LIBS"},
            libraries=["bilby", "gwpy"],
            is_pruned=False,
            current_history_id="sha1",
            current_history_timestamp="2026-01-01T10:00:00Z",
            files=[],
        )

    def test_non_dict_superevent_detail_is_skipped_with_warning(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {
                "sname": "S_BAD_DETAIL",
                "commit_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
            },
        ]
        mock_portal.get_superevent.return_value = "malformed-response"
        mock_portal.iter_current_snames.return_value = ["S_BAD_DETAIL"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        cur = self.con.cursor()
        with self.assertLogs("gwflow_ingest", level="WARNING") as logs:
            phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        mock_gwc.upsert_gwflow_job.assert_not_called()
        self.assertEqual(state.get_failure_count(cur, "S_BAD_DETAIL"), 0)
        self.assertIn("non-dict superevent detail", " ".join(logs.output))

    def test_tie_resume(self):
        cur = self.con.cursor()
        # Set watermark and last_sname in state
        state.set_watermark(self.con, cur, "2026-01-01T10:00:00Z")
        state.set_last_sname(self.con, cur, "S260101a")

        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            # Earlier tie: should be skipped
            {
                "sname": "S260101a",
                "commit_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
            },
            # Same timestamp, later sname: should be processed
            {
                "sname": "S260101b",
                "commit_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
            },
        ]
        mock_portal.get_superevent.return_value = {"sname": "S260101b", "raw_payload": {}}
        mock_portal.iter_current_snames.return_value = ["S260101a", "S260101b"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        # Only S260101b should be processed
        self.assertEqual(mock_gwc.upsert_gwflow_job.call_count, 1)
        self.assertEqual(state.get_last_sname(cur), "S260101b")

    def test_per_sname_failure_and_watermark_held_back(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {
                "sname": "S_OK1",
                "commit_timestamp": "2026-01-01T09:00:00Z",
                "schema_version": "1.0",
            },
            {
                "sname": "S_FAIL",
                "commit_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
            },
            {
                "sname": "S_OK2",
                "commit_timestamp": "2026-01-01T11:00:00Z",
                "schema_version": "1.0",
            },
        ]

        def get_detail_side_effect(sname):
            if sname == "S_FAIL":
                raise ValueError("Portal API temporary failure")
            return {"sname": sname, "raw_payload": {}}

        mock_portal.get_superevent.side_effect = get_detail_side_effect
        mock_portal.iter_current_snames.return_value = ["S_OK1", "S_FAIL", "S_OK2"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        cur = self.con.cursor()
        phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        # S_OK1 succeeded, S_FAIL failed, S_OK2 succeeded
        self.assertEqual(state.get_failure_count(cur, "S_FAIL"), 1)
        self.assertEqual(state.get_failure_count(cur, "S_OK2"), 0)

        # Watermark must be held back at S_OK1's timestamp so S_FAIL is retried on next run!
        self.assertEqual(state.get_watermark(cur), "2026-01-01T09:00:00Z")
        self.assertEqual(state.get_last_sname(cur), "S_OK1")

    def test_prune_diffing(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = []
        # Upstream only has S_KEEP
        mock_portal.iter_current_snames.return_value = ["S_KEEP"]

        mock_gwc = MagicMock()
        # GWCloud currently has S_KEEP and S_DELETED as object with .sname attribute
        mock_gwc.get_gwflow_job_list.return_value = [
            {"sname": "S_KEEP"},
            SimpleNamespace(sname="S_DELETED"),
        ]

        phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        # S_DELETED should be marked is_pruned=True
        mock_gwc.upsert_gwflow_job.assert_called_once_with(sname="S_DELETED", is_pruned=True)

    def test_gwc_known_unpruned_snames_helpers(self):
        with self.assertRaises(AttributeError):
            gwc_known_unpruned_snames(object())

    def test_gwc_known_unpruned_snames_skips_entries_without_sname(self):
        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = [
            {"sname": "S_OK"},
            {},
            SimpleNamespace(sname="S_OBJ"),
            SimpleNamespace(),
            "S_STR",
        ]

        self.assertEqual(gwc_known_unpruned_snames(mock_gwc), {"S_OK", "S_OBJ"})

    @patch("portal.PortalClient")
    def test_phase_metadata_creates_connection_when_con_is_none(self, mock_portal_cls):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = []
        mock_portal.iter_current_snames.return_value = []
        mock_portal_cls.return_value = mock_portal

        phase_metadata(gwc_client=MagicMock())

    def test_non_dict_raw_payload_is_normalized_to_empty_dict(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {
                "sname": "S_RAW",
                "commit_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha1",
            },
        ]
        mock_portal.get_superevent.return_value = {
            "sname": "S_RAW",
            "raw_payload": "not-a-dict",
        }
        mock_portal.get_versions.return_value = [{"is_current": True, "libraries": []}]
        mock_portal.iter_current_snames.return_value = ["S_RAW"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        mock_gwc.upsert_gwflow_job.assert_called_once_with(
            sname="S_RAW",
            schema_version="1.0",
            metadata={},
            libraries=[],
            is_pruned=False,
            current_history_id="sha1",
            current_history_timestamp="2026-01-01T10:00:00Z",
            files=[],
        )

    def test_max_retry_attempts_reached_logs_error(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {"sname": "S_CAP", "commit_timestamp": "2026-01-01T10:00:00Z", "schema_version": "1.0"},
        ]
        mock_portal.get_superevent.side_effect = ValueError("Persistent Failure")
        mock_portal.iter_current_snames.return_value = ["S_CAP"]

        cur = self.con.cursor()
        # Pre-seed failure count to MAX_RETRY_ATTEMPTS - 1
        for _ in range(settings.MAX_RETRY_ATTEMPTS - 1):
            state.record_failure(self.con, cur, "S_CAP", "earlier failure")

        phase_metadata(portal_client=mock_portal, gwc_client=MagicMock(), con=self.con)
        self.assertEqual(state.get_failure_count(cur, "S_CAP"), settings.MAX_RETRY_ATTEMPTS)

    def test_iter_current_snames_exception(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = []
        mock_portal.iter_current_snames.side_effect = Exception("Prune API Error")

        phase_metadata(portal_client=mock_portal, gwc_client=MagicMock(), con=self.con)

    def _changed_row(self, sname="S_LIB"):
        return {
            "sname": sname,
            "commit_timestamp": "2026-01-01T10:00:00Z",
            "schema_version": "1.0",
            "commit_sha": "sha1",
        }

    def _run_phase(self, mock_portal, sname="S_LIB"):
        mock_portal.iter_changed.return_value = [self._changed_row(sname)]
        mock_portal.get_superevent.return_value = {"sname": sname, "raw_payload": {}}
        mock_portal.iter_current_snames.return_value = [sname]
        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []
        phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)
        return mock_gwc

    def test_detail_has_no_libraries_but_current_version_does(self):
        mock_portal = MagicMock()
        mock_portal.get_versions.return_value = [{"is_current": True, "libraries": ["bilby", "gwpy"]}]
        mock_gwc = self._run_phase(mock_portal)

        mock_gwc.upsert_gwflow_job.assert_called_once()
        self.assertEqual(mock_gwc.upsert_gwflow_job.call_args.kwargs["libraries"], ["bilby", "gwpy"])

    def test_get_versions_failure_preserves_libraries(self):
        mock_portal = MagicMock()
        mock_portal.get_versions.side_effect = Exception("versions down")
        mock_gwc = self._run_phase(mock_portal)

        mock_gwc.upsert_gwflow_job.assert_called_once()
        self.assertIsNone(mock_gwc.upsert_gwflow_job.call_args.kwargs["libraries"])

    def test_non_list_versions_preserves_libraries(self):
        mock_portal = MagicMock()
        mock_portal.get_versions.return_value = "malformed"
        mock_gwc = self._run_phase(mock_portal)

        mock_gwc.upsert_gwflow_job.assert_called_once()
        self.assertIsNone(mock_gwc.upsert_gwflow_job.call_args.kwargs["libraries"])

    def test_malformed_current_version_libraries_member_preserves(self):
        # A current version whose libraries member is not a list is malformed:
        # it must preserve existing libraries (pass None), never normalise a
        # generic iterable into a corrupt or empty authoritative value.
        malformed_shapes = [
            "bilby",  # string would otherwise become individual characters
            {"name": "bilby"},  # mapping would otherwise become its keys
            123,  # scalar would otherwise raise TypeError and fail the row
            None,  # null is malformed, not an explicit empty list
        ]
        for idx, shape in enumerate(malformed_shapes):
            with self.subTest(shape=shape):
                mock_portal = MagicMock()
                mock_portal.get_versions.return_value = [{"is_current": True, "libraries": shape}]
                mock_gwc = self._run_phase(mock_portal, sname=f"S_MAL{idx}")

                mock_gwc.upsert_gwflow_job.assert_called_once()
                self.assertIsNone(mock_gwc.upsert_gwflow_job.call_args.kwargs["libraries"])

    def test_missing_current_version_libraries_member_preserves(self):
        mock_portal = MagicMock()
        mock_portal.get_versions.return_value = [{"is_current": True}]
        mock_gwc = self._run_phase(mock_portal)

        mock_gwc.upsert_gwflow_job.assert_called_once()
        self.assertIsNone(mock_gwc.upsert_gwflow_job.call_args.kwargs["libraries"])

    def test_explicit_empty_current_version_libraries_clears(self):
        mock_portal = MagicMock()
        mock_portal.get_versions.return_value = [{"is_current": True, "libraries": []}]
        mock_gwc = self._run_phase(mock_portal)

        mock_gwc.upsert_gwflow_job.assert_called_once()
        self.assertEqual(mock_gwc.upsert_gwflow_job.call_args.kwargs["libraries"], [])

    def test_no_current_version_clears_for_non_pruned(self):
        mock_portal = MagicMock()
        mock_portal.get_versions.return_value = [{"is_current": False, "libraries": ["bilby"]}]
        mock_gwc = self._run_phase(mock_portal)

        mock_gwc.upsert_gwflow_job.assert_called_once()
        self.assertEqual(mock_gwc.upsert_gwflow_job.call_args.kwargs["libraries"], [])

    def test_multiple_current_records_uses_first_and_warns(self):
        mock_portal = MagicMock()
        mock_portal.get_versions.return_value = [
            {"is_current": True, "libraries": ["first"]},
            {"is_current": True, "libraries": ["second"]},
        ]
        mock_portal.iter_changed.return_value = [self._changed_row()]
        mock_portal.get_superevent.return_value = {"sname": "S_LIB", "raw_payload": {}}
        mock_portal.iter_current_snames.return_value = ["S_LIB"]
        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        with self.assertLogs("gwflow_ingest", level="WARNING") as logs:
            phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        mock_gwc.upsert_gwflow_job.assert_called_once()
        self.assertEqual(mock_gwc.upsert_gwflow_job.call_args.kwargs["libraries"], ["first"])
        self.assertIn("Multiple current versions", " ".join(logs.output))


if __name__ == "__main__":
    unittest.main()
