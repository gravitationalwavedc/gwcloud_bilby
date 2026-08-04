import logging
import os
import sys

logger = logging.getLogger("gwflow_ingest")

try:
    from local import (
        CBCFLOW_PORTAL_TOKEN,
        CBCFLOW_PORTAL_URL,
        DB_PATH,
        GWCLOUD_ENDPOINT,
        GWCLOUD_TOKEN,
        HOST_DB_PATH,
        HOST_STAGING_PATH,
        JOB_CONTROLLER_API_URL,
        JOB_CONTROLLER_BUNDLE,
        JOB_CONTROLLER_CLUSTER,
        JOB_CONTROLLER_JWT_SECRET,
        MAX_BYTES_PER_RUN,
        MAX_FILES_PER_RUN,
        MAX_RETRY_ATTEMPTS,
        STAGING_DIR,
    )

    logger.info("Loaded settings from local.py")
except ImportError:
    logger.info("No local.py file found, loading settings from env")
    GWCLOUD_TOKEN = os.getenv("GWCLOUD_TOKEN")
    GWCLOUD_ENDPOINT = os.getenv("GWCLOUD_ENDPOINT", "https://gwcloud.org.au/graphql")
    CBCFLOW_PORTAL_URL = os.getenv("CBCFLOW_PORTAL_URL", "https://cbcflow.gwdc.org.au")
    CBCFLOW_PORTAL_TOKEN = os.getenv("CBCFLOW_PORTAL_TOKEN")
    JOB_CONTROLLER_API_URL = os.getenv("JOB_CONTROLLER_API_URL", "https://jobcontroller.adacs.org.au/job/apiv1")
    JOB_CONTROLLER_JWT_SECRET = os.getenv("JOB_CONTROLLER_JWT_SECRET")
    JOB_CONTROLLER_CLUSTER = os.getenv("JOB_CONTROLLER_CLUSTER", "cit")
    JOB_CONTROLLER_BUNDLE = os.getenv("JOB_CONTROLLER_BUNDLE")
    DB_PATH = os.getenv("DB_PATH")
    HOST_DB_PATH = os.getenv("HOST_DB_PATH")
    STAGING_DIR = os.getenv("STAGING_DIR", "/staging")
    HOST_STAGING_PATH = os.getenv("HOST_STAGING_PATH")
    MAX_FILES_PER_RUN = int(os.getenv("MAX_FILES_PER_RUN", "50"))
    MAX_BYTES_PER_RUN = int(os.getenv("MAX_BYTES_PER_RUN", "21474836480"))
    MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", "24"))

BACKFILL = False


def validate_settings():
    """Verify essential settings and exit if DB_PATH is unset."""
    if not DB_PATH:
        logger.critical("DB_PATH setting is missing or empty")
        sys.exit(1)
