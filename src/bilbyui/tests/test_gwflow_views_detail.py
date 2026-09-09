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

    def test_base_url_redirects_to_metadata(self):
        job = _create_job(self.ligo_user)

        response = self.client.get(reverse("bilbyui:gwflow_job_detail", args=[job.sname]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("bilbyui:gwflow_job_metadata", args=[job.sname]),
        )

    @mock.patch("bilbyui.views.get_superevent", return_value=({}, "live"))
    def test_chrome_renders_context_strip_and_section_nav(self, mock_get_superevent):
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

        response = self.client.get(reverse("bilbyui:gwflow_job_metadata", args=[job.sname]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, job.sname)
        self.assertContains(response, "lib-a")
        self.assertContains(response, "lib-b")
        self.assertContains(response, "v2")
        self.assertContains(response, "pruned")
        self.assertContains(response, "abcdef12")
        self.assertContains(response, "2026-08-10 12:34 UTC")
        self.assertContains(response, "Metadata")
        self.assertContains(response, "Files")
        self.assertContains(response, "History")
        self.assertEqual(response.content.decode().count('aria-current="page"'), 1)
        self.assertNotContains(response, 'role="tab"')
        self.assertNotContains(response, 'href="#"')
        self.assertContains(
            response,
            f'href="{reverse("bilbyui:gwflow_job_metadata", args=[job.sname])}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("bilbyui:gwflow_job_files", args=[job.sname])}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("bilbyui:gwflow_job_history", args=[job.sname])}"',
        )

    @mock.patch("bilbyui.views.get_superevent", return_value=({}, "live"))
    def test_chrome_renders_event_id_values(self, mock_get_superevent):
        event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=12345678.1234,
        )
        job = _create_job(self.ligo_user, event_id=event_id)

        response = self.client.get(reverse("bilbyui:gwflow_job_metadata", args=[job.sname]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GW123456_123456")
        self.assertContains(response, "S123456a")
        self.assertContains(response, "GW123456")

    @mock.patch("bilbyui.views.get_superevent", return_value=({}, "live"))
    def test_full_page_not_fragment(self, mock_get_superevent):
        job = _create_job(self.ligo_user)
        GWFlowFile.objects.create(
            job=job,
            analysis_uid="analysis-1",
            path="data/a.txt",
            file_name="a.txt",
            uploaded=True,
        )

        response = self.client.get(reverse("bilbyui:gwflow_job_metadata", args=[job.sname]))

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

    def _get_fragment(self, url=None):
        return self.client.get(url or self.url, HTTP_HX_REQUEST="true")

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

        response = self._get_fragment()

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

        response = self._get_fragment()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("bilbyui:gwflow_file_download", args=[uploaded.download_token]),
        )
        self.assertNotContains(
            response,
            reverse("bilbyui:gwflow_file_download", args=[pending.download_token]),
        )
        self.assertContains(response, "pending")

    def test_linked_bilby_jobs_listed(self):
        child = BilbyJob.objects.create(
            user=self.ligo_user,
            name="bilby-child",
            gwflow_job=self.job,
            gwflow_analysis_uid="analysis-1",
        )
        GWFlowFile.objects.create(
            job=self.job,
            analysis_uid="analysis-1",
            path="data/a.txt",
            file_name="a.txt",
            uploaded=True,
        )

        response = self._get_fragment()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("bilbyui:view_job", args=[child.id])}"')
        self.assertContains(response, "bilby-child")
        self.assertContains(response, "analysis-1")

    def test_no_linked_job_link_when_absent(self):
        response = self._get_fragment()

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Linked Bilby job")


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
                "schema_version": "v3",
                "gracedb": {"events": [{"uid": "E1", "pipeline": "gstlal"}]},
            },
            "live",
        ),
    )
    def test_live_payload_rendered_without_stale_note(self, mock_get_superevent):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        mock_get_superevent.assert_called_once_with(self.job.sname)
        self.assertContains(response, "E1")
        self.assertContains(response, "gstlal")
        self.assertNotContains(response, "Showing cached copy")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch("bilbyui.views.get_superevent", return_value=({"sname": "S230601ag"}, "stale"))
    def test_stale_payload_shows_context_strip_notice(self, mock_get_superevent):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The cached copy of the current version is shown.")
        self.assertContains(response, "Refresh")
        self.assertContains(response, 'class="async-notice"')

    @mock.patch("bilbyui.views.get_superevent", return_value=(None, "down"))
    def test_down_renders_error_state_with_retry(self, mock_get_superevent):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "async-error")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, '<span class="sr-only">Error:</span>')
        self.assertContains(
            response,
            "Couldn't load the metadata because the service is temporarily unavailable.",
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_metadata", args=[self.job.sname])}"',
        )
        self.assertContains(response, 'hx-target="#detail-pane"')
        self.assertContains(response, "Retry")
        self.assertNotContains(response, "<!doctype html>")
        self.assertEqual(response.content.decode().count('role="alert"'), 1)


