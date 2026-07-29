import logging

from adacs_sso_plugin.models import APISessionToken

logger = logging.getLogger(__name__)


def serialize_token(token):
    """Shape an APISessionToken for templates (matches list_tokens entries)."""
    return {
        "id": token.id,
        "name": token.name,
        "created": token.created,
        "last_used": token.last_used,
        "expiry": token.expiry,
        "expired": token.expired,
        "shortcode": token.token_shortcode,
    }


def list_tokens(user):
    logger.debug("Listing API tokens for user %s", user.id)
    tokens = APISessionToken.get_user_tokens(user.id)
    return [serialize_token(token) for token in tokens]


def create_token(user, name):
    logger.info("Creating API token '%s' for user %s", name, user.id)
    token = APISessionToken(
        user=user,
        name=name,
        authenticated_at=user.last_fetched_at,
        authentication_method=user.authentication_methods[0] if user.authentication_methods else "password",
    )
    token.full_clean()
    token.save()
    return token


def revoke_token(user, token_id):
    logger.info("Revoking API token %s for user %s", token_id, user.id)
    token = APISessionToken.objects.get(id=token_id)
    token.remove(user.id)
    return True
