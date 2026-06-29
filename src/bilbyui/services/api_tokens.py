from adacs_sso_plugin.models import APISessionToken


def list_tokens(user):
    tokens = APISessionToken.get_user_tokens(user.id)
    return [
        {
            "id": token.id,
            "name": token.name,
            "created": token.created,
            "last_used": token.last_used,
            "expiry": token.expiry,
            "expired": token.expired,
            "shortcode": token.token_shortcode,
        }
        for token in tokens
    ]


def create_token(user, name):
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
    token = APISessionToken.objects.get(id=token_id)
    token.remove(user.id)
    return True
