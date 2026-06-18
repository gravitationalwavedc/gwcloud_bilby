"""Minimal settings for Docker build-time collectstatic (no runtime secrets)."""

from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Minimum adacs-sso settings required at import time
ADACS_SSO_CLIENT_NAME = "gwcloud_bilby"
ADACS_SSO_AUTH_HOST = "https://sso.adacs.org.au"
ADACS_SSO_CLIENT_SECRET = "collectstatic-build-placeholder"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "bilbyui.utils.storage.NonStrictManifestStaticFilesStorage",
    },
}
