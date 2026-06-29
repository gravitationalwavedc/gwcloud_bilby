# flake8: noqa
import os

from .base import *

INSTALLED_APPS += ("corsheaders",)

# For requests to include credentials (i.e., http-only cookies) the
# CORS_ALLOWED_ORIGINS must not be ['*']
CORS_ALLOWED_ORIGINS = ["http://localhost:8001"]
CORS_ALLOW_CREDENTIALS = True

MIDDLEWARE.append("corsheaders.middleware.CorsMiddleware")

SITE_URL = "http://localhost:8001"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

EXTERNAL_STORAGE_PATH = os.path.join(BASE_DIR, "job_uploads")
JOB_UPLOAD_STAGING_DIR = os.path.join(EXTERNAL_STORAGE_PATH, "staging")
JOB_UPLOAD_DIR = os.path.join(EXTERNAL_STORAGE_PATH, "jobs")
FILE_UPLOAD_TEMP_DIR = os.path.join(EXTERNAL_STORAGE_PATH, "upload")
SUPPORTING_FILE_UPLOAD_DIR = os.path.join(EXTERNAL_STORAGE_PATH, "supporting_files")

ELASTIC_SEARCH_HOST = "http://localhost:9200"

# LOGIN_URL is set in base.py (reverse_lazy("sso:login")).
# On both login and logout, redirect to the Django htmx frontend.
LOGIN_REDIRECT_URL = "http://localhost:8001/"
LOGOUT_REDIRECT_URL = "http://localhost:8001/"

# adacs-sso settings
ADACS_SSO_CLIENT_NAME = "gwcloud_bilby_dev"
ADACS_SSO_AUTH_HOST = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Test runner / JUnit XML output (dev/CI only)
# ---------------------------------------------------------------------------

TEST_RUNNER = "xmlrunner.extra.djangotestrunner.XMLTestRunner"
TEST_OUTPUT_DIR = os.path.join(BASE_DIR, "reports")
TEST_OUTPUT_FILE_NAME = "junit.xml"

# Required for adacs-sso-plugin v0.4.2 system checks
ADACS_SSO_CLIENT_SECRET = "dev_secret_for_local_testing"
ADACS_SSO_LOCAL_MODE = True

# Use ModelBackend for tests to avoid SSO server calls
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

try:
    from .local import *
except ImportError:
    pass
