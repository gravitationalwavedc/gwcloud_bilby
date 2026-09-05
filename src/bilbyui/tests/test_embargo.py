from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import user_subject_to_embargo


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class UserSubjectToEmbargoTestCase(BilbyTestCase):
    def test_returns_false_when_embargo_start_time_is_none(self):
        # With no embargo start time configured, no user is subject to embargo
        with override_settings(EMBARGO_START_TIME=None):
            user = self.create_user(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
            self.assertFalse(user_subject_to_embargo(user))

    def test_returns_false_for_ligo_user(self):
        # A LIGO user is not subject to embargo once an embargo start time is set
        with override_settings(EMBARGO_START_TIME=123):
            user = self.create_user(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
            self.assertFalse(user_subject_to_embargo(user))

    def test_returns_true_for_non_ligo_user(self):
        # A non-LIGO user is subject to embargo once an embargo start time is set
        with override_settings(EMBARGO_START_TIME=123):
            user = self.create_user(authentication_method="password")
            self.assertTrue(user_subject_to_embargo(user))

    def test_returns_true_for_anonymous_user(self):
        # An anonymous user is not a LIGO user and is therefore subject to embargo
        with override_settings(EMBARGO_START_TIME=123):
            self.assertTrue(user_subject_to_embargo(ADACSAnonymousUser()))
