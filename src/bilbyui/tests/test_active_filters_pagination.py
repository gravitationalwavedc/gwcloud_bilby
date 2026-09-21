"""Template tests for the UX-4 active-filters chips, result count, pagination
partials and page-template search-form include params (issue #51, task-4).

Renders the list fragments via the existing list views (services mocked as in
test_gwflow_views_list.py) and via _render_job_list for full context control.
"""

import re
from pathlib import Path
from unittest import mock

from django.template.loader import get_template
from django.test import RequestFactory
from django.urls import reverse

from bilbyui.models import GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _render_job_list

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "bilbyui"


def _build_gwflow_result(jobs, has_next=False, page=1, page_size=20, total=0):
    records = [{"_id": str(job.id), "_source": {"analyses": []}} for job in jobs]
    return {
        "jobs": {job.id: job for job in jobs},
        "records": records,
        "has_next": has_next,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def _gwflow_jobs_side_effect(has_next=False, total=0):
    def _side_effect(user, *, search="", time_range="all", page=1, page_size=20, **kwargs):
        jobs = list(GWFlowJob.objects.order_by("id"))
        return _build_gwflow_result(jobs, has_next=has_next, page=page, page_size=page_size, total=total)

    return _side_effect


class TestActiveFiltersPagination(BilbyTestCase):
    url = "/gwflow/"

    def setUp(self):
        self.authenticate()

    def _get_gwflow(self, params=None, total=0, has_next=False):
        with (
            mock.patch(
                "bilbyui.views.list_gwflow_jobs",
                side_effect=_gwflow_jobs_side_effect(total=total, has_next=has_next),
            ),
            mock.patch(
                "bilbyui.views.list_gwflow_filter_options",
                return_value={
                    "libraries": {"values": ["lib-a", "lib-b"], "state": "ok"},
                    "review_statuses": {"values": ["reviewed", "pending"], "state": "ok"},
                },
            ),
        ):
            return self.client.get(self.url, params or {})

    def _render_fragment(
        self,
        params=None,
        total=0,
        page_size=20,
        has_next=False,
        fragment_template="bilbyui/_gwflow_job_list_fragment.html",
        list_target_id="gwflow-job-list",
        **kwargs,
    ):
        request = RequestFactory().get(self.url, params or {}, HTTP_HX_REQUEST="true")
        request.user = self.user
        return _render_job_list(
            request,
            rows=[],
            has_next=has_next,
            total=total,
            page_size=page_size,
            jobs_list_url_name="bilbyui:gwflow_jobs",
            template_name="bilbyui/gwflow_jobs.html",
            fragment_template_name=fragment_template,
            list_target_id=list_target_id,
            **kwargs,
        ).render()

    # ------------------------------------------------------------------
    # Result count (role="status")
    # ------------------------------------------------------------------
    def test_gwflow_result_count_renders_role_status(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        response = self._get_gwflow(total=5)
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "5 superevents match")
        self.assertEqual(html.count('role="status"'), 1)
        status = re.search(
            r'<p[^>]*id="gwflow-results-status"[^>]*>(.*?)</p>',
            html,
            re.S,
        )
        self.assertIsNotNone(status)
        self.assertEqual(status.group(1).strip(), "")
        fragment = html[html.index('class="list-fragment"') :]
        self.assertNotIn('role="status"', fragment)
        self.assertNotIn("aria-live", fragment)

    def test_gwflow_result_count_singular(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        response = self._get_gwflow(total=1)

        self.assertContains(response, "1 superevent match")

    def test_gwflow_result_count_zero_keeps_empty_copy(self):
        response = self._get_gwflow(total=0)

        self.assertContains(response, "No superevents yet.")
        self.assertNotContains(response, "0 superevents match")

    def test_gwflow_empty_page_with_positive_total_shows_recovery_copy(self):
        response = self._get_gwflow(total=40)

        self.assertContains(response, "This page has no GWFlow jobs. Choose another page below.")
        self.assertNotContains(response, "40 superevents match")
        self.assertNotContains(response, "No superevents yet.")

    def test_job_fragment_result_count(self):
        response = self._render_fragment(
            total=3,
            fragment_template="bilbyui/_job_list_fragment.html",
            list_target_id="job-list",
        )

        html = response.content.decode()
        self.assertContains(response, "3 jobs match")
        self.assertContains(response, 'data-settled-kind="content"')
        self.assertContains(response, 'data-settled-message="3 jobs match"')
        self.assertNotIn('role="status"', html)
        self.assertNotIn("aria-live", html)

    def test_job_fragment_result_count_singular(self):
        response = self._render_fragment(
            total=1,
            fragment_template="bilbyui/_job_list_fragment.html",
            list_target_id="job-list",
        )

        self.assertContains(response, "1 job match")

    def test_job_empty_page_with_positive_total_shows_recovery_copy(self):
        response = self._render_fragment(
            total=40,
            fragment_template="bilbyui/_job_list_fragment.html",
            list_target_id="job-list",
        )

        self.assertContains(response, "40 jobs match")
        self.assertContains(response, "This page has no jobs. Choose another page below.")
        self.assertNotContains(response, "Create a new job or try searching 'Any time'.")

    def test_error_branch_omits_result_count(self):
        response = self._render_fragment(total=5, service_state="down")

        self.assertNotContains(response, "superevents match")
        self.assertContains(response, "Couldn't load the GWFlow jobs")

    # ------------------------------------------------------------------
    # Active-filter chips
    # ------------------------------------------------------------------
    def test_active_filters_chips_render_with_remove_buttons(self):
        response = self._render_fragment(
            {"search": "foo", "library": "lib-a", "review": "reviewed", "time_range": "1d"},
            total=10,
        )

        self.assertContains(response, "Search: foo")
        self.assertContains(response, "Library: lib-a")
        self.assertContains(response, "Review status: reviewed")
        self.assertContains(response, "Updated: Past 24 hours")
        self.assertContains(response, 'aria-label="Remove search filter"')
        self.assertContains(response, 'aria-label="Remove library filter"')
        self.assertContains(response, 'aria-label="Remove review status filter"')
        self.assertContains(response, 'aria-label="Remove time filter"')
        self.assertContains(response, "Reset all")

    def test_active_filters_remove_url_and_target(self):
        response = self._render_fragment({"search": "foo", "library": "lib-a"}, total=10)

        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_jobs")}?library=lib-a&amp;page=1"',
        )
        self.assertContains(response, 'hx-target="#gwflow-job-list"')
        self.assertContains(response, 'hx-swap="innerHTML"')
        self.assertContains(response, 'hx-push-url="true"')

    def test_active_filters_chips_carry_param_name_metadata(self):
        """Each removable chip carries machine-readable ``data-filter-param``
        metadata so chip removal can reset only the corresponding form control
        via the targeted action sync (issue #75 / UX-17), instead of a
        generic URL write-back. Reset all carries ``data-filter-reset``."""
        response = self._render_fragment(
            {"search": "foo", "library": "lib-a", "review": "reviewed", "time_range": "1d"},
            total=10,
        )

        self.assertContains(response, 'data-filter-param="search"')
        self.assertContains(response, 'data-filter-param="library"')
        self.assertContains(response, 'data-filter-param="review"')
        self.assertContains(response, 'data-filter-param="time_range"')
        self.assertContains(response, "data-filter-reset")

    def test_active_filters_reset_all_link(self):
        response = self._render_fragment({"search": "foo", "time_range": "1d"}, total=10)

        self.assertContains(response, f'href="{reverse("bilbyui:gwflow_jobs")}"')
        self.assertContains(response, f'hx-get="{reverse("bilbyui:gwflow_jobs")}"')
        self.assertContains(response, "Reset all")

    def test_active_filters_absent_when_no_filters(self):
        response = self._render_fragment({}, total=10)

        self.assertNotContains(response, "filter-chip")
        self.assertNotContains(response, "Reset all")
        self.assertNotContains(response, 'aria-label="Remove ')

    def test_time_range_all_produces_no_time_chip(self):
        response = self._render_fragment({"search": "foo", "time_range": "all"}, total=10)

        self.assertContains(response, "Search: foo")
        self.assertNotContains(response, "Updated:")

    def test_active_filters_comment_is_not_rendered_verbatim(self):
        """The template's documentation comments must not leak into the
        rendered output. Regression: a malformed ``{# ... #)`` comment on
        the active-filters partial was emitted verbatim as visible text."""
        response = self._render_fragment({"search": "foo"}, total=10)

        self.assertNotContains(response, "corresponding form control is reset to its default")
        self.assertNotContains(response, "targeted action-specific")

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    def test_pagination_renders_numbered_links_with_aria_current(self):
        response = self._render_fragment({"page": 2}, total=60, has_next=True)

        self.assertContains(response, 'aria-label="Pagination"')
        self.assertContains(response, 'rel="prev"')
        self.assertContains(response, 'rel="next"')
        self.assertContains(response, 'aria-current="page"')
        self.assertContains(response, 'class="page-item active"')
        self.assertContains(
            response,
            f'href="{reverse("bilbyui:gwflow_jobs")}?page=1&search=&library=&review=&time_range=all"',
        )
        self.assertContains(
            response,
            f'href="{reverse("bilbyui:gwflow_jobs")}?page=3&search=&library=&review=&time_range=all"',
        )

    def test_pagination_links_are_progressively_enhanced(self):
        response = self._render_fragment({"page": 2}, total=60, has_next=True)

        self.assertContains(response, 'hx-target="#gwflow-job-list"')
        self.assertContains(response, 'hx-swap="innerHTML"')
        self.assertContains(response, 'hx-push-url="true"')
        # HTMX boosts the canonical native href (no duplicated hx-get URL).
        self.assertContains(response, 'hx-boost="true"')
        self.assertNotContains(response, "hx-get=")
        self.assertContains(
            response,
            f'href="{reverse("bilbyui:gwflow_jobs")}?page=1&search=&library=&review=&time_range=all"',
        )
        self.assertContains(
            response,
            f'href="{reverse("bilbyui:gwflow_jobs")}?page=3&search=&library=&review=&time_range=all"',
        )

    def test_current_page_is_non_actionable(self):
        response = self._render_fragment({"page": 2}, total=60, has_next=True)

        self.assertContains(response, '<span class="page-link" aria-current="page">2</span>')
        self.assertNotContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_jobs")}?page=2&search=&library=&review=&time_range=all"',
        )

    def test_pagination_carries_all_params(self):
        response = self._render_fragment(
            {"search": "foo", "library": "lib-a", "review": "reviewed", "time_range": "1d", "page": 1},
            total=40,
            has_next=True,
        )

        self.assertContains(
            response,
            "search=foo&library=lib-a&review=reviewed&time_range=1d",
        )

    def test_pagination_urlencodes_values(self):
        response = self._render_fragment({"search": "S2306* & co", "page": 1}, total=40, has_next=True)

        self.assertContains(response, "search=S2306%2A%20%26%20co")
        self.assertNotContains(response, "search=S2306* & co")

    def test_pagination_absent_when_single_page(self):
        response = self._render_fragment({}, total=5)

        self.assertNotContains(response, "Pagination")
        self.assertNotContains(response, "page-item")
        self.assertNotContains(response, 'rel="next"')
        self.assertNotContains(response, 'rel="prev"')

    def test_pagination_prev_hidden_on_first_page(self):
        response = self._render_fragment({"page": 1}, total=40, has_next=True)

        self.assertNotContains(response, 'rel="prev"')
        self.assertContains(response, 'rel="next"')

    def test_pagination_out_of_range_renders_recovery_links(self):
        # page=99 with 3 total pages (60 results / 20 per page): the window is
        # clamped to the last valid page so numbered recovery links and a
        # current-page marker are still rendered.
        response = self._render_fragment({"page": 99}, total=60, has_next=False)

        self.assertContains(response, 'aria-label="Pagination"')
        self.assertContains(response, 'aria-current="page"')
        self.assertContains(response, '<span class="page-link" aria-current="page">3</span>')
        for p in (1, 2):
            self.assertContains(
                response,
                f'href="{reverse("bilbyui:gwflow_jobs")}?page={p}&search=&library=&review=&time_range=all"',
            )
        self.assertNotContains(response, "page=99")

    # ------------------------------------------------------------------
    # Sentinel removal
    # ------------------------------------------------------------------
    def test_paging_sentinel_file_and_references_removed(self):
        self.assertFalse((TEMPLATES_DIR / "_paging_sentinel.html").exists())
        for template_path in TEMPLATES_DIR.glob("*.html"):
            self.assertNotIn("_paging_sentinel", template_path.read_text())

    # ------------------------------------------------------------------
    # Page templates pass search-form include params
    # ------------------------------------------------------------------
    def test_gwflow_page_passes_search_form_params(self):
        source = get_template("bilbyui/gwflow_jobs.html").template.source

        self.assertIn('search_help_template="bilbyui/_gwflow_search_help.html"', source)
        self.assertIn("show_gwflow_filters=True", source)
        self.assertIn("filter_options=filter_options", source)
        self.assertIn('list_target_id="gwflow-job-list"', source)

    def test_my_jobs_page_passes_search_form_params(self):
        source = get_template("bilbyui/my_jobs.html").template.source

        self.assertIn('search_help_template="bilbyui/_bilby_search_help.html"', source)
        self.assertIn("show_gwflow_filters=False", source)
        self.assertIn('list_target_id="job-list"', source)

    def test_public_jobs_page_passes_search_form_params(self):
        source = get_template("bilbyui/public_jobs.html").template.source

        self.assertIn('search_help_template="bilbyui/_bilby_search_help.html"', source)
        self.assertIn("show_gwflow_filters=False", source)
        self.assertIn('list_target_id="job-list"', source)

    # ------------------------------------------------------------------
    # Integration: full gwflow page renders chips + pagination together
    # ------------------------------------------------------------------
    def test_gwflow_view_renders_count_chips_and_pagination(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user)
        response = self._get_gwflow(
            {"search": "foo", "library": "lib-a", "review": "reviewed", "time_range": "1d"},
            total=40,
            has_next=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "40 superevents match")
        self.assertContains(response, 'aria-label="Remove search filter"')
        self.assertContains(response, "Reset all")
        self.assertContains(response, 'aria-label="Pagination"')
        self.assertContains(response, 'aria-current="page"')

    def test_chip_reset_pagination_and_retry_source_wiring(self):
        surfaces = (
            (
                "bilbyui/_gwflow_job_list_fragment.html",
                "gwflow-job-list",
                "gwflow-loading-indicator",
            ),
            (
                "bilbyui/_job_list_fragment.html",
                "job-list",
                "my-jobs-loading-indicator",
            ),
            (
                "bilbyui/_job_list_fragment.html",
                "job-list",
                "public-jobs-loading-indicator",
            ),
        )

        for fragment_template, list_target_id, indicator_id in surfaces:
            with self.subTest(surface=indicator_id, source="pagination"):
                html = self._render_fragment(
                    total=60,
                    page_size=20,
                    has_next=True,
                    fragment_template=fragment_template,
                    list_target_id=list_target_id,
                    indicator_id=indicator_id,
                ).content.decode()
                links = re.findall(
                    r'<a\b[^>]*data-pagination-focus="true"[^>]*>',
                    html,
                )
                self.assertTrue(links)
                for link in links:
                    self.assertRegex(link, r'data-page="\d+"')
                    self.assertIn(f'hx-target="#{list_target_id}"', link)
                    self.assertIn(f'hx-indicator="#{indicator_id}"', link)

            with self.subTest(surface=indicator_id, source="Retry"):
                html = self._render_fragment(
                    service_state="down",
                    fragment_template=fragment_template,
                    list_target_id=list_target_id,
                    indicator_id=indicator_id,
                ).content.decode()
                retry = re.search(r"<button\b[^>]*>Retry</button>", html)
                self.assertIsNotNone(retry)
                self.assertIn(f'hx-target="#{list_target_id}"', retry.group(0))
                self.assertIn(f'hx-indicator="#{indicator_id}"', retry.group(0))
                self.assertIn('hx-sync="#jobs-search-region:replace"', retry.group(0))

            with self.subTest(surface=indicator_id, source="chips and Reset"):
                html = self._render_fragment(
                    params={"search": "foo", "library": "lib-a"},
                    fragment_template=fragment_template,
                    list_target_id=list_target_id,
                    indicator_id=indicator_id,
                ).content.decode()
                chip = re.search(r"<a\b[^>]*data-filter-param[^>]*>", html)
                reset = re.search(r"<a\b[^>]*data-filter-reset[^>]*>", html)
                self.assertIsNotNone(chip)
                self.assertIsNotNone(reset)
                self.assertIn('class="filter-chip-remove"', chip.group(0))
                for control in (chip.group(0), reset.group(0)):
                    self.assertIn(f'hx-target="#{list_target_id}"', control)
                    self.assertIn(f'hx-indicator="#{indicator_id}"', control)


