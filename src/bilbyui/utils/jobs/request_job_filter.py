import logging

import requests
from django.conf import settings

from bilbyui.utils.jobs.submit_job import _make_job_controller_request
from bilbyui.utils.misc import check_request_leak_decorator

logger = logging.getLogger(__name__)

# Bound the number of ids per request so the URL stays within server length limits
JOB_FILTER_BATCH_SIZE = 100


@check_request_leak_decorator
def request_job_filter(user_id, ids=None):
    """
    Requests a filtered list of jobs from the job controller

    :param ids: A list of job ids to fetch
    :param user_id: An optional user id to make the request as
    :return: A tuple of (status, result) where status is "OK" on success or "UNKNOWN" on error
    """

    # Batch the ids so a large set is split into bounded requests rather than one
    # oversized URL. An empty set still issues a single request with no query.
    if ids:
        chunks = [ids[i : i + JOB_FILTER_BATCH_SIZE] for i in range(0, len(ids), JOB_FILTER_BATCH_SIZE)]
    else:
        chunks = [None]

    result = []
    for chunk in chunks:
        qs = ["jobIds=" + ",".join(map(str, chunk))] if chunk else []

        url = f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?{'&'.join(qs)}"
        logger.debug("Requesting job filter for user %s: %s", user_id, url)

        try:
            chunk_result = _make_job_controller_request("GET", url, user_id)
        except requests.RequestException:
            logger.warning("Error getting job filter for user %s", user_id)
            return "UNKNOWN", []
        else:
            if not isinstance(chunk_result, list):
                logger.error("Error getting job filter for user %s: malformed response from job controller", user_id)
                return "UNKNOWN", []
            result.extend(chunk_result)

    logger.debug("Successfully retrieved %s jobs for user %s", len(result), user_id)
    return "OK", result
