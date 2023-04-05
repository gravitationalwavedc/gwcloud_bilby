from django.conf import settings
from django.core import mail


def check_request_leak():
    if hasattr(mail, 'outbox') and not hasattr(settings, 'ALLOW_HTTP_LEAKS'):
        # We are in test mode!
        raise Exception("HTTP request leaked during testing")


def check_request_leak_decorator(fn):
    def wrapper(*args, **kwargs):
        check_request_leak()

        return fn(*args, **kwargs)

    return wrapper


def is_ligo_user(user):
    return not user.is_anonymous and user.is_ligo