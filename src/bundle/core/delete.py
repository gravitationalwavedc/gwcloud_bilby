import shutil

from core.misc import working_directory


def delete(details, job_data):
    """
    Attempt to delete a job directory and it's associated files. Currently unused and could have unexpected and
    disasterous consequences.
    """
    try:
        shutil.rmtree(working_directory(details, job_data))
    except Exception:
        pass
