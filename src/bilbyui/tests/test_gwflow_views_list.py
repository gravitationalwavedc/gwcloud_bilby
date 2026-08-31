from unittest import mock

from django.test import RequestFactory
from django.urls import reverse

from bilbyui.models import EventID, GWFlowFile, GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _build_gwflow_job_rows, _render_job_list


def _build_gwflow_result(jobs, analyses=None, has_next=False, page=1, page_size=20, total=0):
    analyses = analyses or {}
    records = [{"_id": str(job.id), "_source": {"analyses": analyses.get(job.id, [])}} for job in jobs]
    return {
        "jobs": {job.id: job for job in jobs},
        "records": records,
        "has_next": has_next,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def _gwflow_jobs_side_effect(analyses=None, has_next=False, total=0):
    def _side_effect(user, *, search="", time_range="all", page=1, page_size=20, **kwargs):
        jobs = list(GWFlowJob.objects.order_by("id"))
        return _build_gwflow_result(
            jobs, analyses=analyses, has_next=has_next, page=page, page_size=page_size, total=total
        )

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
        self.assertContains(response, "<title>GWFlow — GWCloud</title>")
        self.assertNotContains(response, "<h1")

    def test_search_help_renders(self):
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search help")
        self.assertContains(response, "analyses.software")
        self.assertContains(response, "sname:S2306*")

    def test_pagination_renders_when_has_next(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        with mock.patch(
            "bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect(has_next=True, total=40)
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="Pagination"')
        self.assertContains(response, 'rel="next"')
        self.assertContains(response, f'href="{reverse("bilbyui:gwflow_jobs")}?page=2')

    def test_pagination_urlencodes_search(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        with mock.patch(
            "bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect(has_next=True, total=40)
        ):
            response = self.client.get(self.url, {"search": "S2306* & co"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="Pagination"')
        self.assertContains(response, "search=S2306%2A%20%26%20co")
        self.assertNotContains(response, "search=S2306* & co")

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
        mock_list.assert_called_once_with(
            self.user,
            search="foo",
            library="",
            review_status="",
            time_range="1d",
            page=2,
        )

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

    def test_row_building_none_last_updated_does_not_crash(self):
        job = GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        job.last_updated = None
        result = _build_gwflow_result([job])

        rows = _build_gwflow_job_rows(result)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["last_updated"], "")

    def test_row_building_malformed_analyses_counts_as_zero(self):
        job = GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        for malformed in ({"pe": ["a"]}, "not-a-list", 42, None):
            result = _build_gwflow_result([job], analyses={job.id: malformed})
            rows = _build_gwflow_job_rows(result)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["analysis_count"], 0)

    def test_row_building_skips_records_without_matching_job(self):
        job = GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        result = _build_gwflow_result([job])
        result["records"].append({"_id": "999999", "_source": {"analyses": []}})

        rows = _build_gwflow_job_rows(result)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sname"], "S230601ag")

    def test_row_building_skips_missing_or_non_dict_source(self):
        job = GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        records = [
            {"_id": str(job.id)},
            {"_id": str(job.id), "_source": "not-a-dict"},
            {"_id": str(job.id), "_source": {"analyses": ["a"]}},
        ]
        result = {
            "jobs": {job.id: job},
            "records": records,
            "has_next": False,
            "page": 1,
            "page_size": 20,
        }

        rows = _build_gwflow_job_rows(result)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sname"], "S230601ag")
        self.assertEqual(rows[0]["analysis_count"], 1)

    def test_non_list_analyses_does_not_crash(self):
        job = GWFlowJob.objects.create(sname="S230601ag", user=self.user)

        with mock.patch(
            "bilbyui.views.list_gwflow_jobs",
            side_effect=_gwflow_jobs_side_effect({job.id: "not-a-list"}),
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "S230601ag")

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
        mock_list.assert_called_once_with(self.user, search="", library="", review_status="", time_range="all", page=1)

    def test_navbar_active_link(self):
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("bilbyui:gwflow_jobs")}"')
        self.assertContains(response, 'class="nav-link active"')

    def test_detail_missing_job_404(self):
        response = self.client.get(reverse("bilbyui:gwflow_job_detail", args=["S230601ag"]))

        self.assertEqual(response.status_code, 404)


class TestGWFlowJobsListFiltersAndPagination(BilbyTestCase):
    """View contract for the UX-4 search/filtering/pagination feature: the list
    context carries total, pagination window, active-filter chips, filter
    options and a retry URL that preserves every active param."""

    url = "/gwflow/"

    def setUp(self):
        self.authenticate()

    def _get(self, params=None, total=0, has_next=False):
        with (
            mock.patch(
                "bilbyui.views.list_gwflow_jobs",
                side_effect=_gwflow_jobs_side_effect(total=total, has_next=has_next),
            ) as mock_list,
            mock.patch(
                "bilbyui.views.list_gwflow_filter_options",
                return_value={"libraries": ["lib-a", "lib-b"], "review_statuses": ["reviewed", "pending"]},
            ) as mock_options,
        ):
            response = self.client.get(self.url, params or {})
        return response, mock_list, mock_options

    def _render_context(self, params=None, total=0, page_size=20, **kwargs):
        request = RequestFactory().get(self.url, params or {})
        request.user = self.user
        return _render_job_list(
            request,
            rows=[],
            has_next=False,
            total=total,
            page_size=page_size,
            jobs_list_url_name="bilbyui:gwflow_jobs",
            template_name="bilbyui/gwflow_jobs.html",
            fragment_template_name="bilbyui/_gwflow_job_list_fragment.html",
            list_target_id="gwflow-job-list",
            **kwargs,
        ).context_data

    def test_url_state_round_trip_all_params(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        response, mock_list, mock_options = self._get(
            {
                "search": "S2306* & co",
                "library": "cbc-workflow-o4a",
                "review_status": "reviewed",
                "time_range": "1d",
                "page": 3,
            },
            total=57,
        )

        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertEqual(context["search"], "S2306* & co")
        self.assertEqual(context["library"], "cbc-workflow-o4a")
        self.assertEqual(context["review_status"], "reviewed")
        self.assertEqual(context["time_range"], "1d")
        self.assertEqual(context["page"], 3)
        self.assertEqual(context["total"], 57)
        self.assertEqual(
            context["filter_options"], {"libraries": ["lib-a", "lib-b"], "review_statuses": ["reviewed", "pending"]}
        )
        mock_list.assert_called_once_with(
            self.user,
            search="S2306* & co",
            library="cbc-workflow-o4a",
            review_status="reviewed",
            time_range="1d",
            page=3,
        )
        mock_options.assert_called_once_with()

    def test_url_state_round_trip_fragment(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        with (
            mock.patch(
                "bilbyui.views.list_gwflow_jobs",
                side_effect=_gwflow_jobs_side_effect(total=12),
            ) as mock_list,
            mock.patch(
                "bilbyui.views.list_gwflow_filter_options",
                return_value={"libraries": ["lib-a"], "review_statuses": ["reviewed"]},
            ),
        ):
            response = self.client.get(
                self.url,
                {"search": "foo", "library": "lib-a", "review_status": "reviewed", "time_range": "1w", "page": 2},
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<!doctype html>")
        context = response.context
        self.assertEqual(context["search"], "foo")
        self.assertEqual(context["library"], "lib-a")
        self.assertEqual(context["review_status"], "reviewed")
        self.assertEqual(context["time_range"], "1w")
        self.assertEqual(context["page"], 2)
        self.assertEqual(context["total"], 12)
        mock_list.assert_called_once_with(
            self.user,
            search="foo",
            library="lib-a",
            review_status="reviewed",
            time_range="1w",
            page=2,
        )

    def test_missing_page_resets_to_one(self):
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()) as mock_list:
            response = self.client.get(self.url, {"search": "foo", "library": "lib-a"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"], 1)
        mock_list.assert_called_once_with(
            self.user, search="foo", library="lib-a", review_status="", time_range="all", page=1
        )

    def test_total_pages_and_page_range_windowed(self):
        context = self._render_context({"page": 5}, total=400, page_size=20)

        self.assertEqual(context["total_pages"], 20)
        self.assertEqual(context["page_range"], [3, 4, 5, 6, 7])

    def test_page_range_clamped_at_start(self):
        context = self._render_context({"page": 1}, total=400, page_size=20)

        self.assertEqual(context["total_pages"], 20)
        self.assertEqual(context["page_range"], [1, 2, 3])

    def test_page_range_clamped_at_end(self):
        context = self._render_context({"page": 20}, total=400, page_size=20)

        self.assertEqual(context["total_pages"], 20)
        self.assertEqual(context["page_range"], [18, 19, 20])

    def test_total_pages_at_least_one_when_no_results(self):
        context = self._render_context({}, total=0, page_size=20)

        self.assertEqual(context["total_pages"], 1)
        self.assertEqual(context["page_range"], [1])

    def test_total_pages_guards_zero_page_size(self):
        context = self._render_context({"page": 1}, total=100, page_size=0)

        self.assertEqual(context["total_pages"], 1)
        self.assertEqual(context["page_range"], [1])

    def test_active_filters_chips_and_reset(self):
        context = self._render_context(
            {"search": "foo", "library": "lib-a", "review_status": "reviewed", "time_range": "1d"},
            total=10,
        )

        active_filters = context["active_filters"]
        self.assertEqual(
            [f["label"] for f in active_filters],
            ["Search: foo", "Library: lib-a", "Review status: reviewed", "Updated: Past 24 hours"],
        )
        self.assertEqual(
            [f["param_name"] for f in active_filters],
            ["search", "library", "review_status", "time_range"],
        )

        search_chip = active_filters[0]
        self.assertEqual(
            search_chip["remove_url"],
            f"{reverse('bilbyui:gwflow_jobs')}?library=lib-a&review_status=reviewed&time_range=1d&page=1",
        )
        library_chip = active_filters[1]
        self.assertEqual(
            library_chip["remove_url"],
            f"{reverse('bilbyui:gwflow_jobs')}?search=foo&review_status=reviewed&time_range=1d&page=1",
        )
        time_chip = active_filters[3]
        self.assertEqual(
            time_chip["remove_url"],
            f"{reverse('bilbyui:gwflow_jobs')}?search=foo&library=lib-a&review_status=reviewed&page=1",
        )

        self.assertEqual(context["reset_url"], reverse("bilbyui:gwflow_jobs"))

    def test_active_filters_no_chips_when_no_filters(self):
        context = self._render_context({}, total=10)

        self.assertEqual(context["active_filters"], [])
        self.assertEqual(context["reset_url"], reverse("bilbyui:gwflow_jobs"))

    def test_time_range_all_produces_no_time_chip(self):
        context = self._render_context({"search": "foo", "time_range": "all"}, total=10)

        labels = [f["label"] for f in context["active_filters"]]
        self.assertEqual(labels, ["Search: foo"])
        self.assertNotIn("Updated", labels)

    def test_active_filters_quote_remove_url_values(self):
        context = self._render_context({"search": "S2306* & co", "time_range": "1d"}, total=10)

        search_chip = context["active_filters"][0]
        self.assertEqual(search_chip["remove_url"], f"{reverse('bilbyui:gwflow_jobs')}?time_range=1d&page=1")
        self.assertEqual(context["search"], "S2306* & co")

    def test_active_filters_remove_url_encodes_kept_values(self):
        context = self._render_context({"search": "S2306* & co", "library": "lib-a"}, total=10)

        library_chip = context["active_filters"][1]
        self.assertEqual(
            library_chip["remove_url"],
            f"{reverse('bilbyui:gwflow_jobs')}?search=S2306%2A%20%26%20co&page=1",
        )

    def test_retry_url_carries_all_params(self):
        context = self._render_context(
            {"search": "foo", "library": "lib-a", "review_status": "reviewed", "time_range": "1d", "page": 2},
            total=10,
        )

        self.assertEqual(
            context["retry_url"],
            f"{reverse('bilbyui:gwflow_jobs')}?page=2&search=foo&time_range=1d&library=lib-a&review_status=reviewed",
        )

    def test_retry_url_quotes_values(self):
        context = self._render_context({"search": "S2306* & co", "library": "a b", "page": 2}, total=10)

        self.assertEqual(
            context["retry_url"],
            f"{reverse('bilbyui:gwflow_jobs')}?page=2&search=S2306%2A%20%26%20co&time_range=all&library=a%20b",
        )

    def test_retry_url_omits_empty_library_and_review_status(self):
        context = self._render_context({"search": "foo", "page": 2}, total=10)

        self.assertEqual(
            context["retry_url"],
            f"{reverse('bilbyui:gwflow_jobs')}?page=2&search=foo&time_range=all",
        )

    def test_filter_options_default_when_none(self):
        context = self._render_context({}, total=10, filter_options=None)

        self.assertEqual(context["filter_options"], {"libraries": [], "review_statuses": []})

    def test_filter_options_fallback_when_service_raises(self):
        with (
            mock.patch(
                "bilbyui.views.list_gwflow_jobs",
                side_effect=_gwflow_jobs_side_effect(total=5),
            ),
            mock.patch(
                "bilbyui.views.list_gwflow_filter_options",
                side_effect=ConnectionError("es down"),
            ),
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filter_options"], {"libraries": [], "review_statuses": []})

    def test_gwflow_jobs_view_passes_library_and_review_status(self):
        with (
            mock.patch(
                "bilbyui.views.list_gwflow_jobs",
                side_effect=_gwflow_jobs_side_effect(total=5),
            ) as mock_list,
            mock.patch(
                "bilbyui.views.list_gwflow_filter_options",
                return_value={"libraries": [], "review_statuses": []},
            ),
        ):
            response = self.client.get(self.url, {"library": "cbc-workflow-o4a", "review_status": "reviewed"})

        self.assertEqual(response.status_code, 200)
        mock_list.assert_called_once_with(
            self.user,
            search="",
            library="cbc-workflow-o4a",
            review_status="reviewed",
            time_range="all",
            page=1,
        )
        self.assertEqual(response.context["library"], "cbc-workflow-o4a")
        self.assertEqual(response.context["review_status"], "reviewed")

    def test_fragment_title_renders_page_number_and_prefix(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect(total=40)):
            response = self.client.get(self.url, {"page": 2}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>GWFlow — page 2 — GWCloud</title>")

    def test_fragment_title_omits_page_number_on_first_page(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>GWFlow — GWCloud</title>")
        self.assertNotContains(response, "page 1")

    def test_full_page_title_includes_page_number_when_greater_than_one(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect(total=40)):
            response = self.client.get(self.url, {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>GWFlow — page 2 — GWCloud</title>")

    def test_full_page_title_omits_page_number_on_first_page(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        with mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=_gwflow_jobs_side_effect()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>GWFlow — GWCloud</title>")
        self.assertNotContains(response, "page 1")
