import datetime
import json

import jwt
import requests
from django.conf import settings


def request_filter_users(search, user_id):
    """
    Requests a filter of users based on search from the auth service

    :param search: The search string to match space separated
    :param user_id: The id of the user making the request (Usually passed down from request context)
    """

    # Create the jwt token
    jwt_enc = jwt.encode(
        {
            'userId': user_id,
            'exp': datetime.datetime.now() + datetime.timedelta(days=30)
        },
        settings.AUTH_SERVICE_JWT_SECRET,
        algorithm='HS256'
    )

    query = f"""
    query {{
      usernameFilter(search: "{search}") {{
        terms {{
          term
          users {{
            userId
            username
            lastName
            firstName
          }}
        }}
      }}
    }}
    """

    try:
        # Initiate the request to the job controller
        result = requests.request(
            "POST", f"{settings.GWCLOUD_AUTH_API_URL}",
            data={'query': query},
            headers={
                "Authorization": jwt_enc
            }
        )

        # Check that the request was successful
        if result.status_code != 200:
            # Oops
            msg = f"Error filtering users: {result.status_code}\n\n{result.headers}\n\n{result.content}"
            print(msg)
            raise Exception(msg)

        # Parse the response from the job controller
        result = json.loads(result.content)

        return True, result["data"]["usernameFilter"]["terms"]
    except:
        return False, "Error filtering users"
