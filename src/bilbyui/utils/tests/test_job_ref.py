from unittest import mock

from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect
from django.test import RequestFactory
from django.urls import reverse
from graphql_relay.node.node import to_global_id

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.job_ref import canonical_job_path, parse_job_ref, resolve_job_ref_view


class TestParseJobRef(BilbyTestCase):
    def test_numeric_job_ref(self):
        self.assertEqual(parse_job_ref("42"), (42, False))

    def test_relay_job_ref(self):
        relay_id = to_global_id("BilbyJobNode", 7)
        self.assertEqual(parse_job_ref(relay_id), (7, True))

    def test_empty_global_id_raises_404(self):
        with self.assertRaises(Http404):
            parse_job_ref("not-a-valid-global-id")

    @mock.patch("bilbyui.utils.job_ref.from_global_id", side_effect=ValueError("bad id"))
    def test_from_global_id_exception_raises_404(self, _mock_from_global_id):
        with self.assertRaises(Http404):
            parse_job_ref("any-relay-id")

    def test_wrong_node_type_raises_404(self):
        with self.assertRaises(Http404):
            parse_job_ref(to_global_id("UserNode", 1))

    @mock.patch("bilbyui.utils.job_ref.from_global_id", return_value=("BilbyJobNode", "not-an-int"))
    def test_non_integer_pk_raises_404(self, _mock_from_global_id):
        with self.assertRaises(Http404):
            parse_job_ref("dummy-relay-id")


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
        view = mock.Mock(return_value=HttpResponse("ok"))
        wrapped = resolve_job_ref_view(view)

        request = self.factory.get("/job-results/5/")
        response = wrapped(request, "5")

        self.assertEqual(response.status_code, 200)
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
