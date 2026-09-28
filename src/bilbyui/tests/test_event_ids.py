from unittest.mock import patch

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import override_settings

from bilbyui.models import BilbyPermissionError, EventID
from bilbyui.tests.test_utils import silence_errors
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import create_event_id

User = get_user_model()

create_mutation = """
    mutation CreateEventIDMutation($input: EventIDMutationInput!) {
        createEventId (input: $input) {
            result
        }
    }
"""

update_mutation = """
    mutation UpdateEventIDMutation($input: UpdateEventIDMutationInput!) {
        updateEventId (input: $input) {
            result
        }
    }
"""

delete_mutation = """
    mutation DeleteEventIDMutation($input: DeleteEventIDMutationInput!) {
        deleteEventId (input: $input) {
            result
        }
    }
"""

get_event_id_query = """
    query ($eventId: String!){
        eventId (eventId: $eventId) {
            eventId
            triggerId
            nickname
            isLigoEvent
            gpsTime
        }
    }
"""

get_all_event_ids_query = """
    query {
        allEventIds {
            eventId
            isLigoEvent
        }
    }
"""


@override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[1])
class TestEventIDCreation(BilbyTestCase):
    def setUp(self):
        self.query_string = create_mutation

        self.params = {
            "input": {
                "eventId": "GW123456_123456",
                "triggerId": "S123456a",
                "nickname": "GW123456",
                "isLigoEvent": False,
                "gpsTime": 12345678.1234,
            }
        }

    @silence_errors
    def test_create_event_id(self):
        response = self.query(self.query_string, input_data=self.params)
        self.assertResponseHasErrors(response)
        self.assertFalse(EventID.objects.all().exists())

        self.authenticate()

        response = self.query(self.query_string, input_data=self.params["input"])
        self.assertResponseNoErrors(response)

        # Check that the event has input params
        event = EventID.objects.all().last()
        self.assertEqual(event.event_id, self.params["input"]["eventId"])
        self.assertEqual(event.trigger_id, self.params["input"]["triggerId"])
        self.assertEqual(event.nickname, self.params["input"]["nickname"])
        self.assertEqual(event.is_ligo_event, self.params["input"]["isLigoEvent"])
        self.assertEqual(event.gps_time, self.params["input"]["gpsTime"])

    def test_valid_legacy_event_id(self):
        event = EventID.create(event_id="GW150914", gps_time=1126259462.391)
        event.clean_fields()
        self.assertEqual(event.event_id, "GW150914")
        self.assertEqual(event.gps_time, 1126259462.391)

    def test_valid_canonical_event_id(self):
        event = EventID.create(event_id="GW150914_095045", gps_time=1126259462.391)
        event.clean_fields()
        self.assertEqual(event.event_id, "GW150914_095045")
        self.assertEqual(event.gps_time, 1126259462.391)

    def test_valid_gracedb_event_id(self):
        event = EventID.create(event_id="G409107", gps_time=1234567890.0)
        event.clean_fields()
        self.assertEqual(event.event_id, "G409107")
        self.assertEqual(event.gps_time, 1234567890.0)

    def test_valid_legacy_trigger_id(self):
        event = EventID.create(event_id="GW123456", trigger_id="G184098", gps_time=1126259462.391)
        event.clean_fields()
        self.assertEqual(event.event_id, "GW123456")
        self.assertEqual(event.trigger_id, "G184098")
        self.assertEqual(event.gps_time, 1126259462.391)

    def test_valid_superevent_trigger_id(self):
        event = EventID.create(event_id="GW123456_123456", trigger_id="S230601ag", gps_time=1234567890.0)
        event.clean_fields()
        self.assertEqual(event.event_id, "GW123456_123456")
        self.assertEqual(event.trigger_id, "S230601ag")
        self.assertEqual(event.gps_time, 1234567890.0)

    @silence_errors
    def test_bad_event_ids(self):
        self.authenticate()

        bad_event_ids = [
            "GW12345",  # Too few digits for legacy GW
            "GW123456_1234567",  # Too many characters
            "GW123456_12345",  # Too few characters
            "GW1234567_12345",  # Underscore in wrong place
            "GG123456_123456",  # Should start with GW
            "G123456_123456",  # Underscore invalid with G prefix
            "123456_123456",  # Should start with GW or G
            "GW123456-123456",  # Should have underscore
            "GW123a56-123456",  # Must not have letters after the GW
            "invalid",
        ]
        for event_id in bad_event_ids:
            self.params["input"]["eventId"] = event_id
            response = self.query(self.query_string, input_data=self.params["input"])
            self.assertResponseHasErrors(response)
            self.assertFalse(EventID.objects.all().exists())

    @silence_errors
    def test_bad_trigger_ids(self):
        self.authenticate()

        bad_trigger_ids = [
            "S123456",  # Must end with 1 or 2 letters
            "S123456abc",  # Must end with 1 or 2 letters
            "S_123456a",  # Should not have underscore
            "S1234567a",  # Too many numbers
            "S12345a",  # Too few numbers
            "123456a",  # Must start with S
            "G123456a",  # Must not end with letters when using G prefix
            "invalid",
        ]
        for trigger_id in bad_trigger_ids:
            self.params["input"]["triggerId"] = trigger_id
            response = self.query(self.query_string, input_data=self.params["input"])
            self.assertResponseHasErrors(response)
            self.assertFalse(EventID.objects.all().exists())

    def test_invalid_event_ids_raise_validation_error(self):
        bad_event_ids = [
            "GW12345",
            "GW1234567",
            "GW123456_12345",
            "GW123456_1234567",
            "S123456a",
            "invalid",
        ]
        for bad_id in bad_event_ids:
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(ValidationError):
                    event = EventID(event_id=bad_id, gps_time=1234567890.0)
                    event.clean_fields()

    def test_invalid_trigger_ids_raise_validation_error(self):
        bad_trigger_ids = [
            "S12345",
            "S123456",
            "S1234567a",
            "S123456abc",
            "G123456a",
            "GW123456",
            "invalid",
        ]
        for bad_trigger in bad_trigger_ids:
            with self.subTest(bad_trigger=bad_trigger):
                with self.assertRaises(ValidationError):
                    event = EventID(
                        event_id="GW123456_123456",
                        trigger_id=bad_trigger,
                        gps_time=1234567890.0,
                    )
                    event.clean_fields()

    @silence_errors
    def test_create_event_id_mutation_idempotent(self):
        self.authenticate()

        # Initial creation
        response = self.query(self.query_string, input_data=self.params["input"])
        self.assertResponseNoErrors(response)
        self.assertEqual(
            response.data["createEventId"]["result"],
            f"EventID {self.params['input']['eventId']} successfully created!",
        )

        # Duplicate call with identical input succeeds and reports already exists
        response2 = self.query(self.query_string, input_data=self.params["input"])
        self.assertResponseNoErrors(response2)
        self.assertEqual(
            response2.data["createEventId"]["result"],
            f"EventID {self.params['input']['eventId']} already exists (updated)!",
        )
        self.assertEqual(EventID.objects.filter(event_id=self.params["input"]["eventId"]).count(), 1)

    @silence_errors
    def test_create_event_id_mutation_non_permitted_user_blocked(self):
        self.authenticate()
        with override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[]):
            response = self.query(self.query_string, input_data=self.params["input"])
            self.assertResponseHasErrors(response)
            self.assertEqual(response.errors[0]["message"], "User is not permitted to create EventIDs")

    def test_create_event_id_idempotent_duplicate(self):
        user = self.create_user()
        event_id = "GW150914"
        gps_time = 1126259462.391

        msg1 = create_event_id(user, event_id=event_id, gps_time=gps_time)
        self.assertEqual(msg1, f"EventID {event_id} successfully created!")
        self.assertEqual(EventID.objects.filter(event_id=event_id).count(), 1)

        msg2 = create_event_id(user, event_id=event_id, gps_time=gps_time)
        self.assertEqual(msg2, f"EventID {event_id} already exists (updated)!")
        self.assertEqual(EventID.objects.filter(event_id=event_id).count(), 1)

    def test_create_event_id_idempotent_backfills_trigger_id(self):
        user = self.create_user()
        event_id = "GW123456_123456"
        gps_time = 1234567890.0

        msg1 = create_event_id(user, event_id=event_id, gps_time=gps_time, trigger_id=None)
        self.assertEqual(msg1, f"EventID {event_id} successfully created!")
        event = EventID.objects.get(event_id=event_id)
        self.assertIsNone(event.trigger_id)

        msg2 = create_event_id(user, event_id=event_id, gps_time=gps_time, trigger_id="S230601ag")
        self.assertEqual(msg2, f"EventID {event_id} already exists (updated)!")
        event.refresh_from_db()
        self.assertEqual(event.trigger_id, "S230601ag")

        # Calling again does not clobber existing trigger_id even if a different one is passed
        msg3 = create_event_id(user, event_id=event_id, gps_time=gps_time, trigger_id="S230602ab")
        self.assertEqual(msg3, f"EventID {event_id} already exists (updated)!")
        event.refresh_from_db()
        self.assertEqual(event.trigger_id, "S230601ag")

    def test_create_event_id_idempotent_backfills_nickname(self):
        user = self.create_user()
        event_id = "GW123456_123456"
        gps_time = 1234567890.0

        msg1 = create_event_id(user, event_id=event_id, gps_time=gps_time, nickname=None)
        self.assertEqual(msg1, f"EventID {event_id} successfully created!")
        event = EventID.objects.get(event_id=event_id)
        self.assertIsNone(event.nickname)

        msg2 = create_event_id(user, event_id=event_id, gps_time=gps_time, nickname="GW150914")
        self.assertEqual(msg2, f"EventID {event_id} already exists (updated)!")
        event.refresh_from_db()
        self.assertEqual(event.nickname, "GW150914")

        # Calling again does not clobber existing nickname even if a different one is passed
        msg3 = create_event_id(user, event_id=event_id, gps_time=gps_time, nickname="GWOther")
        self.assertEqual(msg3, f"EventID {event_id} already exists (updated)!")
        event.refresh_from_db()
        self.assertEqual(event.nickname, "GW150914")

    def test_create_event_id_validation_still_enforced(self):
        user = self.create_user()
        with self.assertRaises(ValidationError):
            create_event_id(user, event_id="invalid_event_id", gps_time=1234567890.0)

        with self.assertRaises(ValidationError):
            create_event_id(user, event_id="GW150914", trigger_id="invalid_trigger", gps_time=1234567890.0)

        # Also verify validation error when backfilling invalid trigger_id
        create_event_id(user, event_id="GW150914", gps_time=1234567890.0)
        with self.assertRaises(ValidationError):
            create_event_id(user, event_id="GW150914", trigger_id="invalid_trigger", gps_time=1234567890.0)

    def test_create_event_id_concurrent_race_integrity_error(self):
        user = self.create_user()
        event_id = "GW150914"
        gps_time = 1126259462.391

        # Simulate IntegrityError on save due to concurrent insertion race
        with patch.object(EventID, "save", side_effect=IntegrityError("duplicate key")):
            msg = create_event_id(user, event_id=event_id, gps_time=gps_time)
            self.assertEqual(msg, f"EventID {event_id} already exists (updated)!")



