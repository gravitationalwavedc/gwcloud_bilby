from .base import *  # noqa: F401, F403

DEBUG = False

SITE_URL = "https://gw-cloud.org"

STATIC_URL = "/static/"

ALLOWED_HOSTS = ["*"]

EMAIL_HOST = "mail.swin.edu.au"
EMAIL_PORT = 25

GWCLOUD_JOB_CONTROLLER_API_URL = "https://jobcontroller.adacs.org.au/job/apiv1"
ELASTIC_SEARCH_HOST = "http://elasticsearch:9200"

# On both login and logout, redirect to the frontend react app
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# adacs-sso settings
ADACS_SSO_CLIENT_NAME = "gwcloud_bilby"
ADACS_SSO_AUTH_HOST = "https://sso.adacs.org.au"

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name} {module}.{funcName}: {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "[{levelname}] {asctime} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "level": "INFO",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/var/log/gwcloud_bilby/django.log",
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
            "level": "INFO",
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/var/log/gwcloud_bilby/error.log",
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
            "level": "ERROR",
        },
    },
    "root": {
        "handlers": ["console", "file", "error_file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "bilbyui": {
            "handlers": ["console", "file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "bundle": {
            "handlers": ["console", "file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

try:
    from .environment import *  # noqa: F401, F403
except ImportError:
    pass
