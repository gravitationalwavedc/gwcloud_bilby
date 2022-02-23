import datetime
import json

import jwt
import requests
from django.conf import settings


def request_job_status(job, user_id=None):
    """
    Requests and calculates the current job status for the provided job

    :param job: The BilbyJob instance to get the status of
    :param user_id: On optional user id to make the request as
    """

    # Make sure that the job was actually submitted (Might be in a draft state?)
    if not job.job_controller_id:
        return "UNKNOWN", "Job not submitted"

    # Create the jwt token
    jwt_enc = jwt.encode(
        {
            'userId': user_id or job.user_id,
            'exp': datetime.datetime.now() + datetime.timedelta(days=30)
        },
        settings.JOB_CONTROLLER_JWT_SECRET,
        algorithm='HS256'
    )

    try:
        # Initiate the request to the job controller
        result = requests.request(
            "GET", f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?jobIds={job.job_controller_id}",
            headers={
                "Authorization": jwt_enc
            }
        )

        # Check that the request was successful
        if result.status_code != 200:
            # Oops
            msg = f"Error getting job status, got error code: " \
                  f"{result.status_code}\n\n{result.headers}\n\n{result.content}"
            print(msg)
            raise Exception(msg)

        # Parse the response from the job controller
        result = json.loads(result.content)

        return "OK", result[0]["history"]
    except Exception as e:
        print(e)
        return "UNKNOWN", "Error getting job status"
