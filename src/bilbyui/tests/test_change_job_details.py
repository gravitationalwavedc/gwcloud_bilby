from bilbyui.tests.testcases import BilbyTestCase

class TestJobChangeJobDetails(BilbyTestCase):
    def setup(self):


    def test_change_details_mutation(self):
        """
        Change details mutation should set a new jobname and or a new description if the authenticated user is the 
        owner of the job.
        """
        change_job_input = {
            "input": {
                "jobId": "12uvinm12",
                "jobName": "New job name",
                "description": "New job description"
            }
        }

        response = self.client.execute(
            """
            mutation ChangeJobDetailsMutation($input: ChangeJobDetailsMutationInput!) {
                changeJobDetailsMutation(input: $input) {
                    result {
                        jobId
                    }
                }
            }
            """,
            change_job_input
        )

        expected = {
            'changeJobDetailsMutation': {
                'result': {
                    'jobId': '12uvinm12'
                }
            }
        }
        
        self.assertIsNotNone(response.data, "Mutation query returned nothing.")
        self.assertDictEqual(
            expected, response.data, "Change Job Details mutation returned the wrong jobid or threw an error."
        )
        
