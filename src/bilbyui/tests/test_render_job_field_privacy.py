from django.test import RequestFactory

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _render_job_field_privacy


class TestRenderJobFieldPrivacy(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="privacy_job",
            description="A job to render privacy for",
            job_controller_id=10021,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "privacy_job"}),
        )
        self.factory = RequestFactory()

    def _render(self, user, status=200):
        request = self.factory.get("/")
        request.user = user
        response = _render_job_field_privacy(request, self.job, status=status)
        response.render()
        return response

    def test_owner_renders_modifiable_form(self):
        response = self._render(self.user)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context_data["modifiable"])
        self.assertContains(response, "privacy-form-")

    def test_non_owner_renders_read_only(self):
        other_user = self.create_user(id=2, name="other", primary_email="other@gmail.com")
        response = self._render(other_user)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context_data["modifiable"])
        self.assertContains(response, "Public Job")

    def test_custom_status_is_passed_through(self):
        response = self._render(self.user, status=400)

        self.assertEqual(response.status_code, 400)
