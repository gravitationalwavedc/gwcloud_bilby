from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.conf import settings
from django.test import override_settings

from bilbyui.models import BilbyJob, Label
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.test_view_job import request_job_filter_mock
from bilbyui.tests.testcases import BilbyTestCase


class TestEditJobLabels(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.pe_label = Label.objects.create(
            name="PE",
            description="Production estimate label",
            protected=False,
        )
        self.official_label, _ = Label.objects.get_or_create(
            name="Official",
            defaults={
                "description": "Official GWCloud label",
                "protected": True,
            },
        )
        if not self.official_label.protected:
            self.official_label.protected = True
            self.official_label.save()
        self.other_label = Label.objects.create(
            name="TestAssigned",
            description="Assigned test label",
            protected=False,
        )
        self.unassigned_label = Label.objects.create(
            name="TestUnassigned",
            description="Unassigned test label",
            protected=False,
        )
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="viewable_job",
            description="A job to view",
            job_controller_id=10001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "viewable_job"}),
        )
        self.job.labels.add(self.other_label)
        self.base_url = f"/job-results/{self.job.id}/"

    def test_add_label(self):
        response = self.client.post(
            f"{self.base_url}edit/labels/",
            {
                "labels": [self.other_label.name],
                "add": self.pe_label.name,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "save-toast")
        self.assertContains(response, self.pe_label.name)
        self.assertContains(response, "badge-secondary")
        self.job.refresh_from_db()
        self.assertIn(self.pe_label, self.job.labels.all())

    def test_remove_label(self):
        self.job.labels.add(self.pe_label)

        response = self.client.post(
            f"{self.base_url}edit/labels/",
            {
                "labels": [self.other_label.name, self.pe_label.name],
                "remove": self.pe_label.name,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "save-toast")
        self.assertNotContains(response, f'aria-label="Remove {self.pe_label.name}"')
        self.job.refresh_from_db()
        self.assertNotIn(self.pe_label, self.job.labels.all())

    def test_cannot_add_protected_label(self):
        response = self.client.post(
            f"{self.base_url}edit/labels/",
            {
                "labels": [self.other_label.name],
                "add": self.official_label.name,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "save-toast")
        self.job.refresh_from_db()
        self.assertNotIn(self.official_label, self.job.labels.all())

    def test_cannot_remove_protected_label(self):
        self.job.labels.add(self.official_label)

        response = self.client.post(
            f"{self.base_url}edit/labels/",
            {
                "labels": [self.other_label.name],
                "remove": self.official_label.name,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Protected labels cannot be removed.", status_code=400)
        self.job.refresh_from_db()
        self.assertIn(self.official_label, self.job.labels.all())

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_dropdown_only_shows_unassigned_labels(self, request_job_filter):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        self.job.labels.add(self.pe_label)

        response = self.client.get(self.base_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'name="add" value="{self.pe_label.name}"')
        self.assertNotContains(response, f'name="add" value="{self.official_label.name}"')
        self.assertContains(response, f'name="add" value="{self.unassigned_label.name}"')

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    @override_settings(
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        CSRF_TRUSTED_ORIGINS=["https://gwcloud.org.au"],
    )
    def test_add_label_accepts_csrf_header_from_cookie(self, request_job_filter):
        self.client = self.client_class(enforce_csrf_checks=True)
        self.authenticate()

        response = self.client.get(
            self.base_url,
            HTTP_X_FORWARDED_PROTO="https",
        )
        csrf_cookie = response.cookies["csrftoken"].value

        response = self.client.post(
            f"{self.base_url}edit/labels/",
            {
                "labels": [self.other_label.name],
                "add": self.pe_label.name,
            },
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_X_CSRFTOKEN=csrf_cookie,
            HTTP_HX_REQUEST="true",
            HTTP_REFERER=f"https://gwcloud.org.au/job-results/{self.job.id}/",
        )

        self.assertEqual(response.status_code, 200)
        self.job.refresh_from_db()
        self.assertIn(self.pe_label, self.job.labels.all())

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
            f"{other_base_url}edit/labels/",
            {"add": self.pe_label.name},
        )

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_redirected(self):
        self.deauthenticate()
        response = self.client.post(
            f"{self.base_url}edit/labels/",
            {"add": self.pe_label.name},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{settings.LOGIN_URL}?next={self.base_url}edit/labels/",
        )
