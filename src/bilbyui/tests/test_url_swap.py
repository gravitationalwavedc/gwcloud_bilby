from unittest import mock

from django.urls import reverse

from bilbyui.models import BilbyJob
from bilbyui.tests.test_public_jobs_view import elasticsearch_search_mock_no_hits
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


def request_job_filter_mock(*args, **kwargs):
    requested_ids = set(kwargs.get("ids", []))
    jobs = []
    for job in BilbyJob.objects.filter(job_controller_id__in=requested_ids):
        jobs.append(
            {
                "id": job.job_controller_id,
                "history": [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}],
            }
        )

    return True, jobs


class TestUrlSwap(BilbyTestCase):
    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock_no_hits)
    def test_public_jobs_path_returns_200(self, elasticsearch_search):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_my_jobs_path_requires_auth(self):
        response = self.client.get("/jobs/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/sso/login/?next=/jobs/")

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_view_job_path_returns_200(self, request_job_filter):
        self.authenticate()
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="URL swap job",
            description="A job to view",
            job_controller_id=11001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "URL swap job"}),
        )

        response = self.client.get(f"/jobs/{job.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "URL swap job")

    def test_api_tokens_path_requires_auth(self):
        response = self.client.get("/api-tokens/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/sso/login/?next=/api-tokens/")

    def test_unknown_path_returns_404(self):
        response = self.client.get("/some/random/path/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page Not Found", status_code=404)

    def test_graphql_endpoint_still_works(self):
        response = self.query("{ __typename }")
        self.assertResponseNoErrors(response)
        self.assertEqual(response.data["__typename"], "Query")

    def test_file_download_endpoint_still_works(self):
        response = self.client.get(reverse("file_download"))
        self.assertEqual(response.status_code, 404)

    def test_sso_login_endpoint_still_works(self):
        response = self.client.get("/sso/login/")
        self.assertNotEqual(response.status_code, 404)
        self.assertIn(response.status_code, (200, 302))
