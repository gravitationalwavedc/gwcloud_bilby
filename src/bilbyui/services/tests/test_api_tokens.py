from adacs_sso_plugin.models import APISessionToken
from django.core.exceptions import PermissionDenied

from bilbyui.services.api_tokens import create_token, list_tokens, revoke_token
from bilbyui.tests.testcases import BilbyTestCase


class TestApiTokensService(BilbyTestCase):
    def setUp(self):
        self.authenticate()

    def test_list_create_revoke_token_round_trip(self):
        self.assertEqual(list_tokens(self.user), [])

        token = create_token(self.user, "test-token")
        self.assertEqual(token.user_id, self.user.id)
        self.assertEqual(token.name, "test-token")

        tokens = list_tokens(self.user)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["id"], token.id)
        self.assertEqual(tokens[0]["name"], "test-token")
        self.assertEqual(tokens[0]["shortcode"], token.token_shortcode)
        self.assertFalse(tokens[0]["expired"])

        self.assertTrue(revoke_token(self.user, token.id))
        self.assertEqual(list_tokens(self.user), [])
        self.assertFalse(APISessionToken.objects.filter(id=token.id).exists())

    def test_revoke_token_raises_for_other_users_token(self):
        token = create_token(self.user, "test-token")
        self.authenticate(id=2, name="other user", primary_email="other@example.com")

        with self.assertRaises(PermissionDenied):
            revoke_token(self.user, token.id)
