from types import SimpleNamespace

from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _build_job_row


def _labels_manager(labels):
    return SimpleNamespace(all=lambda: labels)


def _job(event_id=None, labels=None):
    return SimpleNamespace(id=1, labels=_labels_manager(labels or []), event_id=event_id)


def _event_id(event_id="GW123456_123456", trigger_id="S123456a", nickname="GW123456"):
    return SimpleNamespace(event_id=event_id, trigger_id=trigger_id, nickname=nickname)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestBuildJobRow(BilbyTestCase):
    def test_known_status_badge_mapping(self):
        for status_name, expected in (
            ("Completed", "primary"),
            ("Error", "danger"),
            ("Running", "info"),
            ("Unknown", "dark"),
        ):
            with self.subTest(status_name=status_name):
                row = _build_job_row(_job(), status_name, "user", "name", "desc")
                self.assertEqual(row["status_badge_class"], expected)

    def test_unknown_status_falls_back_to_primary(self):
        row = _build_job_row(_job(), "SomeOtherStatus", "user", "name", "desc")
        self.assertEqual(row["status_badge_class"], "primary")

    def test_event_id_display_values(self):
        row = _build_job_row(_job(event_id=_event_id()), "Completed", "user", "name", "desc")
        self.assertEqual(row["event_id_values"], ["GW123456_123456", "S123456a", "GW123456"])

    def test_event_id_none_returns_empty_list(self):
        row = _build_job_row(_job(), "Completed", "user", "name", "desc")
        self.assertEqual(row["event_id_values"], [])

    def test_event_id_filters_empty_fields(self):
        event_id = _event_id(event_id="", trigger_id="S123456a", nickname="")
        row = _build_job_row(_job(event_id=event_id), "Completed", "user", "name", "desc")
        self.assertEqual(row["event_id_values"], ["S123456a"])

    def test_labels_collection(self):
        labels = [SimpleNamespace(id=1, name="Production Run"), SimpleNamespace(id=2, name="Test")]
        row = _build_job_row(_job(labels=labels), "Completed", "user", "name", "desc")
        self.assertEqual(list(row["labels"]), labels)

    def test_description_none_becomes_empty_string(self):
        row = _build_job_row(_job(), "Completed", "user", "name", None)
        self.assertEqual(row["description"], "")

    def test_row_fields(self):
        row = _build_job_row(_job(), "Completed", "buffy", "Test job", "A description")
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["user"], "buffy")
        self.assertEqual(row["name"], "Test job")
        self.assertEqual(row["description"], "A description")
        self.assertEqual(row["status_name"], "Completed")
