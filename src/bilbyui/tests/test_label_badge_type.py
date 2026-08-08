from bilbyui.models import Label
from bilbyui.tests.testcases import BilbyTestCase


class TestLabelBadgeType(BilbyTestCase):
    def assert_badge_type(self, name, expected):
        label = Label(name=name)
        self.assertEqual(label.badge_type, expected)

    def test_completed_maps_to_primary(self):
        self.assert_badge_type("Completed", "primary")

    def test_error_maps_to_danger(self):
        self.assert_badge_type("Error", "danger")

    def test_running_maps_to_info(self):
        self.assert_badge_type("Running", "info")

    def test_unknown_maps_to_dark(self):
        self.assert_badge_type("Unknown", "dark")

    def test_production_run_maps_to_success(self):
        self.assert_badge_type("Production Run", "success")

    def test_bad_run_maps_to_danger(self):
        self.assert_badge_type("Bad Run", "danger")

    def test_review_requested_maps_to_secondary(self):
        self.assert_badge_type("Review Requested", "secondary")

    def test_reviewed_maps_to_info(self):
        self.assert_badge_type("Reviewed", "info")

    def test_official_maps_to_warning(self):
        self.assert_badge_type("Official", "warning")

    def test_unknown_label_defaults_to_secondary(self):
        self.assert_badge_type("Some Custom Label", "secondary")
