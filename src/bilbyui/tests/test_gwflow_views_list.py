from unittest import mock

from django.urls import reverse

from bilbyui.models import EventID, GWFlowFile, GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _build_gwflow_job_rows


def _build_gwflow_result(jobs, analyses=None, has_next=False, page=1, page_size=20):
    analyses = analyses or {}
    records = [{"_id": str(job.id), "_source": {"analyses": analyses.get(job.id, [])}} for job in jobs]
    return {
        "jobs": {job.id: job for job in jobs},
        "records": records,
        "has_next": has_next,
        "page": page,
        "page_size": page_size,
    }


def _gwflow_jobs_side_effect(analyses=None, has_next=False):
    def _side_effect(user, *, search="", time_range="all", page=1, page_size=20, **kwargs):
        jobs = list(GWFlowJob.objects.order_by("id"))
        return _build_gwflow_result(jobs, analyses=analyses, has_next=has_next, page=page, page_size=page_size)

    return _side_effect


class TestGWFlowJobsListView(BilbyTestCase):
    url = "/gwflow/"

    def setUp(self):
        self.authenticate()

    def test_full_page_renders_job(self):
        event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=12345678.1234,
        )
        job = GWFlowJob.objects.create(
            sname="S230601ag",
            user=self.user,
            schema_version="3",
            libraries=["cbc-workflow-o4a", "other-lib"],
            event_id=event_id,
        )
        GWFlowFile.objects.create(job=job, analysis_uid="", path="data/a.txt", file_name="a.txt", uploaded=True)
        GWFlowFile.objects.create(job=job, analysis_uid="", path="data/b.txt", file_name="b.txt", uploaded=False)

        with mock.patch(
            "bilbyui.views.list_gwflow_jobs",
            side_effect=_gwflow_jobs_side_effect({job.id: ["a", "b", "c"]}),
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "S230601ag")
        self.assertContains(response, "cbc-workflow-o4a")
        self.assertContains(response, "v3")
        self.assertContains(response, "<span>3</span>")
        self.assertContains(response, "analyses")
        self.assertContains(response, "1/2")
        self.assertContains(response, f'href="{reverse("bilbyui:gwflow_jobs")}"')

    def test_search_form_hx_target_matches_job_list_container(self):
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="gwflow-job-list"')
        self.assertContains(response, 'hx-target="#gwflow-job-list"')

    def test_htmx_request_returns_fragment(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<!doctype html>")
        self.assertContains(response, "S230601ag")
        self.assertNotContains(response, "GWFlow")

    def test_search_help_renders(self):
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search help")
        self.assertContains(response, "analyses.software")
        self.assertContains(response, "sname:S2306*")

    def test_paging_sentinel_renders_when_has_next(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect(has_next=True)):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Loading more")
        self.assertContains(response, f'hx-get="{reverse("bilbyui:gwflow_jobs")}?page=2')

    def test_mirror_progress_zero_files_shows_pending(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "0/0")
        self.assertContains(response, "badge-warning")

    def test_search_time_range_page_passed_through(self):
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()) as mock_list:
            response = self.client.get(self.url, {"search": "foo", "time_range": "1d", "page": 2})

        self.assertEqual(response.status_code, 200)
        mock_list.assert_called_once_with(self.user, search="foo", time_range="1d", page=2)

    def test_row_building_counts_from_db(self):
        job1 = GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        job2 = GWFlowJob.objects.create(sname="S230602ag", user=self.user)

        for job, uploaded in {job1: 2, job2: 1}.items():
            for i in range(3):
                GWFlowFile.objects.create(
                    job=job,
                    analysis_uid=f"analysis_{i}",
                    path=f"data/file_{i}.txt",
                    file_name=f"file_{i}.txt",
                    uploaded=(i < uploaded),
                )

        jobs = list(GWFlowJob.objects.select_related("event_id").order_by("id"))
        result = _build_gwflow_result(jobs)

        with self.assertNumQueries(1):
            rows = _build_gwflow_job_rows(result)

        rows_by_sname = {row["sname"]: row for row in rows}
        self.assertEqual(rows_by_sname["S230601ag"]["files_total"], 3)
        self.assertEqual(rows_by_sname["S230601ag"]["files_uploaded"], 2)
        self.assertEqual(rows_by_sname["S230602ag"]["files_total"], 3)
        self.assertEqual(rows_by_sname["S230602ag"]["files_uploaded"], 1)

        row = rows_by_sname["S230601ag"]
        self.assertEqual(row["id"], job1.id)
        self.assertRegex(row["last_updated"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC$")

    def test_empty_state(self):
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No GWFlow jobs found.")

    def test_renders_event_id_values(self):
        event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=12345678.1234,
        )
        GWFlowJob.objects.create(sname="S230601ag", user=self.user, event_id=event_id)
        GWFlowJob.objects.create(sname="S230602ag", user=self.user)

        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GW123456_123456")
        self.assertContains(response, "S123456a")
        self.assertContains(response, "GW123456")
        self.assertContains(response, "No event ids")

    def test_pruned_badge(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user, is_pruned=True)

        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "badge-dark")
        self.assertContains(response, "pruned")

    def test_mirror_progress_badges(self):
        complete = GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        pending = GWFlowJob.objects.create(sname="S230602ag", user=self.user)

        for i in range(2):
            GWFlowFile.objects.create(
                job=complete,
                analysis_uid=f"a{i}",
                path=f"p{i}",
                file_name=f"f{i}",
                uploaded=True,
            )
        GWFlowFile.objects.create(job=pending, analysis_uid="a0", path="p0", file_name="f0", uploaded=True)
        GWFlowFile.objects.create(job=pending, analysis_uid="a1", path="p1", file_name="f1", uploaded=False)

        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "badge-success")
        self.assertContains(response, "badge-warning")
        self.assertContains(response, "2/2")
        self.assertContains(response, "1/2")

    def test_invalid_page_and_time_range_default(self):
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()) as mock_list:
            response = self.client.get(self.url, {"page": "abc", "time_range": "invalid"})

        self.assertEqual(response.status_code, 200)
        mock_list.assert_called_once_with(self.user, search="", time_range="all", page=1)

    def test_navbar_active_link(self):
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("bilbyui:gwflow_jobs")}"')
        self.assertContains(response, 'class="nav-link active"')

    def test_detail_stub(self):
        response = self.client.get(reverse("bilbyui:gwflow_job_detail", args=["S230601ag"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "S230601ag")
        self.assertContains(response, "coming soon")
