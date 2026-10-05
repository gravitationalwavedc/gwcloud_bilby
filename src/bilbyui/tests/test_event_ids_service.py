from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.test import override_settings

from bilbyui.models import EventID
from bilbyui.services import event_ids as event_ids_service
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import reset_embargo_start_cache


@override_settings(IGNORE_ELASTIC_SEARCH=True, EMBARGO_START_TIME=100.0)
class TestEventIdsService(BilbyTestCase):
    def setUp(self):
        reset_embargo_start_cache()
        self.addCleanup(reset_embargo_start_cache)
        self.user = self.authenticate()
        self.public_event = EventID.objects.create(
            event_id="GW123456_123456",
            gps_time=99.0,
        )
        self.ligo_event = EventID.objects.create(
            event_id="GW654321_654321",
            gps_time=100.0,
        )

    def test_list_event_ids_for_user_non_ligo(self):
        events = event_ids_service.list_event_ids_for_user(self.user)
        self.assertEqual(set(events), {self.public_event})

    def test_list_event_ids_for_user_ligo(self):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        events = event_ids_service.list_event_ids_for_user(self.user)
        self.assertEqual(set(events), {self.public_event, self.ligo_event})

    def test_get_event_id(self):
        event = event_ids_service.get_event_id("GW123456_123456", self.user)
        self.assertEqual(event, self.public_event)
