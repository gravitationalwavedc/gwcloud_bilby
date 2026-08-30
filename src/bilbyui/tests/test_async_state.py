import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import elasticsearch
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.template.loader import get_template
from django.urls import reverse

from bilbyui.models import BilbyJob, GWFlowJob
from bilbyui.services.gwflow import list_gwflow_jobs
from bilbyui.services.jobs import list_public_jobs, list_user_jobs
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase

APP_CSS = Path(__file__).resolve().parents[2] / "static" / "bilbyui" / "app.css"


def render_state(**kwargs):
    """Render the _async_state.html partial with the given context."""
    return get_template("bilbyui/_async_state.html").render(kwargs)


def _live_region_count(html):
    """Count live regions (role=status + role=alert) in rendered HTML."""
    return html.count('role="status"') + html.count('role="alert"')


def _gwflow_jobs_down_result():
    """list_gwflow_jobs result dict for a 'down' service state."""
    return {
        "jobs": {},
        "records": [],
        "has_next": False,
        "page": 1,
        "page_size": 20,
        "state": "down",
    }


def _public_jobs_down_result():
    """list_public_jobs result dict for a 'down' service state."""
    return {
        "jobs": {},
        "records": [],
        "job_controller_jobs": {},
        "has_next": False,
        "page": 1,
        "page_size": 20,
        "state": "down",
    }


def _user_jobs_down_result():
    """list_user_jobs result dict for a 'down' service state."""
    return {
        "jobs": [],
        "has_next": False,
        "page": 1,
        "page_size": 20,
        "state": "down",
    }


