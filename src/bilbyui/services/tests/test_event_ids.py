from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.test import override_settings

from bilbyui.models import UNSET, EventID
from bilbyui.services.event_ids import get_event_id, list_event_ids_for_user
from bilbyui.tests.testcases import BilbyTestCase


@override_settings(EMBARGO_START_TIME=100.0)
class TestEventIdsService(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.null_event = EventID.objects.create(
            event_id="GW123456_123456",
            gps_time=None,
            is_ligo_event=True,
        )
        cls.public_event = EventID.objects.create(
            event_id="GW654321_654321",
            gps_time=99.0,
            is_ligo_event=True,
        )
        cls.threshold_event = EventID.objects.create(
            event_id="GW012345_012345",
            gps_time=100.0,
            is_ligo_event=False,
        )
        cls.embargoed_event = EventID.objects.create(
            event_id="GW543210_543210",
            gps_time=101.0,
            is_ligo_event=False,
        )

    def test_list_event_ids_for_non_member_uses_gps_visibility(self):
        user = self.create_user()
        event_ids = set(list_event_ids_for_user(user).values_list("event_id", flat=True))
        self.assertEqual(event_ids, {self.null_event.event_id, self.public_event.event_id})

    def test_list_event_ids_for_anonymous_user_uses_gps_visibility(self):
        event_ids = set(
            list_event_ids_for_user(ADACSAnonymousUser()).values_list("event_id", flat=True)
        )
        self.assertEqual(event_ids, {self.null_event.event_id, self.public_event.event_id})

    def test_list_event_ids_for_member_includes_embargoed_events(self):
        user = self.create_user(
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]
        )
        event_ids = set(list_event_ids_for_user(user).values_list("event_id", flat=True))
        self.assertEqual(
            event_ids,
            {
                self.null_event.event_id,
                self.public_event.event_id,
                self.threshold_event.event_id,
                self.embargoed_event.event_id,
            },
        )

    def test_get_event_id_returns_public_event_for_non_member(self):
        user = self.create_user()
        self.assertEqual(get_event_id(self.public_event.event_id, user), self.public_event)

    def test_get_event_id_returns_nullable_event_for_anonymous_user(self):
        self.assertEqual(
            get_event_id(self.null_event.event_id, ADACSAnonymousUser()),
            self.null_event,
        )

    def test_get_event_id_denies_equality_with_not_found_behavior(self):
        user = self.create_user()
        with self.assertRaises(EventID.DoesNotExist):
            get_event_id(self.threshold_event.event_id, user)

    def test_get_event_id_denied_and_absent_raise_same_exception(self):
        user = self.create_user()
        for event_id in (self.embargoed_event.event_id, "GW999999_999999"):
            with self.subTest(event_id=event_id):
                with self.assertRaises(EventID.DoesNotExist):
                    get_event_id(event_id, user)

    def test_get_event_id_returns_embargoed_event_for_member(self):
        user = self.create_user(
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]
        )
        self.assertEqual(
            get_event_id(self.embargoed_event.event_id, user),
            self.embargoed_event,
        )

    def test_update_gps_time_preserves_only_for_unset(self):
        event = self.public_event
        event.update(gps_time=UNSET)
        event.refresh_from_db()
        self.assertEqual(event.gps_time, 99.0)

        event.update(gps_time=None)
        event.refresh_from_db()
        self.assertIsNone(event.gps_time)

        event.update(gps_time=42.5)
        event.refresh_from_db()
        self.assertEqual(event.gps_time, 42.5)
