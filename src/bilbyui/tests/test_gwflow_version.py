import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.test import override_settings
from django.urls import reverse

from bilbyui.models import GWFlowJob
from bilbyui.services import gwflow_versions
from bilbyui.services.gwflow_versions import (
    adapt_semantic_diff,
    prepare_version_snapshots,
    resolve_history_selection,
    resolve_version_number,
)
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

    def test_string_returns_empty(self):
        self.assertEqual(normalise_libraries("cbc-workflow-o4a"), [])

    def test_non_iterable_returns_empty(self):
        self.assertEqual(normalise_libraries(123), [])

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
    def test_retired_calculator_is_never_called_by_adapter_or_history(self):
        user = self.create_user(
            id=98,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=user)
        job = GWFlowJob.objects.create(
            sname="S000001a",
            user=user,
            libraries=["cbc-workflow-o4a"],
            current_history_id="b" * 40,
        )
        payload = {
            "sname": job.sname,
            "baseline_version": 1,
            "selected_version": 2,
            "baseline_timestamp": "2026-01-01T00:00:00Z",
            "selected_timestamp": "2026-01-02T00:00:00Z",
            "changes": [],
        }
        versions = [
            {
                "commit_sha": "a" * 40,
                "version_number": 1,
                "record_timestamp": "2026-01-01 00:00:00 UTC",
            },
            {
                "commit_sha": "b" * 40,
                "version_number": 2,
                "record_timestamp": "2026-01-02 00:00:00 UTC",
                "is_current": True,
            },
        ]

        self.assertFalse(hasattr(gwflow_versions, "diff_payloads"))
        with (
            mock.patch(
                "bilbyui.services.gwflow_versions.diff_payloads",
                side_effect=AssertionError("retired calculator called"),
                create=True,
            ) as retired,
            mock.patch(
                "bilbyui.views.get_versions",
                return_value=(versions, "live"),
            ),
            mock.patch(
                "bilbyui.views.get_version",
                return_value=({"raw_payload": {}}, "live"),
            ),
            mock.patch(
                "bilbyui.views.get_diff",
                return_value=(payload, "live"),
            ),
        ):
            outcome = adapt_semantic_diff(
                sname=job.sname,
                baseline_version=1,
                selected_version=2,
                payload=payload,
                state="live",
            )
            response = self.client.get(
                reverse("bilbyui:gwflow_job_history", args=[job.sname]),
                HTTP_HX_REQUEST="true",
            )

            self.assertEqual(outcome.status, "semantic_empty")
            self.assertEqual(response.status_code, 200)
            retired.assert_not_called()

        self.assertFalse(hasattr(gwflow_versions, "diff_payloads"))


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class VersionSnapshotCanonicalTestCase(BilbyTestCase):
    def _snapshots(self, rows, *, current_sha=""):
        return prepare_version_snapshots(rows, current_sha=current_sha)

    def test_canonical_summary_fields_are_accepted(self):
        snapshots = self._snapshots(
            [
                {
                    "commit_sha": "a" * 40,
                    "record_timestamp": "2026-08-08 10:00:00 UTC",
                    "version_number": 7,
                    "is_current": True,
                }
            ]
        )

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].full_sha, "a" * 40)
        self.assertEqual(snapshots[0].short_sha, "a" * 8)
        self.assertEqual(snapshots[0].version_number, 7)
        self.assertEqual(
            snapshots[0].recorded_at,
            datetime(2026, 8, 8, 10, 0, tzinfo=UTC),
        )
        self.assertTrue(snapshots[0].is_current)

    def test_missing_version_number_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "version_number must be an integer"):
            self._snapshots([{"commit_sha": "a" * 40}])

    def test_true_version_number_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "version_number must be an integer"):
            self._snapshots([{"commit_sha": "a" * 40, "version_number": True}])

    def test_false_version_number_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "version_number must be an integer"):
            self._snapshots([{"commit_sha": "a" * 40, "version_number": False}])

    def test_non_integer_version_numbers_are_rejected(self):
        for value in ("1", 1.0, None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "version_number must be an integer"):
                    self._snapshots([{"commit_sha": "a" * 40, "version_number": value}])

    def test_naive_datetime_treated_as_utc(self):
        snapshots = self._snapshots(
            [{"commit_sha": "a" * 40, "record_timestamp": datetime(2024, 1, 1, 12), "version_number": 1}]
        )
        self.assertEqual(snapshots[0].recorded_at, datetime(2024, 1, 1, 12, tzinfo=UTC))

    def test_aware_datetime_converted_to_utc(self):
        raw = datetime(2024, 1, 1, 12, tzinfo=timezone(timedelta(hours=5)))
        snapshots = self._snapshots([{"commit_sha": "a" * 40, "record_timestamp": raw, "version_number": 2}])
        self.assertEqual(snapshots[0].recorded_at, datetime(2024, 1, 1, 7, tzinfo=UTC))

    def test_malformed_or_non_string_timestamp_is_undated(self):
        for value in ("not-a-date", 12345):
            with self.subTest(value=value):
                snapshots = self._snapshots([{"commit_sha": "a" * 40, "record_timestamp": value, "version_number": 3}])
                self.assertIsNone(snapshots[0].recorded_at)

    def test_row_without_sha_is_skipped(self):
        snapshots = self._snapshots(
            [
                {"commit_sha": "a" * 40, "version_number": 4},
                {"commit_sha": "", "version_number": 5},
                {"commit_sha": "b" * 40, "version_number": 6},
            ]
        )
        self.assertEqual([snapshot.full_sha for snapshot in snapshots], ["a" * 40, "b" * 40])

    def test_ordering_preserves_timestamp_sha_and_undated_contract(self):
        snapshots = self._snapshots(
            [
                {
                    "commit_sha": "z" * 40,
                    "record_timestamp": "2026-08-08 10:00:00 UTC",
                    "version_number": 7,
                },
                {"commit_sha": "b" * 40, "record_timestamp": "not-a-date", "version_number": 8},
                {
                    "commit_sha": "a" * 40,
                    "record_timestamp": "2026-08-08 10:00:00 UTC",
                    "version_number": 9,
                },
                {
                    "commit_sha": "m" * 40,
                    "record_timestamp": "2026-08-09 10:00:00 UTC",
                    "version_number": 10,
                },
                {"commit_sha": "d" * 40, "version_number": 11},
            ]
        )
        self.assertEqual(
            [snapshot.full_sha for snapshot in snapshots],
            ["a" * 40, "z" * 40, "m" * 40, "b" * 40, "d" * 40],
        )

    def test_is_current_accepts_canonical_flag_and_current_sha_fallback(self):
        snapshots = self._snapshots(
            [
                {"commit_sha": "a" * 40, "version_number": 12, "is_current": "false"},
                {"commit_sha": "b" * 40, "version_number": 13, "is_current": "true"},
                {"commit_sha": "c" * 40, "version_number": 14, "is_current": False},
            ],
            current_sha="c" * 40,
        )
        self.assertEqual([snapshot.is_current for snapshot in snapshots], [False, True, True])


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class ResolveHistorySelectionVersionNumberTestCase(BilbyTestCase):
    def _snapshots(self):
        return prepare_version_snapshots(
            [
                {
                    "commit_sha": "a" * 40,
                    "record_timestamp": "2026-08-08 10:00:00 UTC",
                    "is_current": False,
                    "version_number": 19,
                },
                {
                    "commit_sha": "b" * 40,
                    "record_timestamp": "2026-08-09 10:00:00 UTC",
                    "is_current": False,
                    "version_number": 20,
                },
                {
                    "commit_sha": "c" * 40,
                    "record_timestamp": "2026-08-10 10:00:00 UTC",
                    "is_current": True,
                    "version_number": 21,
                },
            ],
            current_sha="c" * 40,
        )

    def test_sha_resolves_to_version_number(self):
        self.assertEqual(resolve_version_number(self._snapshots(), "b" * 40), 20)

    def test_unknown_sha_raises_lookup_error(self):
        with self.assertRaisesRegex(LookupError, "Version not found"):
            resolve_version_number(self._snapshots(), "z" * 40)

    def test_default_selects_current_with_previous_baseline(self):
        selected, baseline, mode = resolve_history_selection(self._snapshots(), requested_sha=None, compare=None)
        self.assertEqual(selected.version_number, 21)
        self.assertEqual(baseline.version_number, 20)
        self.assertEqual(mode, "prev")

    def test_compare_current_uses_current_baseline(self):
        selected, baseline, mode = resolve_history_selection(self._snapshots(), requested_sha=None, compare="current")
        self.assertEqual(selected.version_number, 21)
        self.assertEqual(baseline.version_number, 21)
        self.assertEqual(mode, "current")

    def test_deep_link_selects_requested_version(self):
        selected, baseline, mode = resolve_history_selection(
            self._snapshots(),
            requested_sha="a" * 40,
            compare="prev",
        )
        self.assertEqual(selected.version_number, 19)
        self.assertIsNone(baseline)
        self.assertEqual(mode, "prev")

    def test_unknown_version_raises_lookup_error(self):
        with self.assertRaises(LookupError):
            resolve_history_selection(self._snapshots(), requested_sha="z" * 40, compare="prev")

    def test_no_current_row_falls_back_to_latest_snapshot(self):
        snapshots = prepare_version_snapshots(
            [
                {
                    "commit_sha": "a" * 40,
                    "record_timestamp": "2026-08-08 10:00:00 UTC",
                    "is_current": False,
                    "version_number": 22,
                },
                {
                    "commit_sha": "b" * 40,
                    "record_timestamp": "2026-08-09 10:00:00 UTC",
                    "is_current": False,
                    "version_number": 23,
                },
            ]
        )
        selected, baseline, mode = resolve_history_selection(snapshots, requested_sha=None, compare=None)
        self.assertEqual(selected.version_number, 23)
        self.assertEqual(baseline.version_number, 22)
        self.assertEqual(mode, "prev")

    def test_empty_history_raises_lookup_error(self):
        with self.assertRaises(LookupError):
            resolve_history_selection((), requested_sha=None, compare=None)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "gwflow_diff"


