class GWCloudUser:
    """
    Asher suggests converting this to a named tuple
    """
    def __init__(self, username):
        self.is_active = True
        self.is_authenticated = True
        self.is_anonymous = False
        self.username = username


def jwt_get_user(username):
    return GWCloudUser(username)