@override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[1])
class TestEventIDUpdating(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.query_string = update_mutation

        self.original_event = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=1126259462.391,
        )

    @silence_errors
    def test_update_event_id(self):
        new_params = {
            "input": {
                "eventId": "GW123456_123456",
                "triggerId": "S234567a",
                "nickname": "new nickname",
                "isLigoEvent": False,
                "gpsTime": 87654321.87654321,
            }
        }
        response = self.query(self.query_string, input_data=new_params["input"])
        self.assertResponseHasErrors(response)

        event = EventID.objects.all().last()
        self.assertEqual(event.event_id, self.original_event.event_id)
        self.assertEqual(event.trigger_id, self.original_event.trigger_id)
        self.assertEqual(event.nickname, self.original_event.nickname)
        self.assertEqual(event.is_ligo_event, self.original_event.is_ligo_event)
        self.assertEqual(event.gps_time, self.original_event.gps_time)

        self.authenticate()

        response = self.query(self.query_string, input_data=new_params["input"])
        self.assertResponseNoErrors(response)

        # Check that the event has input params
        event = EventID.objects.all().last()
        self.assertEqual(event.event_id, new_params["input"]["eventId"])
        self.assertEqual(event.trigger_id, new_params["input"]["triggerId"])
        self.assertEqual(event.nickname, new_params["input"]["nickname"])
        self.assertEqual(event.is_ligo_event, new_params["input"]["isLigoEvent"])
        self.assertEqual(event.gps_time, new_params["input"]["gpsTime"])

    @silence_errors
    def test_update_nonexistent_event_id(self):
        self.authenticate()

        response = self.query(
            self.query_string,
            input_data={
                "eventId": "GW999999_999999",
                "triggerId": "S123456a",
                "nickname": "new nickname",
                "isLigoEvent": False,
                "gpsTime": 87654321.87654321,
            },
        )

        self.assertResponseHasErrors(response)

        event = EventID.objects.all().last()
        self.assertEqual(event.event_id, self.original_event.event_id)
        self.assertEqual(event.trigger_id, self.original_event.trigger_id)
        self.assertEqual(event.nickname, self.original_event.nickname)
        self.assertEqual(event.is_ligo_event, self.original_event.is_ligo_event)
        self.assertEqual(event.gps_time, self.original_event.gps_time)

    @silence_errors
    def test_update_bad_trigger_ids(self):
        self.authenticate()

        bad_trigger_ids = [
            "S123456",  # Must end with 1 or 2 letters
            "S123456abc",  # Must end with 1 or 2 letters
            "S_123456a",  # Should not have underscore
            "S1234567a",  # Too many numbers
            "S12345a",  # Too few numbers
            "123456a",  # Must start with S
            "G123456a",  # Must start with S
        ]
        for trigger_id in bad_trigger_ids:
            response = self.query(
                self.query_string,
                input_data={
                    "eventId": "GW123456_123456",
                    "triggerId": trigger_id,
                },
            )

            self.assertResponseHasErrors(response)

            event = EventID.objects.get(event_id="GW123456_123456")
            self.assertEqual(event.trigger_id, "S123456a")
            self.assertNotEqual(event.trigger_id, trigger_id)


