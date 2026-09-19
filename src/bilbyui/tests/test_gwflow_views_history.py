from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.http import Http404
from django.test import RequestFactory, override_settings
from django.urls import reverse

from bilbyui.models import GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _render_gwflow_history_section


def _create_job(user, sname="S230601ag", **kwargs):
    defaults = {
        "sname": sname,
        "user": user,
        "libraries": ["cbc-workflow-o4a"],
        "schema_version": "v2",
    }
    defaults.update(kwargs)
    return GWFlowJob.objects.create(**defaults)


class TestGWFlowDetailZeroHistoryRequests(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = _create_job(self.ligo_user)

    @mock.patch("bilbyui.views.get_versions")
    @mock.patch("bilbyui.views.get_version")
    @mock.patch("bilbyui.views.get_superevent", return_value=({}, "live"))
    def test_detail_page_makes_zero_history_portal_requests(
        self,
        mock_get_superevent,
        mock_get_version,
        mock_get_versions,
    ):
        # The base URL redirects to the metadata section; the metadata pane must
        # not trigger any history portal requests.
        response = self.client.get(
            reverse("bilbyui:gwflow_job_detail", args=[self.job.sname]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        mock_get_versions.assert_not_called()
        mock_get_version.assert_not_called()
        self.assertContains(
            response,
            f'href="{reverse("bilbyui:gwflow_job_history", args=[self.job.sname])}"',
        )
        self.assertNotContains(response, 'id="history-pane"')


class TestGWFlowJobHistoryPartial(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = _create_job(
            self.ligo_user,
            current_history_id="1111222233334444555566667777888899990000",
        )
        self.url = reverse("bilbyui:gwflow_job_history", args=[self.job.sname])
        self.get_version_patcher = mock.patch(
            "bilbyui.views.get_version",
            return_value=({"raw_payload": {}}, "live"),
        )
        self.get_version_patcher.start()
        self.addCleanup(self.get_version_patcher.stop)

    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=(
            [
                {
                    "commit_sha": "1111222233334444555566667777888899990000",
                    "commit_timestamp": "2026-08-10 12:00:00 UTC",
                    "schema_version": "v3",
                    "is_current": True,
                },
                {
                    "commit_sha": "aaaabbbbccccddddeeeeffff0000111122223333",
                    "commit_timestamp": "2026-08-09 10:00:00 UTC",
                    "schema_version": "v2",
                    "is_current": False,
                },
            ],
            "live",
        ),
    )
    def test_timeline_rendering_live_versions_with_current_marker(self, mock_get_versions):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        mock_get_versions.assert_called_once_with(self.job.sname)
        # Short SHAs
        self.assertContains(response, "11112222")
        self.assertContains(response, "aaaabbbb")
        # Timestamps
        self.assertContains(response, "2026-08-10 12:00:00 UTC")
        self.assertContains(response, "2026-08-09 10:00:00 UTC")
        # Schema version badges
        self.assertContains(response, "v3")
        self.assertContains(response, "v2")
        self.assertNotContains(response, "vv3")
        # Current badge
        self.assertContains(response, '<span class="badge badge-primary">Current</span>')
        # Canonical history links use query-backed selection and comparison.
        history_url = reverse("bilbyui:gwflow_job_history", args=[self.job.sname])
        self.assertContains(
            response,
            f'hx-get="{history_url}?version=1111222233334444555566667777888899990000&amp;compare=prev"',
        )
        self.assertContains(
            response,
            f'hx-get="{history_url}?version=aaaabbbbccccddddeeeeffff0000111122223333&amp;compare=prev"',
        )
        self.assertContains(response, 'hx-target="#gwflow-history-region"')
        self.assertContains(response, 'id="gwflow-history-version"')
        self.assertNotContains(response, "Showing cached copy")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=(
            [
                {
                    "commit_sha": "aaaabbbbccccddddeeeeffff0000111122223333",
                    "commit_timestamp": "2026-08-09 10:00:00 UTC",
                    "is_current": True,
                }
            ],
            "live",
        ),
    )
    def test_current_marker_fallback_to_is_current(self, mock_get_versions):
        # Job has no current_history_id set
        job = _create_job(self.ligo_user, sname="S230602ag", current_history_id="")
        url = reverse("bilbyui:gwflow_job_history", args=[job.sname])

        response = self.client.get(url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<span class="badge badge-primary">Current</span>')

    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=(
            [
                {
                    "commit_sha": "1111222233334444555566667777888899990000",
                    "commit_timestamp": "2026-08-10 12:00:00 UTC",
                }
            ],
            "stale",
        ),
    )
    def test_stale_timeline_shows_context_strip_notice(self, mock_get_versions):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The cached copy of the current version is shown.")
        self.assertContains(response, "Refresh")
        self.assertContains(response, 'class="async-notice"')

    @mock.patch("bilbyui.views.get_versions", return_value=(None, "down"))
    def test_down_renders_error_state_with_history_retry(self, mock_get_versions):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "async-error")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, '<span class="sr-only">Error:</span>')
        self.assertContains(
            response,
            "Couldn't load the history because the service is temporarily unavailable.",
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history", args=[self.job.sname])}"',
        )
        self.assertContains(response, 'hx-target="#detail-pane"')
        self.assertContains(response, "Retry")
        self.assertNotContains(response, "<!doctype html>")
        self.assertEqual(response.content.decode().count('role="alert"'), 1)

    @mock.patch("bilbyui.views.get_versions", return_value=([], "live"))
    def test_empty_versions_list(self, mock_get_versions):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No version history is available for this record.")
        self.assertContains(response, 'id="gwflow-history-version"')


