import re
from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.conf import settings
from django.test import override_settings

from bilbyui.models import BilbyJob, IniKeyValue
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
        self.page_url = f"/jobs/{self.job.id}/parameters/"

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

    def _set_classification(self, *, trigger_time, simulation):
        BilbyJob.objects.filter(pk=self.job.pk).update(trigger_time=trigger_time)
        self.job.trigger_time = trigger_time
        IniKeyValue.objects.filter(
            job=self.job,
            key="n_simulation",
            processed=False,
        ).delete()
        IniKeyValue.objects.create(
            job=self.job,
            key="n_simulation",
            value=simulation,
            index=0,
            processed=False,
        )

    def _privacy_responses(self):
        full_page = self.client.get(self.page_url)
        with mock.patch("bilbyui.views.update_job") as update_job:
            htmx = self.client.post(
                f"{self.base_url}edit/privacy/",
                {"private": "on"},
                HTTP_HX_REQUEST="true",
            )
        update_job.assert_called_once_with(self.job.id, self.user, private=False)
        return full_page, htmx

    def _assert_privacy_label(self, response, expected, unexpected):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, expected)
        self.assertNotContains(response, unexpected)
        self.assertContains(response, f'id="privacy-form-{self.job.id}"')
        self.assertContains(
            response,
            "hx-target=\"closest [data-field='privacy']\"",
        )
        self.assertContains(response, 'hx-swap="outerHTML"')
        self.assertContains(response, f'id="privacy-indicator-{self.job.id}"')
        self.assertContains(response, "Job privacy")

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    @override_settings(EMBARGO_START_TIME=100.0)
    def test_restricted_real_job_label_matches_full_page_and_htmx(self, request_job_filter):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        self._set_classification(trigger_time=100.0, simulation="0")

        for response in self._privacy_responses():
            self._assert_privacy_label(
                response,
                "Share with LVK collaborators",
                "Share publicly",
            )

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    @override_settings(EMBARGO_START_TIME=100.0)
    def test_public_real_job_label_matches_full_page_and_htmx(self, request_job_filter):
        self._set_classification(trigger_time=99.0, simulation="0")

        for response in self._privacy_responses():
            self._assert_privacy_label(
                response,
                "Share publicly",
                "Share with LVK collaborators",
            )

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    @override_settings(EMBARGO_START_TIME=100.0)
    def test_simulated_job_label_matches_full_page_and_htmx(self, request_job_filter):
        self._set_classification(trigger_time=100.0, simulation="+2")

        for response in self._privacy_responses():
            self._assert_privacy_label(
                response,
                "Share publicly",
                "Share with LVK collaborators",
            )

    def test_other_users_job_returns_404(self):
        other_user = self.create_user(id=2, name="other", primary_email="other@gmail.com")
        other_job = BilbyJob.objects.create(
            user_id=other_user.id,
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

        response = self.client.get(self.page_url)
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
            self.page_url,
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
        response = self.client.get(self.page_url)

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.content.decode(),
            rf'<form id="privacy-form-{self.job.id}"[^>]*hx-post="[^"]*edit/privacy/',
        )
