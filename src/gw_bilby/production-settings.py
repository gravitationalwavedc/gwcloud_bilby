from .base import *  # noqa: F401, F403

DEBUG = False

SITE_URL = "https://gw-cloud.org"

STATIC_URL = "/bilby/static/"

ALLOWED_HOSTS = ["*"]

EMAIL_HOST = "mail.swin.edu.au"
EMAIL_PORT = 25

GWCLOUD_JOB_CONTROLLER_API_URL = "http://adacs-job-controller.jobcontroller.svc.cluster.local:8000/job/apiv1"
GWCLOUD_AUTH_API_URL = "http://gwcloud-auth:8000/auth/graphql"
ELASTIC_SEARCH_HOST = "https://elasticsearch-master.elastic-stack.svc.cluster.local:9200"

try:
    from .environment import *  # noqa: F401, F403
except ImportError:
    pass
