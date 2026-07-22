import re

from bilbyui.models import BilbyJob

MIN_JOB_NAME_LENGTH = 5


def validate_job_name(name):
    # This constraint is not enforced in the database
    if len(name) < MIN_JOB_NAME_LENGTH:
        msg = f"Job name must be at least {MIN_JOB_NAME_LENGTH} characters long."
        raise Exception(msg)

    max_len = BilbyJob._meta.get_field("name").max_length
    # this one is enforced by the database field's max_length
    if len(name) > max_len:
        msg = f"Job name must be at most {max_len} characters long."
        raise Exception(msg)

    pattern = re.compile(r"^[0-9a-z_-]+\Z", flags=re.IGNORECASE | re.ASCII)
    if not pattern.match(name):
        raise Exception("Job name must not contain any spaces or special characters.")
