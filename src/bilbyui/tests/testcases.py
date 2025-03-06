from django.test import override_settings
from gw_bilby.schema import schema

from graphene_django.utils.testing import GraphQLTestCase
import datetime
from adacs_sso_plugin.test_client import ADACSSSOGraphqlSessionClient


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class BilbyTestCase(GraphQLTestCase):
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
    client_class = ADACSSSOGraphqlSessionClient

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We always want to see the full diff when an error occurs.
        self.maxDiff = None

    def default_authenticate(self):
        self.client.authenticate(
            {
                "is_authenticated": True,
                "id": 1,
                "name": "buffy summers",
                "primary_email": "slayer@gmail.com",
                "emails": ["slayer@gmail.com"],
                "authentication_method": "password",
                "authenticated_at": datetime.datetime.now(tz=datetime.UTC).timestamp(),
                "fetched_at": datetime.datetime.now(tz=datetime.UTC).timestamp(),
            }
        )
