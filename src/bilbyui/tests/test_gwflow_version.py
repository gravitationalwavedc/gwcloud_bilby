from datetime import UTC, datetime, timedelta, timezone

from django.test import override_settings

from bilbyui.models import GWFlowJob
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
