import datetime
import json

import jwt
import requests
from django.conf import settings


def request_file_list(job, path, recursive, user_id=None):
    """
    Requests the file list for a job

    :param job: The BilbyJob instance to get the status of
    :param user_id: On optional user id to make the request as
    :param path: The relative path to the job to fetch the file list for
    :param recursive: If the file list should be recursive or not
    """

    # Make sure that the job was actually submitted (Might be in a draft state?)
    if not job.job_controller_id:
        return False, "Job has not been submitted"

    # Create the jwt token
    jwt_enc = jwt.encode(
        {
            'userId': user_id or job.user_id,
            'exp': datetime.datetime.now() + datetime.timedelta(days=30)
        },
        settings.JOB_CONTROLLER_JWT_SECRET,
        algorithm='HS256'
    )

    # Build the data object
    data = {
        'jobId': job.job_controller_id,
        'recursive': recursive,
        'path': path
    }

    try:
        # Initiate the request to the job controller
        result = requests.request(
            "PATCH", f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/",
            data=json.dumps(data),
            headers={
                "Authorization": jwt_enc
            }
        )

        # Check that the request was successful
        if result.status_code != 200:
            # Oops
            msg = f"Error getting job file list, got error code: " \
                  f"{result.status_code}\n\n{result.headers}\n\n{result.content}"
            print(msg)
            raise Exception(msg)

        # Parse the response from the job controller
        result = json.loads(result.content)

        return True, result["files"]
    except Exception:
        return False, "Error getting job file list"
