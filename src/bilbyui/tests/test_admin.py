from django.contrib import admin
from django.test import override_settings

from bilbyui.admin import EventIDAdmin, IniKeyValueAdmin
from bilbyui.models import BilbyJob, EventID
from bilbyui.tests.testcases import BilbyTestCase


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestIniKeyValueAdmin(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.admin = IniKeyValueAdmin(BilbyJob, admin.site)

    def test_has_change_permission(self):
        self.assertFalse(self.admin.has_change_permission(None, None))

    def test_has_add_permission(self):
        self.assertFalse(self.admin.has_add_permission(None, None))

    def test_has_delete_permission(self):
        self.assertFalse(self.admin.has_delete_permission(None, None))


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestEventIDAdmin(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.admin = EventIDAdmin(EventID, admin.site)

    def test_form_initial_gps_time_is_empty(self):
        form_class = self.admin.get_form(None)
        form = form_class()
        # Form field initial must be None and not the historical default 1126259462.391
        self.assertIsNone(form.fields["gps_time"].initial)
        rendered = form["gps_time"].as_widget()
        self.assertNotIn("1126259462.391", rendered)

    def test_form_valid_with_empty_gps_time(self):
        form_class = self.admin.get_form(None)
        data = {
            "event_id": "GW123456_123456",
            "trigger_id": "",
            "nickname": "",
            "gps_time": "",
        }
        form = form_class(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertIsNone(instance.gps_time)

    def test_form_valid_with_non_empty_gps_time(self):
        form_class = self.admin.get_form(None)
        data = {
            "event_id": "GW123456_654321",
            "trigger_id": "",
            "nickname": "",
            "gps_time": "123456789.0",
        }
        form = form_class(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertEqual(instance.gps_time, 123456789.0)
