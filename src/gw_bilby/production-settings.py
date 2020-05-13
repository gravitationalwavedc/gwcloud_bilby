from .base import *

DEBUG = False

SITE_URL = "https://gw-cloud.org"

STATIC_URL = "/bilby/static/"

ALLOWED_HOSTS = ['*']

EMAIL_HOST = 'mail.swin.edu.au'
EMAIL_PORT = 25

try:
    from .environment import *
except ImportError:
    pass

