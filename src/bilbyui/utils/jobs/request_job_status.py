import datetime
import json
import logging

import jwt
import requests
from django.conf import settings

from bilbyui.utils.misc import check_request_leak_decorator

logger = logging.getLogger(__name__)


@check_request_leak_decorator
def request_job_status(job, user_id=None):
    """
    Requests and calculates the current job status for the provided job

    :param job: The BilbyJob instance to get the status of
    :param user_id: On optional user id to make the request as
    """

    logger.debug(f"Requesting job status for job {job.id} (controller ID: {job.job_controller_id})")

    # Make sure that the job was actually submitted (Might be in a draft state?)
    if not job.job_controller_id:
        logger.warning(f"Job {job.id} has no job_controller_id - not submitted")
        return "UNKNOWN", "Job not submitted"

    # Create the jwt token
    jwt_enc = jwt.encode(
        {"userId": user_id or job.user_id, "exp": datetime.datetime.now() + datetime.timedelta(days=30)},
        settings.JOB_CONTROLLER_JWT_SECRET,
        algorithm="HS256",
    )

    try:
        # Initiate the request to the job controller
        result = requests.request(
            "GET",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?jobIds={job.job_controller_id}",
            headers={"Authorization": jwt_enc},
            timeout=30,
        )

        # Check that the request was successful
        if result.status_code != 200:
            # Oops
            msg = f"Error getting job status for job {job.id}, got error code: {result.status_code}: {result.content}"
            logger.error(msg)
            raise Exception(msg)

        # Parse the response from the job controller
        result = json.loads(result.content)

        logger.debug(f"Successfully retrieved status for job {job.id}")
        return "OK", result[0]["history"]
    except Exception as e:
        logger.error(f"Error getting job status for job {job.id}: {str(e)}", exc_info=True)
        return "UNKNOWN", "Error getting job status"
