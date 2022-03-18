from bilbyui.tests.testcases import BilbyTestCase
from graphql_relay.node.node import to_global_id
from django.contrib.auth import get_user_model
from bilbyui.models import BilbyJob

User = get_user_model()


class TestChangeJobDetails(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)

    def test_change_details_mutation(self):
        """
        Change details mutation should set a new jobname and or a new description if the authenticated user is the
        owner of the job.
        """
        job = BilbyJob.objects.create(
            user_id=self.user.id, name="Test1", description="first job", job_controller_id=2, private=False
        )

        global_job_id = to_global_id("BilbyJobNode", job.id)

        change_job_input = {
            "input": {
                "jobId": global_job_id,
                "name": "New_job_name",
                "description": "New job description"
            }
        }

        response = self.client.execute(
            """
            mutation UpdateBilbyJobMutation($input: UpdateBilbyJobMutationInput!) {
                updateBilbyJob(input: $input) {
                    result
                    jobId
                }
            }
            """,
            change_job_input
        )

        expected = {
            "updateBilbyJob": {
                "jobId": global_job_id,
                "result": "Job saved!"
            }
        }

        job.refresh_from_db()

        self.assertIsNone(response.errors, f"Mutation returned errors: {response.errors}")
        self.assertIsNotNone(response.data, "Mutation query returned nothing.")
        self.assertDictEqual(
            expected, response.data, "Change Job Details mutation returned the wrong jobid or threw an error."
        )
        self.assertEqual(job.description, "New job description")
        self.assertEqual(job.name, "New_job_name")
