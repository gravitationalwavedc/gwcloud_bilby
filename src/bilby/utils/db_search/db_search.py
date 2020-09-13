import datetime
import json

import jwt
import requests
from django.conf import settings


def perform_db_search(user_id, kwargs):
    """
    Perform a db job search based on parameters provided in kwargs

    :param kwargs: The search parameters as passed from the relay schema
    :param user_id: The id of the user making the request (Usually passed down from request context)
    """

    # Create the jwt token
    jwt_enc = jwt.encode(
        {
            'userId': user_id,
            'exp': datetime.datetime.now() + datetime.timedelta(days=30)
        },
        settings.DB_SEARCH_SERVICE_JWT_SECRET,
        algorithm='HS256'
    )

    search_params = f"search: \"{kwargs.get('search', '')}\""
    search_params += f", timeRange: \"{kwargs.get('time_range', '')}\""
    # Fetch one extra record to trigger "hasNextPage"
    search_params += f", count: {kwargs.get('first', 0) + 1}"

    query = f"""
    query {{
      publicBilbyJobs ({search_params}) {{
        user {{
          id
          username
          firstName
          lastName
          email
          isLigoUser
        }}
        job {{
          id
          userId
          name
          description
          creationTime
          lastUpdated
          private
          jobId
        }}
        history {{
          id
          timestamp
          what
          state
          details
        }}
      }}
    }}
    """

    try:
        # Initiate the request to the job controller
        result = requests.request(
            "POST", f"{settings.GWCLOUD_DB_SEARCH_API_URL}",
            data={'query': query},
            headers={
                "Authorization": 'JWT ' + jwt_enc.decode()
            }
        )

        # Check that the request was successful
        if result.status_code != 200:
            # Oops
            msg = f"Error searching for jobs: {result.status_code}\n\n{result.headers}\n\n{result.content}"
            print(msg)
            raise Exception(msg)

        # Parse the response from the job controller
        result = json.loads(result.content)

        return True, result["data"]["publicBilbyJobs"]
    except:
        return False, "Error searching for jobs"
