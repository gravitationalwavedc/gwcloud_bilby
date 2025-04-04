from .base import *  # noqa: F401, F403

DEBUG = False

SITE_URL = "https://gw-cloud.org"

STATIC_URL = "/static/"

ALLOWED_HOSTS = ["*"]

EMAIL_HOST = "mail.swin.edu.au"
EMAIL_PORT = 25

GWCLOUD_JOB_CONTROLLER_API_URL = "http://adacs-job-controller.jobcontroller.svc.cluster.local:8000/job/apiv1"
ELASTIC_SEARCH_HOST = "https://elasticsearch-master.elastic-stack.svc.cluster.local:9200"

# On both login and logout, redirect to the frontend react app
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# adacs-sso settings
ADACS_SSO_CLIENT_NAME = "gwcloud_bilby"
ADACS_SSO_AUTH_HOST = "https://sso.adacs.org.au"


try:
    from .environment import *  # noqa: F401, F403
except ImportError:
    pass
