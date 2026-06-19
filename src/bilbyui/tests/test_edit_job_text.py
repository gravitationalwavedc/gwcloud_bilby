from django.conf import settings

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestEditJobText(BilbyTestCase):
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
        self.base_url = f"/job-results/{self.job.id}/"

    def test_name_edit_renders_form(self):
        response = self.client.get(f"{self.base_url}field/name/?editing=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="name"')
        self.assertContains(response, "hx-post")
        self.assertContains(response, "save-button")

    def test_name_edit_saves_valid(self):
        response = self.client.post(
            f"{self.base_url}edit/name/",
            {"name": "updated_name"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "save-toast")
        self.assertContains(response, 'data-field="name"')
        self.job.refresh_from_db()
        self.assertEqual(self.job.name, "updated_name")

    def test_name_edit_rejects_too_short(self):
        response = self.client.post(
            f"{self.base_url}edit/name/",
            {"name": "ab"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "at least 5 characters", status_code=400)
        self.job.refresh_from_db()
        self.assertEqual(self.job.name, "viewable_job")

    def test_name_edit_rejects_invalid_chars(self):
        response = self.client.post(
            f"{self.base_url}edit/name/",
            {"name": "bad name"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "spaces or special characters", status_code=400)
        self.job.refresh_from_db()
        self.assertEqual(self.job.name, "viewable_job")

    def test_description_edit_renders_form(self):
        response = self.client.get(f"{self.base_url}field/description/?editing=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="description"')
        self.assertContains(response, "cancel-button")

    def test_description_edit_saves(self):
        response = self.client.post(
            f"{self.base_url}edit/description/",
            {"description": "Updated description"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "save-toast")
        self.job.refresh_from_db()
        self.assertEqual(self.job.description, "Updated description")

    def test_other_users_job_returns_404(self):
        other_job = BilbyJob.objects.create(
            user_id=self.user.id + 1,
            name="other_users_job",
            description="hidden",
            job_controller_id=10002,
            private=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "other_users_job"}),
        )
        other_base_url = f"/job-results/{other_job.id}/"

        response = self.client.post(
            f"{other_base_url}edit/name/",
            {"name": "stolen_name"},
        )

        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            f"{other_base_url}edit/description/",
            {"description": "stolen description"},
        )

        self.assertEqual(response.status_code, 404)

    def test_other_users_public_job_edit_form_returns_404(self):
        other_job = BilbyJob.objects.create(
            user_id=self.user.id + 1,
            name="public_other_job",
            description="public",
            job_controller_id=10003,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "public_other_job"}),
        )
        other_base_url = f"/job-results/{other_job.id}/"

        response = self.client.get(f"{other_base_url}field/name/?editing=1")

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_redirected(self):
        self.deauthenticate()
        response = self.client.post(
            f"{self.base_url}edit/name/",
            {"name": "new_name"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{settings.LOGIN_URL}?next={self.base_url}edit/name/",
        )
