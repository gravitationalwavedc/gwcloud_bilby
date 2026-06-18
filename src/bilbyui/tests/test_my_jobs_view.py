from unittest import mock

from bilbyui.models import BilbyJob
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


class TestMyJobsView(BilbyTestCase):
    url = "/htmx-preview/jobs/"

    def setUp(self):
        self.deauthenticate()

    def test_unauthenticated_redirected(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/sso/login/?next=/htmx-preview/jobs/")

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_authenticated_returns_user_jobs(self, request_job_filter):
        self.authenticate()

        for index in range(3):
            BilbyJob.objects.create(
                user_id=1,
                name=f"My job {index}",
                description=f"My description {index}",
                job_controller_id=6000 + index,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']", "label": f"My job {index}"}),
            )

        for index in range(3):
            BilbyJob.objects.create(
                user_id=2,
                name=f"Other job {index}",
                description=f"Other description {index}",
                job_controller_id=7000 + index,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']", "label": f"Other job {index}"}),
            )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My job 0")
        self.assertContains(response, "My job 2")
        self.assertNotContains(response, "Other job 0")
        self.assertNotContains(response, "Other job 2")

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_htmx_request_returns_fragment(self, request_job_filter):
        self.authenticate()

        BilbyJob.objects.create(
            user_id=1,
            name="Fragment job",
            description="fragment",
            job_controller_id=8001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Fragment job"}),
        )

        response = self.client.get(
            self.url,
            {"page": 1},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="job-list",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<!doctype html>", status_code=200)
        self.assertContains(response, "Fragment job")
        self.assertNotContains(response, "My Jobs")

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_paging_works(self, request_job_filter):
        self.authenticate()

        for index in range(30):
            BilbyJob.objects.create(
                user_id=1,
                name=f"Paged job {index}",
                description=f"Paged description {index}",
                job_controller_id=9000 + index,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']", "label": f"Paged job {index}"}),
            )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paged job 29")
        self.assertContains(response, "Loading more")
        self.assertContains(response, "page=2")
