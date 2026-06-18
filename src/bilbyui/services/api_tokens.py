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
    session_user_data = {
        "id": user.id,
        "name": user.name,
        "primary_email": user.primary_email,
        "emails": user.emails,
        "authentication_method": user.authentication_method,
        "is_authenticated": user.is_authenticated,
        "authenticated_at": user.authenticated_at.timestamp(),
        "fetched_at": user.fetched_at.timestamp(),
    }
    token = APISessionToken(
        user_id=user.id,
        name=name,
        session_user_data=session_user_data,
    )
    token.full_clean()
    token.save()
    return token


def revoke_token(user, token_id):
    token = APISessionToken.objects.get(id=token_id)
    token.remove(user.id)
    return True
