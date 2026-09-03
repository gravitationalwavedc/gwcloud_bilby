from types import SimpleNamespace

from django.test import RequestFactory

from bilbyui.models import BilbyJob, Label
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _render_job_field_labels


class TestRenderJobFieldLabels(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = self.create_user(id=7)
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="labels_job",
            description="A job to render labels for",
            job_controller_id=10031,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "labels_job"}),
        )
        self.available_label = Label.objects.create(
            name="GardenerAvailable",
            description="Should appear for modifiable jobs",
            protected=False,
        )

    def _request(self, user=None):
        request = self.factory.get("/")
        request.user = user or self.user
        return request

    def test_default_modifiable_for_owner(self):
        response = _render_job_field_labels(self._request(), self.job)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.context_data["modifiable"], True)
        self.assertEqual(response.context_data["error"], "")
        self.assertEqual(response.context_data["job"], self.job)
        self.assertIn(self.available_label, list(response.context_data["available_labels"]))

    def test_default_not_modifiable_for_non_owner(self):
        request = self._request(SimpleNamespace(id=self.user.id + 1))

        response = _render_job_field_labels(request, self.job)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.context_data["modifiable"], False)
        self.assertEqual(list(response.context_data["available_labels"]), [])

    def test_explicit_modifiable_false_returns_empty_available_labels(self):
        request = self._request()

        response = _render_job_field_labels(request, self.job, modifiable=False)

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.context_data["modifiable"], False)
        self.assertEqual(list(response.context_data["available_labels"]), [])

    def test_error_and_status_pass_through(self):
        response = _render_job_field_labels(
            self._request(),
            self.job,
            error="Something went wrong.",
            status=400,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.context_data["error"], "Something went wrong.")