class SemanticDiffTestMixin:
    def payload(self, *, changes=None, baseline_version=1, selected_version=2):
        return {
            "sname": "S000001a",
            "baseline_version": baseline_version,
            "selected_version": selected_version,
            "baseline_timestamp": "2026-01-01T00:00:00Z",
            "selected_timestamp": "2026-01-02T00:00:00Z",
            "changes": [] if changes is None else changes,
        }

    def analysis_change(self, *, identity="analysis-1", kind="modified"):
        if kind == "added":
            before, after, field_diffs = None, {"uid": identity}, {}
        elif kind == "removed":
            before, after, field_diffs = {"uid": identity}, None, {}
        else:
            before = {"uid": identity, "nested": {"value": [None, False, 0]}}
            after = {"uid": identity, "nested": {"value": [{"deep": True}]}}
            field_diffs = {
                "nested": {
                    "baseline": {"value": [None, False, 0]},
                    "selected": {"value": [{"deep": True}]},
                }
            }
        return {
            "entity_type": "analysis",
            "identity": identity,
            "kind": kind,
            "before": before,
            "after": after,
            "field_diffs": field_diffs,
        }

    def review_record(self, occurrence_uid="occurrence-1", *, reviewers=None):
        return {
            "occurrence_uid": occurrence_uid,
            "name": "PE review",
            "description": "",
            "reviewers": ([{"name": "Reviewer One", "email_address": ""}] if reviewers is None else reviewers),
            "passed_review": None,
            "completion_date": None,
            "review_status": "pending",
        }

    def review_change(
        self,
        *,
        analysis_uid="analysis-1",
        occurrence_uid="occurrence-1",
        kind="modified",
    ):
        before = self.review_record(occurrence_uid)
        after = self.review_record(
            occurrence_uid,
            reviewers=[
                {"name": "Reviewer One", "email_address": ""},
                {"name": "Reviewer Two", "email_address": "two@example.test"},
            ],
        )
        field_diffs = {
            "reviewers": {
                "baseline": before["reviewers"],
                "selected": after["reviewers"],
            }
        }
        if kind == "added":
            before, field_diffs = None, {}
        elif kind == "removed":
            after, field_diffs = None, {}
        return {
            "entity_type": "review",
            "identity": {
                "analysis_uid": analysis_uid,
                "occurrence_uid": occurrence_uid,
            },
            "kind": kind,
            "before": before,
            "after": after,
            "field_diffs": field_diffs,
        }

    def gracedb_change(self):
        fields = {
            "has_ns": None,
            "has_remnant": 0,
            "has_mass_gap": 0.25,
            "pipeline_has_ns": 1,
            "pipeline_has_remnant": None,
            "pipeline_has_mass_gap": 0.5,
        }
        return {
            "entity_type": "gracedb_event",
            "identity": "G000001",
            "kind": "modified",
            "before": {"event_name": "G000001", **fields},
            "after": {"event_name": "G000001", **fields},
            "field_diffs": {},
        }

    def adapt(self, payload, **overrides):
        arguments = {
            "sname": "S000001a",
            "baseline_version": 1,
            "selected_version": 2,
            "payload": payload,
            "state": "live",
        }
        arguments.update(overrides)
        return adapt_semantic_diff(**arguments)

    def load_fixture(self, name):
        with (FIXTURE_DIR / name).open(encoding="utf-8") as fixture:
            return json.load(fixture)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class GWFlowDiffAdapterTestCase(SemanticDiffTestMixin, BilbyTestCase):
    def test_no_baseline_precedes_payload_inspection(self):
        outcome = self.adapt(
            None,
            baseline_version=None,
            state="live",
        )
        self.assertEqual(outcome.status, "no_baseline")
        self.assertEqual(outcome.reason, "earlier_version_required")

    def test_live_and_stale_valid_payloads_are_semantic(self):
        payload = self.payload(changes=[self.analysis_change()])
        for state in ("live", "stale"):
            with self.subTest(state=state):
                self.assertEqual(self.adapt(payload, state=state).status, "semantic")

    def test_request_and_response_labels_must_match(self):
        cases = (
            ("sname", "S999999z"),
            ("baseline_version", 8),
            ("selected_version", 9),
        )
        for field, value in cases:
            with self.subTest(field=field):
                payload = self.payload()
                payload[field] = value
                outcome = self.adapt(payload)
                self.assertEqual(outcome.status, "failed")
                self.assertEqual(outcome.reason, f"request_mismatch:{field}")

    def test_all_entity_types_preserved_one_to_one(self):
        golden = self.load_fixture("semantic_diff.json")
        outcome = self.adapt(golden)
        self.assertEqual(outcome.status, "semantic")
        self.assertEqual(len(outcome.rows), len(golden["changes"]))
        for row, change in zip(outcome.rows, golden["changes"], strict=True):
            self.assertEqual(row.entity_type, change["entity_type"])
            self.assertIs(row.identity, change["identity"])
            self.assertEqual(row.kind, change["kind"])
            self.assertIs(row.before, change["before"])
            self.assertIs(row.after, change["after"])
            self.assertIs(row.field_diffs, change["field_diffs"])

    def test_complete_records_and_nested_field_diffs_preserved(self):
        change = self.analysis_change()
        change["before"]["unknown"] = {"array": [0, False, None]}
        change["after"]["unknown"] = {"array": [{"opaque": "value"}]}
        outcome = self.adapt(self.payload(changes=[change]))
        row = outcome.rows[0]
        self.assertIs(row.before, change["before"])
        self.assertIs(row.after, change["after"])
        self.assertIs(row.field_diffs, change["field_diffs"])

    def test_empty_diff_is_semantic_empty(self):
        outcome = self.adapt(self.payload())
        self.assertEqual(outcome.status, "semantic_empty")
        self.assertEqual(outcome.rows, ())

    def test_equal_versions_are_semantic_empty(self):
        payload = self.payload(baseline_version=2, selected_version=2)
        outcome = self.adapt(payload, baseline_version=2, selected_version=2)
        self.assertEqual(outcome.status, "semantic_empty")
        self.assertEqual(outcome.baseline_version, 2)
        self.assertEqual(outcome.selected_version, 2)

    def test_reversed_versions_preserve_direction(self):
        change = self.analysis_change(kind="removed")
        payload = self.payload(
            changes=[change],
            baseline_version=3,
            selected_version=2,
        )
        outcome = self.adapt(payload, baseline_version=3)
        self.assertEqual(outcome.status, "semantic")
        self.assertEqual(outcome.baseline_version, 3)
        self.assertEqual(outcome.selected_version, 2)
        self.assertIs(outcome.rows[0].before, change["before"])
        self.assertIsNone(outcome.rows[0].after)

    def test_version_number_booleans_are_rejected(self):
        for field in ("baseline_version", "selected_version"):
            for value in (True, False):
                with self.subTest(field=field, value=value):
                    payload = self.payload()
                    payload[field] = value
                    outcome = self.adapt(payload)
                    self.assertEqual(outcome.status, "failed")
                    self.assertEqual(outcome.reason, f"invalid_integer:{field}")

    def test_all_gracedb_boolean_fields_are_rejected_on_both_sides(self):
        for side in ("before", "after"):
            for field in (
                "has_ns",
                "has_remnant",
                "has_mass_gap",
                "pipeline_has_ns",
                "pipeline_has_remnant",
                "pipeline_has_mass_gap",
            ):
                for value in (True, False):
                    with self.subTest(side=side, field=field, value=value):
                        change = self.gracedb_change()
                        change[side][field] = value
                        outcome = self.adapt(self.payload(changes=[change]))
                        self.assertEqual(outcome.status, "failed")
                        self.assertEqual(
                            outcome.reason,
                            "invalid_gracedb_record:changes[0]",
                        )

    def test_non_hashable_enums_are_failed_without_rows(self):
        enum_cases = (
            ("entity_type", []),
            ("entity_type", {}),
            ("entity_type", None),
            ("entity_type", 1),
            ("kind", []),
            ("kind", {}),
            ("kind", None),
            ("kind", 1),
        )
        for state in ("live", "stale"):
            for field, value in enum_cases:
                with self.subTest(state=state, field=field, value=value):
                    change = self.analysis_change()
                    change[field] = value
                    outcome = self.adapt(
                        self.payload(changes=[change]),
                        state=state,
                    )
                    self.assertEqual(outcome.status, "failed")
                    self.assertEqual(outcome.rows, ())
                    self.assertLessEqual(len(outcome.reason), 64)

        for state in ("live", "stale"):
            for value in ([], {}, None, 1):
                with self.subTest(state=state, review_status=value):
                    change = self.review_change(kind="added")
                    change["after"]["review_status"] = value
                    outcome = self.adapt(
                        self.payload(changes=[change]),
                        state=state,
                    )
                    self.assertEqual(outcome.status, "failed")
                    self.assertEqual(outcome.rows, ())
                    self.assertEqual(
                        outcome.reason,
                        "invalid_review_record:changes[0]",
                    )

    def test_non_hashable_enum_in_later_row_rejects_all_rows(self):
        invalid = self.analysis_change(identity="B")
        invalid["kind"] = []
        outcome = self.adapt(
            self.payload(
                changes=[
                    self.analysis_change(identity="A"),
                    invalid,
                ]
            )
        )
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.rows, ())
        self.assertEqual(outcome.reason, "invalid_enum:changes[1].kind")

    def test_non_utc_offsets_are_rejected_for_both_timestamps(self):
        for state in ("live", "stale"):
            for field in ("baseline_timestamp", "selected_timestamp"):
                with self.subTest(state=state, field=field):
                    payload = self.payload()
                    payload[field] = "2026-01-01T11:00:00+11:00"
                    outcome = self.adapt(payload, state=state)
                    self.assertEqual(outcome.status, "failed")
                    self.assertEqual(
                        outcome.reason,
                        f"invalid_timestamp:{field}",
                    )

    def test_utc_timestamp_forms_are_accepted(self):
        for value in (
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01 00:00:00 UTC",
        ):
            with self.subTest(value=value):
                payload = self.payload()
                payload["baseline_timestamp"] = value
                payload["selected_timestamp"] = value
                self.assertEqual(self.adapt(payload).status, "semantic_empty")

    def test_surviving_side_must_be_mapping_for_every_entity(self):
        entity_changes = {
            "analysis": lambda kind: self.analysis_change(kind=kind),
            "detector_configuration": lambda kind: {
                **self.analysis_change(identity="H1", kind=kind),
                "entity_type": "detector_configuration",
            },
            "gracedb_event": lambda kind: {
                **self.analysis_change(identity="G000001", kind=kind),
                "entity_type": "gracedb_event",
            },
            "catalog_connection": lambda kind: {
                **self.analysis_change(identity="1:1", kind=kind),
                "entity_type": "catalog_connection",
            },
            "review": lambda kind: self.review_change(kind=kind),
        }
        for entity_type, factory in entity_changes.items():
            for kind, surviving_side in (
                ("added", "after"),
                ("removed", "before"),
            ):
                for invalid in (None, 1, [], "record"):
                    with self.subTest(
                        entity_type=entity_type,
                        kind=kind,
                        invalid=invalid,
                    ):
                        change = factory(kind)
                        change[surviving_side] = invalid
                        outcome = self.adapt(self.payload(changes=[change]))
                        self.assertEqual(outcome.status, "failed")
                        self.assertEqual(outcome.rows, ())
                        self.assertEqual(
                            outcome.reason,
                            "invalid_record_sides:changes[0]",
                        )

    def test_full_kind_matrix_for_non_analysis_entities(self):
        factories = {
            "detector_configuration": lambda kind: {
                **self.analysis_change(identity="H1", kind=kind),
                "entity_type": "detector_configuration",
            },
            "gracedb_event": lambda kind: {
                **self.analysis_change(identity="G000001", kind=kind),
                "entity_type": "gracedb_event",
            },
            "catalog_connection": lambda kind: {
                **self.analysis_change(identity="1:1", kind=kind),
                "entity_type": "catalog_connection",
            },
            "review": lambda kind: self.review_change(kind=kind),
        }
        for entity_type, factory in factories.items():
            for kind in ("added", "removed", "modified"):
                with self.subTest(entity_type=entity_type, kind=kind):
                    outcome = self.adapt(self.payload(changes=[factory(kind)]))
                    self.assertEqual(outcome.status, "semantic")
                    self.assertEqual(outcome.rows[0].entity_type, entity_type)
                    self.assertEqual(outcome.rows[0].kind, kind)

    def test_review_added_and_removed_records_are_validated(self):
        for kind, side in (("added", "after"), ("removed", "before")):
            for mutation in (
                lambda record: record.pop("name"),
                lambda record: record.__setitem__("review_status", {}),
                lambda record: record.__setitem__("occurrence_uid", "wrong"),
            ):
                with self.subTest(kind=kind, mutation=mutation):
                    change = self.review_change(kind=kind)
                    mutation(change[side])
                    outcome = self.adapt(self.payload(changes=[change]))
                    self.assertEqual(outcome.status, "failed")
                    self.assertEqual(
                        outcome.reason,
                        "invalid_review_record:changes[0]",
                    )

    def test_reasons_are_bounded_and_do_not_echo_payload_keys(self):
        supplied_key = "payload-secret-" + ("x" * 200)
        change = self.analysis_change()
        change["field_diffs"] = {
            supplied_key: {
                "baseline": 1,
            }
        }
        outcome = self.adapt(self.payload(changes=[change]))
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason, "invalid_field_diff:changes[0]")
        self.assertLessEqual(len(outcome.reason), 64)
        self.assertNotIn(supplied_key, outcome.reason)

        change = self.analysis_change()
        change[supplied_key] = "payload-value"
        outcome = self.adapt(self.payload(changes=[change]))
        self.assertEqual(outcome.reason, "invalid_keys:changes[0]")
        self.assertLessEqual(len(outcome.reason), 64)
        self.assertNotIn(supplied_key, outcome.reason)

    def test_entity_specific_allowed_kinds(self):
        for kind in ("added", "removed", "modified", "deprecated"):
            with self.subTest(kind=kind):
                outcome = self.adapt(self.payload(changes=[self.analysis_change(kind=kind)]))
                self.assertEqual(outcome.status, "semantic")


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class GWFlowDiffGoldenTestCase(SemanticDiffTestMixin, BilbyTestCase):
    def test_shared_wire_golden_accepted_unchanged(self):
        payload = self.load_fixture("semantic_diff.json")
        changes = payload["changes"]
        outcome = self.adapt(payload)
        self.assertEqual(outcome.status, "semantic")
        self.assertEqual(outcome.sname, payload["sname"])
        self.assertEqual(outcome.baseline_timestamp, payload["baseline_timestamp"])
        self.assertEqual(outcome.selected_timestamp, payload["selected_timestamp"])
        for row, change in zip(outcome.rows, changes, strict=True):
            self.assertIs(row.identity, change["identity"])
            self.assertIs(row.before, change["before"])
            self.assertIs(row.after, change["after"])
            self.assertIs(row.field_diffs, change["field_diffs"])

    def test_missing_occurrence_uid_golden_rejected(self):
        outcome = self.adapt(self.load_fixture("semantic_diff_missing_occurrence_uid.json"))
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason, "invalid_identity:changes[5]")

    def test_copy_on_write_review_contract(self):
        fixture = self.load_fixture("review_copy_on_write.json")
        producer = fixture["producer"]
        self.assertEqual(producer["result"], "success")
        self.assertEqual(producer["operation"], "attachment_created")
        self.assertEqual(producer["analysis_uid"], "A1")
        self.assertEqual(producer["review"]["name"], "R1")
        self.assertEqual(producer["review"]["occurrence_uid"], "O")

        outcomes = {}
        for key in ("version_1", "version_2"):
            payload = fixture[key]
            outcome = self.adapt(
                payload,
                baseline_version=payload["baseline_version"],
                selected_version=payload["selected_version"],
            )
            outcomes[key] = outcome
            self.assertEqual(outcome.status, "semantic")
            self.assertEqual(len(outcome.rows), len(payload["changes"]))

        version_1_rows = outcomes["version_1"].rows
        version_2_rows = outcomes["version_2"].rows

        self.assertEqual(
            [row.identity for row in version_1_rows],
            [
                "A1",
                {"analysis_uid": "A1", "occurrence_uid": "O"},
            ],
        )
        self.assertEqual(
            [row.identity for row in version_2_rows],
            [
                "A2",
                {"analysis_uid": "A2", "occurrence_uid": "O"},
            ],
        )

        a1_analysis = version_1_rows[0].after
        r1_review = version_1_rows[1].after
        a2_analysis = version_2_rows[0].after
        r2_review = version_2_rows[1].after

        self.assertEqual(a1_analysis["reviews"], [r1_review])
        self.assertEqual(r1_review["name"], "R1")
        self.assertEqual(r1_review["occurrence_uid"], "O")

        self.assertEqual(a2_analysis["reviews"], [r2_review])
        self.assertEqual(r2_review["name"], "R2")
        self.assertEqual(r2_review["occurrence_uid"], "O")

        preserved_a1 = a2_analysis["preserved_analyses"][0]
        self.assertEqual(preserved_a1, a1_analysis)
        self.assertEqual(preserved_a1["reviews"][0], r1_review)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class GWFlowDiffOrderingTestCase(SemanticDiffTestMixin, BilbyTestCase):
    def ordered_changes(self):
        return [
            self.analysis_change(identity="A"),
            {
                "entity_type": "detector_configuration",
                "identity": "H1",
                "kind": "added",
                "before": None,
                "after": {"uid": "H1"},
                "field_diffs": {},
            },
            self.gracedb_change(),
            {
                "entity_type": "catalog_connection",
                "identity": "1:1",
                "kind": "removed",
                "before": {"catalog_number": 1, "catalog_version": 1},
                "after": None,
                "field_diffs": {},
            },
            self.review_change(analysis_uid="A", occurrence_uid="O"),
        ]

    def test_authoritative_order_preserved(self):
        changes = self.ordered_changes()
        outcome = self.adapt(self.payload(changes=changes))
        self.assertEqual(outcome.status, "semantic")
        self.assertEqual(
            [row.entity_type for row in outcome.rows],
            [change["entity_type"] for change in changes],
        )

    def test_entity_type_inversion_rejected(self):
        changes = self.ordered_changes()
        changes[0], changes[1] = changes[1], changes[0]
        outcome = self.adapt(self.payload(changes=changes))
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason, "invalid_order:changes[1].entity_type")

    def test_identity_inversion_rejected(self):
        changes = [
            self.analysis_change(identity="B"),
            self.analysis_change(identity="A"),
        ]
        outcome = self.adapt(self.payload(changes=changes))
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason, "invalid_order:changes[1].identity")

    def test_kind_inversion_rejected(self):
        changes = [
            self.analysis_change(identity="A", kind="modified"),
            self.analysis_change(identity="A", kind="added"),
        ]
        outcome = self.adapt(self.payload(changes=changes))
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason, "invalid_order:changes[1].kind")


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class GWFlowDiffMalformedTestCase(SemanticDiffTestMixin, BilbyTestCase):
    def test_malformed_root_variants_are_failed(self):
        variants = (
            None,
            [],
            {"sname": "S000001a"},
            {**self.payload(), "extra": True},
        )
        for payload in variants:
            with self.subTest(payload=payload):
                self.assertEqual(self.adapt(payload).status, "failed")

    def test_root_field_predicates_are_exercised(self):
        cases = (
            ("sname", ""),
            ("sname", 1),
            ("baseline_version", "1"),
            ("selected_version", 2.0),
            ("baseline_timestamp", ""),
            ("baseline_timestamp", "not-a-date"),
            ("baseline_timestamp", "2026-01-01T00:00:00"),
            ("selected_timestamp", 1),
            ("selected_timestamp", "2026-01-02T00:00:00"),
            ("changes", {}),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                payload = self.payload()
                payload[field] = value
                self.assertEqual(self.adapt(payload).status, "failed")

    def test_malformed_change_shapes_and_keys_are_failed(self):
        changes = (
            None,
            {},
            {"entity_type": "analysis"},
            {**self.analysis_change(), "extra": True},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assertEqual(
                    self.adapt(self.payload(changes=[change])).status,
                    "failed",
                )

    def test_unknown_entity_and_kind_are_failed(self):
        for field, value in (("entity_type", "unknown"), ("kind", "changed")):
            with self.subTest(field=field):
                change = self.analysis_change()
                change[field] = value
                self.assertEqual(
                    self.adapt(self.payload(changes=[change])).status,
                    "failed",
                )

    def test_non_analysis_deprecated_rejected(self):
        entities = (
            "detector_configuration",
            "gracedb_event",
            "catalog_connection",
            "review",
        )
        for entity_type in entities:
            with self.subTest(entity_type=entity_type):
                change = self.review_change() if entity_type == "review" else self.analysis_change()
                change["entity_type"] = entity_type
                if entity_type != "review":
                    change["identity"] = "identity"
                change["kind"] = "deprecated"
                outcome = self.adapt(self.payload(changes=[change]))
                self.assertEqual(outcome.status, "failed")

    def test_kind_record_matrix_rejections(self):
        cases = []
        added_before = self.analysis_change(kind="added")
        added_before["before"] = {}
        cases.append(added_before)
        added_diffs = self.analysis_change(kind="added")
        added_diffs["field_diffs"] = {"x": {"baseline": None, "selected": 1}}
        cases.append(added_diffs)
        removed_after = self.analysis_change(kind="removed")
        removed_after["after"] = {}
        cases.append(removed_after)
        removed_diffs = self.analysis_change(kind="removed")
        removed_diffs["field_diffs"] = {"x": {"baseline": 1, "selected": None}}
        cases.append(removed_diffs)
        modified_before = self.analysis_change()
        modified_before["before"] = None
        cases.append(modified_before)
        modified_after = self.analysis_change()
        modified_after["after"] = []
        cases.append(modified_after)
        modified_diffs = self.analysis_change()
        modified_diffs["field_diffs"] = []
        cases.append(modified_diffs)

        for index, change in enumerate(cases):
            with self.subTest(index=index):
                self.assertEqual(
                    self.adapt(self.payload(changes=[change])).status,
                    "failed",
                )

    def test_field_diff_entry_structure_rejected(self):
        variants = (
            None,
            {"baseline": 1},
            {"selected": 2},
            {"baseline": 1, "selected": 2, "extra": 3},
        )
        for difference in variants:
            with self.subTest(difference=difference):
                change = self.analysis_change()
                change["field_diffs"] = {"field": difference}
                self.assertEqual(
                    self.adapt(self.payload(changes=[change])).status,
                    "failed",
                )

    def test_partial_array_with_invalid_later_row_rejected_without_rows(self):
        invalid = self.analysis_change(identity="B")
        del invalid["after"]
        outcome = self.adapt(self.payload(changes=[self.analysis_change(identity="A"), invalid]))
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.rows, ())

    def test_transport_and_client_states(self):
        for state, expected in (
            ("down", "unavailable"),
            ("failed", "failed"),
            ("malformed", "failed"),
            ("unexpected", "failed"),
        ):
            with self.subTest(state=state):
                outcome = self.adapt(None, state=state)
                self.assertEqual(outcome.status, expected)
                self.assertIsNotNone(outcome.reason)

    def test_none_payload_with_live_or_stale_is_failed(self):
        for state in ("live", "stale"):
            with self.subTest(state=state):
                self.assertEqual(self.adapt(None, state=state).status, "failed")

    def test_non_string_identity_rejected_for_non_review_entities(self):
        for identity in ("", None, 1, {}):
            with self.subTest(identity=identity):
                change = self.analysis_change()
                change["identity"] = identity
                self.assertEqual(
                    self.adapt(self.payload(changes=[change])).status,
                    "failed",
                )

    def test_gracedb_non_numbers_and_non_mapping_side_rejected(self):
        for value in ("1", [], {}):
            with self.subTest(value=value):
                change = self.gracedb_change()
                change["before"]["has_ns"] = value
                self.assertEqual(
                    self.adapt(self.payload(changes=[change])).status,
                    "failed",
                )
        change = self.gracedb_change()
        change["before"] = []
        self.assertEqual(
            self.adapt(self.payload(changes=[change])).status,
            "failed",
        )


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class GWFlowDiffReviewIdentityTestCase(SemanticDiffTestMixin, BilbyTestCase):
    def test_review_identity_requires_both_components(self):
        for missing in ("analysis_uid", "occurrence_uid"):
            with self.subTest(missing=missing):
                change = self.review_change()
                del change["identity"][missing]
                self.assertEqual(
                    self.adapt(self.payload(changes=[change])).status,
                    "failed",
                )
        for field in ("analysis_uid", "occurrence_uid"):
            for value in ("", None, 1):
                with self.subTest(field=field, value=value):
                    change = self.review_change()
                    change["identity"][field] = value
                    self.assertEqual(
                        self.adapt(self.payload(changes=[change])).status,
                        "failed",
                    )

    def test_scalar_and_extra_key_review_identities_rejected(self):
        for identity in (
            "occurrence-1",
            None,
            {
                "analysis_uid": "analysis-1",
                "occurrence_uid": "occurrence-1",
                "extra": "value",
            },
        ):
            with self.subTest(identity=identity):
                change = self.review_change()
                change["identity"] = identity
                self.assertEqual(
                    self.adapt(self.payload(changes=[change])).status,
                    "failed",
                )

    def test_review_identity_orders_analysis_then_occurrence(self):
        valid = [
            self.review_change(analysis_uid="A", occurrence_uid="Z"),
            self.review_change(analysis_uid="B", occurrence_uid="A"),
        ]
        self.assertEqual(
            self.adapt(self.payload(changes=valid)).status,
            "semantic",
        )
        invalid_analysis = list(reversed(valid))
        self.assertEqual(
            self.adapt(self.payload(changes=invalid_analysis)).status,
            "failed",
        )
        invalid_occurrence = [
            self.review_change(analysis_uid="A", occurrence_uid="Z"),
            self.review_change(analysis_uid="A", occurrence_uid="A"),
        ]
        self.assertEqual(
            self.adapt(self.payload(changes=invalid_occurrence)).status,
            "failed",
        )

    def test_review_ordering_ignores_identity_object_insertion_order(self):
        first = self.review_change(
            analysis_uid="A",
            occurrence_uid="A",
        )
        second = self.review_change(
            analysis_uid="A",
            occurrence_uid="B",
        )
        first["identity"] = {
            "analysis_uid": "A",
            "occurrence_uid": "A",
        }
        second["identity"] = {
            "occurrence_uid": "B",
            "analysis_uid": "A",
        }
        outcome = self.adapt(self.payload(changes=[first, second]))
        self.assertEqual(outcome.status, "semantic")
        self.assertEqual(
            [(row.identity["analysis_uid"], row.identity["occurrence_uid"]) for row in outcome.rows],
            [("A", "A"), ("A", "B")],
        )

        reversed_semantic_identity = self.review_change(
            analysis_uid="A",
            occurrence_uid="A",
        )
        reversed_semantic_identity["identity"] = {
            "occurrence_uid": "A",
            "analysis_uid": "A",
        }
        later = self.review_change(
            analysis_uid="A",
            occurrence_uid="B",
        )
        later["identity"] = {
            "analysis_uid": "A",
            "occurrence_uid": "B",
        }
        outcome = self.adapt(self.payload(changes=[reversed_semantic_identity, later]))
        self.assertEqual(outcome.status, "semantic")

    def test_reviewer_set_change_is_one_modified_row(self):
        change = self.review_change()
        outcome = self.adapt(self.payload(changes=[change]))
        self.assertEqual(outcome.status, "semantic")
        self.assertEqual(len(outcome.rows), 1)
        self.assertEqual(outcome.rows[0].kind, "modified")
        self.assertIs(outcome.rows[0].field_diffs, change["field_diffs"])

    def test_zero_one_and_multiple_reviews(self):
        payloads = (
            self.payload(),
            self.payload(changes=[self.review_change()]),
            self.payload(
                changes=[
                    self.review_change(occurrence_uid="occurrence-1"),
                    self.review_change(occurrence_uid="occurrence-2"),
                ]
            ),
        )
        for expected_count, payload in enumerate(payloads):
            with self.subTest(expected_count=expected_count):
                outcome = self.adapt(payload)
                expected_status = "semantic_empty" if expected_count == 0 else "semantic"
                self.assertEqual(outcome.status, expected_status)
                self.assertEqual(len(outcome.rows), expected_count)

    def test_review_record_required_fields_and_types(self):
        required_fields = (
            "occurrence_uid",
            "name",
            "description",
            "reviewers",
            "passed_review",
            "completion_date",
            "review_status",
        )
        for side in ("before", "after"):
            for field in required_fields:
                with self.subTest(side=side, missing=field):
                    change = self.review_change()
                    del change[side][field]
                    self.assertEqual(
                        self.adapt(self.payload(changes=[change])).status,
                        "failed",
                    )

        mutations = (
            ("occurrence_uid", "", "after"),
            ("occurrence_uid", "different", "after"),
            ("name", None, "after"),
            ("description", None, "after"),
            ("reviewers", {}, "after"),
            ("passed_review", 1, "after"),
            ("completion_date", 1, "after"),
            ("review_status", "unknown", "after"),
        )
        for field, value, side in mutations:
            with self.subTest(field=field, value=value):
                change = self.review_change()
                change[side][field] = value
                self.assertEqual(
                    self.adapt(self.payload(changes=[change])).status,
                    "failed",
                )

    def test_reviewer_structure_rejected(self):
        reviewers = (
            [None],
            [{"name": "Reviewer"}],
            [{"name": "Reviewer", "email_address": "", "extra": ""}],
            [{"name": 1, "email_address": ""}],
            [{"name": "Reviewer", "email_address": None}],
        )
        for value in reviewers:
            with self.subTest(value=value):
                change = self.review_change()
                change["after"]["reviewers"] = value
                self.assertEqual(
                    self.adapt(self.payload(changes=[change])).status,
                    "failed",
                )

    def test_review_non_null_side_must_be_mapping(self):
        change = self.review_change()
        change["after"] = []
        self.assertEqual(
            self.adapt(self.payload(changes=[change])).status,
            "failed",
        )
