from django.conf import settings

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestEventIdModal(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="viewable_job",
            description="A job to view",
            job_controller_id=10001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "viewable_job"}),
        )
        self.modal_url = f"/job-results/{self.job.id}/event-id-modal/"

    def test_modal_renders_job(self):
        response = self.client.get(self.modal_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Set Event ID")
        self.assertContains(response, f"event-id-modal-{self.job.id}")

    def test_modal_nonexistent_job_returns_404(self):
        response = self.client.get("/job-results/999999/event-id-modal/")

        self.assertEqual(response.status_code, 404)

    def test_modal_other_users_job_returns_404(self):
        other_user = self.create_user(id=self.user.id + 1, name="other user", primary_email="other@gmail.com")
        other_job = BilbyJob.objects.create(
            user_id=other_user.id,
            name="other_users_job",
            description="hidden",
            job_controller_id=10002,
            private=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "other_users_job"}),
        )

        response = self.client.get(f"/job-results/{other_job.id}/event-id-modal/")

        self.assertEqual(response.status_code, 404)

    def test_modal_unauthenticated_redirected(self):
        self.deauthenticate()
        response = self.client.get(self.modal_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{settings.LOGIN_URL}?next={self.modal_url}",
        )