# ============================================================================
# task-2: partial render contract tests (issue #50)
# ============================================================================
class TestAsyncStatePartialRender(BilbyTestCase):
    """Contract tests for the _async_state.html dispatcher partial.

    Enumerates all seven states and asserts the announcement contract: exactly
    one live region per render (role="status" for loading/empty, role="alert"
    for stale/error), empty copy distinct from error wording, and
    Retry/Refresh re-requesting into the same target via retry_url/retry_target.
    """

    def test_idle_renders_nothing(self):
        html = render_state(state="idle")
        self.assertEqual(html.strip(), "")
        self.assertEqual(_live_region_count(html), 0)

    def test_content_renders_nothing(self):
        html = render_state(state="content")
        self.assertEqual(html.strip(), "")
        self.assertEqual(_live_region_count(html), 0)

    def test_loading_renders_skeleton_and_status(self):
        html = render_state(state="loading", thing="the metadata")
        self.assertIn("async-skeleton", html)
        self.assertIn("async-skeleton-row", html)
        self.assertIn("Loading the metadata…", html)
        self.assertIn('role="status"', html)
        self.assertNotIn('role="alert"', html)
        self.assertEqual(_live_region_count(html), 1)

    def test_loading_skeleton_is_hidden_from_at(self):
        html = render_state(state="loading")
        self.assertIn('aria-hidden="true"', html)

    def test_empty_renders_copy_and_hint_with_status(self):
        html = render_state(
            state="empty",
            thing="files",
            empty_hint="Upload your first file to get started.",
        )
        self.assertIn("No files yet.", html)
        self.assertIn("Upload your first file to get started.", html)
        self.assertIn('role="status"', html)
        self.assertNotIn('role="alert"', html)
        self.assertEqual(_live_region_count(html), 1)

    def test_empty_copy_differs_from_error_wording(self):
        empty_html = render_state(state="empty", thing="files")
        error_html = render_state(state="error", thing="files")
        self.assertNotEqual(empty_html, error_html)
        self.assertIn("No files yet.", empty_html)
        self.assertNotIn("No files yet.", error_html)
        self.assertNotIn("Couldn't load", empty_html)

    def test_stale_renders_notice_and_refresh_with_alert(self):
        html = render_state(
            state="stale",
            thing="the metadata",
            retry_url="/gwflow/S230601ag/metadata/",
            retry_target="#metadata-pane",
        )
        self.assertIn("async-notice", html)
        self.assertIn("The cached copy of the metadata is shown.", html)
        self.assertIn("bi-exclamation-triangle", html)
        self.assertIn("Refresh", html)
        self.assertIn('role="alert"', html)
        self.assertNotIn('role="status"', html)
        self.assertEqual(_live_region_count(html), 1)

    def test_stale_refresh_reuses_retry_url_and_target(self):
        html = render_state(
            state="stale",
            retry_url="/gwflow/S230601ag/history/",
            retry_target="#history-pane",
        )
        self.assertIn('hx-get="/gwflow/S230601ag/history/"', html)
        self.assertIn('hx-target="#history-pane"', html)
        self.assertIn('hx-swap="innerHTML"', html)

    def test_error_renders_hidden_prefix_copy_and_retry_with_alert(self):
        html = render_state(
            state="error",
            thing="the metadata",
            reason="the service is temporarily unavailable",
            retry_url="/gwflow/S230601ag/metadata/",
            retry_target="#metadata-pane",
        )
        self.assertIn("async-error", html)
        self.assertIn('<span class="sr-only">Error:</span>', html)
        self.assertIn(
            "Couldn't load the metadata because the service is temporarily unavailable.",
            html,
        )
        self.assertIn("Retry", html)
        self.assertIn('role="alert"', html)
        self.assertNotIn('role="status"', html)
        self.assertEqual(_live_region_count(html), 1)

    def test_error_retry_reuses_retry_url_and_target(self):
        html = render_state(
            state="error",
            retry_url="/gwflow/S230601ag/version/abc/",
            retry_target="#gwflow-history-version",
        )
        self.assertIn('hx-get="/gwflow/S230601ag/version/abc/"', html)
        self.assertIn('hx-target="#gwflow-history-version"', html)
        self.assertIn('hx-swap="innerHTML"', html)

    def test_error_uses_default_reason_when_omitted(self):
        html = render_state(state="error", thing="the history")
        self.assertIn("Couldn't load the history because the service is temporarily unavailable.", html)

    def test_thing_defaults_to_this(self):
        loading_html = render_state(state="loading")
        self.assertIn("Loading this…", loading_html)
        empty_html = render_state(state="empty")
        self.assertIn("No this yet.", empty_html)

    def test_region_label_used_as_aria_label(self):
        html = render_state(state="error", region_label="Metadata", thing="the metadata")
        self.assertIn('aria-label="Metadata"', html)

    def test_no_retry_button_without_retry_url(self):
        error_html = render_state(state="error")
        self.assertNotIn("Retry", error_html)
        stale_html = render_state(state="stale")
        self.assertNotIn("Refresh", stale_html)

    def test_no_action_with_retry_url_but_no_target(self):
        """Same-target contract: an action renders only when BOTH retry_url and
        retry_target are supplied — URL-only input must not render a control
        whose HTMX swap would default to the button itself."""
        error_html = render_state(state="error", retry_url="/some/url/")
        self.assertNotIn("Retry", error_html)
        self.assertNotIn("hx-get", error_html)
        stale_html = render_state(state="stale", retry_url="/some/url/")
        self.assertNotIn("Refresh", stale_html)
        self.assertNotIn("hx-get", stale_html)


# ============================================================================
# task-2: compiled-CSS reduced-motion contract (issue #50)
# ============================================================================
class TestAsyncStateCompiledCss(BilbyTestCase):
    """The shimmer is animation-based so the global prefers-reduced-motion block
    in _shell.scss collapses it to a static block (Frontend Bible rule 10)."""

    def test_shimmer_animation_compiled_into_app_css(self):
        css = APP_CSS.read_text()
        self.assertIn("@keyframes async-shimmer", css)
        self.assertIn("animation: async-shimmer", css)

    def test_reduced_motion_block_collapses_animations(self):
        css = APP_CSS.read_text()
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("animation-duration: 0.01ms !important", css)
        self.assertIn("animation-iteration-count: 1 !important", css)

    def test_skeleton_explicitly_static_under_reduced_motion(self):
        """Selector-specific: the .async-skeleton-row rule inside a
        prefers-reduced-motion block must disable the shimmer animation
        (issue #50 acceptance criterion E), not rely on the global rule."""
        css = APP_CSS.read_text()
        block = re.search(
            r"@media \(prefers-reduced-motion: reduce\)\s*\{([^}]*\.async-skeleton-row[^}]*)\}",
            css,
            re.S,
        )
        self.assertIsNotNone(block, "no reduced-motion block scoping .async-skeleton-row found")
        self.assertIn("animation: none", block.group(1))


