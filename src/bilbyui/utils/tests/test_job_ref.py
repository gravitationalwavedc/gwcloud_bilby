from django.test import RequestFactory, override_settings
from django.urls import reverse
from graphql_relay.node.node import to_global_id

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.job_ref import canonical_job_path


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestCanonicalJobPath(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_replaces_job_id_in_view_job_path(self):
        relay_id = to_global_id("BilbyJobNode", "42")
        request = self.factory.get(f"/job-results/{relay_id}/")
        path = canonical_job_path(request, 42)
        self.assertEqual(path, reverse("bilbyui:view_job", kwargs={"job_id": 42}))

    def test_preserves_view_name_for_edit_paths(self):
        relay_id = to_global_id("BilbyJobNode", "7")
        request = self.factory.get(f"/job-results/{relay_id}/edit/name/")
        path = canonical_job_path(request, 7)
        self.assertEqual(path, reverse("bilbyui:edit_job_name", kwargs={"job_id": 7}))

    def test_preserves_query_string(self):
        request = self.factory.get("/job-results/42/", {"tab": "results", "page": "2"})
        path = canonical_job_path(request, 42)
        self.assertEqual(path, f"{reverse('bilbyui:view_job', kwargs={'job_id': 42})}?tab=results&page=2")

    def test_no_query_string_when_get_empty(self):
        request = self.factory.get("/job-results/42/")
        path = canonical_job_path(request, 42)
        self.assertEqual(path, reverse("bilbyui:view_job", kwargs={"job_id": 42}))
