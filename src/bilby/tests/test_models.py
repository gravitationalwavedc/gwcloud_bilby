from django.test import TestCase

from bilby.models import BilbyJob, Data, Label
from bilby.variables import bilby_parameters
from bilby.views import update_bilby_job


class TestBilbyJobModel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.job = BilbyJob.objects.create(
            user_id=1,
            name='Test Job',
            description='Test job description',
            private=False
        )
        cls.job.save()

    def test_update_privacy(self):
        """
        Check that update_bilby_job view can update privacy of a job
        """
        self.assertEqual(self.job.private, False)

        update_bilby_job(self.job.id, 1, True, [])

        self.job.refresh_from_db()
        self.assertEqual(self.job.private, True)

    def test_update_labels(self):
        """
        Check that update_bilby_job view can update job labels
        """

        self.assertFalse(self.job.labels.exists())

        update_bilby_job(self.job.id, 1, False, ['Bad Run', 'Review Requested'])

        self.job.refresh_from_db()
        self.assertQuerysetEqual(
            self.job.labels.all(),
            list(map(repr, Label.objects.filter(name__in=['Bad Run', 'Review Requested']))),
            ordered=False
        )


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
