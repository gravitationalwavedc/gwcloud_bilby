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

# Path to the ingest lock file. `run_cron.sh` bind-mounts HOST_LOCK_PATH here so
# a single lock is shared across container invocations; without the mount the
# lock would live in the container's private overlay and fail to serialise
# separate `docker run` instances. Falls back to a sibling of DB_PATH when unset.
LOCK_PATH = os.getenv("LOCK_PATH")

# Ordered, comma-separated list of file systems the cron is allowed to stage
# files from, highest precedence first. No default: an unprovisioned
# deployment must fail closed rather than silently accept staging from an
# arbitrary file system. Defined here, after the try/except ImportError block
# above, so it is always read from the environment and never from local.py
# (adding it to the `from local import (...)` list would turn any local.py
# that lacks the name into an ImportError, and the except clause would then
# silently load every setting from the environment instead).
_raw_file_systems = os.getenv("ACCESSIBLE_FILE_SYSTEMS", "")
ACCESSIBLE_FILE_SYSTEMS = (
    tuple(part.strip() for part in _raw_file_systems.split(",")) if _raw_file_systems.strip() else ()
)

BACKFILL = False


def validate_settings():
    """Verify essential settings and exit if any required setting is unset."""
    required = [
        ("DB_PATH", DB_PATH),
        ("GWCLOUD_TOKEN", GWCLOUD_TOKEN),
        ("JOB_CONTROLLER_JWT_SECRET", JOB_CONTROLLER_JWT_SECRET),
        ("JOB_CONTROLLER_BUNDLE", JOB_CONTROLLER_BUNDLE),
        ("ACCESSIBLE_FILE_SYSTEMS", ACCESSIBLE_FILE_SYSTEMS),
    ]
    for name, val in required:
        if not val:
            logger.critical(f"{name} setting is missing or empty")
            sys.exit(1)

    if "" in ACCESSIBLE_FILE_SYSTEMS:
        logger.critical("ACCESSIBLE_FILE_SYSTEMS setting has an empty entry")
        sys.exit(1)

    if len(set(ACCESSIBLE_FILE_SYSTEMS)) != len(ACCESSIBLE_FILE_SYSTEMS):
        logger.critical("ACCESSIBLE_FILE_SYSTEMS setting has a duplicate entry")
        sys.exit(1)