class TestGWFlowSectionRoutes(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.non_ligo_user = self.create_user(id=11)
        self.authenticate(user=self.ligo_user)
        self.job = _create_job(self.ligo_user)

    def _section_url(self, section):
        return reverse(f"bilbyui:gwflow_job_{section}", args=[self.job.sname])

    def _mock_section(self, section):
        if section == "history":
            return mock.patch("bilbyui.views.get_versions", return_value=([], "live"))
        return mock.patch("bilbyui.views.get_superevent", return_value=({}, "live"))

    def test_each_section_renders_full_page_without_js(self):
        for section in ("metadata", "files", "history"):
            with self._mock_section(section):
                response = self.client.get(self._section_url(section))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "<!doctype html>")
            self.assertContains(response, 'aria-current="page"')
            self.assertEqual(response.content.decode().count('aria-current="page"'), 1)

    def test_each_section_returns_fragment_with_hx_request(self):
        for section in ("metadata", "files", "history"):
            with self._mock_section(section):
                response = self.client.get(self._section_url(section), HTTP_HX_REQUEST="true")
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "<!doctype html>")
            self.assertNotContains(response, 'aria-current="page"')

    def test_invalid_section_returns_404(self):
        response = self.client.get(f"/gwflow/{self.job.sname}/bogus/")
        self.assertEqual(response.status_code, 404)

    def test_no_tab_role_or_placeholder_href_remnants(self):
        with mock.patch("bilbyui.views.get_superevent", return_value=({}, "live")):
            response = self.client.get(self._section_url("metadata"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'role="tab"')
        self.assertNotContains(response, 'role="tablist"')
        self.assertNotContains(response, "aria-selected")
        self.assertNotContains(response, 'href="#"')

    def test_provenance_triple_appears_once_in_context_strip(self):
        job = _create_job(
            self.ligo_user,
            sname="S230603ag",
            schema_version="v2",
            current_history_id="abcdef1234567890abcdef1234567890abcdef12",
            current_history_timestamp="2026-08-10 12:34:56+00:00",
        )
        with mock.patch(
            "bilbyui.views.get_superevent",
            return_value=(
                {
                    "sname": "S230603ag",
                    "schema_version": "v3",
                    "gracedb": {"events": [{"uid": "E1", "pipeline": "gstlal"}]},
                },
                "live",
            ),
        ):
            response = self.client.get(reverse("bilbyui:gwflow_job_metadata", args=[job.sname]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Design rule G: identify the current-context component (the context
        # strip's provenance line) and assert exactly one triple inside it,
        # rather than counting strings across the whole page.
        strip_start = content.index('class="context-strip')
        region_end = content.index('id="detail-region"')
        strip_region = content[strip_start:region_end]
        provenance_start = strip_region.index('class="context-provenance"')
        provenance_region = strip_region[provenance_start:]

        # Exactly one current-provenance triple (short SHA, recorded timestamp,
        # schema version) inside the current-context component.
        self.assertEqual(provenance_region.count("abcdef12"), 1)
        self.assertEqual(provenance_region.count("2026-08-10 12:34 UTC"), 1)
        self.assertEqual(provenance_region.count("v2"), 1)

        # The pane (metadata cards) omits the current provenance entirely.
        pane_region = content[content.index('id="detail-pane"') :]
        self.assertNotIn("abcdef12", pane_region)
        self.assertNotIn("2026-08-10 12:34 UTC", pane_region)
        self.assertNotIn("v2", pane_region)


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

    def _section_routes(self, sname):
        return [
            reverse("bilbyui:gwflow_job_files", args=[sname]),
            reverse("bilbyui:gwflow_job_metadata", args=[sname]),
            reverse("bilbyui:gwflow_job_history", args=[sname]),
        ]

    def test_anonymous_404_on_all_routes(self):
        self.deauthenticate()
        for url in self._section_routes(self.ligo_job.sname) + [
            reverse("bilbyui:gwflow_job_detail", args=[self.ligo_job.sname])
        ]:
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_non_ligo_user_404_on_all_routes(self):
        self.authenticate(user=self.non_ligo_user)
        for url in self._section_routes(self.ligo_job.sname) + [
            reverse("bilbyui:gwflow_job_detail", args=[self.ligo_job.sname])
        ]:
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_non_ligo_user_404_on_hx_requests(self):
        self.authenticate(user=self.non_ligo_user)
        for url in self._section_routes(self.ligo_job.sname):
            self.assertEqual(self.client.get(url, HTTP_HX_REQUEST="true").status_code, 404)

    def test_ligo_user_200_on_all_routes(self):
        with mock.patch("bilbyui.views.get_superevent", return_value=({}, "live")):
            with mock.patch("bilbyui.views.get_versions", return_value=([], "live")):
                for url in self._section_routes(self.ligo_job.sname):
                    self.assertEqual(self.client.get(url).status_code, 200)
        # Base URL redirects for an authorised user.
        self.assertEqual(
            self.client.get(reverse("bilbyui:gwflow_job_detail", args=[self.ligo_job.sname])).status_code,
            302,
        )

    def test_non_ligo_only_job_visible_to_non_ligo_user(self):
        self.authenticate(user=self.non_ligo_user)
        with mock.patch("bilbyui.views.get_superevent", return_value=({}, "live")):
            with mock.patch("bilbyui.views.get_versions", return_value=([], "live")):
                for url in self._section_routes(self.public_job.sname):
                    self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("bilbyui:gwflow_job_detail", args=[self.public_job.sname])).status_code,
            302,
        )

    def test_missing_job_404(self):
        self.authenticate(user=self.ligo_user)
        response = self.client.get(reverse("bilbyui:gwflow_job_detail", args=["S999999zz"]))

        self.assertEqual(response.status_code, 404)