class TestUX18ServerRenderedContract(BilbyTestCase):
    def setUp(self):
        self.authenticate()

    def _fragment(self, **overrides):
        request = RequestFactory().get("/gwflow/", HTTP_HX_REQUEST="true")
        request.user = self.user
        values = {
            "rows": [],
            "has_next": False,
            "total": 3,
            "page_size": 20,
            "jobs_list_url_name": "bilbyui:gwflow_jobs",
            "template_name": "bilbyui/gwflow_jobs.html",
            "fragment_template_name": "bilbyui/_gwflow_job_list_fragment.html",
            "list_target_id": "gwflow-job-list",
            "indicator_id": "gwflow-loading-indicator",
            "region_id": "gwflow-results-region",
            "region_heading_id": "gwflow-results-heading",
            "region_status_id": "gwflow-results-status",
        }
        values.update(overrides)
        return _render_job_list(request, **values).render().content.decode()

    def test_fragment_excludes_persistent_page_owners(self):
        html = self._fragment()
        for identifier in (
            "gwflow-results-region",
            "gwflow-loading-indicator",
            "gwflow-results-heading",
            "gwflow-results-status",
            "gwflow-job-list",
        ):
            self.assertNotIn(f'id="{identifier}"', html)
        self.assertNotIn('role="status"', html)
        self.assertNotIn("aria-live", html)

    def test_async_state_does_not_render_persistent_indicator(self):
        source = get_template("bilbyui/_async_state.html").template.source
        self.assertNotIn("_list_loading_indicator.html", source)
        self.assertNotIn("data-list-indicator-el", source)

    def test_settled_metadata_content_empty_and_error(self):
        content = self._fragment(total=3, rows=[{"sname": "S230601ag"}])
        self.assertIn('data-settled-kind="content"', content)
        self.assertIn('data-settled-message="3 superevents match"', content)
        self.assertNotIn('role="status"', content)
        self.assertNotIn("aria-live", content)

        empty = self._fragment(total=0)
        self.assertIn('data-settled-kind="empty"', empty)
        self.assertIn("No superevents yet.", empty)
        self.assertNotIn('role="status"', empty)
        self.assertNotIn("aria-live", empty)

        error = self._fragment(total=0, service_state="down")
        self.assertIn('data-settled-kind="error"', error)
        wrapper = re.search(r'<div class="list-fragment"[^>]*>', error)
        self.assertIsNotNone(wrapper)
        self.assertNotIn("data-settled-message", wrapper.group(0))
        self.assertEqual(error.count('role="alert"'), 1)
        self.assertNotIn('role="status"', error)
