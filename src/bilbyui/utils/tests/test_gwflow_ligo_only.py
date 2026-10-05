from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import _gwflow_trigger_time_from_metadata, gwflow_ligo_only_from_metadata


def _metadata_with_events(events):
    return {"GraceDB": {"Events": events}}


class TestGWFlowTriggerTimeFromMetadata(BilbyTestCase):
    def test_top_level_gracedb(self):
        metadata = _metadata_with_events([{"GPSTime": "1234.5"}])

        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 1234.5)

    def test_nested_raw_payload_gracedb(self):
        metadata = {"raw_payload": _metadata_with_events([{"GPSTime": 2345.6}])}

        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 2345.6)

    def test_lowercase_shapes_and_gps_spellings(self):
        cases = (
            ({"gracedb": {"events": [{"gps_time": "0"}]}}, 0.0),
            ({"raw_payload": {"gracedb": {"events": [{"gpstime": 3456.7}]}}}, 3456.7),
        )

        for metadata, expected in cases:
            with self.subTest(metadata=metadata):
                self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), expected)

    def test_mapping_precedence(self):
        metadata = {
            "GraceDB": {"Events": [{"GPSTime": 1000.0}]},
            "raw_payload": {"GraceDB": {"Events": [{"GPSTime": 2000.0}]}},
            "gracedb": {"events": [{"gps_time": 3000.0}]},
        }

        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 1000.0)

    def test_top_level_mapping_does_not_fall_through_for_bad_events(self):
        cases = (
            {
                "GraceDB": {},
                "raw_payload": {"GraceDB": {"Events": [{"GPSTime": 2000.0}]}},
            },
            {
                "GraceDB": {"Events": "not-a-list"},
                "raw_payload": {"GraceDB": {"Events": [{"GPSTime": 2000.0}]}},
            },
            {
                "GraceDB": {"Events": [{"GPSTime": "bad"}]},
                "raw_payload": {"GraceDB": {"Events": [{"GPSTime": 2000.0}]}},
            },
        )

        for metadata in cases:
            with self.subTest(metadata=metadata):
                self.assertIsNone(_gwflow_trigger_time_from_metadata(metadata))

    def test_non_mapping_higher_precedence_value_falls_through(self):
        metadata = {
            "GraceDB": "not-a-mapping",
            "raw_payload": {"GraceDB": {"Events": [{"GPSTime": 2000.0}]}},
        }

        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 2000.0)

    def test_preferred_usable_event_wins(self):
        metadata = _metadata_with_events(
            [
                {"GPSTime": "bad", "State": "preferred"},
                {"GPSTime": 1000.0},
                {"GPSTime": 2000.0, "state": "preferred"},
            ]
        )

        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 2000.0)

    def test_first_usable_event_is_fallback(self):
        metadata = _metadata_with_events(
            [
                "not-a-mapping",
                {"GPSTime": "bad"},
                {"GPSTime": 1000.0},
                {"GPSTime": 2000.0},
            ]
        )

        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 1000.0)

    def test_gps_key_precedence_and_none_fallthrough(self):
        cases = (
            ({"GPSTime": None, "gps_time": "11.5", "gpstime": 12.5}, 11.5),
            ({"GPSTime": None, "gps_time": None, "gpstime": "13.5"}, 13.5),
        )

        for event, expected in cases:
            with self.subTest(event=event):
                self.assertEqual(
                    _gwflow_trigger_time_from_metadata(_metadata_with_events([event])),
                    expected,
                )

    def test_malformed_earlier_gps_key_makes_event_unusable(self):
        metadata = _metadata_with_events(
            [
                {"GPSTime": "bad", "gps_time": 1000.0, "State": "preferred"},
                {"GPSTime": 2000.0},
            ]
        )

        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 2000.0)

    def test_boolean_gps_values_are_rejected(self):
        cases = (
            _metadata_with_events([{"GPSTime": True}]),
            _metadata_with_events([{"GPSTime": False}]),
            {"raw_payload": {"gracedb": {"events": [{"gps_time": True}]}}},
        )

        for metadata in cases:
            with self.subTest(metadata=metadata):
                self.assertIsNone(_gwflow_trigger_time_from_metadata(metadata))

    def test_preferred_boolean_event_is_unusable(self):
        metadata = _metadata_with_events(
            [
                {"GPSTime": True, "State": "preferred"},
                {"GPSTime": 2000.0},
            ]
        )

        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 2000.0)

    def test_non_finite_and_overflow_values_are_rejected(self):
        values = (float("nan"), float("inf"), float("-inf"), "nan", "inf", "-inf", "1e10000", 10**10000)

        for index, value in enumerate(values):
            with self.subTest(index=index, value_type=type(value).__name__):
                self.assertIsNone(_gwflow_trigger_time_from_metadata(_metadata_with_events([{"GPSTime": value}])))

    def test_malformed_and_missing_metadata_return_none(self):
        cases = (
            None,
            [],
            {},
            {"raw_payload": "not-a-mapping"},
            {"GraceDB": {}},
            {"GraceDB": {"Events": []}},
            {"GraceDB": {"Events": "not-a-list"}},
            {"GraceDB": {"Events": [None, {}, {"GPSTime": None}]}},
            {"GraceDB": {"Events": [{"GPSTime": []}]}},
        )

        for metadata in cases:
            with self.subTest(metadata=metadata):
                self.assertIsNone(_gwflow_trigger_time_from_metadata(metadata))


