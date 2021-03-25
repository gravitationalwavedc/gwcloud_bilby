from django.test import TestCase

from gw_bilby.jwt_tools import jwt_get_user_by_payload


class TestJWTTools(TestCase):
    def test_jwt_get_user_by_payload(self):
        """
        Check that jwt_get_user_by_payload works as expected
        """

        # Create a test payload
        payload = {
            'username': 'billy',
            'userId': 43,
            'isLigo': True
        }

        # Get the user from the payload and verify that the returned GWCloudUser object is valid
        user = jwt_get_user_by_payload(payload)

        # Assert that the fields of the gwcloud user are accurate
        self.assertEqual(user.username, payload['username'])
        self.assertEqual(user.user_id, payload['userId'])
        self.assertEqual(user.is_ligo, payload['isLigo'])

        # The user object should indicate that the user is active
        self.assertEqual(user.is_active, True)

        # The user should also be authenticated by default
        self.assertEqual(user.is_authenticated, True)

        # The user should not be anonymous
        self.assertEqual(user.is_anonymous, False)
