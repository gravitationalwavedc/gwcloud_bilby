import logging

from adacs_sso_plugin.utils import auth_request

from bilbyui.utils.misc import check_request_leak_decorator

logger = logging.getLogger(__name__)


@check_request_leak_decorator
def request_lookup_users(ids):
    """
    Requests a list of users from the ids provided

    :param ids: The list of ids to use to look up users
    :return: A tuple (success, result) where success is a bool, and result is the
        list of users on success or an error string on failure
    """

    try:
        resp = auth_request("get_users", {"ids": ids})
        return True, resp["users"]
    except Exception as e:
        logger.error(f"Error looking up users: {e}", exc_info=True)
        return False, f"Error looking up users: {e}"
