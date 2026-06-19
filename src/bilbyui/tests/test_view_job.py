import uuid
from unittest import mock

from django.conf import settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob, FileDownloadToken
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


class TestViewJob(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Viewable job",
            description="A job to view",
            job_controller_id=10001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Viewable job"}),
        )
        self.base_url = f"/job-results/{self.job.id}/"

    def test_unauthenticated_redirected(self):
        self.deauthenticate()
        response = self.client.get(self.base_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.LOGIN_URL}?next={self.base_url}")

    def test_unknown_job_returns_404(self):
        response = self.client.get("/job-results/99999/")

        self.assertEqual(response.status_code, 404)

    def test_other_users_job_returns_404(self):
        other_job = BilbyJob.objects.create(
            user_id=self.user.id + 1,
            name="Private other job",
            description="hidden",
            job_controller_id=10002,
            private=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Private other job"}),
        )

        response = self.client.get(f"/job-results/{other_job.id}/")

        self.assertEqual(response.status_code, 404)

    def test_embargoed_job_for_non_ligo_user_returns_404(self):
        ligo_job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="LIGO job",
            description="ligo only",
            job_controller_id=10003,
            private=False,
            is_ligo_job=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "LIGO job"}),
        )

        response = self.client.get(f"/job-results/{ligo_job.id}/")

        self.assertEqual(response.status_code, 404)

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_renders_known_job(self, request_job_filter):
        response = self.client.get(self.base_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Viewable job")
        self.assertContains(response, "Parameters")
        self.assertContains(response, "Results")
        self.assertContains(response, "COMPLETED —")

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_parameters_partial(self, request_job_filter):
        response = self.client.get(f"{self.base_url}parameters/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Data")
        self.assertContains(response, "Detectors")
        self.assertContains(response, "Signal &amp; Parameters")
        self.assertContains(response, "Priors")
        self.assertContains(response, "Sampler Parameters")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_results_partial(self, request_job_filter):
        files = [
            {"path": "/a", "isDir": True, "fileSize": 0},
            {"path": "/a/path/here.txt", "isDir": False, "fileSize": 12345},
        ]

        with mock.patch.object(BilbyJob, "get_file_list", return_value=(True, files)):
            response = self.client.get(f"{self.base_url}results/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/a")
        self.assertContains(response, "/a/path/here.txt")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch("bilbyui.views.request_file_download_ids")
    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_file_download_redirect(self, request_job_filter, request_file_download_ids):
        download_id = str(uuid.uuid4())
        request_file_download_ids.return_value = (True, [download_id])

        token = FileDownloadToken.objects.create(job=self.job, path="/a/path/here.txt")

        response = self.client.get(f"/job-results/{self.job.id}/files/{token.token}/download/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/?fileId={download_id}",
        )

    def test_file_download_redirect_uploaded_job(self):
        uploaded_job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Uploaded job",
            description="Uploaded",
            job_type=BilbyJobType.UPLOADED,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Uploaded job"}),
        )
        token = FileDownloadToken.objects.create(job=uploaded_job, path="/result.txt")

        response = self.client.get(f"/job-results/{uploaded_job.id}/files/{token.token}/download/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"/file_download/?fileId={token.token}")
