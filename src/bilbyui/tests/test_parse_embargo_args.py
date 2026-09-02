from types import SimpleNamespace
from unittest.mock import patch

import requests

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _parse_embargo_args


def _args(**kwargs):
    return SimpleNamespace(**kwargs)


class TestParseEmbargoArgs(BilbyTestCase):
    def test_float_trigger_time(self):
        trigger_time, n_simulation = _parse_embargo_args(_args(trigger_time="2.0", n_simulation="0"))
        self.assertEqual(trigger_time, 2.0)
        self.assertFalse(n_simulation)

    @patch("bilbyui.views.event_gps", return_value=1126259462.4)
    def test_event_name_trigger_time_resolved(self, _mock_event_gps):
        trigger_time, _ = _parse_embargo_args(_args(trigger_time="GW150914", n_simulation="0"))
        _mock_event_gps.assert_called_once_with("GW150914")
        self.assertEqual(trigger_time, 1126259462.4)

    @patch("bilbyui.views.event_gps", side_effect=ValueError("unknown event"))
    def test_unresolvable_trigger_time_returns_none(self, _mock_event_gps):
        trigger_time, _ = _parse_embargo_args(_args(trigger_time="NOT_A_REAL_EVENT", n_simulation="0"))
        self.assertIsNone(trigger_time)

    @patch("bilbyui.views.event_gps", side_effect=requests.RequestException("unreachable"))
    def test_gwosc_unreachable_trigger_time_returns_none(self, _mock_event_gps):
        trigger_time, _ = _parse_embargo_args(_args(trigger_time="NOT_A_REAL_EVENT", n_simulation="0"))
        self.assertIsNone(trigger_time)

    def test_trigger_time_type_error_returns_none(self):
        trigger_time, _ = _parse_embargo_args(_args(trigger_time=None, n_simulation="0"))
        self.assertIsNone(trigger_time)

    def test_n_simulation_none_passed_through(self):
        _, n_simulation = _parse_embargo_args(_args(trigger_time="2.0", n_simulation=None))
        self.assertIsNone(n_simulation)

    def test_n_simulation_int_converted_to_bool(self):
        _, n_simulation = _parse_embargo_args(_args(trigger_time="2.0", n_simulation="1"))
        self.assertTrue(n_simulation)

    def test_malformed_n_simulation_falls_back_to_false(self):
        _, n_simulation = _parse_embargo_args(_args(trigger_time="2.0", n_simulation="not-a-number"))
        self.assertFalse(n_simulation)
