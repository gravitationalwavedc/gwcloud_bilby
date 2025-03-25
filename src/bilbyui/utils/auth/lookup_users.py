import datetime
import json

import jwt
import requests
from django.conf import settings

from bilbyui.utils.misc import check_request_leak_decorator
from adacs_sso_plugin.utils import auth_request


@check_request_leak_decorator
def request_lookup_users(ids):
    """
    Requests a list of users from the id's provided

    :param ids: The list of ids to use to look up users
    :param user_id: The id of the user making the request (Usually passed down from request context)
    """

    try:
        resp = auth_request("get_users", {"ids": ids})
        return True, resp["users"]
    except Exception:
        return False, "Error filtering users"
