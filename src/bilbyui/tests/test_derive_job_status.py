from django.test import override_settings

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
