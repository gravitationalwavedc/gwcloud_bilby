import logging

from django.conf import settings

from bilbyui.utils.jobs.submit_job import _make_job_controller_request
from bilbyui.utils.misc import check_request_leak_decorator

logger = logging.getLogger(__name__)


@check_request_leak_decorator
def request_job_filter(user_id, ids=None, end_time_gt=None):
    """
    Requests a filtered list of jobs from the job controller

    :param ids: A list of job ids to fetch
    :param user_id: An optional user id to make the request as
    :param end_time_gt: An optional parameter for jobs with an end time greater than this
    """

    qs = []

    # Generate the query string
    if ids:
        qs.append("jobIds=" + ",".join(map(str, ids)))

    if end_time_gt:
        qs.append("endTimeGt=" + str(round(end_time_gt.timestamp())))

    url = f"""{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?{"&".join(qs)}"""
    logger.debug(f"Requesting job filter for user {user_id}: {url}")

    try:
        result = _make_job_controller_request("GET", url, user_id)

        logger.debug(f"Successfully retrieved {len(result)} jobs for user {user_id}")
        return "OK", result
    except Exception as e:
        logger.error(f"Error getting job filter for user {user_id}: {str(e)}", exc_info=True)
        return "UNKNOWN", "Error getting job filter"
