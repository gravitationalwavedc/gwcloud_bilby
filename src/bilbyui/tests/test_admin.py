from django.contrib import admin
from django.test import override_settings

from bilbyui.admin import IniKeyValueAdmin
from bilbyui.models import BilbyJob
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
