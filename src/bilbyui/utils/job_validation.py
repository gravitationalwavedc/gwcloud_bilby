import re

from bilbyui.models import BilbyJob


def validate_job_name(name):
    # This constraint is not enforced in the database
    if len(name) < 5:
        raise Exception("Job name must be at least 5 characters long.")

    max_len = BilbyJob._meta.get_field("name").max_length  # noqa: SLF001
    # this one is enforced by the database field's max_length
    if len(name) > max_len:
        raise Exception(f"Job name must be less than {max_len} characters long.")

    pattern = re.compile(r"^[0-9a-z_-]+\Z", flags=re.IGNORECASE | re.ASCII)
    if not pattern.match(name):
        raise Exception("Job name must not contain any spaces or special characters.")
