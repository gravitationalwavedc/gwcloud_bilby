import json
import uuid
from unittest import mock

import requests
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import LiveServerTestCase
from django.test import override_settings
from django.utils import timezone
from graphql_relay import to_global_id

from bilbyui.models import BilbyJob, AnonymousMetrics
from bilbyui.tests.test_utils import silence_errors

User = get_user_model()


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestAnonymousMetrics(LiveServerTestCase):

    def setUp(self):
        self.user = User.objects.create(username="bill", first_name="Bill", last_name="Nye")
        self.public_id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())

        self.job1 = BilbyJob.objects.create(
            user_id=self.user.id, name="Test1", description="first job", job_controller_id=2, private=False
        )

        self.job2 = BilbyJob.objects.create(
            user_id=self.user.id, name="Test2", job_controller_id=1, description="A test job", private=False
        )

        self.variables = {
            "count": 50,
            "search": None,
            "timeRange": "all"
        }

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
                            'id': to_global_id("BilbyJobNode", self.job1.id),
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
                            'id': to_global_id("BilbyJobNode", self.job2.id),
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
                    'id': list(BilbyJob.objects.all())[-1].id,
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
                    'id': list(BilbyJob.objects.all())[-2].id,
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
    def _request(self, query, variables, db_search_mock, headers=None):
        if headers is None:
            headers = {}

        request_params = {
            "json": {
                "query": query,
                "variables": variables
            }
        }

        request = requests.request(
            method="POST",
            url=self.live_server_url + "/graphql",
            headers=headers,
            **request_params
        )

        content = json.loads(request.content)

        if 'errors' in content:
            raise Exception(f"Error returned when it should not have been {content['errors']}")

        return content.get('data', None)

    def test_valid_anonymous_request(self):
        headers = {
            'X-Correlation-ID': f'{self.public_id} {self.session_id}'
        }

        now = timezone.now()
        result = self._request(self.public_bilby_job_query, self.variables, headers=headers)
        then = timezone.now()

        self.assertDictEqual(result, self.public_bilby_job_expected)

        metrics = AnonymousMetrics.objects.all()
        self.assertEqual(metrics.count(), 1)

        metric = metrics.first()
        self.assertEqual(str(metric.public_id), self.public_id)
        self.assertEqual(str(metric.session_id), self.session_id)
        self.assertEqual(metric.request, 'publicBilbyJobs')
        params = {
            'first': self.variables['count'],
            'time_range': self.variables['timeRange']
        }
        self.assertDictEqual(json.loads(metric.params), params)
        self.assertTrue(now < metric.timestamp < then)

    def test_anonymous_request_no_header(self):
        result = self._request(self.public_bilby_job_query, self.variables)
        self.assertDictEqual(result, self.public_bilby_job_expected)

        self.assertEqual(AnonymousMetrics.objects.all().count(), 0)

    def test_anonymous_request_no_space_in_header(self):
        headers = {
            'X-Correlation-ID': f'{self.public_id}{self.session_id}'
        }

        result = self._request(self.public_bilby_job_query, self.variables, headers=headers)
        self.assertDictEqual(result, self.public_bilby_job_expected)

        self.assertEqual(AnonymousMetrics.objects.all().count(), 0)

    def test_anonymous_request_not_enough_uuids(self):
        headers = {
            'X-Correlation-ID': f'{self.public_id} '
        }

        result = self._request(self.public_bilby_job_query, self.variables, headers=headers)
        self.assertDictEqual(result, self.public_bilby_job_expected)

        self.assertEqual(AnonymousMetrics.objects.all().count(), 0)

    def test_anonymous_request_too_many_uuids(self):
        headers = {
            'X-Correlation-ID': f'{self.public_id} {self.public_id} {self.session_id}'
        }

        result = self._request(self.public_bilby_job_query, self.variables, headers=headers)
        self.assertDictEqual(result, self.public_bilby_job_expected)

        self.assertEqual(AnonymousMetrics.objects.all().count(), 0)

    def test_anonymous_request_invalid_uuids(self):
        headers = {
            'X-Correlation-ID': f'{self.public_id[0:-2]} {self.public_id}'
        }

        result = self._request(self.public_bilby_job_query, self.variables, headers=headers)
        self.assertDictEqual(result, self.public_bilby_job_expected)

        self.assertEqual(AnonymousMetrics.objects.all().count(), 0)
