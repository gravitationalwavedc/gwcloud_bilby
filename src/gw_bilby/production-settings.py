from .base import *

DEBUG = False

SITE_URL = "https://gw-cloud.org"

STATIC_URL = "/bilby/static/"

ALLOWED_HOSTS = ['*']

EMAIL_HOST = 'mail.swin.edu.au'
EMAIL_PORT = 25

GWCLOUD_JOB_CONTROLLER_API_URL = "http://gwcloud-job-server:8000/job/apiv1"
GWCLOUD_AUTH_API_URL = "http://gwcloud-auth:8000/auth/graphql"
GWCLOUD_DB_SEARCH_API_URL = "http://gwcloud-db-search:8000/graphql"
ELASTIC_SEARCH_HOST = 'http://elasticsearch-master.elastic-stack.svc.cluster.local:9200'

try:
    from .environment import *
except ImportError:
    pass
