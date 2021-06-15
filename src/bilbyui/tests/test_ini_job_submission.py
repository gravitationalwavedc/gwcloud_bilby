from unittest.mock import patch

from django.contrib.auth import get_user_model

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import compare_ini_kvs, create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


class TestIniJobSubmission(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user, is_ligo=True)

        self.mutation = """
            mutation NewIniJobMutation($input: BilbyJobFromIniStringMutationInput!) {
              newBilbyJobFromIniString(input: $input) {
                result {
                  jobId
                }
              }
            }
        """

    @patch("bilbyui.views.submit_job")
    def test_ini_job_submission(self, mock_api_call):
        self.client.authenticate(self.user, is_ligo=True)

        mock_api_call.return_value = {'jobId': 4321}
        test_name = "Test Name"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string()

        test_input = {
                "input": {
                    "params": {
                        "details": {
                            "name": test_name,
                            "description": test_description,
                            "private": test_private
                        },
                        "iniString": {
                            "iniString": test_ini_string
                        }
                    }
                }
            }

        response = self.client.execute(self.mutation, test_input)

        expected = {
            'newBilbyJobFromIniString': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjE='
                }
            }
        }

        self.assertDictEqual(
            expected, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # And should create all k/v's with default values
        job = BilbyJob.objects.all().last()
        compare_ini_kvs(self, job, test_ini_string)

        self.assertEqual(job.name, test_name)
        self.assertEqual(job.description, test_description)
        self.assertEqual(job.private, test_private)
