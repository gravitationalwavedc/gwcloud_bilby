from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.models import EventID
from bilbyui.services import event_ids as event_ids_service
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestEventIdsService(BilbyTestCase):
    def setUp(self):
        self.user = self.authenticate()

        self.public_event = EventID.objects.create(
            event_id="GW123456_123456",
            is_ligo_event=False,
        )
        self.ligo_event = EventID.objects.create(
            event_id="GW654321_654321",
            is_ligo_event=True,
        )

    def test_list_event_ids_for_user_non_ligo(self):
        with patch("bilbyui.services.event_ids.is_ligo_user", return_value=False):
            events = event_ids_service.list_event_ids_for_user(self.user)

        self.assertEqual(set(events), {self.public_event})

    def test_list_event_ids_for_user_ligo(self):
        with patch("bilbyui.services.event_ids.is_ligo_user", return_value=True):
            events = event_ids_service.list_event_ids_for_user(self.user)

        self.assertEqual(set(events), {self.public_event, self.ligo_event})

    def test_get_event_id(self):
        event = event_ids_service.get_event_id("GW123456_123456", self.user)
        self.assertEqual(event, self.public_event)
