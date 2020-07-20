from django.contrib.auth import get_user_model
from graphql_relay.node.node import to_global_id
from bilby.models import BilbyJob
from bilby.tests.testcases import BilbyTestCase

User = get_user_model()


class TestQueriesWithAuthenticatedUser(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy")
        self.client.authenticate(self.user)

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
                "lastUpdated": job.last_updated.strftime("%d/%m/%Y, %H:%M:%S"),
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
