from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.test_view_job import request_job_filter_mock
from bilbyui.tests.testcases import BilbyTestCase


class TestEditJobPrivacy(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="viewable_job",
            description="A job to view",
            job_controller_id=10001,
            private=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "viewable_job"}),
        )
        self.base_url = f"/htmx-preview/jobs/{self.job.id}/"

    def test_toggling_to_public(self):
        response = self.client.post(
            f"{self.base_url}edit/privacy/",
            {"private": "on"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "save-toast")
        self.job.refresh_from_db()
        self.assertFalse(self.job.private)
        self.assertContains(response, "checked")

    def test_toggling_to_private(self):
        self.job.private = False
        self.job.save()

        response = self.client.post(
            f"{self.base_url}edit/privacy/",
            {},
        )

        self.assertEqual(response.status_code, 200)
        self.job.refresh_from_db()
        self.assertTrue(self.job.private)

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_label_text_for_ligo_job(self, request_job_filter):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        ligo_job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="ligo_job",
            description="ligo",
            job_controller_id=10002,
            private=False,
            is_ligo_job=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "ligo_job"}),
        )

        response = self.client.get(f"/htmx-preview/jobs/{ligo_job.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Share with LVK collaborators")

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_label_text_for_non_ligo_job(self, request_job_filter):
        response = self.client.get(self.base_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Share publicly")

    def test_other_users_job_returns_404(self):
        other_job = BilbyJob.objects.create(
            user_id=self.user.id + 1,
            name="other_users_job",
            description="hidden",
            job_controller_id=10003,
            private=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "other_users_job"}),
        )
        other_base_url = f"/htmx-preview/jobs/{other_job.id}/"

        response = self.client.post(
            f"{other_base_url}edit/privacy/",
            {"private": "on"},
        )

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_redirected(self):
        self.deauthenticate()
        response = self.client.post(
            f"{self.base_url}edit/privacy/",
            {"private": "on"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"/sso/login/?next={self.base_url}edit/privacy/",
        )