# ============================================================================
# task-1: service contracts — list result dicts carry state='ok'|'down'
# ============================================================================
class TestListGWFlowJobsStateFlag(BilbyTestCase):
    """Service contract: list_gwflow_jobs returns state='ok'|'down'."""

    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=100, name="GWFlow User", primary_email="gwflow@example.com")
        self.job = GWFlowJob.objects.create(
            sname="S200101a",
            user=self.user,
            ligo_only=False,
            is_pruned=False,
        )

    def _mock_search(self, mock_es_cls, hits):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": hits}}
        return mock_client

    @patch("elasticsearch.Elasticsearch")
    def test_success_returns_state_ok(self, mock_es_cls):
        self._mock_search(mock_es_cls, [{"_id": self.job.id}])
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertIn(self.job.id, res["jobs"])

    @patch("elasticsearch.Elasticsearch")
    def test_no_hits_returns_state_ok(self, mock_es_cls):
        self._mock_search(mock_es_cls, [])
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_private_info_search_returns_state_ok(self, mock_es_cls):
        res = list_gwflow_jobs(self.user, search="_private_info_.userId:100")
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})
        mock_es_cls.assert_not_called()

    @patch("elasticsearch.Elasticsearch")
    def test_reconciliation_mismatch_returns_state_ok(self, mock_es_cls):
        ligo_job = GWFlowJob.objects.create(
            sname="S200101b",
            user=self.user,
            ligo_only=True,
            is_pruned=False,
        )
        self._mock_search(mock_es_cls, [{"_id": ligo_job.id}])
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_connection_error_on_client_returns_state_down(self, mock_es_cls):
        mock_es_cls.side_effect = elasticsearch.exceptions.ConnectionError("Connection refused")
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_connection_error_on_search_returns_state_down(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.exceptions.ConnectionError("Connection refused")
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_not_found_error_returns_state_down(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.NotFoundError(404, "index not found", {})
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})


class TestListPublicJobsStateFlag(BilbyTestCase):
    """Service contract: list_public_jobs returns state='ok'|'down'."""

    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=200, name="Public User", primary_email="public@example.com")
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Public job",
            description="public",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Public job"}),
        )

    def _mock_search(self, mock_es_cls, hits):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": hits}}
        return mock_client

    @patch("elasticsearch.Elasticsearch")
    def test_success_returns_state_ok(self, mock_es_cls):
        self._mock_search(mock_es_cls, [{"_id": self.job.id, "_source": {}}])
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertIn(self.job.id, res["jobs"])

    @patch("elasticsearch.Elasticsearch")
    def test_no_hits_returns_state_ok(self, mock_es_cls):
        self._mock_search(mock_es_cls, [])
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_private_info_search_returns_state_ok(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        res = list_public_jobs(self.user, search="_private_info_.userId:200")
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})
        mock_client.search.assert_not_called()

    @patch("elasticsearch.Elasticsearch")
    def test_reconciliation_mismatch_returns_state_ok(self, mock_es_cls):
        private_job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Private job",
            description="private",
            private=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Private job"}),
        )
        self._mock_search(mock_es_cls, [{"_id": private_job.id, "_source": {}}])
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_connection_error_on_client_returns_state_down(self, mock_es_cls):
        mock_es_cls.side_effect = elasticsearch.exceptions.ConnectionError("Connection refused")
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_connection_error_on_search_returns_state_down(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.exceptions.ConnectionError("Connection refused")
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_not_found_error_returns_state_down(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.NotFoundError(404, "index not found", {})
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})


