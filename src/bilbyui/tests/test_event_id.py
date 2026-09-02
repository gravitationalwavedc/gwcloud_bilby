from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.contrib.auth import get_user_model

from bilbyui.models import BilbyPermissionError, EventID
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


class TestEventIDGetByEventId(BilbyTestCase):
    def setUp(self):
        self.ligo_event = EventID.create(event_id="GW123456_123456", gps_time=1234567890.0, is_ligo_event=True)
        self.public_event = EventID.create(event_id="GW123456_654321", gps_time=1234567890.0, is_ligo_event=False)

    def test_get_by_event_id_returns_event_for_non_ligo_user(self):
        user = self.create_user()
        self.assertEqual(self.get_by_event_id(self.public_event.event_id, user), self.public_event)

    def test_get_by_event_id_raises_for_ligo_event_non_ligo_user(self):
        user = self.create_user()
        with self.assertRaises(BilbyPermissionError):
            self.get_by_event_id(self.ligo_event.event_id, user)

    def test_get_by_event_id_returns_ligo_event_for_ligo_user(self):
        user = self.create_user(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        self.assertEqual(self.get_by_event_id(self.ligo_event.event_id, user), self.ligo_event)

    def get_by_event_id(self, event_id, user):
        return EventID.get_by_event_id(event_id, user)


class TestEventIDFilterByLigo(BilbyTestCase):
    def setUp(self):
        EventID.create(event_id="GW123456_123456", gps_time=1234567890.0, is_ligo_event=True)
        EventID.create(event_id="GW123456_654321", gps_time=1234567890.0, is_ligo_event=False)

    def test_filter_by_ligo_true_returns_all(self):
        self.assertEqual(EventID.filter_by_ligo(True).count(), 2)

    def test_filter_by_ligo_false_excludes_ligo_events(self):
        self.assertEqual(EventID.filter_by_ligo(False).count(), 1)
        self.assertFalse(EventID.filter_by_ligo(False).filter(is_ligo_event=True).exists())
