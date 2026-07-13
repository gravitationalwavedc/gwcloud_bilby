from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.misc import check_request_leak_decorator, is_ligo_user


def _return_ok():
    return "ok"


class TestCheckRequestLeakDecorator(BilbyTestCase):
    @override_settings(ALLOW_HTTP_LEAKS=True)
    def test_decorator_returns_wrapped_function_result(self):
        @check_request_leak_decorator
        def sample_fn(value):
            return value + 1

        self.assertEqual(sample_fn(1), 2)

    def test_decorator_raises_when_request_leaks_in_test(self):
        decorated = check_request_leak_decorator(_return_ok)

        with self.assertRaises(Exception) as ctx:
            decorated()
        self.assertIn("HTTP request leaked", str(ctx.exception))

    @override_settings(ALLOW_HTTP_LEAKS=True)
    def test_decorator_allows_calls_when_http_leaks_permitted(self):
        decorated = check_request_leak_decorator(_return_ok)

        self.assertEqual(decorated(), "ok")


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestIsLigoUser(BilbyTestCase):
    def test_anonymous_user_is_not_ligo_user(self):
        self.user = ADACSAnonymousUser()
        self.assertFalse(is_ligo_user(self.user))

    def test_authenticated_user_is_not_ligo_user(self):
        self.authenticate()
        self.assertFalse(is_ligo_user(self.user))

    def test_ligo_shibboleth_user_is_ligo_user(self):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        self.assertTrue(is_ligo_user(self.user))
