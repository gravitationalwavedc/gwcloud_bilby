from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS

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
        self.base_url = f"/htmx-preview/jobs/{self.job.id}/"

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

    def test_other_users_job_returns_404(self):
        other_job = BilbyJob.objects.create(
            user_id=self.user.id + 1,
            name="other_users_job",
            description="hidden",
            job_controller_id=10002,
            private=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "other_users_job"}),
        )
        other_base_url = f"/htmx-preview/jobs/{other_job.id}/"

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
            f"/sso/login/?next={self.base_url}edit/labels/",
        )
