from bilbyui.models import EventID
from bilbyui.services.event_ids import get_event_id, list_event_ids_for_user
from bilbyui.tests.testcases import BilbyTestCase


class TestEventIdsService(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.public_event = EventID.objects.create(event_id="GW123456_123456", is_ligo_event=False)
        EventID.objects.create(event_id="GW654321_654321", is_ligo_event=False)
        cls.ligo_event = EventID.objects.create(event_id="GW012345_012345", is_ligo_event=True)
        EventID.objects.create(event_id="GW543210_543210", is_ligo_event=True)

    def test_list_event_ids_for_user_non_ligo_excludes_ligo_events(self):
        self.authenticate()
        event_ids = list(list_event_ids_for_user(self.user).values_list("event_id", flat=True))
        self.assertEqual(len(event_ids), 2)
        self.assertNotIn("GW012345_012345", event_ids)
        self.assertNotIn("GW543210_543210", event_ids)

    def test_list_event_ids_for_user_ligo_includes_ligo_events(self):
        self.authenticate(authentication_method="ligo_shibboleth")
        event_ids = list(list_event_ids_for_user(self.user).values_list("event_id", flat=True))
        self.assertEqual(len(event_ids), 4)
        self.assertIn("GW012345_012345", event_ids)
        self.assertIn("GW543210_543210", event_ids)

    def test_get_event_id_returns_non_ligo_event(self):
        self.authenticate()
        event = get_event_id(self.public_event.event_id, self.user)
        self.assertEqual(event, self.public_event)

    def test_get_event_id_returns_ligo_event_for_ligo_user(self):
        self.authenticate(authentication_method="ligo_shibboleth")
        event = get_event_id(self.ligo_event.event_id, self.user)
        self.assertEqual(event, self.ligo_event)

    def test_get_event_id_raises_for_ligo_event_non_ligo_user(self):
        self.authenticate()
        with self.assertRaises(Exception) as ctx:
            get_event_id(self.ligo_event.event_id, self.user)
        self.assertEqual(str(ctx.exception), "Permission Denied")

    def test_get_event_id_raises_for_unknown_event(self):
        self.authenticate()
        with self.assertRaises(EventID.DoesNotExist):
            get_event_id("GW999999_999999", self.user)
