import logging
import re

from bilbyui.models import BilbyJob

MIN_JOB_NAME_LENGTH = 5

logger = logging.getLogger(__name__)


def validate_job_name(name):
    if name is None:
        msg = "Job name must not be None."
        logger.warning("Job name is None: %s", msg)
        raise ValueError(msg)

    # This constraint is not enforced in the database
    if len(name) < MIN_JOB_NAME_LENGTH:
        msg = f"Job name must be at least {MIN_JOB_NAME_LENGTH} characters long."
        logger.warning("Job name '%s' is too short: %s", name, msg)
        raise ValueError(msg)

    max_len = BilbyJob._meta.get_field("name").max_length
    # this one is enforced by the database field's max_length
    if len(name) > max_len:
        msg = f"Job name must be at most {max_len} characters long."
        logger.warning("Job name '%s' is too long: %s", name, msg)
        raise ValueError(msg)

    pattern = re.compile(r"^[0-9a-z_-]+\Z", flags=re.IGNORECASE | re.ASCII)
    if not pattern.match(name):
        msg = "Job name must not contain any spaces or special characters."
        logger.warning("Job name '%s' has invalid characters: %s", name, msg)
        raise ValueError(msg)
