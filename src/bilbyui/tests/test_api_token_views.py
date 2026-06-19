from django.conf import settings

from bilbyui.services.api_tokens import create_token, list_tokens
from bilbyui.tests.testcases import BilbyTestCase


class TestApiTokenViews(BilbyTestCase):
    url = "/api-token/"
    create_url = "/api-token/create/"

    def setUp(self):
        self.deauthenticate()

    def test_unauthenticated_redirected(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.LOGIN_URL}?next=/api-token/")

    def test_renders_existing_tokens(self):
        self.authenticate()
        create_token(self.user, "token-one")
        create_token(self.user, "token-two")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "token-one")
        self.assertContains(response, "token-two")
        self.assertContains(response, "API Tokens")

    def test_creates_token(self):
        self.authenticate()

        response = self.client.post(self.create_url, {"name": "my-token"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "save-toast")
        self.assertContains(response, "This is the only time this token will be visible")
        self.assertContains(response, "my-token")
        tokens = list_tokens(self.user)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["name"], "my-token")

    def test_create_with_empty_name_returns_400(self):
        self.authenticate()

        response = self.client.post(self.create_url, {"name": ""})

        self.assertEqual(response.status_code, 400)

    def test_create_with_too_long_name_returns_400(self):
        self.authenticate()

        response = self.client.post(self.create_url, {"name": "x" * 65})

        self.assertEqual(response.status_code, 400)

    def test_create_with_duplicate_name_returns_400(self):
        self.authenticate()
        create_token(self.user, "my-token")

        response = self.client.post(self.create_url, {"name": "my-token"})

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "Ensure you do not already have a token with the same name",
            status_code=400,
        )
        self.assertEqual(len(list_tokens(self.user)), 1)

    def test_revoke_token(self):
        self.authenticate()
        token = create_token(self.user, "revoke-me")
        revoke_url = f"/api-token/{token.id}/revoke/"

        response = self.client.post(revoke_url)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Trigger"], "token-revoked")
        self.assertEqual(list_tokens(self.user), [])

    def test_revoke_other_users_token_returns_404(self):
        self.authenticate()
        token = create_token(self.user, "other-users-token")
        self.authenticate(id=2, name="other user", primary_email="other@example.com")
        revoke_url = f"/api-token/{token.id}/revoke/"

        response = self.client.post(revoke_url)

        self.assertEqual(response.status_code, 404)
