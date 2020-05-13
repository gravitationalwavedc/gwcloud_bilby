from .base import *

DEBUG = False

SITE_URL = "https://gw-cloud.org"

STATIC_URL = "/bilby/static/"

ALLOWED_HOSTS = ['*']

EMAIL_HOST = 'mail.swin.edu.au'
EMAIL_PORT = 25

GWCLOUD_JOB_CONTROLLER_API_URL = "http://gwcloud-job-server:8000/job/apiv1/job/"

try:
    from .environment import *
except ImportError:
    pass

