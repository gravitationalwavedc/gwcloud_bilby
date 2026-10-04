from unittest.mock import patch

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.models import EventID
from bilbyui.services import event_ids as event_ids_service
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import reset_embargo_start_cache

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

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_list_event_ids_for_user_embargoed_by_trigger_time(self):
        reset_embargo_start_cache()
        embargoed_event = EventID.objects.create(
            event_id="GW999999_999999",
            is_ligo_event=False,
            gps_time=2.0,
        )

        non_ligo_user = self.create_user(id=2)
        events = event_ids_service.list_event_ids_for_user(non_ligo_user)
        self.assertNotIn(embargoed_event, events)
        self.assertIn(self.public_event, events)

        ligo_user = self.create_user(
            id=3,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        events = event_ids_service.list_event_ids_for_user(ligo_user)
        self.assertIn(embargoed_event, events)
