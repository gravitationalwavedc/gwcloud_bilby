from types import SimpleNamespace
from unittest.mock import patch

from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.ini_utils import bilby_ini_string_to_args
from bilbyui.views import check_job_embargo_status

User = get_user_model()


def _args_from_ini(config):
    return bilby_ini_string_to_args(create_test_ini_string(config).encode("utf-8"))


def _args(**kwargs):
    return SimpleNamespace(**kwargs)


class TestCheckJobEmbargoStatus(BilbyTestCase):
    @override_settings(EMBARGO_START_TIME=1.5)
    def test_float_trigger_time_real_data_after_embargo(self):
        args = _args_from_ini(
            {
                "detectors": "['H1']",
                "trigger-time": "2.0",
                "n-simulation": "0",
            }
        )
        self.user = ADACSAnonymousUser()
        self.assertTrue(check_job_embargo_status(self.user, args))

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_float_trigger_time_before_embargo(self):
        args = _args_from_ini(
            {
                "detectors": "['H1']",
                "trigger-time": "1.0",
                "n-simulation": "0",
            }
        )
        self.user = ADACSAnonymousUser()
        self.assertFalse(check_job_embargo_status(self.user, args))

    @override_settings(EMBARGO_START_TIME=1.5)
    @patch("bilbyui.views.event_gps", return_value=2.0)
    def test_event_name_trigger_time_resolved(self, _mock_event_gps):
        args = _args(trigger_time="GW150914", n_simulation="0")
        self.assertTrue(check_job_embargo_status(None, args))
        _mock_event_gps.assert_called_once_with("GW150914")

    @override_settings(EMBARGO_START_TIME=1.5)
    @patch("bilbyui.views.event_gps", side_effect=ValueError("unknown event"))
    def test_unresolvable_trigger_time_not_embargoed(self, _mock_event_gps):
        args = _args(trigger_time="NOT_A_REAL_EVENT", n_simulation="0")
        self.assertFalse(check_job_embargo_status(None, args))

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_trigger_time_type_error_treated_as_none(self):
        args = _args(trigger_time=None, n_simulation="0")
        self.assertFalse(check_job_embargo_status(None, args))

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_simulated_job_not_embargoed_despite_late_trigger(self):
        args = _args_from_ini(
            {
                "detectors": "['H1']",
                "trigger-time": "2.0",
                "n-simulation": "1",
            }
        )
        self.assertFalse(check_job_embargo_status(None, args))

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_n_simulation_none_passed_through(self):
        args = _args(trigger_time="2.0", n_simulation=None)
        self.assertTrue(check_job_embargo_status(None, args))

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_ligo_user_bypasses_embargo(self):
        args = _args(trigger_time="2.0", n_simulation="0")
        self.user, _ = User.objects.update_or_create(
            id=1,
            defaults={"name": "buffy summers", "primary_email": "slayer@gmail.com"},
        )
        self.user.authentication_methods = [AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]]
        self.assertFalse(check_job_embargo_status(self.user, args))

    @override_settings(EMBARGO_START_TIME=None)
    def test_no_embargo_always_false(self):
        args = _args(trigger_time="2.0", n_simulation="0")
        self.assertFalse(check_job_embargo_status(None, args))
