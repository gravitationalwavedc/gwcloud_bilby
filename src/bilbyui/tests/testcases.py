import datetime

from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.test_client import ADACSSSOSessionClient
from django.contrib.auth import get_user_model
from django.test import override_settings
from graphene_django.utils.testing import GraphQLTestCase
from graphene_file_upload.django.testing import GraphQLFileUploadTestMixin

from gw_bilby.schema import schema

User = get_user_model()


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class BilbyTestCase(GraphQLFileUploadTestMixin, GraphQLTestCase):
    """Bilby test classes should inherit from this class.

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

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.create_user()

    @classmethod
    def create_user(
        cls,
        id=1,
        name="buffy summers",
        primary_email="slayer@gmail.com",
        emails=None,
        authentication_method="password",
        **kwargs,
    ):
        """Create a test User with sensible defaults.

        Args:
            id: User ID (default: 1)
            name: User name (default: "buffy summers")
            primary_email: Email (default: "slayer@gmail.com")
            emails: List of emails (default: None, resolved to [primary_email])
            authentication_method: Auth method to set as list (default: "password")
            **kwargs: Additional fields to pass to create_user()

        Returns:
            User instance

        """
        if emails is None:
            emails = [primary_email]

        try:
            user = User.objects.get(id=id)
        except User.DoesNotExist:
            pass
        else:
            user.name = name
            user.primary_email = primary_email
            user.emails = emails
            for key, value in kwargs.items():
                setattr(user, key, value)
            user.authentication_methods = [authentication_method]
            user.save()
            return user

        # If this is not the default user, use a unique email to avoid conflicts
        if id != 1 and primary_email == "slayer@gmail.com":
            primary_email = f"user{id}@test.com"
            emails = [primary_email]

        user = User.objects.create_user(id=id, name=name, primary_email=primary_email, **kwargs)
        user.emails = emails
        user.authentication_methods = [authentication_method]
        user.save()

        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We always want to see the full diff when an error occurs.
        self.maxDiff = None

    # Log in as a user. Any parameters can be overwritten with **kwargs
    def authenticate(self, user=None, **kwargs):
        if user is None:
            user = self.create_user(**kwargs)
        user_dict = {
            "id": user.id,
            "name": user.name,
            "primary_email": user.primary_email,
            "emails": user.emails,
            "authentication_method": user.authentication_methods[0] if user.authentication_methods else "password",
            "is_authenticated": True,
            "authenticated_at": datetime.datetime.now(tz=datetime.UTC).timestamp(),
            "fetched_at": datetime.datetime.now(tz=datetime.UTC).timestamp(),
        }
        self.client.authenticate(user_dict)
        user.last_fetched_at = datetime.datetime.now(tz=datetime.UTC)
        user.save()
        self.user = user
        self.client.force_login(self.user)

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
        response.data = response_json.get("data")
        response.errors = response_json.get("errors")
        return response

    def file_query(self, *args, **kwargs):
        response = super().file_query(*args, **kwargs)
        response_json = response.json()
        response.data = response_json.get("data")
        response.errors = response_json.get("errors")
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
