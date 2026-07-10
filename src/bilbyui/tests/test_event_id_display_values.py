from bilbyui.models import EventID
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _event_id_display_values


class TestEventIdDisplayValues(BilbyTestCase):
    def test_returns_empty_list_when_event_id_is_none(self):
        self.assertEqual(_event_id_display_values(None), [])

    def test_returns_event_id_only(self):
        event_id = EventID.objects.create(
            event_id="GW111111_111111",
            gps_time=1126259462.391,
        )

        self.assertEqual(_event_id_display_values(event_id), ["GW111111_111111"])

    def test_returns_event_id_and_trigger_id(self):
        event_id = EventID.objects.create(
            event_id="GW222222_222222",
            trigger_id="S222222a",
            gps_time=1126259462.391,
        )

        self.assertEqual(_event_id_display_values(event_id), ["GW222222_222222", "S222222a"])

    def test_returns_event_id_and_nickname(self):
        event_id = EventID.objects.create(
            event_id="GW333333_333333",
            nickname="TestEvent",
            gps_time=1126259462.391,
        )

        self.assertEqual(_event_id_display_values(event_id), ["GW333333_333333", "TestEvent"])

    def test_returns_all_event_id_fields(self):
        event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            gps_time=12345678.1234,
        )

        self.assertEqual(
            _event_id_display_values(event_id),
            ["GW123456_123456", "S123456a", "GW123456"],
        )
