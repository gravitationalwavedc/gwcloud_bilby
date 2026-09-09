from unittest import mock

from django.test import RequestFactory, override_settings
from django.urls import reverse

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _render_gwflow_history_section


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestRenderGWFlowHistorySection(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.sname = "S230601ag"
        self.request = self.factory.get(reverse("bilbyui:gwflow_job_history", args=[self.sname]))

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
