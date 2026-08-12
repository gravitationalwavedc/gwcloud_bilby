from django.test import override_settings

from bilbyui.status import JobStatus
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.derive_job_status import derive_job_status


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class DeriveJobStatusTestCase(BilbyTestCase):
    def test_empty_history_returns_draft_fallback(self):
        state, name, timestamp = derive_job_status([])

        self.assertEqual(state, 0)
        self.assertEqual(name, "Unknown")
        self.assertIsNone(timestamp)

    def test_latest_status_selected_by_timestamp(self):
        history = [
            {"timestamp": "2024-01-01 00:00:00.000000 UTC", "state": 30},
            {"timestamp": "2024-01-03 00:00:00.000000 UTC", "state": 50},
            {"timestamp": "2024-01-02 00:00:00.000000 UTC", "state": 40},
        ]

        state, name, timestamp = derive_job_status(history)

        self.assertEqual(state, 50)
        self.assertEqual(name, "Running")
        self.assertEqual(str(timestamp), "2024-01-03 00:00:00")

    def test_none_history_returns_draft_fallback(self):
        state, name, timestamp = derive_job_status(None)

        self.assertEqual(state, JobStatus.DRAFT)
        self.assertEqual(name, "Unknown")
        self.assertIsNone(timestamp)

    def test_non_list_history_returns_draft_fallback(self):
        state, name, timestamp = derive_job_status({"timestamp": "2024-01-01 00:00:00 UTC", "state": 50})

        self.assertEqual(state, JobStatus.DRAFT)
        self.assertEqual(name, "Unknown")
        self.assertIsNone(timestamp)

    def test_non_dict_entries_are_ignored(self):
        history = [
            "not a dict",
            42,
            {"timestamp": "2024-01-01 00:00:00 UTC", "state": 30},
        ]

        state, name, timestamp = derive_job_status(history)

        self.assertEqual(state, 30)
        self.assertEqual(name, "Submitted")
        self.assertEqual(str(timestamp), "2024-01-01 00:00:00")

    def test_missing_state_is_ignored(self):
        history = [
            {"timestamp": "2024-01-01 00:00:00 UTC"},
            {"timestamp": "2024-01-02 00:00:00 UTC", "state": 40},
        ]

        state, name, timestamp = derive_job_status(history)

        self.assertEqual(state, 40)
        self.assertEqual(name, "Queued")
        self.assertEqual(str(timestamp), "2024-01-02 00:00:00")

    def test_unparseable_timestamps_are_ignored(self):
        history = [
            {"timestamp": "not-a-timestamp", "state": 30},
            {"timestamp": "2024-01-01 00:00:00 UTC", "state": 50},
        ]

        state, name, timestamp = derive_job_status(history)

        self.assertEqual(state, 50)
        self.assertEqual(name, "Running")
        self.assertEqual(str(timestamp), "2024-01-01 00:00:00")

    def test_no_valid_entries_returns_draft_fallback(self):
        history = [
            "not a dict",
            {"state": 30},
            {"timestamp": "not-a-timestamp", "state": 30},
        ]

        state, name, timestamp = derive_job_status(history)

        self.assertEqual(state, JobStatus.DRAFT)
        self.assertEqual(name, "Unknown")
        self.assertIsNone(timestamp)

    def test_timestamp_without_microseconds_is_parsed(self):
        history = [{"timestamp": "2024-01-01 12:34:56 UTC", "state": 50}]

        state, name, timestamp = derive_job_status(history)

        self.assertEqual(state, 50)
        self.assertEqual(name, "Running")
        self.assertEqual(str(timestamp), "2024-01-01 12:34:56")

    def test_unknown_state_uses_unknown_display_name(self):
        history = [{"timestamp": "2024-01-01 00:00:00 UTC", "state": 999}]

        state, name, timestamp = derive_job_status(history)

        self.assertEqual(state, 999)
        self.assertEqual(name, "Unknown")
        self.assertEqual(str(timestamp), "2024-01-01 00:00:00")
