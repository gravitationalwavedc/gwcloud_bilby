from types import SimpleNamespace

from django.test import override_settings

from bilbyui.models import EventID
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _filter_event_ids_for_query


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestFilterEventIdsForQuery(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.by_event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="alpha",
        )
        cls.by_trigger = EventID.objects.create(
            event_id="GW654321_654321",
            trigger_id="S654321b",
            nickname=None,
        )
        cls.by_nickname = EventID.objects.create(
            event_id="GW111111_111111",
            trigger_id=None,
            nickname="beta-nick",
        )

    def test_returns_empty_for_no_events(self):
        self.assertEqual(_filter_event_ids_for_query([], "query"), [])

    def test_matches_event_id_case_insensitive(self):
        results = _filter_event_ids_for_query(
            [self.by_event_id, self.by_trigger, self.by_nickname],
            "gw123456",
        )
        self.assertEqual(results, [self.by_event_id])

    def test_matches_trigger_id_case_insensitive(self):
        results = _filter_event_ids_for_query(
            [self.by_event_id, self.by_trigger, self.by_nickname],
            "s654321b",
        )
        self.assertEqual(results, [self.by_trigger])

    def test_matches_nickname_case_insensitive(self):
        results = _filter_event_ids_for_query(
            [self.by_event_id, self.by_trigger, self.by_nickname],
            "BETA-NICK",
        )
        self.assertEqual(results, [self.by_nickname])

    def test_returns_empty_when_no_match(self):
        results = _filter_event_ids_for_query(
            [self.by_event_id, self.by_trigger, self.by_nickname],
            "nomatch",
        )
        self.assertEqual(results, [])

    def test_handles_none_event_id_and_matches_trigger_id(self):
        event = SimpleNamespace(event_id=None, trigger_id="S999999z", nickname=None)
        self.assertEqual(_filter_event_ids_for_query([event], "s999999"), [event])

    def test_handles_none_trigger_and_event_id_matches_nickname(self):
        event = SimpleNamespace(event_id=None, trigger_id=None, nickname="findme")
        self.assertEqual(_filter_event_ids_for_query([event], "findme"), [event])