class TestGWFlowJobHistoryVersionPartial(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = _create_job(self.ligo_user)
        self.sha = "1111222233334444555566667777888899990000"
        self.url = reverse("bilbyui:gwflow_job_history_version", args=[self.job.sname, self.sha])

    @mock.patch(
        "bilbyui.views.get_version",
        return_value=(
            {
                "schema_version": "v3",
                "commit_sha": "1111222233334444555566667777888899990000",
                "commit_timestamp": "2026-08-10 12:00:00 UTC",
                "gracedb": {"events": [{"uid": "E99", "pipeline": "pycbc"}]},
            },
            "live",
        ),
    )
    def test_live_version_renders_metadata_payload(self, mock_get_version):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        mock_get_version.assert_called_once_with(self.job.sname, self.sha)
        self.assertContains(response, "11112222")
        self.assertContains(response, "v3")
        self.assertContains(response, "E99")
        self.assertContains(response, "pycbc")
        self.assertContains(response, "Viewing version 11112222 (historical) — not the current record")
        self.assertNotContains(response, "vv3")
        self.assertNotContains(response, "Showing cached copy")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch(
        "bilbyui.views.get_version",
        return_value=(
            {
                "schema_version": "v3",
                "commit_sha": "1111222233334444555566667777888899990000",
                "gracedb": {"events": [{"uid": "E99", "pipeline": "pycbc"}]},
            },
            "stale",
        ),
    )
    def test_stale_version_renders_payload_without_cached_notice(self, mock_get_version):
        # The stale notice now lives in the full-page context strip; the version
        # fragment renders the payload without a duplicate cached-copy note.
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "E99")
        self.assertContains(response, "pycbc")
        self.assertContains(response, "Viewing version 11112222 (historical) — not the current record")
        self.assertNotContains(response, "Showing cached copy")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch("bilbyui.views.get_version", return_value=(None, "down"))
    def test_down_renders_error_state_with_version_retry(self, mock_get_version):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "async-error")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, '<span class="sr-only">Error:</span>')
        self.assertContains(
            response,
            "Couldn't load the version details because the service is temporarily unavailable.",
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history_version", args=[self.job.sname, self.sha])}"',
        )
        self.assertContains(response, 'hx-target="#gwflow-history-version"')
        self.assertContains(response, "Retry")
        self.assertNotContains(response, "<!doctype html>")
        self.assertEqual(response.content.decode().count('role="alert"'), 1)

    @mock.patch("bilbyui.views.get_version", return_value=(None, "live"))
    def test_missing_version_raises_404(self, mock_get_version):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)


