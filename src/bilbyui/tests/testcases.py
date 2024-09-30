from django.test import testcases, override_settings
from graphql_jwt.testcases import JSONWebTokenClient
from gw_bilby.schema import schema
from graphql_jwt.shortcuts import get_token
from graphql_jwt.settings import jwt_settings


class BilbyJSONWebTokenClient(JSONWebTokenClient):
    """Bilby test client with a custom authentication method."""

    def authenticate(self, user, is_ligo=False):
        """Payload for authentication in bilby requires a special userID parameter."""

        if user:
            self._credentials = {
                jwt_settings.JWT_AUTH_HEADER_NAME: "{0} {1}".format(
                    jwt_settings.JWT_AUTH_HEADER_PREFIX, get_token(user, userId=user.id, isLigo=is_ligo)
                ),
            }
        else:
            self._credentials = {}


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class BilbyTestCase(testcases.TestCase):
    """
    Bilby test classes should inherit from this class.

    It overrides some settings that will be common to most bilby test cases.

    Attributes
    ----------

    GRAPHQL_SCHEMA : schema object
        Uses the bilby schema file as the default schema.

    GRAPHQL_URL : str
        Sets the graphql url to the current bilby url.

    client_class : class
        Sets client to be a special bilby specific object that uses a custom authentication.
        method.
    """

    GRAPHQL_SCHEMA = schema
    GRAPHQL_URL = "/graphql"
    client_class = BilbyJSONWebTokenClient

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We always want to see the full diff when an error occurs.
        self.maxDiff = None

    def assertResponseHasNoErrors(self, resp, msg=None):
        """Semi-borrowed from graphene_django.utils.testing
        They also check status_code, which we don't have access to"""
        self.assertIsNone(resp.errors, msg or resp)

    def assertResponseHasErrors(self, resp, msg=None):
        """Borrowed from graphene_django.utils.testing"""
        self.assertIsNotNone(resp.errors, msg or resp)
