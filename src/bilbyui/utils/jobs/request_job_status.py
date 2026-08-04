import logging

import requests
from django.conf import settings

from bilbyui.utils.jobs.submit_job import _make_job_controller_request
from bilbyui.utils.misc import check_request_leak_decorator

logger = logging.getLogger(__name__)


@check_request_leak_decorator
def request_job_status(job, user_id=None):
    """
    Requests and calculates the current job status for the provided job

    :param job: The BilbyJob instance to get the status of
    :param user_id: An optional user id to make the request as
    """

    logger.debug("Requesting job status for job %s (controller ID: %s)", job.id, job.job_controller_id)

    # Make sure that the job was actually submitted (Might be in a draft state?)
    if not job.job_controller_id:
        logger.warning("Job %s has no job_controller_id - not submitted", job.id)
        return "UNKNOWN", "Job not submitted"

    url = f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?jobIds={job.job_controller_id}"

    try:
        result = _make_job_controller_request("GET", url, user_id or job.user_id)

        logger.debug("Successfully retrieved status for job %s", job.id)
        return "OK", result[0]["history"]
    except requests.RequestException as e:
        logger.error("Error getting job status for job %s: %s", job.id, e, exc_info=True)
        return "UNKNOWN", "Error getting job status"
