from bilbyui.tests.test_utils import silence_errors, create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from graphql_relay.node.node import to_global_id
from django.contrib.auth import get_user_model
from bilbyui.models import BilbyJob

User = get_user_model()


class TestChangeJobDetails(BilbyTestCase):
    def setUp(self):
        self.authenticate()

        self.mutation_string = """
            mutation UpdateBilbyJobMutation($input: UpdateBilbyJobMutationInput!) {
                updateBilbyJob(input: $input) {
                    result
                    jobId
                }
            }
        """

        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Test1",
            description="first job",
            job_controller_id=2,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

        self.global_job_id = to_global_id("BilbyJobNode", self.job.id)

    def test_change_details_mutation(self):
        """
        Change details mutation should set a new jobname and or a new description if the authenticated user is the
        owner of the job.
        """
        change_job_input = {
            "jobId": self.global_job_id,
            "name": "New_job_name",
            "description": "New job description",
        }

        response = self.query(self.mutation_string, input_data=change_job_input)

        expected = {
            "updateBilbyJob": {"jobId": self.global_job_id, "result": "Job saved!"}
        }

        self.job.refresh_from_db()

        self.assertIsNone(
            response.errors, f"Mutation returned errors: {response.errors}"
        )
        self.assertIsNotNone(response.data, "Mutation query returned nothing.")
        self.assertDictEqual(
            expected,
            response.data,
            "Change Job Details mutation returned the wrong jobid or threw an error.",
        )
        self.assertEqual(self.job.description, "New job description")
        self.assertEqual(self.job.name, "New_job_name")

    @silence_errors
    def test_change_job_name_symbols(self):
        """
        Try to update a bilby job with a name that contains symbols
        """
        change_job_input = {
            "jobId": self.global_job_id,
            "name": "Test_job$",
            "description": "New job description",
        }

        response = self.query(self.mutation_string, input_data=change_job_input)

        self.assertDictEqual({"updateBilbyJob": None}, response.data)
        self.assertEqual(
            response.errors[0]["message"],
            "Job name must not contain any spaces or special characters.",
        )

    @silence_errors
    def test_change_job_name_too_long(self):
        """
        Try to update a bilby job with a name that is too long
        """
        change_job_input = {
            "jobId": self.global_job_id,
            "name": "aa" * BilbyJob._meta.get_field("name").max_length,
            "description": "New job description",
        }

        response = self.query(self.mutation_string, input_data=change_job_input)

        self.assertDictEqual({"updateBilbyJob": None}, response.data)
        self.assertEqual(
            response.errors[0]["message"],
            "Job name must be less than 255 characters long.",
        )

    @silence_errors
    def test_change_job_name_too_short(self):
        """
        Try to update a bilby job with a name that is too short
        """
        change_job_input = {
            "jobId": self.global_job_id,
            "name": "a",
            "description": "New job description",
        }

        response = self.query(self.mutation_string, input_data=change_job_input)

        self.assertDictEqual({"updateBilbyJob": None}, response.data)
        self.assertEqual(
            response.errors[0]["message"],
            "Job name must be at least 5 characters long.",
        )
