from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import should_embargo_job

EMBARGO_START = 1000.0


@override_settings(IGNORE_ELASTIC_SEARCH=True, EMBARGO_START_TIME=EMBARGO_START)
class ShouldEmbargoJobTestCase(BilbyTestCase):
    def test_ligo_user_returns_false(self):
        # A LIGO user is never subject to embargo regardless of trigger time
        user = self.create_user(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        self.assertFalse(should_embargo_job(user, EMBARGO_START, False))

    def test_simulated_data_returns_false(self):
        # Simulated data is never embargoed, even for a non-LIGO user
        user = self.create_user()
        self.assertFalse(should_embargo_job(user, EMBARGO_START, True))

    def test_none_trigger_time_returns_false(self):
        # A job with no trigger time is never embargoed
        user = self.create_user()
        self.assertFalse(should_embargo_job(user, None, False))

    def test_no_embargo_start_time_returns_false(self):
        # With no EMBARGO_START_TIME configured, nothing is embargoed
        user = self.create_user()
        with override_settings(EMBARGO_START_TIME=None):
            self.assertFalse(should_embargo_job(user, EMBARGO_START, False))

    def test_trigger_time_below_start_returns_false(self):
        # Real data before the embargo start time is not embargoed
        user = self.create_user()
        self.assertFalse(should_embargo_job(user, EMBARGO_START - 1, False))

    def test_trigger_time_at_start_returns_true(self):
        # Real data at the embargo start time is embargoed for a non-LIGO user
        user = self.create_user()
        self.assertTrue(should_embargo_job(user, EMBARGO_START, False))

    def test_trigger_time_above_start_returns_true(self):
        # Real data after the embargo start time is embargoed for a non-LIGO user
        user = self.create_user()
        self.assertTrue(should_embargo_job(user, EMBARGO_START + 1, False))

    def test_none_user_treated_as_non_ligo(self):
        # A None user is treated as a non-LIGO user and subject to embargo
        self.assertTrue(should_embargo_job(None, EMBARGO_START, False))
