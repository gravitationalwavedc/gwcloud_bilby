import datetime
import json
import logging

import jwt
import requests
from django.conf import settings

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

    # Create the jwt token
    jwt_enc = jwt.encode(
        {"userId": user_id, "exp": datetime.datetime.now() + datetime.timedelta(days=30)},
        settings.JOB_CONTROLLER_JWT_SECRET,
        algorithm="HS256",
    )

    qs = []

    # Generate the query string
    if ids:
        qs.append("jobIds=" + ",".join(map(str, ids)))

    if end_time_gt:
        qs.append("endTimeGt=" + str(round(end_time_gt.timestamp())))

    url = f"""{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?{"&".join(qs)}"""
    logger.debug(f"Requesting job filter for user {user_id}: {url}")

    try:
        # Initiate the request to the job controller
        result = requests.request(
            "GET",
            url,
            headers={"Authorization": jwt_enc},
            timeout=10,
        )

        # Check that the request was successful
        if result.status_code != 200:
            # Oops
            msg = f"Error getting job filter for user {user_id}, got error code: {result.status_code}: {result.content}"
            logger.error(msg)
            raise Exception(msg)

        # Parse the response from the job controller
        result = json.loads(result.content)

        logger.debug(f"Successfully retrieved {len(result)} jobs for user {user_id}")
        return "OK", result
    except Exception as e:
        logger.error(f"Error getting job filter for user {user_id}: {str(e)}", exc_info=True)
        return "UNKNOWN", "Error getting job filter"
