# flake8: noqa
import os

from .base import *

INSTALLED_APPS += ("corsheaders",)
CORS_ORIGIN_ALLOW_ALL = True

MIDDLEWARE.append("corsheaders.middleware.CorsMiddleware")

SITE_URL = "http://localhost:3000"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

EXTERNAL_STORAGE_PATH = os.path.join(BASE_DIR, "job_uploads")
JOB_UPLOAD_STAGING_DIR = os.path.join(EXTERNAL_STORAGE_PATH, "staging")
JOB_UPLOAD_DIR = os.path.join(EXTERNAL_STORAGE_PATH, "jobs")
FILE_UPLOAD_TEMP_DIR = os.path.join(EXTERNAL_STORAGE_PATH, "upload")
SUPPORTING_FILE_UPLOAD_DIR = os.path.join(EXTERNAL_STORAGE_PATH, "supporting_files")

ELASTIC_SEARCH_HOST = "http://localhost:9200"

try:
    from .local import *
except Exception as e:
    print(f"Unable to load local.py settings because {e}")
