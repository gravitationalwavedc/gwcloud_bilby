from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from graphql_relay.node.node import to_global_id

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.tests.test_utils import silence_errors, create_test_ini_string, generate_elastic_doc
from gw_bilby.jwt_tools import GWCloudUser

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
                            'id': 'QmlsYnlKb2JOb2RlOjI=',
                            'name': 'Test2',
                            'jobStatus': {
                                'name': 'Completed',
                            },
                            'timestamp': '2020-01-01 12:00:00 UTC',
                            'user': 'buffy summers'
                        }
                    },
                    {
                        'node': {
                            'description': 'first job',
                            'id': 'QmlsYnlKb2JOb2RlOjE=',
                            'name': 'Test1',
                            'jobStatus': {
                                'name': 'Completed'
                            },
                            'timestamp': '2020-01-01 12:00:00 UTC',
                            'user': 'buffy summers'
                        }
                    }
                ]
            }
        }

    def elasticsearch_search_mock(*args, **kwargs):
        user = User.objects.all().first()
        gwuser = GWCloudUser(user.username)
        gwuser.user_id = user.id
        gwuser.first_name = user.first_name
        gwuser.last_name = user.last_name

        jobs = []
        for job in BilbyJob.objects.filter(user_id=user.id):
            doc = {
                '_source': generate_elastic_doc(job, user),
                '_id': job.id
            }
            jobs.append(doc)

        return {
            'hits':
                {
                    'hits': jobs
                }
        }

    def request_job_filter_mock(*args, **kwargs):
        jobs = []
        for job in BilbyJob.objects.filter(user_id=User.objects.all().first().id):
            jobs.append({
                'id': job.job_controller_id,
                'history': [
                    {
                        'state': 500,
                        'timestamp': '2020-01-01 12:00:00 UTC'
                    }
                ]
            })

        return True, jobs

    # @silence_errors
    @mock.patch('elasticsearch.Elasticsearch.search', side_effect=elasticsearch_search_mock)
    @mock.patch('bilbyui.schema.request_job_filter', side_effect=request_job_filter_mock)
    def test_public_bilby_jobs_query_no_cursor(self, request_job_filter, elasticsearch_search):
        BilbyJob.objects.create(
            user_id=self.user.id, name="Test1", description="first job", job_controller_id=2345, private=False,
            ini_string=create_test_ini_string({'detectors': "['H1']"})
        )
        BilbyJob.objects.create(
            user_id=self.user.id, name="Test2", job_controller_id=1234, description="A test job", private=False,
            ini_string=create_test_ini_string({'detectors': "['H1']"})
        )
        # This job shouldn't appear in the list because it's private and owned by a different user
        BilbyJob.objects.create(
            user_id=self.user.id+1, name="Test3", job_controller_id=3456, private=True,
            ini_string=create_test_ini_string({'detectors': "['H1']"})
        )

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

            self.assertDictEqual(
                elasticsearch_search.mock_calls[-1].kwargs,
                {
                    'index': settings.ELASTIC_SEARCH_INDEX,
                    'q': '(*) AND _private_info_.private:false',
                    'size': 51,
                    'from_': 0
                }
            )

        self.assertEqual(request_job_filter.mock_calls[0].args[0], 0)
        self.assertEqual(request_job_filter.mock_calls[1].args[0], self.user.id)

        self.assertEqual(list(request_job_filter.mock_calls[0].kwargs['ids']), [1234, 2345])
        self.assertEqual(list(request_job_filter.mock_calls[1].kwargs['ids']), [1234, 2345])

    @silence_errors
    @mock.patch('elasticsearch.Elasticsearch.search', side_effect=elasticsearch_search_mock)
    @mock.patch('bilbyui.schema.request_job_filter', side_effect=request_job_filter_mock)
    def test_public_bilby_jobs_query_test_cursor_count(self, request_job_filter, elasticsearch_search):
        BilbyJob.objects.create(
            user_id=self.user.id, name="Test1", description="first job", job_controller_id=2345, private=False,
            ini_string=create_test_ini_string({'detectors': "['H1']"})
        )
        BilbyJob.objects.create(
            user_id=self.user.id, name="Test2", job_controller_id=1234, description="A test job", private=False,
            ini_string=create_test_ini_string({'detectors': "['H1']"})
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

            # Verify that the "first" and "count" arguments were passed to the elastic search search function
            self.assertDictEqual(
                elasticsearch_search.mock_calls[-1].kwargs,
                {
                    'index': settings.ELASTIC_SEARCH_INDEX,
                    'q': '(*) AND _private_info_.private:false',
                    'size': 51,
                    'from_': 99
                }
            )

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
                self.assertDictEqual(
                    elasticsearch_search.mock_calls[-1].kwargs,
                    {
                        'index': settings.ELASTIC_SEARCH_INDEX,
                        'q': '(*) AND _private_info_.private:false',
                        'size': 26,
                        'from_': idx
                    }
                )

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
            self.client.execute(self.public_bilby_job_query, variables)

            self.assertDictEqual(
                elasticsearch_search.mock_calls[-1].kwargs,
                {
                    'index': settings.ELASTIC_SEARCH_INDEX,
                    'q': '(*) AND _private_info_.private:false',
                    'size': 26,
                    'from_': 0
                }
            )

            # Authenticate the user now for the second iteration
            self.client.authenticate(self.user)

    @silence_errors
    @mock.patch('elasticsearch.Elasticsearch.search', side_effect=elasticsearch_search_mock)
    @mock.patch('bilbyui.schema.request_job_filter', side_effect=request_job_filter_mock)
    def test_public_bilby_jobs_uploaded(self, request_job_filter, elasticsearch_search):
        job1 = BilbyJob.objects.create(
            user_id=self.user.id, name="Test1", description="first job", job_controller_id=2, private=False,
            job_type=BilbyJobType.UPLOADED, ini_string=create_test_ini_string({'detectors': "['H1']"})
        )
        job2 = BilbyJob.objects.create(
            user_id=self.user.id, name="Test2", job_controller_id=1, description="A test job", private=False,
            job_type=BilbyJobType.UPLOADED, ini_string=create_test_ini_string({'detectors': "['H1']"})
        )
        # This job shouldn't appear in the list because it's private.
        BilbyJob.objects.create(
            user_id=4, name="Test3", job_controller_id=3, private=True,
            job_type=BilbyJobType.UPLOADED, ini_string=create_test_ini_string({'detectors': "['H1']"})
        )

        self.public_bilby_job_expected['publicBilbyJobs']['edges'][0]['node']['timestamp'] = str(job2.creation_time)
        self.public_bilby_job_expected['publicBilbyJobs']['edges'][1]['node']['timestamp'] = str(job1.creation_time)

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
    @mock.patch('elasticsearch.Elasticsearch.search', side_effect=elasticsearch_search_mock)
    @mock.patch('bilbyui.schema.request_job_filter', side_effect=request_job_filter_mock)
    def test_public_bilby_jobs_unknown_job_type(self, request_job_filter, elasticsearch_search):
        BilbyJob.objects.create(
            user_id=self.user.id, name="Test1", description="first job", job_controller_id=2, private=False,
            job_type=666, ini_string=create_test_ini_string({'detectors': "['H1']"})
        )

        variables = {
            "count": 50,
            "search": None,
            "timeRange": "all"
        }

        # This query should raise an invalid job type error

        response = self.client.execute(self.public_bilby_job_query, variables)
        self.assertEqual(
            response.errors[0].message,
            "Unknown Bilby Job Type 666",
            "publicBilbyJobs query returned unexpected data."
        )
