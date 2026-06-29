# flake8: noqa
# Test settings - inherits from dev settings

# Import dev settings
from gw_bilby.dev import *  # noqa: F401,F403

# Override authentication backend for tests to avoid SSO server calls
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

# Test-specific settings
ADACS_SSO_CLIENT_SECRET = "test_secret_for_ci"
