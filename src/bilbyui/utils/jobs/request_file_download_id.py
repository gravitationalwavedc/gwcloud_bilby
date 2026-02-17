import datetime
import json
import logging

import jwt
import requests
from django.conf import settings

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
    :param paths: The list of paths to generate download identifies for
    :param user_id: On optional user id to make the request as

    :return: tuple(result -> bool, details)
    """
    user = user_id or job.user_id
    logger.info(f"User {user} requesting file download IDs for job {job.id}: {len(paths)} files")

    # Make sure that the job was actually submitted (Might be in a draft state?)
    if not job.job_controller_id:
        logger.warning(f"Job {job.id} has no job_controller_id - not submitted")
        return False, "Job not submitted"

    # Create the jwt token
    jwt_enc = jwt.encode(
        {"userId": user, "exp": datetime.datetime.now() + datetime.timedelta(minutes=5)},
        settings.JOB_CONTROLLER_JWT_SECRET,
        algorithm="HS256",
    )

    # Generate the post payload
    data = {"jobId": job.job_controller_id, "paths": paths}

    try:
        # Initiate the request to the job controller
        result = requests.request(
            "POST",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/",
            data=json.dumps(data),
            headers={"Authorization": jwt_enc},
            timeout=10,
        )

        # Check that the request was successful
        if result.status_code != 200:
            # todo: Spruce the exception handling up a bit
            # Oops
            msg = (
                f"Error getting file download URLs for job {job.id}, "
                f"got error code: {result.status_code}: {result.content}"
            )
            logger.error(msg)
            raise Exception(msg)

        # Parse the response from the job controller
        result = json.loads(result.content)

        logger.info(f"Successfully generated {len(result['fileIds'])} download IDs for job {job.id}")
        # Return the file ids
        return True, result["fileIds"]
    except Exception as e:
        logger.error(f"Error getting file download URLs for job {job.id}: {str(e)}", exc_info=True)
        return False, "Error getting job file download url"


def request_file_download_id(job, path, user_id=None):
    """
    Requests a file download id from the job controller for the provided file path

    :param job: The BilbyJob instance to get the status of
    :param path: The path to the file to download
    :param user_id: On optional user id to make the request as
    """
    success, results = request_file_download_ids(job, [path], user_id)

    # Return the first result if the request was successful otherwise return the result as it contains an error message
    return success, results[0] if success else results
