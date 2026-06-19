import re
from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.conf import settings
from django.test import override_settings

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
        self.base_url = f"/job-results/{self.job.id}/"

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

        response = self.client.get(f"/job-results/{ligo_job.id}/")

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
        other_base_url = f"/job-results/{other_job.id}/"

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
            f"{settings.LOGIN_URL}?next={self.base_url}edit/privacy/",
        )

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_post_requires_csrf_token(self, request_job_filter):
        self.client = self.client_class(enforce_csrf_checks=True)
        self.authenticate()

        response = self.client.get(self.base_url)
        self.assertEqual(response.status_code, 200)

        csrf_token = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"',
            response.content.decode(),
        ).group(1)

        response = self.client.post(
            f"{self.base_url}edit/privacy/",
            {"private": "on"},
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            f"{self.base_url}edit/privacy/",
            {"private": "on", "csrfmiddlewaretoken": csrf_token},
        )
        self.assertEqual(response.status_code, 200)
        self.job.refresh_from_db()
        self.assertFalse(self.job.private)

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    @override_settings(
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        CSRF_TRUSTED_ORIGINS=["https://gwcloud.org.au"],
    )
    def test_post_accepts_csrf_header_from_cookie(self, request_job_filter):
        self.client = self.client_class(enforce_csrf_checks=True)
        self.authenticate()

        response = self.client.get(
            self.base_url,
            HTTP_X_FORWARDED_PROTO="https",
        )
        csrf_cookie = response.cookies["csrftoken"].value

        response = self.client.post(
            f"{self.base_url}edit/privacy/",
            {"private": "on"},
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_X_CSRFTOKEN=csrf_cookie,
            HTTP_HX_REQUEST="true",
            HTTP_REFERER="https://gwcloud.org.au/job-results/74/",
        )
        self.assertEqual(response.status_code, 200)
        self.job.refresh_from_db()
        self.assertFalse(self.job.private)

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_privacy_form_submits_via_form_element(self, request_job_filter):
        response = self.client.get(self.base_url)

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.content.decode(),
            rf'<form id="privacy-form-{self.job.id}"[^>]*hx-post="[^"]*edit/privacy/',
        )
