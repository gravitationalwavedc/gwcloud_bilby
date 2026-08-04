from adacs_sso_plugin.models import APISessionToken
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
        self.assertNotIn("HX-Trigger", response)
        self.assertContains(response, "This is the only time this token will be visible")
        tokens = list_tokens(self.user)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["name"], "my-token")
        db_token = APISessionToken.objects.get(id=tokens[0]["id"])
        # React showed the raw secret once; success fragment replaces #token-actions
        self.assertContains(response, str(db_token.token))
        self.assertContains(response, f'data-new-token-id="{tokens[0]["id"]}"')
        self.assertNotContains(response, 'id="token-create-form"')
        # OOB list row uses list_tokens shape (shortcode), and hides empty state
        self.assertContains(response, tokens[0]["shortcode"])
        self.assertContains(response, 'hx-swap-oob="afterbegin:#token-list"')
        self.assertContains(response, 'id="no-tokens-message"')
        self.assertContains(response, 'hx-swap-oob="true"')

    def test_create_page_wiring(self):
        self.authenticate()

        response = self.client.get(self.url)

        self.assertContains(response, 'hx-target="#token-actions"')
        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'action="/api-token/create/"')
        self.assertContains(response, 'id="token-actions-idle-template"')
        self.assertNotContains(response, 'id="save-toast"')
        self.assertRegex(
            response.content.decode(),
            r'<p id="no-tokens-message"(?! style="display: none;")>',
        )

    def test_create_with_empty_name_returns_400(self):
        self.authenticate()

        response = self.client.post(self.create_url, {"name": ""})

        self.assertEqual(response.status_code, 400)

    def test_create_with_too_long_name_returns_400(self):
        self.authenticate()
        max_len = APISessionToken._meta.get_field("name").max_length

        response = self.client.post(self.create_url, {"name": "x" * (max_len + 1)})

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
