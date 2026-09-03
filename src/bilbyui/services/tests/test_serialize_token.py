import datetime
import uuid

from adacs_sso_plugin.models import APISessionToken
from django.utils import timezone

from bilbyui.services.api_tokens import serialize_token
from bilbyui.tests.testcases import BilbyTestCase


class TestSerializeToken(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.token = APISessionToken(
            user=self.user,
            name="test-token",
            token=uuid.UUID("12345678-1234-1234-1234-123456789abc"),
            authenticated_at=timezone.now(),
            authentication_method="password",
            created=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
            last_used=datetime.datetime(2024, 1, 2, tzinfo=datetime.UTC),
            expiry=timezone.now() + datetime.timedelta(days=30),
        )

    def test_serialize_token_returns_full_dict_shape(self):
        result = serialize_token(self.token)

        self.assertEqual(
            set(result.keys()),
            {"id", "name", "created", "last_used", "expiry", "expired", "shortcode"},
        )
        self.assertEqual(result["id"], self.token.id)
        self.assertEqual(result["name"], "test-token")
        self.assertEqual(result["created"], self.token.created)
        self.assertEqual(result["last_used"], self.token.last_used)
        self.assertEqual(result["expiry"], self.token.expiry)

    def test_serialize_token_shortcode_is_first_eight_chars_of_token(self):
        result = serialize_token(self.token)

        self.assertEqual(result["shortcode"], "12345678")

    def test_serialize_token_expired_flag_false_for_future_expiry(self):
        self.token.expiry = timezone.now() + datetime.timedelta(days=30)
        self.assertFalse(serialize_token(self.token)["expired"])

    def test_serialize_token_expired_flag_true_for_past_expiry(self):
        self.token.expiry = timezone.now() - datetime.timedelta(days=1)
        self.assertTrue(serialize_token(self.token)["expired"])
