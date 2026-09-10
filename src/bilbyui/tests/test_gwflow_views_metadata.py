from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.test import RequestFactory
from django.urls import reverse

from bilbyui.models import GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _render_gwflow_metadata_section


def _create_job(user, sname="S230601ag", **kwargs):
    defaults = {
        "sname": sname,
        "user": user,
        "libraries": ["cbc-workflow-o4a"],
        "schema_version": "v2",
    }
    defaults.update(kwargs)
    return GWFlowJob.objects.create(**defaults)


class TestRenderGWFlowMetadataSection(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = _create_job(self.ligo_user)
        self.request = RequestFactory().get("/")
        self.request.user = self.ligo_user

    @mock.patch("bilbyui.views.get_superevent", return_value=(None, "down"))
    def test_down_renders_async_error_with_metadata_retry(self, mock_get_superevent):
        response, stale = _render_gwflow_metadata_section(self.request, self.job.sname)

        mock_get_superevent.assert_called_once_with(self.job.sname)
        self.assertFalse(stale)
        self.assertEqual(response.template_name, "bilbyui/_async_state.html")
        rendered = response.render()
        self.assertEqual(rendered.status_code, 200)
        self.assertContains(rendered, "async-error")
        self.assertContains(rendered, 'role="alert"')
        self.assertContains(rendered, '<span class="sr-only">Error:</span>')
        self.assertContains(
            rendered,
            "Couldn't load the metadata because the service is temporarily unavailable.",
        )
        self.assertContains(
            rendered,
            f'hx-get="{reverse("bilbyui:gwflow_job_metadata", args=[self.job.sname])}"',
        )
        self.assertContains(rendered, 'hx-target="#detail-pane"')
        self.assertContains(rendered, "Retry")

    @mock.patch(
        "bilbyui.views.get_superevent",
        return_value=({"gracedb": {"events": [{"uid": "E1", "pipeline": "gstlal"}]}}, "live"),
    )
    def test_live_renders_metadata_payload_without_stale(self, mock_get_superevent):
        response, stale = _render_gwflow_metadata_section(self.request, self.job.sname)

        mock_get_superevent.assert_called_once_with(self.job.sname)
        self.assertFalse(stale)
        self.assertEqual(response.template_name, "bilbyui/_gwflow_metadata.html")
        rendered = response.render()
        self.assertEqual(rendered.status_code, 200)
        self.assertContains(rendered, "E1")
        self.assertContains(rendered, "gstlal")
        self.assertNotContains(rendered, "async-error")

    @mock.patch(
        "bilbyui.views.get_superevent",
        return_value=({"gracedb": {"events": [{"uid": "E1", "pipeline": "gstlal"}]}}, "stale"),
    )
    def test_stale_renders_metadata_payload_with_stale_flag(self, mock_get_superevent):
        response, stale = _render_gwflow_metadata_section(self.request, self.job.sname)

        mock_get_superevent.assert_called_once_with(self.job.sname)
        self.assertTrue(stale)
        self.assertEqual(response.template_name, "bilbyui/_gwflow_metadata.html")
        rendered = response.render()
        self.assertEqual(rendered.status_code, 200)
        self.assertContains(rendered, "E1")
        self.assertContains(rendered, "gstlal")
