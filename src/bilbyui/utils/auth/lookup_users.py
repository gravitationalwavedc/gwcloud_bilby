from adacs_sso_plugin.utils import auth_request

from bilbyui.utils.misc import check_request_leak_decorator


@check_request_leak_decorator
def request_lookup_users(ids):
    """
    Requests a list of users from the id's provided

    :param ids: The list of ids to use to look up users
    """

    try:
        resp = auth_request("get_users", {"ids": ids})
        return True, resp["users"]
    except Exception:
        return False, "Error filtering users"
