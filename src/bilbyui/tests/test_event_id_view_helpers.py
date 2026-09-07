from types import SimpleNamespace

from django.test import RequestFactory, override_settings

from bilbyui.models import BilbyJob, EventID
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import (
    _event_id_display_values,
    _event_id_field_values,
    _filter_event_ids_for_query,
    _render_job_field_event_id,
)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestEventIdFieldValues(BilbyTestCase):
    def test_returns_event_id_trigger_id_nickname_tuple(self):
        event = EventID(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
        )
        self.assertEqual(
            _event_id_field_values(event),
            ("GW123456_123456", "S123456a", "GW123456"),
        )

    def test_returns_none_for_missing_optional_fields(self):
        event = EventID(event_id="GW123456_123456", trigger_id=None, nickname=None)
        self.assertEqual(_event_id_field_values(event), ("GW123456_123456", None, None))


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestEventIdDisplayValues(BilbyTestCase):
    def test_none_event_id_returns_empty_list(self):
        self.assertEqual(_event_id_display_values(None), [])

    def test_all_fields_present(self):
        event = EventID(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
        )
        self.assertEqual(
            _event_id_display_values(event),
            ["GW123456_123456", "S123456a", "GW123456"],
        )

    def test_omits_empty_optional_fields(self):
        event = EventID(event_id="GW123456_123456", trigger_id=None, nickname=None)
        self.assertEqual(_event_id_display_values(event), ["GW123456_123456"])

    def test_omits_blank_optional_fields(self):
        event = EventID(event_id="GW123456_123456", trigger_id="", nickname="")
        self.assertEqual(_event_id_display_values(event), ["GW123456_123456"])


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestFilterEventIdsForQuery(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.events = [
            EventID.objects.create(
                event_id="GW111111_111111",
                trigger_id="S111111a",
                nickname="nick-one",
            ),
            EventID.objects.create(
                event_id="GW222222_222222",
                trigger_id="S222222b",
                nickname="nick-two",
            ),
            EventID.objects.create(
                event_id="GW333333_333333",
                trigger_id=None,
                nickname=None,
            ),
        ]

    def test_matches_event_id(self):
        matches = _filter_event_ids_for_query(self.events, "222222")
        self.assertEqual(matches, [self.events[1]])

    def test_matches_trigger_id(self):
        matches = _filter_event_ids_for_query(self.events, "S111111")
        self.assertEqual(matches, [self.events[0]])

    def test_matches_nickname(self):
        matches = _filter_event_ids_for_query(self.events, "nick-two")
        self.assertEqual(matches, [self.events[1]])

    def test_case_insensitive_match(self):
        matches = _filter_event_ids_for_query(self.events, "gw111111")
        self.assertEqual(matches, [self.events[0]])

    def test_no_match_returns_empty_list(self):
        self.assertEqual(_filter_event_ids_for_query(self.events, "no-such-event"), [])

    def test_empty_query_matches_all(self):
        self.assertEqual(_filter_event_ids_for_query(self.events, ""), self.events)

    def test_handles_missing_optional_fields(self):
        matches = _filter_event_ids_for_query(self.events, "333333")
        self.assertEqual(matches, [self.events[2]])


class TestRenderJobFieldEventId(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = self.create_user(id=7)
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="viewable_job",
            description="A job to view",
            job_controller_id=10001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "viewable_job"}),
        )

    def test_default_modifiable_for_owner(self):
        request = self.factory.get("/")
        request.user = self.user

        response = _render_job_field_event_id(request, self.job)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.context_data["modifiable"], True)
        self.assertEqual(response.context_data["error"], "")
        self.assertEqual(response.context_data["job"], self.job)

    def test_default_not_modifiable_for_non_owner(self):
        request = self.factory.get("/")
        request.user = SimpleNamespace(id=self.user.id + 1)

        response = _render_job_field_event_id(request, self.job)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.context_data["modifiable"], False)

    def test_explicit_modifiable_override(self):
        request = self.factory.get("/")
        request.user = SimpleNamespace(id=self.user.id + 1)

        response = _render_job_field_event_id(request, self.job, modifiable=True)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.context_data["modifiable"], True)

    def test_error_and_status_pass_through(self):
        request = self.factory.get("/")
        request.user = self.user

        response = _render_job_field_event_id(
            request,
            self.job,
            error="Event ID 'GW999999_999999' not found.",
            status=400,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.context_data["error"], "Event ID 'GW999999_999999' not found.")
