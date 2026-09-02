from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.http import Http404
from django.test import RequestFactory

from bilbyui.models import GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _get_gwflow_job_or_404


class TestGetGWFlowJobOr404(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.non_ligo_user = self.create_user(id=11)

    def _request_for(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def _create_job(self, sname="S230601ag", **kwargs):
        defaults = {
            "sname": sname,
            "user": self.ligo_user,
            "libraries": ["cbc-workflow-o4a"],
            "schema_version": "v2",
        }
        defaults.update(kwargs)
        return GWFlowJob.objects.create(**defaults)

    def test_returns_job_when_visible(self):
        job = self._create_job(ligo_only=False)

        result = _get_gwflow_job_or_404(self._request_for(self.non_ligo_user), job.sname)

        self.assertEqual(result, job)

    def test_raises_404_for_missing_job(self):
        with self.assertRaises(Http404):
            _get_gwflow_job_or_404(self._request_for(self.non_ligo_user), "missing-sname")

    def test_ligo_only_job_hidden_from_non_ligo_user(self):
        job = self._create_job(ligo_only=True)

        with self.assertRaises(Http404):
            _get_gwflow_job_or_404(self._request_for(self.non_ligo_user), job.sname)

    def test_ligo_only_job_visible_to_ligo_user(self):
        job = self._create_job(ligo_only=True)

        result = _get_gwflow_job_or_404(self._request_for(self.ligo_user), job.sname)

        self.assertEqual(result, job)
