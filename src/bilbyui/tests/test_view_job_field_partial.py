from django.test import override_settings

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestViewJobFieldPartial(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Field job",
            description="A job for field partials",
            job_controller_id=10011,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Field job"}),
        )

    def test_unknown_field_returns_404(self):
        response = self.client.get(f"/job-results/{self.job.id}/field/unknown/")

        self.assertEqual(response.status_code, 404)

    def test_editing_by_non_owner_returns_404(self):
        other_user = self.create_user(id=2, name="other", primary_email="other@gmail.com")
        BilbyJob.objects.create(
            user_id=other_user.id,
            name="Other field job",
            description="hidden",
            job_controller_id=10012,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Other field job"}),
        )

        self.authenticate(user=other_user)
        response = self.client.get(f"/job-results/{self.job.id}/field/name/?editing=1")

        self.assertEqual(response.status_code, 404)
