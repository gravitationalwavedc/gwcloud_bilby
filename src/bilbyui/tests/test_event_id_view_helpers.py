from django.test import override_settings

from bilbyui.models import EventID
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _event_id_display_values, _filter_event_ids_for_query


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
