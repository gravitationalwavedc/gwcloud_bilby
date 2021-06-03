import datetime
import json

import jwt
import requests
from django.conf import settings


def request_job_filter(user_id, ids=None, end_time_gt=None):
    """
    Requests a filtered list of jobs from the job controller

    :param ids: A list of job ids to fetch
    :param user_id: An optional user id to make the request as
    :param end_time_gt: An optional parameter for jobs with an end time greater than this
    """

    # Create the jwt token
    jwt_enc = jwt.encode(
        {
            'userId': user_id,
            'exp': datetime.datetime.now() + datetime.timedelta(days=30)
        },
        settings.JOB_CONTROLLER_JWT_SECRET,
        algorithm='HS256'
    )

    qs = []

    # Generate the query string
    if ids:
        qs.append("jobIds=" + ",".join(map(str, ids)))

    if end_time_gt:
        qs.append("endTimeGt=" + str(round(end_time_gt.timestamp())))

    print(f"""{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?{"&".join(qs)}""")

    try:
        # Initiate the request to the job controller
        result = requests.request(
            "GET", f"""{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/?{"&".join(qs)}""",
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

        return "OK", result
    except Exception as e:
        print(e)
        return "UNKNOWN", "Error getting job status"