class TestGWFlowLigoOnlyFromMetadata(BilbyTestCase):
    @override_settings(EMBARGO_START_TIME=None)
    def test_no_embargo_start_time(self):
        # EMBARGO_START_TIME is None -> always public (False), regardless of trigger.
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": 2000.0}])))
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": 100.0}])))
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([])))
        self.assertFalse(gwflow_ligo_only_from_metadata({}))
        self.assertFalse(gwflow_ligo_only_from_metadata(None))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_trigger_below_threshold(self):
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": 1000.0}])))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_trigger_equal_threshold(self):
        # Equality is LIGO-only.
        self.assertTrue(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": 1500.0}])))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_trigger_above_threshold(self):
        self.assertTrue(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": 2000.0}])))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_malformed_gps_time(self):
        # Non-numeric or missing GPSTime -> no usable event -> fail-open (False).
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": "not-a-number"}])))
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": None}])))
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([{}])))
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": [1, 2]}])))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_boolean_gps_time_fail_open(self):
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": True}])))
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": False}])))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_missing_event(self):
        self.assertFalse(gwflow_ligo_only_from_metadata({}))
        self.assertFalse(gwflow_ligo_only_from_metadata({"GraceDB": {}}))
        self.assertFalse(gwflow_ligo_only_from_metadata({"GraceDB": {"Events": []}}))
        self.assertFalse(gwflow_ligo_only_from_metadata({"GraceDB": {"Events": "not-a-list"}}))
        self.assertFalse(gwflow_ligo_only_from_metadata(None))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_preferred_event_selected(self):
        # Preferred event present -> its GPSTime is used even if it is not first.
        metadata = _metadata_with_events(
            [
                {"GPSTime": 1000.0},
                {"GPSTime": 2000.0, "State": "preferred"},
            ]
        )
        self.assertTrue(gwflow_ligo_only_from_metadata(metadata))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_no_preferred_uses_first_usable(self):
        # No preferred event -> first usable numeric GPSTime is used.
        metadata = _metadata_with_events(
            [
                {"GPSTime": 1000.0},
                {"GPSTime": 2000.0},
            ]
        )
        self.assertFalse(gwflow_ligo_only_from_metadata(metadata))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_malformed_entries_skipped(self):
        # Malformed entries (missing/non-numeric GPSTime) are skipped before
        # selection; the first usable one is used.
        metadata = _metadata_with_events(
            [
                {"GPSTime": "bad"},
                {"GPSTime": None},
                {"GPSTime": 2000.0},
            ]
        )
        self.assertTrue(gwflow_ligo_only_from_metadata(metadata))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_none_usable_fail_open(self):
        # All entries malformed -> no usable event -> fail-open (False).
        metadata = _metadata_with_events(
            [
                {"GPSTime": "bad"},
                {"GPSTime": None},
                "not-a-dict",
            ]
        )
        self.assertFalse(gwflow_ligo_only_from_metadata(metadata))

    @override_settings(EMBARGO_START_TIME="1500.0")
    def test_embargo_start_time_as_string(self):
        # EMBARGO_START_TIME arrives as a string from the environment; it is
        # cast to a numeric threshold. Equality is LIGO-only.
        self.assertTrue(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": 1500.0}])))
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": 1000.0}])))

    @override_settings(EMBARGO_START_TIME="not-a-number")
    def test_malformed_embargo_start_time_fail_closed(self):
        # Malformed non-null EMBARGO_START_TIME is a deployment error.
        with self.assertRaises(ImproperlyConfigured):
            gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": 2000.0}]))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_lowercase_shape(self):
        # Canonical lowercase portal shape (gracedb/events/gps_time) yields
        # the correct ligo_only value instead of always public.
        metadata = {"gracedb": {"events": [{"state": "preferred", "gps_time": 2000.0}]}}
        self.assertTrue(gwflow_ligo_only_from_metadata(metadata))
        metadata_below = {"gracedb": {"events": [{"state": "preferred", "gps_time": 1000.0}]}}
        self.assertFalse(gwflow_ligo_only_from_metadata(metadata_below))
