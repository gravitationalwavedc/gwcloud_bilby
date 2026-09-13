from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import _gwflow_trigger_time_from_metadata, gwflow_ligo_only_from_metadata


def _metadata_with_events(events):
    return {"GraceDB": {"Events": events}}


class TestGWFlowTriggerTimeFromMetadata(BilbyTestCase):
    def test_missing_metadata(self):
        # Missing GraceDB or Events -> None (never raises).
        self.assertIsNone(_gwflow_trigger_time_from_metadata(None))
        self.assertIsNone(_gwflow_trigger_time_from_metadata({}))
        self.assertIsNone(_gwflow_trigger_time_from_metadata({"GraceDB": {}}))

    def test_events_not_a_list(self):
        self.assertIsNone(_gwflow_trigger_time_from_metadata({"GraceDB": {"Events": "not-a-list"}}))

    def test_no_usable_events(self):
        # Empty list and all-malformed entries -> None.
        self.assertIsNone(_gwflow_trigger_time_from_metadata(_metadata_with_events([])))
        self.assertIsNone(
            _gwflow_trigger_time_from_metadata(
                _metadata_with_events([{"GPSTime": "bad"}, {"GPSTime": None}, "not-a-dict"])
            )
        )

    def test_preferred_event_selected(self):
        # Preferred event is used even when it is not first.
        metadata = _metadata_with_events(
            [
                {"GPSTime": 1000.0},
                {"GPSTime": 2000.0, "State": "preferred"},
            ]
        )
        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 2000.0)

    def test_no_preferred_uses_first_usable(self):
        # No preferred event -> first usable numeric GPSTime is used.
        metadata = _metadata_with_events(
            [
                {"GPSTime": 1000.0},
                {"GPSTime": 2000.0},
            ]
        )
        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 1000.0)

    def test_malformed_entries_skipped(self):
        # Malformed entries (missing/non-numeric GPSTime, non-dict) are
        # skipped before selection; the first usable one is used.
        metadata = _metadata_with_events(
            [
                {"GPSTime": "bad"},
                {"GPSTime": None},
                "not-a-dict",
                {"GPSTime": 2000.0},
            ]
        )
        self.assertEqual(_gwflow_trigger_time_from_metadata(metadata), 2000.0)


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
    def test_malformed_embargo_start_time_fail_open(self):
        # Malformed EMBARGO_START_TIME fails open (public).
        self.assertFalse(gwflow_ligo_only_from_metadata(_metadata_with_events([{"GPSTime": 2000.0}])))
