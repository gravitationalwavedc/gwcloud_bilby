import django.core.mail
from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.misc import check_request_leak, check_request_leak_decorator, is_ligo_user


def _leak_helper():
    return "value"


_leak_helper_wrapped = check_request_leak_decorator(_leak_helper)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class IsLigoUserTestCase(BilbyTestCase):
    def test_anonymous_user_is_not_ligo(self):
        # An anonymous user is not authenticated, so is_ligo_user must return False
        self.assertFalse(is_ligo_user(ADACSAnonymousUser()))

    def test_authenticated_non_ligo_user_is_not_ligo(self):
        # An authenticated user without LIGO Shibboleth auth is not a LIGO user
        user = self.create_user(authentication_method="password")
        self.assertFalse(is_ligo_user(user))

    def test_authenticated_ligo_user_is_ligo(self):
        # An authenticated user with LIGO Shibboleth auth is a LIGO user
        user = self.create_user(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        self.assertTrue(is_ligo_user(user))


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class CheckRequestLeakTestCase(BilbyTestCase):
    def test_leak_raises_in_test_mode(self):
        # In test mode mail.outbox exists and ALLOW_HTTP_LEAKS is not set, so a leak must be raised
        with self.assertRaisesRegex(Exception, "HTTP request leaked during testing"):
            check_request_leak()

    def test_no_leak_when_allowed(self):
        # When ALLOW_HTTP_LEAKS is set, check_request_leak must not raise
        with override_settings(ALLOW_HTTP_LEAKS=True):
            check_request_leak()

    def test_no_leak_when_outbox_absent(self):
        # When mail.outbox is absent (not test mode), check_request_leak must not raise
        original = django.core.mail.outbox
        try:
            del django.core.mail.outbox
            check_request_leak()
        finally:
            django.core.mail.outbox = original

    def test_decorator_raises_in_test_mode(self):
        # The decorator must enforce the leak check before calling the wrapped function
        with self.assertRaisesRegex(Exception, "HTTP request leaked during testing"):
            _leak_helper_wrapped()

    def test_decorator_passes_through_when_allowed(self):
        # When leaks are allowed, the decorator must call and return the wrapped function's result
        with override_settings(ALLOW_HTTP_LEAKS=True):
            self.assertEqual(_leak_helper_wrapped(), "value")
