import shutil

from core.misc import working_directory


def delete(details, job_data):
    """
    Attempt to delete a job directory and its associated files. Currently unused and could have unexpected and
    disastrous consequences.
    """
    try:
        shutil.rmtree(working_directory(details, job_data))
    except Exception:
        pass
