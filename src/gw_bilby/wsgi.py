"""
WSGI config for gwcloud_auth project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gw_bilby.production-settings")

application = get_wsgi_application()

# Verify file logging is active (so we can confirm logs reach the host volume)
import logging

logging.getLogger("bilbyui").info("GWCloud Bilby application started; file logging active")
