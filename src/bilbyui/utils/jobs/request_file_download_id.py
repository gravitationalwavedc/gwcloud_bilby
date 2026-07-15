import datetime
import logging

from django.conf import settings

from bilbyui.utils.jobs.submit_job import _make_job_controller_request
from bilbyui.utils.misc import check_request_leak_decorator

logger = logging.getLogger(__name__)


@check_request_leak_decorator
def request_file_download_ids(job, paths, user_id=None):
    """
    Requests a list of file download ids from the job controller for the provided list of file paths

    If a file download id is generated successfully for all paths, the result will be a tuple of:-
        True, [id, id, id, id, id]

    If any download id fails to be generated, the result will be a tuple of:-
        False, str (Reason for the failure)

    On success, the list of ids is guaranteed to be the same size and order as the provided paths parameter

    :param job: The BilbyJob instance to get the status of
    :param paths: The list of paths to generate download identifiers for
    :param user_id: An optional user id to make the request as

    :return: tuple(result -> bool, details)
    """
    user = user_id or job.user_id
    logger.info(f"User {user} requesting file download IDs for job {job.id}: {len(paths)} files")

    # Make sure that the job was actually submitted (Might be in a draft state?)
    if not job.job_controller_id:
        logger.warning(f"Job {job.id} has no job_controller_id - not submitted")
        return False, "Job not submitted"

    data = {"jobId": job.job_controller_id, "paths": paths}

    try:
        result = _make_job_controller_request(
            "POST",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/",
            user,
            data=data,
            jwt_expiry=datetime.timedelta(minutes=5),
        )

        logger.info(f"Successfully generated {len(result['fileIds'])} download IDs for job {job.id}")
        return True, result["fileIds"]
    except Exception as e:
        logger.error(f"Error getting file download IDs for job {job.id}: {str(e)}", exc_info=True)
        return False, "Error getting job file download id"


def request_file_download_id(job, path, user_id=None):
    """
    Requests a file download id from the job controller for the provided file path

    :param job: The BilbyJob instance to get the status of
    :param path: The path to the file to download
    :param user_id: An optional user id to make the request as
    """
    success, results = request_file_download_ids(job, [path], user_id)

    # Return the first result if the request was successful otherwise return the result as it contains an error message
    return success, results[0] if success else results
