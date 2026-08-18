from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.urls import reverse

from bilbyui.models import GWFlowJob
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
    def test_detail_page_makes_zero_history_portal_requests(
        self,
        mock_get_version,
        mock_get_versions,
    ):
        response = self.client.get(reverse("bilbyui:gwflow_job_detail", args=[self.job.sname]))

        self.assertEqual(response.status_code, 200)
        mock_get_versions.assert_not_called()
        mock_get_version.assert_not_called()
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history", args=[self.job.sname])}"',
        )
        self.assertContains(response, 'hx-trigger="click once from:#history-tab"')
        self.assertContains(response, 'id="history-pane"')


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

    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=(
            [
                {
                    "commit_sha": "1111222233334444555566667777888899990000",
                    "commit_timestamp": "2026-08-10 12:00:00 UTC",
                    "schema_version": "3",
                    "is_current": True,
                },
                {
                    "commit_sha": "aaaabbbbccccddddeeeeffff0000111122223333",
                    "commit_timestamp": "2026-08-09 10:00:00 UTC",
                    "schema_version": "2",
                    "is_current": False,
                },
            ],
            "live",
        ),
    )
    def test_timeline_rendering_live_versions_with_current_marker(self, mock_get_versions):
        response = self.client.get(self.url)

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
        # Current badge
        self.assertContains(response, '<span class="badge badge-primary">current</span>')
        # Version inspection HTMX attributes
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history_version", args=[self.job.sname, "1111222233334444555566667777888899990000"])}"',
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history_version", args=[self.job.sname, "aaaabbbbccccddddeeeeffff0000111122223333"])}"',
        )
        self.assertContains(response, 'hx-target="#gwflow-history-version"')
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

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<span class="badge badge-primary">current</span>')

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
    def test_stale_timeline_shows_cached_notice(self, mock_get_versions):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Showing cached copy.")

    @mock.patch("bilbyui.views.get_versions", return_value=(None, "down"))
    def test_down_renders_portal_error_with_history_retry(self, mock_get_versions):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The history service is currently unavailable.")
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history", args=[self.job.sname])}"',
        )
        self.assertContains(response, 'hx-target="#history-pane"')
        self.assertContains(response, "Retry")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch("bilbyui.views.get_versions", return_value=([], "live"))
    def test_empty_versions_list(self, mock_get_versions):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No history available.")
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
                "schema_version": "3",
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
        self.assertNotContains(response, "Showing cached copy")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch(
        "bilbyui.views.get_version",
        return_value=(
            {
                "schema_version": "3",
                "commit_sha": "1111222233334444555566667777888899990000",
                "gracedb": {"events": [{"uid": "E99", "pipeline": "pycbc"}]},
            },
            "stale",
        ),
    )
    def test_stale_version_shows_cached_notice(self, mock_get_version):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Showing cached copy.")

    @mock.patch("bilbyui.views.get_version", return_value=(None, "down"))
    def test_down_renders_portal_error_with_version_retry(self, mock_get_version):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The version details service is currently unavailable.")
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history_version", args=[self.job.sname, self.sha])}"',
        )
        self.assertContains(response, 'hx-target="#gwflow-history-version"')
        self.assertContains(response, "Retry")
        self.assertNotContains(response, "<!doctype html>")

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
