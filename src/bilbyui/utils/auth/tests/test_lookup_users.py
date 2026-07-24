from unittest import mock

from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.auth.lookup_users import request_lookup_users


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestRequestLookupUsers(BilbyTestCase):
    @mock.patch("bilbyui.utils.auth.lookup_users.auth_request")
    def test_request_lookup_users_success(self, auth_request_mock):
        users = [{"id": 1, "name": "Test User"}]
        auth_request_mock.return_value = {"users": users}

        success, result = request_lookup_users([1])

        self.assertTrue(success)
        self.assertEqual(result, users)
        auth_request_mock.assert_called_once_with("get_users", {"ids": [1]})

    @mock.patch("bilbyui.utils.auth.lookup_users.auth_request")
    def test_request_lookup_users_error(self, auth_request_mock):
        auth_request_mock.side_effect = Exception("auth failed")

        success, result = request_lookup_users([1, 2])

        self.assertFalse(success)
        self.assertEqual(result, "Error filtering users: auth failed")
        auth_request_mock.assert_called_once_with("get_users", {"ids": [1, 2]})
