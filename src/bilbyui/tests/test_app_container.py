from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.urls import reverse

from bilbyui.models import BilbyJob, EventID, GWFlowJob
from bilbyui.tests.test_public_jobs_view import elasticsearch_search_mock_no_hits
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


def request_job_filter_mock(*args, **kwargs):
    requested_ids = set(kwargs.get("ids", []))
    jobs = [
        {
            "id": job.job_controller_id,
            "history": [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}],
        }
        for job in BilbyJob.objects.filter(job_controller_id__in=requested_ids)
    ]

    return "OK", jobs


def empty_gwflow_jobs_side_effect():
    def _side_effect(user, *, search="", time_range="all", page=1, page_size=20, **kwargs):
        return {
            "jobs": {},
            "records": [],
            "has_next": False,
            "page": page,
            "page_size": page_size,
        }

    return _side_effect


class AppContainerLayoutTest(BilbyTestCase):
    """Page templates use the shared .app-container shell instead of col-md-10 offset-md-1."""

    def setUp(self):
        self.authenticate()

    def _assert_page_uses_app_container(self, url, **get_kwargs):
        response = self.client.get(url, get_kwargs)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("app-container", content)
        self.assertNotIn("col-md-10", content)

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock_no_hits)
    def test_public_jobs_uses_app_container(self, elasticsearch_search):
        self.deauthenticate()
        self._assert_page_uses_app_container(reverse("bilbyui:public_jobs"))

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock_no_hits)
    def test_my_jobs_uses_app_container(self, elasticsearch_search):
        self._assert_page_uses_app_container(reverse("bilbyui:my_jobs"))

    @mock.patch(
        "bilbyui.views.list_gwflow_jobs",
        side_effect=empty_gwflow_jobs_side_effect(),
    )
    def test_gwflow_jobs_uses_app_container(self, list_gwflow_jobs):
        self._assert_page_uses_app_container(reverse("bilbyui:gwflow_jobs"))

    @mock.patch(
        "bilbyui.views.list_gwflow_jobs",
        side_effect=empty_gwflow_jobs_side_effect(),
    )
    def test_gwflow_detail_uses_app_container(self, list_gwflow_jobs):
        ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=ligo_user)
        event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=12345678.1234,
        )
        job = GWFlowJob.objects.create(
            sname="S230601ag",
            user=ligo_user,
            schema_version="3",
            libraries=["cbc-workflow-o4a"],
            event_id=event_id,
        )

        self._assert_page_uses_app_container(reverse("bilbyui:gwflow_job_detail", args=[job.sname]))

    @mock.patch("bilbyui.views.request_job_filter", side_effect=request_job_filter_mock)
    def test_view_job_uses_app_container(self, request_job_filter):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="App container job",
            description="A job to view",
            job_controller_id=12001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "App container job"}),
        )

        self._assert_page_uses_app_container(reverse("bilbyui:view_job", kwargs={"job_id": job.id}))