class TestListUserJobsStateFlag(BilbyTestCase):
    """Service contract: list_user_jobs is DB-backed and always state='ok'."""

    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=300, name="My Jobs User", primary_email="myjobs@example.com")

    def test_success_returns_state_ok(self):
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="My job",
            description="mine",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "My job"}),
        )
        res = list_user_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(len(res["jobs"]), 1)

    def test_empty_returns_state_ok(self):
        res = list_user_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], [])


# ============================================================================
# task-5: view failure-branch tests (issue #50)
# ============================================================================
class TestGWFlowMetadataFailureBranch(BilbyTestCase):
    """gwflow_job_metadata_partial 'down' branch renders the error state partial
    IN PLACE with the correct retry_url/retry_target and a single announcement."""

    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = GWFlowJob.objects.create(sname="S230601ag", user=self.ligo_user)
        self.url = reverse("bilbyui:gwflow_job_metadata", args=[self.job.sname])

    @patch("bilbyui.views.get_superevent", return_value=(None, "down"))
    def test_down_renders_error_state_with_retry(self, mock_get_superevent):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        mock_get_superevent.assert_called_once_with(self.job.sname)
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
        self.assertContains(response, 'hx-target="#metadata-pane"')
        self.assertContains(response, "Retry")
        self.assertEqual(_live_region_count(response.content.decode()), 1)


class TestGWFlowHistoryFailureBranch(BilbyTestCase):
    """gwflow_job_history_partial 'down' branch renders the error state partial
    with retry re-requesting the history URL into #history-pane."""

    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = GWFlowJob.objects.create(sname="S230601ag", user=self.ligo_user)
        self.url = reverse("bilbyui:gwflow_job_history", args=[self.job.sname])

    @patch("bilbyui.views.get_versions", return_value=(None, "down"))
    def test_down_renders_error_state_with_history_retry(self, mock_get_versions):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        mock_get_versions.assert_called_once_with(self.job.sname)
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
        self.assertContains(response, 'hx-target="#history-pane"')
        self.assertContains(response, "Retry")
        self.assertEqual(_live_region_count(response.content.decode()), 1)


class TestGWFlowHistoryVersionFailureBranch(BilbyTestCase):
    """gwflow_job_history_version_partial 'down' branch renders the error state
    partial with retry re-requesting the version URL into #gwflow-history-version."""

    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = GWFlowJob.objects.create(sname="S230601ag", user=self.ligo_user)
        self.sha = "1111222233334444555566667777888899990000"
        self.url = reverse("bilbyui:gwflow_job_history_version", args=[self.job.sname, self.sha])

    @patch("bilbyui.views.get_version", return_value=(None, "down"))
    def test_down_renders_error_state_with_version_retry(self, mock_get_version):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        mock_get_version.assert_called_once_with(self.job.sname, self.sha)
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
        self.assertEqual(_live_region_count(response.content.decode()), 1)


