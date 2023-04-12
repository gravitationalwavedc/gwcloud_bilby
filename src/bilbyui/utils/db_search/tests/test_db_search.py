import json
from urllib.parse import urlencode

import responses
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings

from bilbyui.tests.test_utils import silence_errors
from bilbyui.utils.db_search.db_search import perform_db_search

User = get_user_model()


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestDbSearch(TestCase):
    def setUp(self):
        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.user.user_id = 1234
        self.user.is_ligo = True

        self.mock_data = [
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

    @staticmethod
    def get_query(params):
        return {'query': f"""
    query {{
      publicBilbyJobs ({params}) {{
        user {{
          id
          username
          firstName
          lastName
          email
          isLigoUser
        }}
        job {{
          id
          userId
          name
          description
          creationTime
          lastUpdated
          private
          jobControllerId
        }}
        history {{
          id
          timestamp
          what
          state
          details
        }}
      }}
    }}
    """}

    @silence_errors
    def test_perform_db_search_return_code_error(self):
        self.responses.add(
            responses.POST,
            f"{settings.GWCLOUD_DB_SEARCH_API_URL}",
            body=json.dumps({}),
            status=400
        )

        # Test job search error
        result = perform_db_search(self.user, {})
        self.assertEqual(result, (False, "Error searching for jobs"))

        self.assertEqual(
            self.responses.calls[0].request.body,
            urlencode(self.get_query('search: "", timeRange: "", first: 0, count: 1, excludeLigoJobs: false'))
        )

    def test_perform_db_search_success_no_args(self):
        self.responses.add(
            responses.POST,
            f"{settings.GWCLOUD_DB_SEARCH_API_URL}",
            body=json.dumps({"data": {"publicBilbyJobs": self.mock_data}}),
            status=200
        )

        # Test working search without any arguments
        result = perform_db_search(self.user, {})
        self.assertEqual(result[1], self.mock_data)

        self.assertEqual(
            self.responses.calls[0].request.body,
            urlencode(self.get_query('search: "", timeRange: "", first: 0, count: 1, excludeLigoJobs: false'))
        )

    def test_perform_db_search_success_search_terms(self):
        self.responses.add(
            responses.POST,
            f"{settings.GWCLOUD_DB_SEARCH_API_URL}",
            body=json.dumps({"data": {"publicBilbyJobs": self.mock_data}}),
            status=200
        )

        # Test working search with search argument - including quotes that should be removed
        result = perform_db_search(self.user, {"search": "hello \"bill nye\" 'not quoted'"})
        self.assertEqual(result[1], self.mock_data)

        self.assertEqual(
            self.responses.calls[0].request.body,
            urlencode(
                self.get_query(
                    'search: "hello bill nye not quoted", timeRange: "", first: 0, count: 1, excludeLigoJobs: false')
            )
        )

    def test_perform_db_search_success_time_range(self):
        self.responses.add(
            responses.POST,
            f"{settings.GWCLOUD_DB_SEARCH_API_URL}",
            body=json.dumps({"data": {"publicBilbyJobs": self.mock_data}}),
            status=200
        )

        # Test working search with time range argument
        result = perform_db_search(self.user, {"time_range": "10 years"})
        self.assertEqual(result[1], self.mock_data)

        self.assertEqual(
            self.responses.calls[0].request.body,
            urlencode(self.get_query('search: "", timeRange: "10 years", first: 0, count: 1, excludeLigoJobs: false'))
        )

    def test_perform_db_search_success_first(self):
        self.responses.add(
            responses.POST,
            f"{settings.GWCLOUD_DB_SEARCH_API_URL}",
            body=json.dumps({"data": {"publicBilbyJobs": self.mock_data}}),
            status=200
        )

        # Test working search with first argument
        result = perform_db_search(self.user, {"after": 4321})
        self.assertEqual(result[1], self.mock_data)

        self.assertEqual(
            self.responses.calls[0].request.body,
            urlencode(self.get_query('search: "", timeRange: "", first: 4321, count: 1, excludeLigoJobs: false'))
        )

    def test_perform_db_search_success_count(self):
        self.responses.add(
            responses.POST,
            f"{settings.GWCLOUD_DB_SEARCH_API_URL}",
            body=json.dumps({"data": {"publicBilbyJobs": self.mock_data}}),
            status=200
        )

        # Test working search with first argument
        result = perform_db_search(self.user, {"first": 4321})
        self.assertEqual(result[1], self.mock_data)

        # One extra record is added to the search so that hasNextPage works as expected in pagination
        self.assertEqual(
            self.responses.calls[0].request.body,
            urlencode(self.get_query('search: "", timeRange: "", first: 0, count: 4322, excludeLigoJobs: false'))
        )

    def test_perform_db_search_success_exclude_ligo_jobs(self):
        self.responses.add(
            responses.POST,
            f"{settings.GWCLOUD_DB_SEARCH_API_URL}",
            body=json.dumps({"data": {"publicBilbyJobs": self.mock_data}}),
            status=200
        )

        self.user.is_ligo = False

        # Test working search without any arguments
        result = perform_db_search(self.user, {})
        self.assertEqual(result[1], self.mock_data)

        self.assertEqual(
            self.responses.calls[0].request.body,
            urlencode(self.get_query('search: "", timeRange: "", first: 0, count: 1, excludeLigoJobs: true'))
        )

    def test_perform_db_search_success_all_args(self):
        self.responses.add(
            responses.POST,
            f"{settings.GWCLOUD_DB_SEARCH_API_URL}",
            body=json.dumps({"data": {"publicBilbyJobs": self.mock_data}}),
            status=200
        )

        self.user.is_ligo = False

        # Test working search without any arguments
        result = perform_db_search(self.user, {
            "search": "hello \"bill nye\" 'not quoted'", "time_range": "10 years", "after": 4321, "first": 1234
        })
        self.assertEqual(result[1], self.mock_data)

        self.assertEqual(
            self.responses.calls[0].request.body,
            urlencode(
                self.get_query(
                    'search: "hello bill nye not quoted", timeRange: "10 years", first: 4321, count: 1235, '
                    'excludeLigoJobs: true'
                )
            )
        )

    def test_perform_db_search_success_exclude_ligo_jobs_user_anonymous(self):
        self.responses.add(
            responses.POST,
            f"{settings.GWCLOUD_DB_SEARCH_API_URL}",
            body=json.dumps({"data": {"publicBilbyJobs": self.mock_data}}),
            status=200
        )

        # Test working search without any arguments
        result = perform_db_search(AnonymousUser(), {})
        self.assertEqual(result[1], self.mock_data)

        self.assertEqual(
            self.responses.calls[0].request.body,
            urlencode(self.get_query('search: "", timeRange: "", first: 0, count: 1, excludeLigoJobs: true'))
        )