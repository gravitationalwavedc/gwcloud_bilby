import unittest
from unittest.mock import MagicMock

from base import GWFlowTestBase

import state
from gwflow_ingest import phase_metadata


class TestMetadataPhase(GWFlowTestBase):
    def test_happy_path_delta_sync_and_watermark_advancement(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
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
            "libraries": [{"name": "bilby"}],
        }
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
        # GWCloud currently has S_KEEP and S_DELETED
        mock_gwc.get_gwflow_job_list.return_value = [{"sname": "S_KEEP"}, {"sname": "S_DELETED"}]

        phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        # S_DELETED should be marked is_pruned=True
        mock_gwc.upsert_gwflow_job.assert_called_once_with(sname="S_DELETED", is_pruned=True)


if __name__ == "__main__":
    unittest.main()
