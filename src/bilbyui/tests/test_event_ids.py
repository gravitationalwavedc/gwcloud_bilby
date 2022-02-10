from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.models import EventID
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.tests.test_utils import silence_errors

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
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)

        self.query = create_mutation

        self.params = {
            "input": {
                "eventId": "GW123456_123456",
                "triggerId": "S123456a",
                "nickname": "GW123456",
                "isLigoEvent": False,
            }
        }

    @silence_errors
    def test_create_event_id(self):
        response = self.client.execute(self.query, self.params)

        self.assertResponseHasNoErrors(response)

        # Check that the event has input params
        event = EventID.objects.all().last()
        self.assertEqual(event.event_id, self.params['input']['eventId'])
        self.assertEqual(event.trigger_id, self.params['input']['triggerId'])
        self.assertEqual(event.nickname, self.params['input']['nickname'])
        self.assertEqual(event.is_ligo_event, self.params['input']['isLigoEvent'])

    @silence_errors
    def test_bad_event_ids(self):
        bad_event_ids = [
            'GW123456_1234567',  # Too many characters
            'GW123456_12345',    # Too few characters
            'GW1234567_12345',   # Underscore in wrong place
            'GG123456_123456',   # Should start with GW
            'G123456_123456',    # Should start with GW
            '123456_123456',     # Should start with GW
            'GW123456-123456',   # Should have underscore
            'GW123a56-123456'    # Must not have letters after the GW
        ]
        for event_id in bad_event_ids:
            self.params['input']['eventId'] = event_id
            response = self.client.execute(self.query, self.params)
            self.assertResponseHasErrors(response)
            self.assertFalse(EventID.objects.all().exists())

    @silence_errors
    def test_bad_trigger_ids(self):
        bad_trigger_ids = [
            'S123456',     # Must end with 1 or 2 letters
            'S123456abc',  # Must end with 1 or 2 letters
            'S_123456a',   # Should not have underscore
            'S1234567a',   # Too many numbers
            'S12345a',     # Too few numbers
            '123456a',     # Must start with S
            'G123456a',    # Must start with S
        ]
        for trigger_id in bad_trigger_ids:
            self.params['input']['triggerId'] = trigger_id
            response = self.client.execute(self.query, self.params)
            self.assertResponseHasErrors(response)
            self.assertFalse(EventID.objects.all().exists())


@override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[1])
class TestEventIDUpdating(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)

        self.query = update_mutation

        EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False
        )

    @silence_errors
    def test_update_event_id(self):
        new_params = {
            "input": {
                "eventId": "GW123456_123456",
                "triggerId": "S234567a",
                "nickname": "new nickname",
                "isLigoEvent": False,
            }
        }
        response = self.client.execute(self.query, new_params)

        self.assertResponseHasNoErrors(response)

        # Check that the event has input params
        event = EventID.objects.all().last()
        self.assertEqual(event.event_id, new_params['input']['eventId'])
        self.assertEqual(event.trigger_id, new_params['input']['triggerId'])
        self.assertEqual(event.nickname, new_params['input']['nickname'])
        self.assertEqual(event.is_ligo_event, new_params['input']['isLigoEvent'])

    @silence_errors
    def test_update_bad_trigger_ids(self):
        bad_trigger_ids = [
            'S123456',     # Must end with 1 or 2 letters
            'S123456abc',  # Must end with 1 or 2 letters
            'S_123456a',   # Should not have underscore
            'S1234567a',   # Too many numbers
            'S12345a',     # Too few numbers
            '123456a',     # Must start with S
            'G123456a',    # Must start with S
        ]
        for trigger_id in bad_trigger_ids:
            response = self.client.execute(
                self.query,
                {
                    "input": {
                        "eventId": "GW123456_123456",
                        "triggerId": trigger_id,
                    }
                }
            )

            self.assertResponseHasErrors(response)

            event = EventID.objects.get(event_id="GW123456_123456")
            self.assertEqual(event.trigger_id, "S123456a")
            self.assertNotEqual(event.trigger_id, trigger_id)


