import re
from datetime import timedelta, datetime
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from graphql_relay.node.node import to_global_id

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import silence_errors, create_test_ini_string, generate_elastic_doc
from bilbyui.tests.testcases import BilbyTestCase
from gw_bilby.jwt_tools import GWCloudUser

User = get_user_model()


class TestPublicBilbyJobsQueries(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

        self.job1 = BilbyJob.objects.create(
            user_id=self.user.id, name="Test1", description="first job", job_controller_id=2345, private=False,
            ini_string=create_test_ini_string({'detectors': "['H1']"})
        )

        self.job2 = BilbyJob.objects.create(
            user_id=self.user.id, name="Test2", job_controller_id=1234, description="A test job", private=False,
            ini_string=create_test_ini_string({'detectors': "['H1']"})
        )

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
        # This job shouldn't appear in the list because it's private and owned by a different user
        BilbyJob.objects.create(
            user_id=self.user.id + 1, name="Test3", job_controller_id=3456, private=True,
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
        # This job shouldn't appear in the list because it's private.
        BilbyJob.objects.create(
            user_id=4, name="Test3", job_controller_id=3, private=True,
            job_type=BilbyJobType.UPLOADED, ini_string=create_test_ini_string({'detectors': "['H1']"})
        )

        self.job1.job_type = BilbyJobType.UPLOADED
        self.job1.save()

        self.job2.job_type = BilbyJobType.UPLOADED
        self.job2.save()

        self.public_bilby_job_expected['publicBilbyJobs']['edges'][0]['node']['timestamp'] = \
            str(self.job2.creation_time)
        self.public_bilby_job_expected['publicBilbyJobs']['edges'][1]['node']['timestamp'] = \
            str(self.job1.creation_time)

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
        BilbyJob.objects.all().delete()

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

    @mock.patch('elasticsearch.Elasticsearch.search', side_effect=elasticsearch_search_mock)
    @mock.patch('bilbyui.schema.request_job_filter', side_effect=request_job_filter_mock)
    def test_public_bilby_jobs_query_private_info(self, request_job_filter, elasticsearch_search):
        for term in [
            "_private_info_.private:true",
            "_private_info_.userId:50",
            "_private_info_"
        ]:
            variables = {
                "count": 50,
                "search": term,
                "timeRange": "all"
            }

            # Should return no results
            response = self.client.execute(self.public_bilby_job_query, variables)
            self.assertDictEqual(
                response.data,
                {'publicBilbyJobs': {'edges': []}},
                "publicBilbyJobs query returned unexpected data."
            )

    @mock.patch('elasticsearch.Elasticsearch.search', side_effect=elasticsearch_search_mock)
    @mock.patch('bilbyui.schema.request_job_filter', side_effect=request_job_filter_mock)
    def test_public_bilby_jobs_query_time_ranges(self, request_job_filter, elasticsearch_search):
        for time_range in [
            "1d",
            "1w",
            "1m",
            "1y",
            "all"
        ]:
            variables = {
                "count": 50,
                "search": None,
                "timeRange": time_range
            }

            now = timezone.now()

            # Should return no results
            response = self.client.execute(self.public_bilby_job_query, variables)
            self.assertDictEqual(
                response.data,
                self.public_bilby_job_expected,
                "publicBilbyJobs query returned unexpected data."
            )

            self.assertEqual(
                elasticsearch_search.mock_calls[-1].kwargs,
                elasticsearch_search.mock_calls[-1].kwargs |
                {
                    'index': settings.ELASTIC_SEARCH_INDEX,
                    'size': 51,
                    'from_': 0
                }
            )

            if time_range == 'all':
                self.assertEqual(
                    elasticsearch_search.mock_calls[-1].kwargs['q'],
                    '(*) AND _private_info_.private:false'
                )
            else:
                delta = None
                if time_range == "1d":
                    delta = timedelta(days=1)
                elif time_range == "1w":
                    delta = timedelta(days=7)
                elif time_range == "1m":
                    delta = timedelta(days=31)
                elif time_range == "1y":
                    delta = timedelta(days=365)

                regex = re.compile('job\.creationTime:\["([^"]+)" TO "([^"]+)"\]')
                _from, to = regex.search(elasticsearch_search.mock_calls[-1].kwargs['q']).groups()

                _from = datetime.fromisoformat(_from)
                to = datetime.fromisoformat(to)

                # To should be very close to now
                self.assertTrue((to - now).total_seconds() < 1)

                # From -> To should be equal to the delta
                self.assertEqual((to - _from), delta)

    @override_settings(EMBARGO_START_TIME=1234)
    @mock.patch('elasticsearch.Elasticsearch.search', side_effect=elasticsearch_search_mock)
    @mock.patch('bilbyui.schema.request_job_filter', side_effect=request_job_filter_mock)
    def test_public_bilby_jobs_query_embargo(self, request_job_filter, elasticsearch_search):
        variables = {
            "count": 50,
            "search": None,
            "timeRange": "all"
        }

        # Should return no results
        response = self.client.execute(self.public_bilby_job_query, variables)
        self.assertDictEqual(
            response.data,
            self.public_bilby_job_expected,
            "publicBilbyJobs query returned unexpected data."
        )

        self.assertEqual(
            elasticsearch_search.mock_calls[-1].kwargs['q'],
            f"((*) AND _private_info_.private:false) AND (params.trigger_time:<{settings.EMBARGO_START_TIME} "
            f"OR ini.n_simulation:>0)"
        )

    @override_settings(EMBARGO_START_TIME=1234)
    @mock.patch('elasticsearch.Elasticsearch.search', side_effect=elasticsearch_search_mock)
    @mock.patch('bilbyui.schema.request_job_filter', side_effect=request_job_filter_mock)
    def test_public_bilby_jobs_query_combine_all(self, request_job_filter, elasticsearch_search):
        variables = {
            "count": 50,
            "search": 'test',
            "timeRange": "1m",
            "cursor": "YXJyYXljb25uZWN0aW9uOjk5",
        }

        # Should return expected results
        now = timezone.now()
        response = self.client.execute(self.public_bilby_job_query, variables)
        self.assertDictEqual(
            response.data,
            self.public_bilby_job_expected,
            "publicBilbyJobs query returned unexpected data."
        )

        regex = re.compile('job\.creationTime:\["([^"]+)" TO "([^"]+)"\]')
        _from, to = regex.search(elasticsearch_search.mock_calls[-1].kwargs['q']).groups()

        _from = datetime.fromisoformat(_from)
        to = datetime.fromisoformat(to)

        delta = timedelta(days=31)
        # To should be very close to now
        self.assertTrue((to - now).total_seconds() < 1)

        # From -> To should be equal to the delta
        self.assertEqual((to - _from), delta)

        print(elasticsearch_search.mock_calls[-1].kwargs)

        self.assertEqual(
            elasticsearch_search.mock_calls[-1].kwargs['q'],
            f'(((test) AND job.creationTime:["{_from.isoformat()}" TO "{to.isoformat()}"]) AND '
            f'_private_info_.private:false) AND (params.trigger_time:<{settings.EMBARGO_START_TIME} '
            f'OR ini.n_simulation:>0)'
        )

        self.assertEqual(
            elasticsearch_search.mock_calls[-1].kwargs,
            elasticsearch_search.mock_calls[-1].kwargs |
            {
                'index': settings.ELASTIC_SEARCH_INDEX,
                'size': 51,
                'from_': 99
            }
        )
