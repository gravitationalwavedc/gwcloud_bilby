from django.contrib.auth import get_user_model
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.tests.test_utils import silence_errors

User = get_user_model()


class TestAllLabels(BilbyTestCase):
    def make_request(self):
        query = """
                query {
                    allLabels {
                        edges {
                            node {
                                name
                                description
                                protected
                            }
                        }
                    }
                }
                """
        response = self.client.execute(query)
        expected = {
            "allLabels": {
                "edges": [
                    {
                        "node": {
                            "name": "Bad Run",
                            "description": "This run contains some issues and should not be used for science.",
                            "protected": False,
                        }
                    },
                    {
                        "node": {
                            "name": "Production Run",
                            "description": "This run has been completed successfully and can be used for science.",
                            "protected": False,
                        }
                    },
                    {
                        "node": {
                            "name": "Review Requested",
                            "description": "This run should be reviewed by peers.",
                            "protected": False,
                        }
                    },
                    {"node": {"name": "Reviewed", "description": "This run has been reviewed.", "protected": False}},
                    {
                        "node": {
                            "name": "Official",
                            "description": "This run has been marked by GWCloud admins as preferred for analysis of "
                            "this event.",
                            # noqa: E501
                            "protected": True,
                        }
                    },
                ]
            }
        }
        self.assertResponseHasNoErrors(response)
        self.assertDictEqual(response.data, expected)

    @silence_errors
    def test_get_all_labels_without_authentication(self):
        # An anonymous user should be able to get all the labels
        self.make_request()

    def test_get_all_labels(self):
        # An authenticated user should be able to get all the labels
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)
        self.make_request()
