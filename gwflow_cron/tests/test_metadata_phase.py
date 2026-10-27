import unittest
from unittest.mock import MagicMock, patch

try:
    from tests.base import GWFlowTestBase
except ImportError:
    from base import GWFlowTestBase

import settings
import state
from gwflow_ingest import phase_metadata
from portal import PortalMalformedResponseError


class TestMetadataPhase(GWFlowTestBase):
    def test_happy_path_delta_sync_and_watermark_advancement(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            "non_dict_row",
            {"sname": "S_MISSING_TS"},
            {
                "sname": "S260101a",
                "record_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha1",
            },
            {
                "sname": "S260102b",
                "record_timestamp": "2026-01-02T12:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha2",
            },
        ]
        mock_portal.get_superevent.side_effect = lambda sname: {
            "sname": sname,
            "version_number": 1,
            "raw_payload": {"sname": sname},
        }
        mock_portal.get_versions.return_value = [{"is_current": True, "libraries": ["bilby"]}]
        mock_portal.iter_current_snames.return_value = ["S260101a", "S260102b"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        cur = self.con.cursor()
        result = phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)
        self.assertEqual(result, [])

        # Assert upserts
        self.assertEqual(mock_gwc.upsert_gwflow_job.call_count, 2)
        mock_gwc.upsert_gwflow_job.assert_any_call(
            sname="S260101a",
            event_id="S260101a",
            schema_version="1.0",
            metadata={"sname": "S260101a"},
            libraries=["bilby"],
            is_pruned=False,
            current_version_number=1,
            current_history_timestamp="2026-01-01T10:00:00Z",
        )

        # Assert state updated to latest row
        self.assertEqual(state.get_watermark(cur), "2026-01-02T12:00:00Z")
        self.assertEqual(state.get_last_sname(cur), "S260102b")

    def test_history_pointer_comes_from_detail_when_list_row_omits_it(self):
        """The canonical list row carries no commit_sha/schema_version."""
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {"sname": "S_CANON", "record_timestamp": "2026-01-01T10:00:00Z"},
        ]
        mock_portal.get_superevent.return_value = {
            "sname": "S_CANON",
            "record_timestamp": "2026-01-01T10:00:00Z",
            "version_number": 7,
            "raw_payload": {"sname": "S_CANON"},
        }
        mock_portal.get_versions.return_value = [{"is_current": True, "libraries": []}]
        mock_gwc = MagicMock()

        result = phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)
        self.assertEqual(result, [])

        kwargs = mock_gwc.upsert_gwflow_job.call_args.kwargs
        self.assertEqual(kwargs["current_version_number"], 7)
        self.assertEqual(kwargs["current_history_timestamp"], "2026-01-01T10:00:00Z")
        self.assertIsNone(kwargs["schema_version"])

    def test_malformed_libraries_entry_is_skipped(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {
                "sname": "S_LIBS",
                "record_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha1",
            },
        ]
        mock_portal.get_superevent.return_value = {
            "sname": "S_LIBS",
            "version_number": 1,
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
            event_id="S_LIBS",
            schema_version="1.0",
            metadata={"sname": "S_LIBS"},
            libraries=["bilby", "gwpy"],
            is_pruned=False,
            current_version_number=1,
            current_history_timestamp="2026-01-01T10:00:00Z",
        )

    def test_non_dict_superevent_detail_is_rejected_and_records_failure(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {
                "sname": "S_BAD_DETAIL",
                "record_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
            },
        ]
        mock_portal.get_superevent.return_value = "malformed-response"
        mock_portal.iter_current_snames.return_value = ["S_BAD_DETAIL"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        cur = self.con.cursor()
        with self.assertLogs("gwflow_ingest", level="ERROR") as logs:
            rejections = phase_metadata(
                portal_client=mock_portal,
                gwc_client=mock_gwc,
                con=self.con,
            )

        mock_gwc.upsert_gwflow_job.assert_not_called()
        self.assertEqual(state.get_failure_count(cur, "S_BAD_DETAIL"), 1)
        self.assertEqual(len(rejections), 1)
        self.assertEqual(rejections[0].sname, "S_BAD_DETAIL")
        self.assertEqual(rejections[0].reason, "non-dict superevent detail")
        self.assertIn("non-dict superevent detail", " ".join(logs.output))

    def test_malformed_detail_response_returns_rejection(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {
                "sname": "S_MALFORMED",
                "record_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
            },
        ]
        malformed_error = PortalMalformedResponseError.__new__(PortalMalformedResponseError)
        Exception.__init__(malformed_error, "invalid detail payload")
        mock_portal.get_superevent.side_effect = malformed_error
        mock_gwc = MagicMock()

        result = phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].sname, "S_MALFORMED")
        self.assertIn("invalid detail payload", result[0].reason)
        mock_gwc.upsert_gwflow_job.assert_not_called()

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
                "record_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
            },
            # Same timestamp, later sname: should be processed
            {
                "sname": "S260101b",
                "record_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
            },
        ]
        mock_portal.get_superevent.return_value = {"sname": "S260101b", "version_number": 1, "raw_payload": {}}
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
                "record_timestamp": "2026-01-01T09:00:00Z",
                "schema_version": "1.0",
            },
            {
                "sname": "S_FAIL",
                "record_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
            },
            {
                "sname": "S_OK2",
                "record_timestamp": "2026-01-01T11:00:00Z",
                "schema_version": "1.0",
            },
        ]

        def get_detail_side_effect(sname):
            if sname == "S_FAIL":
                raise ValueError("Portal API temporary failure")
            return {"sname": sname, "version_number": 1, "raw_payload": {}}

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
                "record_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha1",
            },
        ]
        mock_portal.get_superevent.return_value = {
            "sname": "S_RAW",
            "version_number": 1,
            "raw_payload": "not-a-dict",
        }
        mock_portal.get_versions.return_value = [{"is_current": True, "libraries": []}]
        mock_portal.iter_current_snames.return_value = ["S_RAW"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        mock_gwc.upsert_gwflow_job.assert_called_once_with(
            sname="S_RAW",
            event_id="S_RAW",
            schema_version="1.0",
            metadata={},
            libraries=[],
            is_pruned=False,
            current_version_number=1,
            current_history_timestamp="2026-01-01T10:00:00Z",
        )

    def test_max_retry_attempts_reached_logs_error(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {"sname": "S_CAP", "record_timestamp": "2026-01-01T10:00:00Z", "schema_version": "1.0"},
        ]
        mock_portal.get_superevent.side_effect = ValueError("Persistent Failure")
        mock_portal.iter_current_snames.return_value = ["S_CAP"]

        cur = self.con.cursor()
        # Pre-seed failure count to MAX_RETRY_ATTEMPTS - 1
        for _ in range(settings.MAX_RETRY_ATTEMPTS - 1):
            state.record_failure(self.con, cur, "S_CAP", "earlier failure")

        phase_metadata(portal_client=mock_portal, gwc_client=MagicMock(), con=self.con)
        self.assertEqual(state.get_failure_count(cur, "S_CAP"), settings.MAX_RETRY_ATTEMPTS)

    def _changed_row(self, sname="S_LIB"):
        return {
            "sname": sname,
            "record_timestamp": "2026-01-01T10:00:00Z",
            "schema_version": "1.0",
            "commit_sha": "sha1",
        }

    def _run_phase(self, mock_portal, sname="S_LIB", detail=None):
        mock_portal.iter_changed.return_value = [self._changed_row(sname)]
        mock_portal.get_superevent.return_value = (
            {"sname": sname, "version_number": 1, "raw_payload": {}} if detail is None else detail
        )
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

    def test_missing_version_libraries_uses_detail_libraries(self):
        mock_portal = MagicMock()
        mock_portal.get_versions.return_value = [{"is_current": True}]
        detail = {
            "sname": "S_LIB",
            "version_number": 1,
            "raw_payload": {},
            "libraries": ["bilby", "gwpy"],
        }

        mock_gwc = self._run_phase(mock_portal, detail=detail)

        mock_gwc.upsert_gwflow_job.assert_called_once()
        self.assertEqual(
            mock_gwc.upsert_gwflow_job.call_args.kwargs["libraries"],
            ["bilby", "gwpy"],
        )

    def test_malformed_version_and_detail_libraries_preserves_libraries(self):
        mock_portal = MagicMock()
        mock_portal.get_versions.return_value = [{"is_current": True, "libraries": "bilby"}]
        detail = {
            "sname": "S_LIB",
            "version_number": 1,
            "raw_payload": {},
            "libraries": {"name": "gwpy"},
        }

        mock_gwc = self._run_phase(mock_portal, detail=detail)

        mock_gwc.upsert_gwflow_job.assert_called_once()
        self.assertIsNone(mock_gwc.upsert_gwflow_job.call_args.kwargs["libraries"])

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
        mock_portal.get_superevent.return_value = {"sname": "S_LIB", "version_number": 1, "raw_payload": {}}
        mock_portal.iter_current_snames.return_value = ["S_LIB"]
        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        with self.assertLogs("gwflow_ingest", level="WARNING") as logs:
            phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        mock_gwc.upsert_gwflow_job.assert_called_once()
        self.assertEqual(mock_gwc.upsert_gwflow_job.call_args.kwargs["libraries"], ["first"])
        self.assertIn("Multiple current versions", " ".join(logs.output))

    def test_phase_metadata_creates_event_id_for_superevents(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {
                "sname": "S_EV",
                "record_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha1",
            },
        ]
        mock_portal.get_superevent.return_value = {
            "sname": "S_EV",
            "version_number": 1,
            "raw_payload": {},
            "gracedb_events": [
                {"event_name": "EVT-X", "gps_time": 1234567890.5, "state": "preferred"},
            ],
        }
        mock_portal.get_versions.return_value = [{"is_current": True, "libraries": []}]
        mock_portal.iter_current_snames.return_value = ["S_EV"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        mock_gwc.create_event_id.assert_called_once_with("EVT-X", 1234567890.5, trigger_id="S_EV")
        mock_gwc.upsert_gwflow_job.assert_called_once()

    def test_phase_metadata_missing_gracedb_graceful(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {
                "sname": "S_NOGDB",
                "record_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha1",
            },
        ]
        mock_portal.get_superevent.return_value = {
            "sname": "S_NOGDB",
            "version_number": 1,
            "raw_payload": {},
        }
        mock_portal.get_versions.return_value = [{"is_current": True, "libraries": []}]
        mock_portal.iter_current_snames.return_value = ["S_NOGDB"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []

        phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        mock_gwc.create_event_id.assert_not_called()
        mock_gwc.upsert_gwflow_job.assert_called_once()

    def test_phase_metadata_create_event_id_exception_handled(self):
        mock_portal = MagicMock()
        mock_portal.iter_changed.return_value = [
            {
                "sname": "S_EVFAIL",
                "record_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha1",
            },
        ]
        mock_portal.get_superevent.return_value = {
            "sname": "S_EVFAIL",
            "version_number": 1,
            "raw_payload": {},
            "gracedb_events": [
                {"event_name": "EVT-Y", "gps_time": 9876543210.0, "state": "preferred"},
            ],
        }
        mock_portal.get_versions.return_value = [{"is_current": True, "libraries": []}]
        mock_portal.iter_current_snames.return_value = ["S_EVFAIL"]

        mock_gwc = MagicMock()
        mock_gwc.get_gwflow_job_list.return_value = []
        mock_gwc.create_event_id.side_effect = RuntimeError("event id API down")

        with self.assertLogs("gwflow_ingest", level="WARNING") as logs:
            phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=self.con)

        self.assertIn("create_event_id failed", " ".join(logs.output))
        mock_gwc.upsert_gwflow_job.assert_called_once()


if __name__ == "__main__":
    unittest.main()
