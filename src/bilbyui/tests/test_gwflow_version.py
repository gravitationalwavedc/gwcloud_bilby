from datetime import UTC, datetime, timedelta, timezone

from django.test import override_settings

from bilbyui.models import GWFlowJob
from bilbyui.services.gwflow_versions import diff_payloads, prepare_version_snapshots, resolve_history_selection
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.gwflow_version import (
    normalise_current_history_timestamp,
    normalise_libraries,
    version_tuple,
)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class NormaliseLibrariesTestCase(BilbyTestCase):
    def test_empty_list_returns_empty(self):
        self.assertEqual(normalise_libraries([]), [])

    def test_none_returns_empty(self):
        self.assertEqual(normalise_libraries(None), [])

    def test_populated_libraries_preserved(self):
        self.assertEqual(
            normalise_libraries(["cbc-workflow-o4a", "cbc-workflow-o4b"]),
            ["cbc-workflow-o4a", "cbc-workflow-o4b"],
        )

    def test_whitespace_only_values_dropped(self):
        self.assertEqual(normalise_libraries(["lib", "   ", "\t", ""]), ["lib"])

    def test_values_are_trimmed(self):
        self.assertEqual(normalise_libraries([" lib "]), ["lib"])

    def test_non_string_values_dropped(self):
        self.assertEqual(
            normalise_libraries(["lib", 123, None, 4.5, {"a": 1}, ["x"]]),
            ["lib"],
        )

    def test_order_preserved(self):
        self.assertEqual(
            normalise_libraries(["b", "a", "c"]),
            ["b", "a", "c"],
        )

    def test_dedup_case_sensitive(self):
        self.assertEqual(
            normalise_libraries(["Lib", "lib", "LIB", "lib"]),
            ["Lib", "lib", "LIB"],
        )

    def test_dedup_against_trimmed_form(self):
        self.assertEqual(
            normalise_libraries(["lib", " lib ", "lib"]),
            ["lib"],
        )


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class NormaliseCurrentHistoryTimestampTestCase(BilbyTestCase):
    def test_none_returns_none(self):
        self.assertIsNone(normalise_current_history_timestamp(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(normalise_current_history_timestamp(""))

    def test_naive_datetime_treated_as_utc(self):
        dt = normalise_current_history_timestamp(datetime(2024, 1, 1, 12, 0, 0))
        self.assertEqual(dt, datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC))
        self.assertEqual(dt.tzinfo, UTC)

    def test_offset_datetime_converted_to_utc(self):
        raw = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=5)))
        dt = normalise_current_history_timestamp(raw)
        self.assertEqual(dt, datetime(2024, 1, 1, 7, 0, 0, tzinfo=UTC))

    def test_iso_string_parsed_as_utc(self):
        dt = normalise_current_history_timestamp("2024-01-01T12:00:00")
        self.assertEqual(dt, datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC))

    def test_iso_string_with_offset(self):
        dt = normalise_current_history_timestamp("2024-01-01T12:00:00+05:00")
        self.assertEqual(dt, datetime(2024, 1, 1, 7, 0, 0, tzinfo=UTC))

    def test_malformed_string_returns_none(self):
        self.assertIsNone(normalise_current_history_timestamp("not-a-date"))

    def test_unsupported_type_returns_none(self):
        self.assertIsNone(normalise_current_history_timestamp(12345))


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class VersionTupleTestCase(BilbyTestCase):
    def test_version_tuple_returns_timestamp_and_id(self):
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        job = GWFlowJob(current_history_timestamp=ts, current_history_id="abc123")
        self.assertEqual(version_tuple(job), (ts, "abc123"))

    def test_version_tuple_with_none_timestamp(self):
        job = GWFlowJob(current_history_timestamp=None, current_history_id="")
        self.assertEqual(version_tuple(job), (None, ""))


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class GWFlowStructuredDiffTestCase(BilbyTestCase):
    def test_added_leaf(self):
        outcome = diff_payloads({}, {"info": {"status": "ready"}}, baseline_schema="v1", selected_schema="v1")
        self.assertEqual(outcome.status, "semantic")
        self.assertEqual(outcome.changes[0].kind, "added")
        self.assertEqual(outcome.changes[0].path, ("info",))

    def test_removed_leaf(self):
        outcome = diff_payloads({"status": "ready"}, {}, baseline_schema="v1", selected_schema="v1")
        self.assertEqual(outcome.changes[0].kind, "removed")
        self.assertFalse(outcome.changes[0].selected_present)

    def test_changed_leaf(self):
        outcome = diff_payloads({"status": "draft"}, {"status": "ready"})
        self.assertEqual(outcome.changes[0].kind, "changed")

    def test_nested_leaf_path(self):
        outcome = diff_payloads({"pe": {"status": "draft"}}, {"pe": {"status": "ready"}})
        self.assertEqual(outcome.changes[0].path, ("pe", "status"))

    def test_scalar_type_change_is_changed(self):
        outcome = diff_payloads({"value": False}, {"value": 0})
        self.assertEqual(outcome.changes[0].kind, "changed")
        self.assertIs(outcome.changes[0].baseline_value, False)
        self.assertEqual(type(outcome.changes[0].selected_value), int)

    def test_cross_schema_is_caveated_without_semantic_changes(self):
        outcome = diff_payloads({"status": "a"}, {"status": "b"}, baseline_schema="v1", selected_schema="v2")
        self.assertEqual(outcome.status, "cross_schema")
        self.assertEqual(outcome.changes, ())
        self.assertEqual(outcome.reason, "Diff may be incomplete across schema versions")

    def test_no_baseline_when_baseline_is_none(self):
        outcome = diff_payloads(None, {"status": "ready"}, baseline_schema="v1", selected_schema="v1")
        self.assertEqual(outcome.status, "no_baseline")
        self.assertEqual(outcome.baseline_schema, "v1")
        self.assertEqual(outcome.selected_schema, "v1")

    def test_unavailable_when_selected_is_none(self):
        outcome = diff_payloads({"status": "ready"}, None, baseline_schema="v1", selected_schema="v1")
        self.assertEqual(outcome.status, "unavailable")
        self.assertEqual(outcome.reason, "selected payload unavailable")

    def test_unsupported_shape_for_non_mapping_root(self):
        outcome = diff_payloads({"status": "ready"}, ["not", "a", "mapping"])
        self.assertEqual(outcome.status, "unsupported_shape")
        self.assertEqual(outcome.reason, "payload root must be a mapping")

    def test_mapping_vs_list_shape_mismatch_is_changed(self):
        outcome = diff_payloads({"detectors": {"a": 1}}, {"detectors": ["a"]})
        self.assertEqual(outcome.status, "semantic")
        self.assertEqual(outcome.changes[0].kind, "changed")
        self.assertEqual(outcome.changes[0].path, ("detectors",))

    def test_list_added_tail_produces_added_records(self):
        outcome = diff_payloads(
            {"detectors": ["H1"]},
            {"detectors": ["H1", "L1", "V1"]},
            baseline_schema="v1",
            selected_schema="v1",
        )
        self.assertEqual(outcome.status, "semantic")
        kinds = [c.kind for c in outcome.changes]
        self.assertEqual(kinds, ["added", "added"])
        self.assertEqual(outcome.changes[0].path, ("detectors", 1))
        self.assertEqual(outcome.changes[1].path, ("detectors", 2))

    def test_list_removed_tail_produces_removed_records(self):
        outcome = diff_payloads(
            {"detectors": ["H1", "L1", "V1"]},
            {"detectors": ["H1"]},
            baseline_schema="v1",
            selected_schema="v1",
        )
        self.assertEqual(outcome.status, "semantic")
        kinds = [c.kind for c in outcome.changes]
        self.assertEqual(kinds, ["removed", "removed"])
        self.assertFalse(outcome.changes[0].selected_present)

    def test_list_equal_length_changed_element(self):
        outcome = diff_payloads(
            {"detectors": ["H1", "L1"]},
            {"detectors": ["H1", "V1"]},
            baseline_schema="v1",
            selected_schema="v1",
        )
        self.assertEqual(outcome.status, "semantic")
        self.assertEqual(outcome.changes[0].kind, "changed")
        self.assertEqual(outcome.changes[0].path, ("detectors", 1))


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class GWFlowSnapshotTimestampTestCase(BilbyTestCase):
    def _snapshots(self, rows):
        return prepare_version_snapshots(rows)

    def test_naive_datetime_treated_as_utc(self):
        snapshots = self._snapshots([{"commit_sha": "a" * 40, "commit_timestamp": datetime(2024, 1, 1, 12, 0, 0)}])
        self.assertEqual(snapshots[0].recorded_at, datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC))
        self.assertEqual(snapshots[0].recorded_at.tzinfo, UTC)

    def test_aware_datetime_converted_to_utc(self):
        raw = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=5)))
        snapshots = self._snapshots([{"commit_sha": "a" * 40, "commit_timestamp": raw}])
        self.assertEqual(snapshots[0].recorded_at, datetime(2024, 1, 1, 7, 0, 0, tzinfo=UTC))

    def test_non_string_timestamp_returns_none(self):
        snapshots = self._snapshots([{"commit_sha": "a" * 40, "commit_timestamp": 12345}])
        self.assertIsNone(snapshots[0].recorded_at)

    def test_malformed_timestamp_returns_none(self):
        snapshots = self._snapshots([{"commit_sha": "a" * 40, "commit_timestamp": "not-a-date"}])
        self.assertIsNone(snapshots[0].recorded_at)

    def test_row_without_sha_is_skipped(self):
        snapshots = self._snapshots(
            [
                {"commit_sha": "a" * 40, "commit_timestamp": "2026-08-08 10:00:00 UTC"},
                {"commit_timestamp": "2026-08-09 10:00:00 UTC"},
                {"commit_sha": "b" * 40, "commit_timestamp": "2026-08-10 10:00:00 UTC"},
            ]
        )
        self.assertEqual([s.full_sha for s in snapshots], ["a" * 40, "b" * 40])

    def test_undated_rows_retained_after_dated_in_source_order(self):
        snapshots = self._snapshots(
            [
                {"commit_sha": "a" * 40, "commit_timestamp": "2026-08-10 10:00:00 UTC"},
                {"commit_sha": "b" * 40, "commit_timestamp": "not-a-date"},
                {"commit_sha": "c" * 40, "commit_timestamp": "2026-08-08 10:00:00 UTC"},
                {"commit_sha": "d" * 40},
                {"commit_sha": "e" * 40, "commit_timestamp": "not-a-date"},
            ]
        )
        self.assertEqual([s.full_sha for s in snapshots], ["c" * 40, "a" * 40, "b" * 40, "d" * 40, "e" * 40])

    def test_dated_rows_sort_by_timestamp_then_sha(self):
        snapshots = self._snapshots(
            [
                {"commit_sha": "z" * 40, "commit_timestamp": "2026-08-08 10:00:00 UTC"},
                {"commit_sha": "a" * 40, "commit_timestamp": "2026-08-08 10:00:00 UTC"},
                {"commit_sha": "m" * 40, "commit_timestamp": "2026-08-09 10:00:00 UTC"},
            ]
        )
        self.assertEqual([s.full_sha for s in snapshots], ["a" * 40, "z" * 40, "m" * 40])


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class GWFlowHistorySelectionTestCase(BilbyTestCase):
    def _snapshots(self):
        return prepare_version_snapshots(
            [
                {"commit_sha": "a" * 40, "commit_timestamp": "2026-08-08 10:00:00 UTC", "is_current": False},
                {"commit_sha": "b" * 40, "commit_timestamp": "2026-08-09 10:00:00 UTC", "is_current": False},
                {"commit_sha": "c" * 40, "commit_timestamp": "2026-08-10 10:00:00 UTC", "is_current": True},
            ],
            current_sha="c" * 40,
        )

    def test_default_selects_current_with_previous_baseline(self):
        selected, baseline, mode = resolve_history_selection(self._snapshots(), requested_sha=None, compare=None)
        self.assertEqual(selected.full_sha, "c" * 40)
        self.assertEqual(baseline.full_sha, "b" * 40)
        self.assertEqual(mode, "prev")

    def test_compare_current_uses_current_baseline(self):
        selected, baseline, mode = resolve_history_selection(self._snapshots(), requested_sha=None, compare="current")
        self.assertEqual(selected.full_sha, "c" * 40)
        self.assertEqual(baseline.full_sha, "c" * 40)
        self.assertEqual(mode, "current")

    def test_deep_link_selects_requested_version(self):
        selected, baseline, mode = resolve_history_selection(self._snapshots(), requested_sha="a" * 40, compare="prev")
        self.assertEqual(selected.full_sha, "a" * 40)
        self.assertIsNone(baseline)

    def test_unknown_version_raises_lookup_error(self):
        with self.assertRaises(LookupError):
            resolve_history_selection(self._snapshots(), requested_sha="z" * 40, compare="prev")

    def test_no_current_row_falls_back_to_latest_snapshot(self):
        snapshots = prepare_version_snapshots(
            [
                {"commit_sha": "a" * 40, "commit_timestamp": "2026-08-08 10:00:00 UTC", "is_current": False},
                {"commit_sha": "b" * 40, "commit_timestamp": "2026-08-09 10:00:00 UTC", "is_current": False},
            ],
            current_sha="",
        )
        selected, baseline, mode = resolve_history_selection(snapshots, requested_sha=None, compare=None)
        self.assertEqual(selected.full_sha, "b" * 40)
        self.assertEqual(baseline.full_sha, "a" * 40)
        self.assertEqual(mode, "prev")

    def test_empty_history_raises_lookup_error(self):
        with self.assertRaises(LookupError):
            resolve_history_selection((), requested_sha=None, compare=None)
