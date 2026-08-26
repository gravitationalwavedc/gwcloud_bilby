import datetime
import json
import logging

import jwt
import requests
from django.conf import settings
from django.utils import timezone

from bilbyui.utils.misc import check_request_leak_decorator

logger = logging.getLogger(__name__)

HTTP_OK = 200


def _make_job_controller_request(method, url, user_id, data=None, jwt_expiry=None):
    """
    Helper to make a request to the job controller with JWT auth.

    :param method: HTTP method (GET, POST, etc.)
    :param url: Full URL to the job controller endpoint
    :param user_id: User ID for JWT token
    :param data: Optional data payload to send
    :param jwt_expiry: Optional timedelta for JWT expiry (default: 30 days)
    :return: Parsed JSON response dict
    """
    if jwt_expiry is None:
        jwt_expiry = datetime.timedelta(days=30)

    jwt_enc = jwt.encode(
        {"userId": user_id, "exp": timezone.now() + jwt_expiry},
        settings.JOB_CONTROLLER_JWT_SECRET,
        algorithm="HS256",
    )

    kwargs = {
        "headers": {"Authorization": jwt_enc},
        "timeout": 10,
    }
    if data is not None:
        kwargs["data"] = json.dumps(data)
        kwargs["headers"]["Content-Type"] = "application/json"

    result = requests.request(method, url, **kwargs)

    if result.status_code != HTTP_OK:
        msg = f"Job controller returned {result.status_code}: {result.content}"
        logger.error(msg)
        raise requests.RequestException(msg)

    try:
        return json.loads(result.content)
    except json.JSONDecodeError as e:
        msg = f"Job controller returned invalid JSON: {result.content}"
        logger.error(msg)
        raise requests.RequestException(msg) from e


@check_request_leak_decorator
def submit_job(user_id, params, cluster):
    """
    Submits a new job with `params` to the job controller

    :param user_id: The id of the user who is making the request
    :param params: The dictionary object to dump to json and submit as the parameters
    :param cluster: The cluster to submit the job to

    :return: The job controller id of the submitted job
    """

    logger.info("User %s submitting job to cluster '%s'", user_id, cluster)

    # Choose the first (default) cluster if one is not provided
    cluster = cluster or settings.CLUSTERS[0]

    # Check that the specified cluster is valid for submission
    if cluster not in settings.CLUSTERS:
        msg = f"Error submitting job, cluster '{cluster}' is not one of [{' '.join(settings.CLUSTERS)}]"
        logger.error(msg)
        raise ValueError(msg)

    # Construct the request parameters to the job controller, note that parameters must be a string, not an object
    data = {"parameters": json.dumps(params), "cluster": cluster, "bundle": "fbc9f7c0815f1a83b0de36f957351c93797b2049"}

    try:
        result_data = _make_job_controller_request(
            "POST",
            settings.GWCLOUD_JOB_CONTROLLER_API_URL + "/job/",
            user_id,
            data=data,
        )
    except requests.RequestException as e:
        logger.exception("Request exception submitting job for user %s", user_id)
        raise RuntimeError(f"Error submitting job: {e}") from e
    else:
        logger.info("Job submitted successfully for user %s: status 200", user_id)

        if not isinstance(result_data, dict):
            msg = "Job controller returned a malformed response (expected an object with a jobId)"
            logger.error(msg)
            raise RuntimeError(f"Error submitting job: {msg}")

        logger.info("Job controller assigned ID %s for user %s", result_data.get("jobId"), user_id)
        return result_data