class TestGWFlowHistoryVisibility(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.non_ligo_user = self.create_user(id=11)
        self.ligo_job = _create_job(self.ligo_user, sname="S230601ag", ligo_only=True)
        self.public_job = _create_job(self.ligo_user, sname="S230602ag", ligo_only=False)
        self.sha = "1111222233334444555566667777888899990000"

    def _history_routes(self, sname):
        return [
            reverse("bilbyui:gwflow_job_history", args=[sname]),
            reverse("bilbyui:gwflow_job_history_version", args=[sname, self.sha]),
        ]

    def test_anonymous_404_on_all_history_routes(self):
        self.deauthenticate()
        for url in self._history_routes(self.ligo_job.sname):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_non_ligo_user_404_on_all_history_routes(self):
        self.authenticate(user=self.non_ligo_user)
        for url in self._history_routes(self.ligo_job.sname):
            self.assertEqual(self.client.get(url).status_code, 404)

    @mock.patch("bilbyui.views.get_versions", return_value=([], "live"))
    @mock.patch("bilbyui.views.get_version", return_value=({}, "live"))
    def test_ligo_user_200_on_all_history_routes(self, mock_get_version, mock_get_versions):
        self.authenticate(user=self.ligo_user)
        for url in self._history_routes(self.ligo_job.sname):
            self.assertEqual(self.client.get(url).status_code, 200)

    @mock.patch("bilbyui.views.get_versions", return_value=([], "live"))
    @mock.patch("bilbyui.views.get_version", return_value=({}, "live"))
    def test_public_job_visible_to_non_ligo_user_on_history_routes(
        self,
        mock_get_version,
        mock_get_versions,
    ):
        self.authenticate(user=self.non_ligo_user)
        for url in self._history_routes(self.public_job.sname):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_missing_job_history_404(self):
        self.authenticate(user=self.ligo_user)
        for url in self._history_routes("S999999zz"):
            self.assertEqual(self.client.get(url).status_code, 404)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestRenderGWFlowHistorySection(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.sname = "S230601ag"
        self.request = self.factory.get(reverse("bilbyui:gwflow_job_history", args=[self.sname]))
        self.get_version_patcher = mock.patch(
            "bilbyui.views.get_version",
            return_value=({"raw_payload": {}}, "live"),
        )
        self.mock_get_version = self.get_version_patcher.start()
        self.addCleanup(self.get_version_patcher.stop)

    @mock.patch("bilbyui.views._get_gwflow_job_or_404", return_value=mock.Mock())
    @mock.patch("bilbyui.views.get_versions", return_value=(None, "down"))
    def test_down_state_renders_error_with_history_retry(self, mock_get_versions, mock_get_job):
        response, stale = _render_gwflow_history_section(self.request, self.sname)

        self.assertFalse(stale)
        response.render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template_name, "bilbyui/_async_state.html")
        self.assertContains(response, "async-error")
        self.assertContains(
            response,
            "Couldn't load the history because the service is temporarily unavailable.",
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history", args=[self.sname])}"',
        )
        self.assertContains(response, 'hx-target="#detail-pane"')

    @mock.patch("bilbyui.views._get_gwflow_job_or_404", return_value=mock.Mock())
    @mock.patch("bilbyui.views.get_versions", return_value=(None, "live"))
    def test_none_versions_renders_error_with_history_retry(self, mock_get_versions, mock_get_job):
        response, stale = _render_gwflow_history_section(self.request, self.sname)

        self.assertFalse(stale)
        response.render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template_name, "bilbyui/_async_state.html")
        self.assertContains(response, "async-error")
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history", args=[self.sname])}"',
        )

    @mock.patch("bilbyui.views._get_gwflow_job_or_404", return_value=mock.Mock())
    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=(
            [
                {
                    "commit_sha": "1111222233334444555566667777888899990000",
                    "commit_timestamp": "2026-08-10 12:00:00 UTC",
                    "is_current": True,
                }
            ],
            "live",
        ),
    )
    def test_live_render_returns_history_template(self, mock_get_versions, mock_get_job):
        response, stale = _render_gwflow_history_section(self.request, self.sname)

        self.assertFalse(stale)
        response.render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template_name, "bilbyui/_gwflow_history.html")
        self.assertContains(response, "11112222")
        self.assertNotContains(response, "async-error")

    @mock.patch("bilbyui.views._get_gwflow_job_or_404", return_value=mock.Mock())
    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=(
            [
                {
                    "commit_sha": "1111222233334444555566667777888899990000",
                    "commit_timestamp": "2026-08-10 12:00:00 UTC",
                    "is_current": True,
                }
            ],
            "stale",
        ),
    )
    def test_stale_render_returns_stale_flag(self, mock_get_versions, mock_get_job):
        response, stale = _render_gwflow_history_section(self.request, self.sname)

        self.assertTrue(stale)
        response.render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template_name, "bilbyui/_gwflow_history.html")

    @mock.patch("bilbyui.views._get_gwflow_job_or_404", return_value=mock.Mock())
    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=(
            [
                {
                    "commit_sha": "1111222233334444555566667777888899990000",
                    "commit_timestamp": "2026-08-09 10:00:00 UTC",
                    "schema_version": "v1",
                    "is_current": False,
                },
                {
                    "commit_sha": "aaaabbbbccccddddeeeeffff0000111122223333",
                    "commit_timestamp": "2026-08-10 10:00:00 UTC",
                    "schema_version": "v2",
                    "is_current": True,
                },
            ],
            "live",
        ),
    )
    def test_cross_schema_renders_side_by_side_summaries(self, mock_get_versions, mock_get_job):
        self.mock_get_version.side_effect = [
            ({"raw_payload": {"info": {"status": "ready"}}}, "live"),
            ({"raw_payload": {"info": {"status": "draft"}}}, "live"),
        ]
        response, _ = _render_gwflow_history_section(self.request, self.sname)
        response.render()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Diff may be incomplete across schema versions")
        # Both curated side-by-side summaries must render (not just SHAs).
        self.assertContains(response, "Baseline — version 11112222")
        self.assertContains(response, "Selected — version aaaabbbb")
        self.assertContains(response, "draft")
        self.assertContains(response, "ready")

    @mock.patch("bilbyui.views._get_gwflow_job_or_404", return_value=mock.Mock())
    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=(
            [
                {
                    "commit_sha": "1111222233334444555566667777888899990000",
                    "commit_timestamp": "2026-08-10 10:00:00 UTC",
                    "schema_version": "v1",
                    "is_current": True,
                }
            ],
            "live",
        ),
    )
    def test_selected_version_renders_completed_announcement(self, mock_get_versions, mock_get_job):
        self.mock_get_version.return_value = (
            {"raw_payload": {"info": {"status": "ready"}}},
            "live",
        )
        response, _ = _render_gwflow_history_section(self.request, self.sname)
        response.render()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="status"')
        self.assertContains(response, "Selected version 11112222")

    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    @mock.patch("bilbyui.views.get_versions")
    def test_unknown_version_deep_link_raises_404(self, mock_get_versions, mock_get_job):
        mock_get_job.return_value.current_history_id = "aaaabbbbccccddddeeeeffff0000111122223333"
        mock_get_versions.return_value = (self._metadata_versions(), "live")
        request = self.factory.get(
            reverse("bilbyui:gwflow_job_history", args=[self.sname]),
            {"version": "ffffffffffffffffffffffffffffffffffffffff"},
        )

        with self.assertRaises(Http404):
            _render_gwflow_history_section(request, self.sname)

    def _metadata_versions(self):
        return [
            {
                "commit_sha": "0000000000000000000000000000000000000000",
                "commit_timestamp": "2026-08-08 10:00:00 UTC",
                "schema_version": "v2",
                "is_current": False,
            },
            {
                "commit_sha": "1111222233334444555566667777888899990000",
                "commit_timestamp": "2026-08-09 10:00:00 UTC",
                "schema_version": "v2",
                "is_current": False,
            },
            {
                "commit_sha": "aaaabbbbccccddddeeeeffff0000111122223333",
                "commit_timestamp": "2026-08-10 10:00:00 UTC",
                "schema_version": "v2",
                "is_current": True,
            },
        ]

    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    @mock.patch("bilbyui.views.get_versions")
    def test_payload_less_rows_render_detail_payload_diff(self, mock_get_versions, mock_get_job):
        mock_get_job.return_value.current_history_id = "aaaabbbbccccddddeeeeffff0000111122223333"
        mock_get_versions.return_value = (self._metadata_versions()[1:], "live")
        self.mock_get_version.side_effect = [
            ({"raw_payload": {"info": {"status": "ready"}}}, "live"),
            ({"raw_payload": {"info": {"status": "draft"}}}, "live"),
        ]

        response, stale = _render_gwflow_history_section(self.request, self.sname)
        response.render()

        self.assertFalse(stale)
        self.assertEqual(response.context_data["diff_outcome"].status, "semantic")
        self.assertContains(response, "info.status")
        self.assertContains(response, "draft")
        self.assertContains(response, "ready")
        self.assertNotEqual(response.context_data["baseline_raw_json"], "null")
        self.assertNotEqual(response.context_data["selected_raw_json"], "null")

    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    @mock.patch("bilbyui.views.get_versions")
    def test_fetches_only_selected_and_resolved_baseline_details(self, mock_get_versions, mock_get_job):
        selected_sha = "aaaabbbbccccddddeeeeffff0000111122223333"
        baseline_sha = "1111222233334444555566667777888899990000"
        mock_get_job.return_value.current_history_id = selected_sha
        mock_get_versions.return_value = (self._metadata_versions(), "live")
        self.mock_get_version.side_effect = [
            ({"raw_payload": {"value": 2}}, "live"),
            ({"raw_payload": {"value": 1}}, "live"),
        ]

        _render_gwflow_history_section(self.request, self.sname)

        self.assertEqual(
            self.mock_get_version.call_args_list,
            [
                mock.call(self.sname, selected_sha),
                mock.call(self.sname, baseline_sha),
            ],
        )

    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    @mock.patch("bilbyui.views.get_versions")
    def test_compare_current_fetches_same_sha_once(self, mock_get_versions, mock_get_job):
        current_sha = "aaaabbbbccccddddeeeeffff0000111122223333"
        mock_get_job.return_value.current_history_id = current_sha
        mock_get_versions.return_value = (self._metadata_versions(), "live")
        request = self.factory.get(
            reverse("bilbyui:gwflow_job_history", args=[self.sname]),
            {"version": current_sha, "compare": "current"},
        )
        self.mock_get_version.return_value = (
            {"raw_payload": {"info": {"status": "ready"}}},
            "live",
        )

        response, _ = _render_gwflow_history_section(request, self.sname)
        response.render()

        self.mock_get_version.assert_called_once_with(self.sname, current_sha)
        self.assertEqual(
            response.context_data["baseline_raw_json"],
            response.context_data["selected_raw_json"],
        )

    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    @mock.patch("bilbyui.views.get_versions")
    def test_selected_detail_failure_renders_unavailable(self, mock_get_versions, mock_get_job):
        mock_get_job.return_value.current_history_id = "aaaabbbbccccddddeeeeffff0000111122223333"
        mock_get_versions.return_value = (self._metadata_versions()[1:], "live")
        self.mock_get_version.side_effect = [
            (None, "down"),
            ({"raw_payload": {"info": {"status": "draft"}}}, "live"),
        ]

        response, stale = _render_gwflow_history_section(self.request, self.sname)
        response.render()

        self.assertFalse(stale)
        self.assertEqual(response.context_data["diff_outcome"].status, "unavailable")
        self.assertContains(response, "A semantic comparison is unavailable")
        self.assertEqual(response.context_data["selected_raw_json"], "null")

    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    @mock.patch("bilbyui.views.get_versions")
    def test_baseline_detail_failure_renders_no_baseline(self, mock_get_versions, mock_get_job):
        mock_get_job.return_value.current_history_id = "aaaabbbbccccddddeeeeffff0000111122223333"
        mock_get_versions.return_value = (self._metadata_versions()[1:], "live")
        self.mock_get_version.side_effect = [
            ({"raw_payload": {"info": {"status": "ready"}}}, "live"),
            (None, "down"),
        ]

        response, stale = _render_gwflow_history_section(self.request, self.sname)
        response.render()

        self.assertFalse(stale)
        self.assertEqual(response.context_data["diff_outcome"].status, "no_baseline")
        self.assertContains(response, "No previous version is available for comparison")
        self.assertEqual(response.context_data["baseline_raw_json"], "null")
        self.assertNotEqual(response.context_data["selected_raw_json"], "null")

    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    @mock.patch("bilbyui.views.get_versions")
    def test_stale_required_detail_sets_stale_indicator(self, mock_get_versions, mock_get_job):
        mock_get_job.return_value.current_history_id = "aaaabbbbccccddddeeeeffff0000111122223333"
        mock_get_versions.return_value = (self._metadata_versions()[1:], "live")
        self.mock_get_version.side_effect = [
            ({"raw_payload": {"info": {"status": "ready"}}}, "stale"),
            ({"raw_payload": {"info": {"status": "draft"}}}, "live"),
        ]

        response, stale = _render_gwflow_history_section(self.request, self.sname)
        response.render()

        self.assertTrue(stale)
        self.assertTrue(response.context_data["stale"])
        self.assertContains(response, "Showing cached copy")
