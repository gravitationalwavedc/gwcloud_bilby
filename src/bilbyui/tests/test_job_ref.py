from unittest import mock

from django.http import HttpResponsePermanentRedirect
from django.test import RequestFactory
from django.urls import reverse
from graphql_relay.node.node import to_global_id

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.job_ref import canonical_job_path, resolve_job_ref_view


class TestCanonicalJobPath(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_canonical_path_without_query_string(self):
        request = self.factory.get("/job-results/99/")
        path = canonical_job_path(request, 99)
        self.assertEqual(path, reverse("bilbyui:view_job", kwargs={"job_id": 99}))

    def test_canonical_path_preserves_query_string(self):
        request = self.factory.get("/job-results/99/?tab=results")
        path = canonical_job_path(request, 99)
        expected = f"{reverse('bilbyui:view_job', kwargs={'job_id': 99})}?tab=results"
        self.assertEqual(path, expected)

    def test_canonical_path_for_nested_view(self):
        request = self.factory.get("/job-results/99/edit/name/")
        path = canonical_job_path(request, 99)
        self.assertEqual(path, reverse("bilbyui:edit_job_name", kwargs={"job_id": 99}))


class TestResolveJobRefView(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_numeric_id_passes_through(self):
        view = mock.Mock(return_value="ok")
        wrapped = resolve_job_ref_view(view)

        request = self.factory.get("/job-results/5/")
        response = wrapped(request, "5")

        self.assertEqual(response, "ok")
        view.assert_called_once_with(request, 5)

    def test_relay_id_redirects(self):
        view = mock.Mock()
        wrapped = resolve_job_ref_view(view)

        relay_id = to_global_id("BilbyJobNode", 12)
        request = self.factory.get(f"/job-results/{relay_id}/?tab=results")
        response = wrapped(request, relay_id)

        view.assert_not_called()
        self.assertIsInstance(response, HttpResponsePermanentRedirect)
        self.assertEqual(
            response["Location"],
            f"{reverse('bilbyui:view_job', kwargs={'job_id': 12})}?tab=results",
        )
