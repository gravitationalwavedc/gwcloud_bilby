from django.contrib.auth import get_user_model


class GWCloudUser:
    """
    Asher suggests converting this to a named tuple
    """

    def __init__(self, username):
        self.is_active = True
        self.is_authenticated = True
        self.is_anonymous = False
        self.username = username


def jwt_get_user_by_payload(payload):
    # Get the username
    username = payload.get(get_user_model().USERNAME_FIELD)

    # Create the user object that django can consume
    user = GWCloudUser(username)

    # Next extract any other fields from the payload that we need
    user.user_id = payload.get("userId")
    user.is_ligo = payload.get("isLigo", False)

    # All done
    return user