@override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[1])
class TestEventIDDeletion(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.query_string = delete_mutation

        EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
        )

    @silence_errors
    def test_delete_event_id(self):
        params = {
            "input": {
                "eventId": "GW123456_123456",
            }
        }

        response = self.query(self.query_string, input_data=params["input"])

        self.assertResponseHasErrors(response)

        self.authenticate()

        self.assertTrue(EventID.objects.filter(event_id="GW123456_123456").exists())
        response = self.query(self.query_string, input_data=params["input"])

        self.assertResponseNoErrors(response)

        self.assertFalse(EventID.objects.filter(event_id="GW123456_123456").exists())

    @silence_errors
    def test_delete_nonexistent_event_id(self):
        self.authenticate()

        self.assertTrue(EventID.objects.filter(event_id="GW123456_123456").exists())

        response = self.query(
            self.query_string,
            input_data={"eventId": "GW999999_999999"},
        )

        self.assertResponseHasErrors(response)

        self.assertTrue(EventID.objects.filter(event_id="GW123456_123456").exists())


@override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[1])
class TestEventIDPermissions(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.event_id1 = EventID.objects.create(event_id="GW123456_123456", is_ligo_event=False)
        self.event_id2 = EventID.objects.create(event_id="GW654321_654321", is_ligo_event=False)
        self.event_id_ligo1 = EventID.objects.create(event_id="GW012345_012345", is_ligo_event=True)
        self.event_id_ligo2 = EventID.objects.create(event_id="GW543210_543210", is_ligo_event=True)

    @silence_errors
    def test_create_event_id_permissions(self):
        new_event_id = "GW111111_111111"
        params = {"input": {"eventId": new_event_id, "gpsTime": 1126259462.391}}

        # Run this test twice, the first time without an authenticated user, and the second with an authenticated user
        for _ in range(2):
            with override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[]):
                response = self.query(create_mutation, input_data=params["input"])
                self.assertResponseHasErrors(response)
                self.assertFalse(EventID.objects.filter(event_id=new_event_id).exists())

            self.authenticate()

        response = self.query(create_mutation, input_data=params["input"])
        self.assertResponseNoErrors(response)
        self.assertTrue(EventID.objects.filter(event_id=new_event_id).exists())

    @silence_errors
    def test_update_event_id_permissions(self):
        new_trigger_id = "S111111a"
        params = {
            "input": {
                "eventId": self.event_id1.event_id,
                "triggerId": new_trigger_id,
                "gpsTime": 1126259462.391,
            }
        }

        # Run this test twice, the first time without an authenticated user, and the second with an authenticated user
        for _ in range(2):
            with override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[]):
                response = self.query(update_mutation, input_data=params["input"])
                self.assertResponseHasErrors(response)
                self.assertNotEqual(new_trigger_id, self.event_id1.trigger_id)

            self.authenticate()

        response = self.query(update_mutation, input_data=params["input"])
        self.assertResponseNoErrors(response)
        self.assertNotEqual(new_trigger_id, self.event_id1.trigger_id)

    @silence_errors
    def test_delete_event_id_permissions(self):
        params = {
            "input": {
                "eventId": self.event_id1.event_id,
            }
        }

        # Run this test twice, the first time without an authenticated user, and the second with an authenticated user
        for _ in range(2):
            with override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[]):
                response = self.query(delete_mutation, input_data=params["input"])
                self.assertResponseHasErrors(response)
                self.assertTrue(EventID.objects.filter(event_id=self.event_id1.event_id).exists())

            self.authenticate()

        response = self.query(delete_mutation, input_data=params["input"])
        self.assertResponseNoErrors(response)
        self.assertFalse(EventID.objects.filter(event_id=self.event_id1.event_id).exists())

    @silence_errors
    def test_view_event_id_permissions(self):
        variables_not_ligo = {"eventId": self.event_id1.event_id}

        variables_ligo = {"eventId": self.event_id_ligo1.event_id}

        response = self.query(get_event_id_query, variables=variables_not_ligo)
        self.assertResponseNoErrors(response)
        self.assertFalse(response.data["eventId"]["isLigoEvent"])

        response = self.query(get_event_id_query, variables=variables_ligo)
        self.assertResponseNoErrors(response)
        self.assertIsNone(response.data["eventId"])

        self.authenticate()
        response = self.query(get_event_id_query, variables=variables_not_ligo)
        self.assertResponseNoErrors(response)
        self.assertFalse(response.data["eventId"]["isLigoEvent"])

        response = self.query(get_event_id_query, variables=variables_ligo)
        self.assertResponseNoErrors(response)
        self.assertIsNone(response.data["eventId"])

        self.authenticate(authentication_method="ligo_shibboleth")
        response = self.query(get_event_id_query, variables=variables_not_ligo)
        self.assertResponseNoErrors(response)
        self.assertFalse(response.data["eventId"]["isLigoEvent"])

        response = self.query(get_event_id_query, variables=variables_ligo)
        self.assertResponseNoErrors(response)
        self.assertTrue(response.data["eventId"]["isLigoEvent"])

    def test_view_nonexistent_event_id(self):
        self.authenticate()
        response = self.query(get_event_id_query, variables={"eventId": "GW999999_999999"})
        self.assertResponseNoErrors(response)
        self.assertIsNone(response.data["eventId"])

    @silence_errors
    def test_view_event_id_list_permissions(self):
        response = self.query(get_all_event_ids_query)
        self.assertEqual(len(response.data["allEventIds"]), 2)
        self.assertTrue(all(not event["isLigoEvent"] for event in response.data["allEventIds"]))

        self.authenticate()
        response = self.query(get_all_event_ids_query)
        self.assertEqual(len(response.data["allEventIds"]), 2)
        self.assertTrue(all(not event["isLigoEvent"] for event in response.data["allEventIds"]))

        self.authenticate(authentication_method="ligo_shibboleth")
        response = self.query(get_all_event_ids_query)
        self.assertEqual(len(response.data["allEventIds"]), 4)


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
