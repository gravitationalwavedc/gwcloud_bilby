import datetime
import json

import jwt
import requests
from django.conf import settings


def request_lookup_users(ids, user_id):
    """
    Requests a list of users from the id's provided

    :param ids: The list of ids to use to look up users
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
      usernameLookup(ids: [{",".join(map(str, ids))}]) {{
        userId
        username
        lastName
        firstName
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
            msg = f"Error looking up users: {result.status_code}\n\n{result.headers}\n\n{result.content}"
            print(msg)
            raise Exception(msg)

        # Parse the response from the job controller
        result = json.loads(result.content)

        return True, result["data"]["usernameLookup"]
    except:
        return False, "Error filtering users"
