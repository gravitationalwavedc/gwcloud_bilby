from django.contrib.auth import get_user_model
from graphql_relay.node.node import to_global_id
from bilby.models import BilbyJob
from bilby.tests.testcases import BilbyTestCase
from unittest import mock

User = get_user_model()


class TestQueriesWithAuthenticatedUser(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)

    def request_job_filter_mock(*args, **kwargs):
        return "Ok", [
            {
                'user': 1,
                'id': 1,
                'history': [{'state': 500, 'timestamp': '2020-1-1 12:0:0.1 UTC'}],
            },
            {
                'user': 1,
                'id': 2,
                'history': [{'state': 500, 'timestamp': '2020-1-1 12:0:0.1 UTC'}],
            }
        ]

    def request_file_list_mock(*args, **kwargs):
        return True, [{'path': '/a/path/here', 'isDir': False, 'fileSize': 123, 'downloadId': 1}]

    def request_file_download_id_mock(*args, **kwargs):
        return True, 26

    def request_lookup_users_mock(*args, **kwargs):
        return '', [{
            'userId': 1,
            'username': 'buffy',
            'lastName': 'summers',
            'firstName': 'buffy'
        }]

    def test_bilby_job_query(self):
        """
        bilbyJob node query should return a single job for an autheniticated user."
        """
        job = BilbyJob.objects.create(user_id=self.user.id)
        global_id = to_global_id("BilbyJobNode", job.id)
        response = self.client.execute(
            f"""
            query {{
                bilbyJob(id:"{global_id}"){{
                    id
                    name
                    userId
                    description
                    jobId
                    private
                    lastUpdated
                    start {{
                        name
                        description
                        private
                    }}
                }}
            }}
            """
        )
        expected = {
            "bilbyJob": {
                "id": "QmlsYnlKb2JOb2RlOjE=",
                "name": "",
                "userId": 1,
                "description": None,
                "jobId": None,
                "private": False,
                "lastUpdated": job.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "start": {"name": "", "description": None, "private": False},
            }
        }
        self.assertDictEqual(
            expected, response.data, "bilbyJob query returned unexpected data."
        )

    def test_bilby_jobs_query(self):
        """
        bilbyJobs query should return a list of personal jobs for an autheniticated user.
        """
        BilbyJob.objects.create(user_id=self.user.id, name="Test1", job_id=2)
        BilbyJob.objects.create(
            user_id=self.user.id, name="Test2", job_id=1, description="A test job"
        )
        # This job shouldn't appear in the list because it belongs to another user.
        BilbyJob.objects.create(user_id=4, name="Test3", job_id=3)
        response = self.client.execute(
            """
            query {
                bilbyJobs{
                    edges {
                        node {
                            userId
                            name
                            description
                        }
                    }
                }
            }
            """
        )
        expected = {
            "bilbyJobs": {
                "edges": [
                    {"node": {"userId": 1, "name": "Test1", "description": None}},
                    {
                        "node": {
                            "userId": 1,
                            "name": "Test2",
                            "description": "A test job",
                        }
                    },
                ]
            }
        }
        self.assertDictEqual(
            response.data, expected, "bilbyJobs query returned unexpected data."
        )

    @mock.patch('bilby.schema.request_job_filter', side_effect=request_job_filter_mock)
    @mock.patch('bilby.schema.request_lookup_users', side_effect=request_lookup_users_mock)
    def test_public_bilby_jobs_query(self, request_job_filter, request_lookup_users):
        BilbyJob.objects.create(user_id=self.user.id, name="Test1", description="first job", job_id=2, private=False)
        BilbyJob.objects.create(
            user_id=self.user.id, name="Test2", job_id=1, description="A test job", private=False
        )
        # This job shouldn't appear in the list because it's private.
        BilbyJob.objects.create(user_id=4, name="Test3", job_id=3, private=True)
        response = self.client.execute(
           """
           query {
               publicBilbyJobs(search:"", timeRange:"all") {
                   edges {
                       node {
                           user
                           description
                           name
                           jobStatus
                           timestamp
                           id
                       }
                    }
                }
            }
            """
        )
        expected = {'publicBilbyJobs':
                    {'edges': [
                        {'node': {
                            'description': 'A test job',
                            'id': 'QmlsYnlKb2JOb2RlOjI=',
                            'name': 'Test2',
                            'jobStatus': 'Completed',
                            'timestamp': '2020-01-01 12:00:00 UTC',
                            'user': 'buffy summers'
                        }},
                        {'node': {
                            'description': 'first job',
                            'id': 'QmlsYnlKb2JOb2RlOjE=',
                            'name': 'Test1',
                            'jobStatus': 'Completed',
                            'timestamp': '2020-01-01 12:00:00 UTC',
                            'user': 'buffy summers'
                        }}
                    ]}}
        self.assertDictEqual(response.data, expected, "publicBilbyJobs query returned unexpected data.")

    @mock.patch('bilby.models.request_file_list', side_effect=request_file_list_mock)
    @mock.patch('bilby.models.request_file_download_id', side_effect=request_file_download_id_mock)
    def test_bilby_result_files(self, request_file_list, request_file_download_id_mock):
        """
        BilbyResultFiles query should return a file object.
        """
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Test1",
            description="first job",
            job_id=2,
            private=False
        )
        global_id = to_global_id("BilbyJobNode", job.id)
        response = self.client.execute(
            f"""
            query {{
                bilbyResultFiles (jobId: "{global_id}") {{
                    files {{
                        path
                        isDir
                        fileSize
                        downloadId
                    }}
                }}
            }}
            """
        )
        expected = {
            'bilbyResultFiles': {
                'files': [
                    {'path': '/a/path/here', 'isDir': False, 'fileSize': 123, 'downloadId': '26'}
                ]
            }
        }
        self.assertDictEqual(response.data, expected)
