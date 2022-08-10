import datetime
import json
import logging

import jwt
import requests
from django.conf import settings

from bilbyui.utils.misc import check_request_leak_decorator


@check_request_leak_decorator
def submit_job(user_id, params, cluster):
    """
    Submits a new job with `params` to the job controller

    :param user_id: The id of the user who is making the request
    :param params: The dictionary object to dump to json and submit as the parameters
    :param cluster: The cluster to submit the job to

    :return: The job controller id of the submitted job
    """

    # Choose the first (default) cluster if one is not provided
    cluster = settings.CLUSTERS[0] if not cluster else cluster

    # Check that the specified cluster is valid for submission
    if cluster not in settings.CLUSTERS:
        msg = f"Error submitting job, cluster '{cluster}' is not one of [{' '.join(settings.CLUSTERS)}]"
        logging.error(msg)
        raise Exception(msg)

    # Construct the request parameters to the job controller, note that parameters must be a string, not an object
    data = {
        "parameters": json.dumps(params),
        "cluster": cluster,
        "bundle": "fbc9f7c0815f1a83b0de36f957351c93797b2049"
    }

    # Create the jwt token
    jwt_enc = jwt.encode(
        {
            'userId': user_id,
            'exp': datetime.datetime.now() + datetime.timedelta(days=30)
        },
        settings.JOB_CONTROLLER_JWT_SECRET,
        algorithm='HS256'
    )

    # Initiate the request to the job controller
    result = requests.request(
        "POST", settings.GWCLOUD_JOB_CONTROLLER_API_URL + "/job/",
        data=json.dumps(data),
        headers={
            "Authorization": jwt_enc
        }
    )

    # Check that the request was successful
    if result.status_code != 200:
        # Oops
        msg = f"Error submitting job, got error code: {result.status_code}\n\n{result.headers}\n\n{result.content}"
        logging.error(msg)
        raise Exception(msg)

    logging.info(f"Job submitted OK.\n{result.headers}\n\n{result.content}")

    # Parse the response from the job controller
    result = json.loads(result.content)

    return result
