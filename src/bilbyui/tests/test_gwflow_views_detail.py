from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.urls import reverse

from bilbyui.models import BilbyJob, EventID, GWFlowFile, GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase


def _create_job(user, sname="S230601ag", **kwargs):
    defaults = {
        "sname": sname,
        "user": user,
        "libraries": ["cbc-workflow-o4a"],
        "schema_version": "v2",
    }
    defaults.update(kwargs)
    return GWFlowJob.objects.create(**defaults)


class TestGWFlowJobDetailView(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.non_ligo_user = self.create_user(id=11)
        self.authenticate(user=self.ligo_user)

    def test_chrome_renders_sname_badges_and_tabs(self):
        event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=12345678.1234,
        )
        job = _create_job(
            self.ligo_user,
            libraries=["lib-a", "lib-b"],
            schema_version="v2",
            is_pruned=True,
            current_history_id="abcdef123456",
            current_history_timestamp="2026-08-10 12:34:56+00:00",
            event_id=event_id,
        )

        response = self.client.get(reverse("bilbyui:gwflow_job_detail", args=[job.sname]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, job.sname)
        self.assertContains(response, "lib-a")
        self.assertContains(response, "lib-b")
        self.assertContains(response, "v2")
        self.assertContains(response, "pruned")
        self.assertContains(response, "abcdef12")
        self.assertContains(response, "2026-08-10 12:34:56 UTC")
        self.assertContains(response, "Metadata")
        self.assertContains(response, "Analyses &amp; Files")
        self.assertContains(response, "History")
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_metadata", args=[job.sname])}"',
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_files", args=[job.sname])}"',
        )

    def test_chrome_renders_event_id_values(self):
        event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=12345678.1234,
        )
        job = _create_job(self.ligo_user, event_id=event_id)

        response = self.client.get(reverse("bilbyui:gwflow_job_detail", args=[job.sname]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GW123456_123456")
        self.assertContains(response, "S123456a")
        self.assertContains(response, "GW123456")

    def test_full_page_not_fragment(self):
        job = _create_job(self.ligo_user)
        GWFlowFile.objects.create(
            job=job,
            analysis_uid="analysis-1",
            path="data/a.txt",
            file_name="a.txt",
            uploaded=True,
        )

        response = self.client.get(reverse("bilbyui:gwflow_job_detail", args=[job.sname]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<!doctype html>")
        self.assertNotContains(response, "Superevent-level")
        self.assertNotContains(response, "a.txt")


class TestGWFlowJobFilesPartial(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = _create_job(self.ligo_user)
        self.url = reverse("bilbyui:gwflow_job_files", args=[self.job.sname])

    def test_files_grouped_by_analysis_uid(self):
        GWFlowFile.objects.create(
            job=self.job,
            analysis_uid="",
            path="data/super.txt",
            file_name="super.txt",
            file_size=1024,
            uploaded=True,
        )
        GWFlowFile.objects.create(
            job=self.job,
            analysis_uid="analysis-1",
            path="data/a.txt",
            file_name="a.txt",
            file_size=2048,
            uploaded=True,
        )
        GWFlowFile.objects.create(
            job=self.job,
            analysis_uid="analysis-1",
            path="data/b.txt",
            file_name="b.txt",
            file_size=None,
            uploaded=False,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Superevent-level")
        self.assertContains(response, "analysis-1")
        self.assertContains(response, "✓ mirrored")
        self.assertContains(response, "pending")
        self.assertContains(response, "1.0")
        self.assertContains(response, "2.0")
        self.assertNotContains(response, "<!doctype html>")

    def test_download_link_only_for_uploaded_files(self):
        uploaded = GWFlowFile.objects.create(
            job=self.job,
            analysis_uid="analysis-1",
            path="data/a.txt",
            file_name="a.txt",
            uploaded=True,
        )
        pending = GWFlowFile.objects.create(
            job=self.job,
            analysis_uid="analysis-1",
            path="data/b.txt",
            file_name="b.txt",
            uploaded=False,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"/file_download/?fileId={uploaded.download_token}")
        self.assertNotContains(response, f"/file_download/?fileId={pending.download_token}")
        self.assertContains(response, "pending")

    def test_linked_bilby_jobs_listed(self):
        child = BilbyJob.objects.create(
            user=self.ligo_user,
            name="bilby-child",
            gwflow_job=self.job,
            gwflow_analysis_uid="analysis-1",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("bilbyui:view_job", args=[child.id])}"')
        self.assertContains(response, "bilby-child")
        self.assertContains(response, "analysis-1")

    def test_no_linked_bilby_jobs_note(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No linked bilby jobs.")


class TestGWFlowJobMetadataPartial(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = _create_job(self.ligo_user)
        self.url = reverse("bilbyui:gwflow_job_metadata", args=[self.job.sname])

    @mock.patch(
        "bilbyui.views.get_superevent",
        return_value=(
            {
                "sname": "S230601ag",
                "schema_version": "3",
                "gracedb": {"events": [{"uid": "E1", "pipeline": "gstlal"}]},
            },
            "live",
        ),
    )
    def test_live_payload_rendered_without_stale_note(self, mock_get_superevent):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        mock_get_superevent.assert_called_once_with(self.job.sname)
        self.assertContains(response, "v3")
        self.assertContains(response, "E1")
        self.assertContains(response, "gstlal")
        self.assertNotContains(response, "Showing cached copy")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch("bilbyui.views.get_superevent", return_value=({"sname": "S230601ag"}, "stale"))
    def test_stale_payload_shows_cached_note(self, mock_get_superevent):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Showing cached copy")

    @mock.patch("bilbyui.views.get_superevent", return_value=(None, "down"))
    def test_down_renders_portal_error_with_retry(self, mock_get_superevent):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The metadata service is currently unavailable.")
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_metadata", args=[self.job.sname])}"',
        )
        self.assertContains(response, 'hx-target="#metadata-pane"')
        self.assertContains(response, "Retry")
        self.assertNotContains(response, "<!doctype html>")


class TestGWFlowJobVisibility(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.non_ligo_user = self.create_user(id=11)
        self.ligo_job = _create_job(self.ligo_user, sname="S230601ag", ligo_only=True)
        self.public_job = _create_job(self.ligo_user, sname="S230602ag", ligo_only=False)
        self.authenticate(user=self.ligo_user)

    def _routes(self, sname):
        return [
            reverse("bilbyui:gwflow_job_detail", args=[sname]),
            reverse("bilbyui:gwflow_job_files", args=[sname]),
            reverse("bilbyui:gwflow_job_metadata", args=[sname]),
        ]

    def test_anonymous_404_on_all_routes(self):
        self.deauthenticate()
        for url in self._routes(self.ligo_job.sname):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_non_ligo_user_404_on_all_routes(self):
        self.authenticate(user=self.non_ligo_user)
        for url in self._routes(self.ligo_job.sname):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_ligo_user_200_on_all_routes(self):
        with mock.patch("bilbyui.views.get_superevent", return_value=({}, "live")):
            for url in self._routes(self.ligo_job.sname):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_non_ligo_only_job_visible_to_non_ligo_user(self):
        self.authenticate(user=self.non_ligo_user)
        for url in self._routes(self.public_job.sname):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_missing_job_404(self):
        self.authenticate(user=self.ligo_user)
        response = self.client.get(reverse("bilbyui:gwflow_job_detail", args=["S999999zz"]))

        self.assertEqual(response.status_code, 404)
