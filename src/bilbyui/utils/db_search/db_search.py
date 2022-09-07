import datetime
import json
import logging

import jwt
import requests
from django.conf import settings

from bilbyui.utils.misc import check_request_leak_decorator


@check_request_leak_decorator
def perform_db_search(user, kwargs):
    """
    Perform a db job search based on parameters provided in kwargs

    :param kwargs: The search parameters as passed from the relay schema
    :param user: The user making the request (Passed down from the request context)
    """

    # Create the jwt token
    jwt_enc = jwt.encode(
        {
            'userId': user.user_id,
            'exp': datetime.datetime.now() + datetime.timedelta(days=30)
        },
        settings.DB_SEARCH_SERVICE_JWT_SECRET,
        algorithm='HS256'
    )

    # Strip all quotes and double quotes from the search term
    search_terms = kwargs.get('search', '').replace("\"", '').replace("\'", '')

    search_params = f"search: \"{search_terms}\""
    search_params += f", timeRange: \"{kwargs.get('time_range', '')}\""
    search_params += f", first: {kwargs.get('after', 0)}"
    # Fetch one extra record to trigger "hasNextPage"
    search_params += f", count: {kwargs.get('first', 0) + 1}"
    search_params += f", excludeLigoJobs: {'false' if user.is_ligo else 'true'}"

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
          jobControllerId
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
            raise Exception(msg)

        # Parse the response from the job controller
        result = json.loads(result.content)

        return True, result["data"]["publicBilbyJobs"]
    except Exception as exception:
        logging.error(str(exception))
        return False, "Error searching for jobs"
