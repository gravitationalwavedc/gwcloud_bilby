from adacs_sso_plugin.adacs_user import ADACSAnonymousUser, ADACSUser
from django.test import override_settings
from gw_bilby.schema import schema

from graphene_django.utils.testing import GraphQLTestCase
from graphene_file_upload.django.testing import GraphQLFileUploadTestMixin
import datetime
from adacs_sso_plugin.test_client import ADACSSSOSessionClient


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class BilbyTestCase(GraphQLFileUploadTestMixin, GraphQLTestCase):
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
    client_class = ADACSSSOSessionClient

    DEFAULT_USER = {
        "is_authenticated": True,
        "id": 1,
        "name": "buffy summers",
        "primary_email": "slayer@gmail.com",
        "emails": ["slayer@gmail.com"],
        "authentication_method": "password",
        "authenticated_at": 0,
        "fetched_at": 0,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We always want to see the full diff when an error occurs.
        self.maxDiff = None
        self.user = ADACSAnonymousUser()

    # Log in as a user. Any parameters can be overwritten with **kwargs
    def authenticate(self, **kwargs):
        user_dict = {
            **BilbyTestCase.DEFAULT_USER,
            "authenticated_at": datetime.datetime.now(tz=datetime.UTC).timestamp(),
            "fetched_at": datetime.datetime.now(tz=datetime.UTC).timestamp(),
            **kwargs,
        }
        self.client.authenticate(user_dict)
        self.user = ADACSUser(**user_dict)

    def deauthenticate(self):
        self.client.deauthenticate()
        self.user = ADACSAnonymousUser()

    # Deprecated function name redirect
    def assertResponseHasNoErrors(self, resp, msg=None):
        return self.assertResponseNoErrors(resp, msg)

    # Add a .data parameter as a result of doing a query
    def query(self, *args, **kwargs):
        response = super().query(*args, **kwargs)
        response_json = response.json()
        response.data = response_json["data"] if "data" in response_json else None
        response.errors = response_json["errors"] if "errors" in response_json else None
        return response

    def file_query(self, *args, **kwargs):
        response = super().file_query(*args, **kwargs)
        response_json = response.json()
        response.data = response_json["data"] if "data" in response_json else None
        response.errors = response_json["errors"] if "errors" in response_json else None
        return response

    def get_upload_token(self):
        generate_job_upload_token_mutation = """
            query GenerateBilbyJobUploadToken {
            generateBilbyJobUploadToken {
                token
            }
            }
        """

        response = self.query(generate_job_upload_token_mutation)

        return response.data["generateBilbyJobUploadToken"]["token"]
