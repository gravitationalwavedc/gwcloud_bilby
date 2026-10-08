from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import _gwflow_trigger_time_from_metadata


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

    def test_top_level_wins_over_raw_payload_across_key_case(self):
        cases = (
            (
                {
                    "gracedb": {"Events": [{"GPSTime": 100.0}]},
                    "raw_payload": {"GraceDB": {"Events": [{"GPSTime": 200.0}]}},
                },
                100.0,
            ),
            (
                {
                    "GraceDB": {"Events": [{"GPSTime": 100.0}]},
                    "raw_payload": {"gracedb": {"Events": [{"GPSTime": 200.0}]}},
                },
                100.0,
            ),
        )

        for metadata, expected in cases:
            with self.subTest(metadata=metadata):
                self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), expected)

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

    def test_preferred_event_gps_fallback(self):
        # No usable per-event GPS time -> gracedb-level preferred_event_gps is used.
        metadata = {"gracedb": {"events": [{"gps_time": None}], "preferred_event_gps": 2000.0}}
        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 2000.0)

    def test_gps_time_fallback(self):
        # No usable per-event GPS time and no preferred_event_gps ->
        # gracedb-level gps_time is used.
        metadata = {"gracedb": {"events": [], "gps_time": 2000.0}}
        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 2000.0)

    def test_no_gracedb_gps_fallback_returns_none(self):
        # No usable event GPS and no gracedb-level fallback -> None.
        metadata = {"gracedb": {"events": [{"gps_time": "bad"}], "preferred_event_gps": None, "gps_time": None}}
        self.assertIsNone(_gwflow_trigger_time_from_metadata(metadata))

    def test_capitalized_state_preferred_selected(self):
        # Capitalised preferred state (State/state: "Preferred") is treated
        # as preferred, matching resolve_event_id_for's case-insensitive match.
        metadata_cap = _metadata_with_events(
            [
                {"GPSTime": 1000.0},
                {"GPSTime": 2000.0, "State": "Preferred"},
            ]
        )
        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata_cap), 2000.0)
        metadata_lower_shape = {"gracedb": {"events": [{"state": "Preferred", "gps_time": 2000.0}]}}
        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata_lower_shape), 2000.0)