@override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[1])
class TestEventIDDeletion(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)

        self.query = delete_mutation

        EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False
        )

    @silence_errors
    def test_delete_event_id(self):
        self.assertTrue(EventID.objects.filter(event_id="GW123456_123456").exists())
        response = self.client.execute(
            self.query,
            {
                "input": {
                    "eventId": "GW123456_123456",
                }
            }
        )

        self.assertResponseHasNoErrors(response)

        self.assertFalse(EventID.objects.filter(event_id="GW123456_123456").exists())


@override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[1])
class TestEventIDPermissions(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

        self.event_id1 = EventID.objects.create(
            event_id="GW123456_123456",
            is_ligo_event=False
        )
        self.event_id2 = EventID.objects.create(
            event_id="GW654321_654321",
            is_ligo_event=False
        )
        self.event_id_ligo1 = EventID.objects.create(
            event_id="GW012345_012345",
            is_ligo_event=True
        )
        self.event_id_ligo2 = EventID.objects.create(
            event_id="GW543210_543210",
            is_ligo_event=True
        )

    @silence_errors
    def test_create_event_id_permissions(self):
        new_event_id = "GW111111_111111"
        params = {
            "input": {
                "eventId": new_event_id,
            }
        }

        self.client.authenticate(self.user)
        with override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[]):
            response = self.client.execute(create_mutation, params)
            self.assertResponseHasErrors(response)
            self.assertFalse(EventID.objects.filter(event_id=new_event_id).exists())

        response = self.client.execute(create_mutation, params)
        self.assertResponseHasNoErrors(response)
        self.assertTrue(EventID.objects.filter(event_id=new_event_id).exists())

    @silence_errors
    def test_update_event_id_permissions(self):
        new_trigger_id = "S111111a"
        params = {
            "input": {
                "eventId": self.event_id1.event_id,
                "triggerId": new_trigger_id
            }
        }

        self.client.authenticate(self.user)
        with override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[]):
            response = self.client.execute(update_mutation, params)
            self.assertResponseHasErrors(response)
            self.assertNotEqual(new_trigger_id, self.event_id1.trigger_id)

        response = self.client.execute(update_mutation, params)
        self.assertResponseHasNoErrors(response)
        self.assertNotEqual(new_trigger_id, self.event_id1.trigger_id)

    @silence_errors
    def test_delete_event_id_permissions(self):
        params = {
            "input": {
                "eventId": self.event_id1.event_id,
            }
        }

        self.client.authenticate(self.user)
        with override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[]):
            response = self.client.execute(delete_mutation, params)
            self.assertResponseHasErrors(response)
            self.assertTrue(EventID.objects.filter(event_id=self.event_id1.event_id).exists())

        response = self.client.execute(delete_mutation, params)
        self.assertResponseHasNoErrors(response)
        self.assertFalse(EventID.objects.filter(event_id=self.event_id1.event_id).exists())

    @silence_errors
    def test_view_event_id_permissions(self):
        variables_not_ligo = {
            "eventId": self.event_id1.event_id
        }

        variables_ligo = {
            "eventId": self.event_id_ligo1.event_id
        }
        self.client.authenticate(self.user, is_ligo=False)
        response = self.client.execute(get_event_id_query, variables_not_ligo)
        self.assertResponseHasNoErrors(response)
        self.assertFalse(response.data['eventId']['isLigoEvent'])

        response = self.client.execute(get_event_id_query, variables_ligo)
        self.assertResponseHasErrors(response)

        self.client.authenticate(self.user, is_ligo=True)
        response = self.client.execute(get_event_id_query, variables_not_ligo)
        self.assertResponseHasNoErrors(response)
        self.assertFalse(response.data['eventId']['isLigoEvent'])

        response = self.client.execute(get_event_id_query, variables_ligo)
        self.assertResponseHasNoErrors(response)
        self.assertTrue(response.data['eventId']['isLigoEvent'])

    @silence_errors
    def test_view_event_id_list_permissions(self):
        self.client.authenticate(self.user, is_ligo=False)
        response = self.client.execute(get_all_event_ids_query)
        self.assertEqual(len(response.data['allEventIds']), 2)
        self.assertTrue(all([not event['isLigoEvent'] for event in response.data['allEventIds']]))

        self.client.authenticate(self.user, is_ligo=True)
        response = self.client.execute(get_all_event_ids_query)
        self.assertEqual(len(response.data['allEventIds']), 4)
