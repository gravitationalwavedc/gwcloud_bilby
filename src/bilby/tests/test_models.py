from django.test import TestCase

from bilby.models import BilbyJob, Data
from bilby.variables import bilby_parameters


class TestModels(TestCase):
    def test_data_to_json(self):
        """
        Check that a Data object can be successfully converted to json
        """

        job = BilbyJob(user_id=1)
        job.save()

        data = Data(job=job, data_choice=bilby_parameters.SIMULATED)
        data.save()

        self.assertDictEqual(data.as_json(), {
            "id": data.id,
            "value": {
                "job": job.id,
                "choice": bilby_parameters.SIMULATED
            }
        })
