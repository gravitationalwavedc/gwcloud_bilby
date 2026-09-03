from types import SimpleNamespace

from django.test import RequestFactory

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _render_job_field_event_id


class TestRenderJobFieldEventId(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = self.create_user(id=7)
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="viewable_job",
            description="A job to view",
            job_controller_id=10001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "viewable_job"}),
        )

    def test_default_modifiable_for_owner(self):
        request = self.factory.get("/")
        request.user = self.user

        response = _render_job_field_event_id(request, self.job)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.context_data["modifiable"], True)
        self.assertEqual(response.context_data["error"], "")
        self.assertEqual(response.context_data["job"], self.job)

    def test_default_not_modifiable_for_non_owner(self):
        request = self.factory.get("/")
        request.user = SimpleNamespace(id=self.user.id + 1)

        response = _render_job_field_event_id(request, self.job)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.context_data["modifiable"], False)

    def test_explicit_modifiable_override(self):
        request = self.factory.get("/")
        request.user = SimpleNamespace(id=self.user.id + 1)

        response = _render_job_field_event_id(request, self.job, modifiable=True)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.context_data["modifiable"], True)

    def test_error_and_status_pass_through(self):
        request = self.factory.get("/")
        request.user = self.user

        response = _render_job_field_event_id(
            request,
            self.job,
            error="Event ID 'GW999999_999999' not found.",
            status=400,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.context_data["error"], "Event ID 'GW999999_999999' not found.")
