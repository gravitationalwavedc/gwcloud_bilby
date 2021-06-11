import datetime
import json
import logging

import jwt
import requests
from django.conf import settings


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
    # Make sure that the job was actually submitted (Might be in a draft state?)
    if not job.job_controller_id:
        return False, "Job not submitted"

    # Create the jwt token
    jwt_enc = jwt.encode(
        {
            'userId': user_id or job.user_id,
            'exp': datetime.datetime.now() + datetime.timedelta(minutes=5)
        },
        settings.JOB_CONTROLLER_JWT_SECRET,
        algorithm='HS256'
    )

    # Generate the post payload
    data = {
        'jobId': job.job_controller_id,
        'paths': paths
    }

    try:
        # Initiate the request to the job controller
        result = requests.request(
            "POST", f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/",
            data=json.dumps(data),
            headers={
                "Authorization": jwt_enc
            }
        )

        # Check that the request was successful
        if result.status_code != 200:
            # todo: Spruce the exception handling up a bit
            # Oops
            msg = f"Error getting job file download urls, got error code: " \
                  f"{result.status_code}\n\n{result.headers}\n\n{result.content}"
            logging.error(msg)
            raise Exception(msg)

        # Parse the response from the job controller
        result = json.loads(result.content)

        # Return the file ids
        return True, result['fileIds']
    except Exception:
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