class TestGWFlowJobsListFailureBranch(BilbyTestCase):
    """gwflow_jobs_view renders the error state partial in the list fragment when
    the service reports state='down', retrying the same list URL into
    #gwflow-job-list."""

    url = "/gwflow/"

    def setUp(self):
        self.authenticate()

    @patch("bilbyui.views.list_gwflow_jobs", return_value=_gwflow_jobs_down_result())
    def test_down_renders_error_state_with_retry(self, mock_list):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "async-error")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, '<span class="sr-only">Error:</span>')
        self.assertContains(
            response,
            "Couldn't load the GWFlow jobs because the service is temporarily unavailable.",
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_jobs")}?page=1&amp;search=&amp;time_range=all"',
        )
        self.assertContains(response, 'hx-target="#gwflow-job-list"')
        self.assertContains(response, "Retry")
        self.assertNotContains(response, "No GWFlow jobs found.")
        self.assertEqual(_live_region_count(response.content.decode()), 1)

    @patch("bilbyui.views.list_gwflow_jobs", return_value=_gwflow_jobs_down_result())
    def test_down_htmx_fragment_renders_error_state(self, mock_list):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<!doctype html>")
        self.assertContains(response, "async-error")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, '<span class="sr-only">Error:</span>')
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_jobs")}?page=1&amp;search=&amp;time_range=all"',
        )
        self.assertContains(response, 'hx-target="#gwflow-job-list"')
        self.assertContains(response, "Retry")
        self.assertEqual(_live_region_count(response.content.decode()), 1)

    @patch("bilbyui.views.list_gwflow_jobs", return_value=_gwflow_jobs_down_result())
    def test_down_retry_url_preserves_search(self, mock_list):
        response = self.client.get(self.url, {"search": "S2306* & co", "page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "async-error")
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_jobs")}?page=2&amp;search=S2306%2A%20%26%20co&amp;time_range=all"',
        )
        self.assertContains(response, 'hx-target="#gwflow-job-list"')
        self.assertEqual(_live_region_count(response.content.decode()), 1)


class TestPublicJobsListFailureBranch(BilbyTestCase):
    """public_jobs_view renders the error state partial in the list fragment when
    the service reports state='down', retrying the same list URL into #job-list."""

    url = "/"

    def setUp(self):
        self.authenticate()

    @patch("bilbyui.views.list_public_jobs", return_value=_public_jobs_down_result())
    def test_down_renders_error_state_with_retry(self, mock_list):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "async-error")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, '<span class="sr-only">Error:</span>')
        self.assertContains(
            response,
            "Couldn't load the job list because the service is temporarily unavailable.",
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:public_jobs")}?page=1&amp;search=&amp;time_range=all"',
        )
        self.assertContains(response, 'hx-target="#job-list"')
        self.assertContains(response, "Retry")
        self.assertEqual(_live_region_count(response.content.decode()), 1)

    @patch("bilbyui.views.list_public_jobs", return_value=_public_jobs_down_result())
    def test_down_htmx_fragment_renders_error_state(self, mock_list):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<!doctype html>")
        self.assertContains(response, "async-error")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, '<span class="sr-only">Error:</span>')
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:public_jobs")}?page=1&amp;search=&amp;time_range=all"',
        )
        self.assertContains(response, 'hx-target="#job-list"')
        self.assertContains(response, "Retry")
        self.assertEqual(_live_region_count(response.content.decode()), 1)


class TestMyJobsListFailureBranch(BilbyTestCase):
    """my_jobs_view renders the error state partial in the list fragment when the
    service reports state='down', retrying the same list URL into #job-list."""

    url = "/job-list/"

    def setUp(self):
        self.authenticate()

    @patch("bilbyui.views.list_user_jobs", return_value=_user_jobs_down_result())
    def test_down_renders_error_state_with_retry(self, mock_list):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "async-error")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, '<span class="sr-only">Error:</span>')
        self.assertContains(
            response,
            "Couldn't load the job list because the service is temporarily unavailable.",
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:my_jobs")}?page=1&amp;search=&amp;time_range=all"',
        )
        self.assertContains(response, 'hx-target="#job-list"')
        self.assertContains(response, "Retry")
        self.assertEqual(_live_region_count(response.content.decode()), 1)

    @patch("bilbyui.views.list_user_jobs", return_value=_user_jobs_down_result())
    def test_down_htmx_fragment_renders_error_state(self, mock_list):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<!doctype html>")
        self.assertContains(response, "async-error")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, '<span class="sr-only">Error:</span>')
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:my_jobs")}?page=1&amp;search=&amp;time_range=all"',
        )
        self.assertContains(response, 'hx-target="#job-list"')
        self.assertContains(response, "Retry")
        self.assertEqual(_live_region_count(response.content.decode()), 1)
