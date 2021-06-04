from django.test import TestCase

from bilbyui.models import BilbyJob, Label
from bilbyui.views import update_bilby_job
from gw_bilby.jwt_tools import GWCloudUser


class TestBilbyJobModel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.job = BilbyJob.objects.create(
            user_id=1,
            name='Test Job',
            description='Test job description',
            private=False,
            ini_string='test-config=12345'
        )
        cls.job.save()

    def test_update_privacy(self):
        """
        Check that update_bilby_job view can update privacy of a job
        """
        self.assertEqual(self.job.private, False)

        user = GWCloudUser('bill')
        user.user_id = 1

        update_bilby_job(self.job.id, user, True, [])

        self.job.refresh_from_db()
        self.assertEqual(self.job.private, True)

    def test_update_labels(self):
        """
        Check that update_bilby_job view can update job labels
        """

        self.assertFalse(self.job.labels.exists())

        user = GWCloudUser('bill')
        user.user_id = 1

        update_bilby_job(self.job.id, user, False, ['Bad Run', 'Review Requested'])

        self.job.refresh_from_db()
        self.assertQuerysetEqual(
            self.job.labels.all(),
            list(map(repr, Label.objects.filter(name__in=['Bad Run', 'Review Requested']))),
            ordered=False
        )

    def test_as_json(self):
        params = self.job.as_json()

        self.assertEqual(params['name'], self.job.name)
        self.assertEqual(params['description'], self.job.description)
        self.assertEqual(params['ini_string'], self.job.ini_string)
