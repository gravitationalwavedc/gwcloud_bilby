from unittest import mock

from django.contrib.auth import get_user_model
from graphql_relay.node.node import to_global_id

from bilbyui.models import BilbyJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.tests.test_utils import silence_errors

User = get_user_model()


class TestPublicBilbyJobsQueries(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

        self.public_bilby_job_query = """
            query($count: Int!, $cursor: String, $search: String, $timeRange: String) {
                publicBilbyJobs(first: $count, after: $cursor, search: $search, timeRange: $timeRange) {
                    edges {
                        node {
                            user
                            description
                            name
                            jobStatus {
                                name
                            }
                            timestamp
                            id
                        }
                    }
                }
            }
        """

        self.public_bilby_job_expected = {
            'publicBilbyJobs': {
                'edges': [
                    {
                        'node': {
                            'description': 'A test job',
                            'id': 'QmlsYnlKb2JOb2RlOjE=',
                            'name': 'Test1',
                            'jobStatus': {
                                'name': 'Completed'
                            },
                            'timestamp': '2020-01-01 12:00:00 UTC',
                            'user': 'buffy summers'
                        }
                    },
                    {
                        'node': {
                            'description': '',
                            'id': 'QmlsYnlKb2JOb2RlOjI=',
                            'name': 'Test2',
                            'jobStatus': {
                                'name': 'Completed',
                            },
                            'timestamp': '2020-01-01 12:00:00 UTC',
                            'user': 'buffy summers'
                        }
                    }
                ]
            }
        }

    def perform_db_search_mock(*args, **kwargs):
        return True, [
            {
                'user': {
                    'id': 1,
                    'firstName': 'buffy',
                    'lastName': 'summers'
                },
                'job': {
                    'id': 1,
                    'name': 'Test1',
                    'description': 'A test job'
                },
                'history': [{'state': 500, 'timestamp': '2020-01-01 12:00:00 UTC'}],
            },
            {
                'user': {
                    'id': 1,
                    'firstName': 'buffy',
                    'lastName': 'summers'
                },
                'job': {
                    'id': 2,
                    'name': 'Test2',
                    'description': ''
                },
                'history': [{'state': 500, 'timestamp': '2020-01-01 12:00:00 UTC'}],
            }
        ]

    def request_lookup_users_mock(*args, **kwargs):
        user = User.objects.first()
        if user:
            return True, [{
                'userId': user.id,
                'username': user.username,
                'firstName': user.first_name,
                'lastName': user.last_name
            }]
        return False, []

    @silence_errors
    @mock.patch('bilbyui.schema.perform_db_search', side_effect=perform_db_search_mock)
    def test_public_bilby_jobs_query_no_cursor(self, perform_db_search):
        BilbyJob.objects.create(
            user_id=self.user.id, name="Test1", description="first job", job_controller_id=2, private=False
        )
        BilbyJob.objects.create(
            user_id=self.user.id, name="Test2", job_controller_id=1, description="A test job", private=False
        )
        # This job shouldn't appear in the list because it's private.
        BilbyJob.objects.create(user_id=4, name="Test3", job_controller_id=3, private=True)

        variables = {
            "count": 50,
            "search": None,
            "timeRange": "all"
        }

        # This query should work as expected for both authenticated and anonymous users.

        # Loop twice, the first loop the user will not be authenticated, the second loop the user will be authenticated
        for _ in range(2):
            # Try again with authenticated user
            response = self.client.execute(self.public_bilby_job_query, variables)
            self.assertDictEqual(
                response.data,
                self.public_bilby_job_expected,
                "publicBilbyJobs query returned unexpected data."
            )

            # Authenticate the user for the second iteration
            self.client.authenticate(self.user)

    @silence_errors
    @mock.patch('bilbyui.schema.perform_db_search', side_effect=perform_db_search_mock)
    def test_public_bilby_jobs_query_test_cursor_count(self, perform_db_search):
        BilbyJob.objects.create(
            user_id=self.user.id, name="Test1", description="first job", job_controller_id=2, private=False
        )
        BilbyJob.objects.create(
            user_id=self.user.id, name="Test2", job_controller_id=1, description="A test job", private=False
        )

        # Loop twice, the first loop the user will not be authenticated, the second loop the user will be authenticated
        for _ in range(2):
            variables = {
                "count": 50,
                "cursor": "YXJyYXljb25uZWN0aW9uOjk5",
                "search": "",
                "timeRange": "all"
            }

            # Check that providing a cursor works as expected
            response = self.client.execute(self.public_bilby_job_query, variables)
            self.assertDictEqual(
                response.data,
                self.public_bilby_job_expected,
                "publicBilbyJobs query returned unexpected data."
            )

            # Verify that the "first" and "count" arguments were passed to the database search function
            self.assertTrue(perform_db_search.call_args[0][1]['after'], 99)
            self.assertTrue(perform_db_search.call_args[0][1]['first'], 50)

            # Double check that all array connection values from 0 - 100 work as expected
            for idx in range(100):
                variables = {
                    "count": 25,
                    "cursor": to_global_id('arrayconnection', idx),
                    "search": None,
                    "timeRange": "all"
                }

                # Check that providing a cursor works as expected
                response = self.client.execute(self.public_bilby_job_query, variables)

                # Verify that the expected results are returned, first = count, after = cursor
                self.assertEqual(perform_db_search.call_args[0][1]['first'], 25)
                self.assertEqual(perform_db_search.call_args[0][1]['after'], idx)

                self.assertDictEqual(
                    response.data,
                    self.public_bilby_job_expected,
                    "publicBilbyJobs query returned unexpected data."
                )

            variables = {
                "count": 25,
                "cursor": None,
                "search": None,
                "timeRange": "all"
            }

            # Check that providing a cursor works as expected
            response = self.client.execute(self.public_bilby_job_query, variables)

            self.assertEqual(perform_db_search.call_args[0][1]['first'], 25)
            # after is not passed through if it is None
            self.assertTrue('after' not in perform_db_search.call_args[0][1])

            # Authenticate the user now for the second iteration
            self.client.authenticate(self.user)
