"""Template tests for the search form partial and surface-specific help partials.

Issue #51 (UX-4 GWFlow search/filtering/pagination), task-3. Renders
``_search_form.html`` directly (via ``get_template``) and through the three
job-list views, asserting the coordinated-form contract:

* every control has a programmatic ``<label>`` (WCAG 3.3.2)
* one coordinated request stream (``hx-sync="#jobs-search-region:replace"`` + 300 ms debounce)
* hidden ``page=1`` reset on any filter change
* GWFlow-only selects appear only when ``show_gwflow_filters``
* the advanced-syntax input is always visible
* the in-place help panel is present on all three surfaces with the
  surface-specific partial
"""

import re
from unittest import mock

from django.template.loader import get_template
from django.urls import reverse

from bilbyui.tests.testcases import BilbyTestCase


def _render_search_form(**overrides):
    """Render ``_search_form.html`` directly with a full context."""
    context = {
        "jobs_list_url_name": "bilbyui:gwflow_jobs",
        "list_target_id": "gwflow-job-list",
        "search_help_template": "bilbyui/_gwflow_search_help.html",
        "filter_options": {
            "libraries": ["cbc-workflow-o4a", "cbc-workflow-o4c"],
            "review_statuses": ["reviewed", "unreviewed", "pending", "approved"],
        },
        "search": "",
        "library": "",
        "review": "",
        "time_range": "all",
    }
    context.update(overrides)
    return get_template("bilbyui/_search_form.html").render(context)


def _named_control_ids(html):
    """Map ``name`` -> ``id`` for every named input/select in the form.

    The hidden ``page`` input has no ``id`` and is intentionally skipped.
    """
    controls = {}
    for tag in re.findall(r"<(?:input|select)\b[^>]*>", html):
        name = re.search(r'name="([^"]+)"', tag)
        cid = re.search(r'id="([^"]+)"', tag)
        if name and cid:
            controls[name.group(1)] = cid.group(1)
    return controls


def _labelled_ids(html):
    """Return the set of ids referenced by ``<label for="...">`` elements."""
    return set(re.findall(r'<label[^>]*for="([^"]+)"', html))


def _gwflow_ok_result():
    return {
        "jobs": {},
        "records": [],
        "has_next": False,
        "page": 1,
        "page_size": 20,
        "total": 0,
        "state": "ok",
    }


def _user_jobs_ok_result():
    return {
        "jobs": [],
        "has_next": False,
        "total": 0,
        "page": 1,
        "page_size": 20,
        "state": "ok",
    }


def _public_jobs_ok_result():
    return {
        "jobs": {},
        "records": [],
        "job_controller_jobs": {},
        "has_next": False,
        "total": 0,
        "page": 1,
        "page_size": 20,
        "state": "ok",
    }


class TestSearchFormStructure(BilbyTestCase):
    """Direct-render contract tests for ``_search_form.html``."""

    def test_every_control_has_programmatic_label(self):
        html = _render_search_form()
        labelled = _labelled_ids(html)
        for name, cid in _named_control_ids(html).items():
            self.assertIn(
                cid,
                labelled,
                f"control name={name!r} id={cid!r} has no <label for>",
            )

    def test_every_control_has_programmatic_label_without_gwflow_filters(self):
        html = _render_search_form(show_gwflow_filters=False)
        labelled = _labelled_ids(html)
        for name, cid in _named_control_ids(html).items():
            self.assertIn(cid, labelled, f"control name={name!r} id={cid!r} has no <label for>")

    def test_form_has_coordinated_htmx_attributes(self):
        html = _render_search_form()
        self.assertIn('hx-sync="#jobs-search-region:replace"', html)
        self.assertIn('hx-push-url="true"', html)
        self.assertIn('hx-swap="innerHTML"', html)
        self.assertIn('hx-get="/gwflow/"', html)

    def test_form_targets_list_region_not_itself(self):
        html = _render_search_form()
        self.assertIn('hx-target="#gwflow-job-list"', html)
        self.assertNotIn('hx-target="#search', html)

    def test_hidden_page_input_resets_to_one(self):
        html = _render_search_form()
        self.assertIn('<input type="hidden" name="page" value="1">', html)

    def test_search_input_has_300ms_debounce(self):
        html = _render_search_form()
        self.assertIn('name="search"', html)
        self.assertIn('hx-trigger="input changed delay:300ms, search"', html)

    def test_advanced_syntax_input_always_visible_and_single(self):
        html = _render_search_form()
        self.assertEqual(html.count('name="search"'), 1)
        self.assertIn('id="search"', html)
        self.assertIn('<label for="search">Search</label>', html)
        self.assertIn('<label for="advanced-search">Advanced syntax:</label>', html)
        self.assertIn('id="advanced-search"', html)
        self.assertEqual(html.count('<label for="search"'), 1, "search input must have exactly one label (WCAG 3.3.2)")

    def test_gwflow_selects_rendered_when_show_gwflow_filters(self):
        html = _render_search_form(show_gwflow_filters=True)
        self.assertIn('name="library"', html)
        self.assertIn('name="review"', html)
        self.assertIn("cbc-workflow-o4a", html)
        self.assertIn("reviewed", html)

    def test_gwflow_selects_absent_without_show_gwflow_filters(self):
        html = _render_search_form(
            jobs_list_url_name="bilbyui:my_jobs",
            list_target_id="job-list",
            show_gwflow_filters=False,
        )
        self.assertNotIn('name="library"', html)
        self.assertNotIn('name="review"', html)

    def test_gwflow_selects_absent_on_bilby_url_without_param(self):
        html = _render_search_form(
            jobs_list_url_name="bilbyui:public_jobs",
            list_target_id="job-list",
        )
        self.assertNotIn('name="library"', html)
        self.assertNotIn('name="review"', html)

    def test_gwflow_selects_default_on_gwflow_url_without_param(self):
        html = _render_search_form(jobs_list_url_name="bilbyui:gwflow_jobs")
        self.assertIn('name="library"', html)
        self.assertIn('name="review"', html)

    def test_updated_select_present_on_all_surfaces(self):
        html = _render_search_form(show_gwflow_filters=False)
        self.assertIn('name="time_range"', html)
        for label in (
            "Any time",
            "Updated past 24 hours",
            "Updated past week",
            "Updated past month",
            "Updated past year",
        ):
            self.assertIn(label, html)

    def test_help_toggle_button_present(self):
        html = _render_search_form()
        self.assertIn('data-target="#search-help"', html)
        self.assertIn('aria-label="Search help"', html)

    def test_mobile_filters_disclosure_button_present(self):
        html = _render_search_form()
        self.assertIn('data-target="#search-filters"', html)
        self.assertIn("Filters", html)

    def test_current_values_are_preserved(self):
        html = _render_search_form(
            search="sname:S2306*",
            library="cbc-workflow-o4c",
            review="reviewed",
            time_range="1w",
        )
        self.assertIn('value="sname:S2306*"', html)
        self.assertIn('value="cbc-workflow-o4c" selected', html)
        self.assertIn('value="reviewed" selected', html)
        self.assertIn('value="1w" selected', html)


class TestSearchHelpPartials(BilbyTestCase):
    """The help partials render as in-place collapsible panels."""

    def test_gwflow_help_lists_all_searchable_fields(self):
        html = get_template("bilbyui/_gwflow_search_help.html").render({})
        self.assertIn('id="search-help"', html)
        self.assertIn('class="collapse mt-2"', html)
        for field in (
            "sname",
            "libraries",
            "schemaVersion",
            "analyses.uid",
            "analyses.software",
            "analyses.waveform",
            "analyses.analysts",
            "analyses.reviewers",
            "analyses.runStatus",
            "analyses.reviewStatus",
            "gracedb.uids",
            "gracedb.instruments",
            "eventId.triggerId",
        ):
            self.assertIn(f"<code>{field}</code>", html)
        self.assertIn("sname:S2306*", html)
        for abbreviation in ("UID", "PE", "TGR", "GraceDB", "CBC"):
            self.assertIn(f"<code>{abbreviation}</code>", html)

    def test_sync_script_defaults_time_range_to_all(self):
        html = get_template("bilbyui/_search_state_sync.html").render({})
        self.assertIn('name === "time_range" ? "all" : ""', html)
        self.assertNotIn('"page"', html.split("forEach")[1].split(";")[0], "page must not be restored from the URL")

    def test_sync_script_does_not_restore_page(self):
        html = get_template("bilbyui/_search_state_sync.html").render({})
        # The hidden page control must keep its form default of 1 so a filter
        # change after history restoration resets to page 1 (GOV.UK rule).
        self.assertNotIn('"search", "library", "review", "time_range", "page"', html)
        self.assertIn('["search", "library", "review", "time_range"]', html)

    def test_bilby_help_lists_all_searchable_fields(self):
        html = get_template("bilbyui/_bilby_search_help.html").render({})
        self.assertIn('id="search-help"', html)
        self.assertIn('class="collapse mt-2"', html)
        for field in (
            "job.name",
            "job.description",
            "labels.name",
            "eventId.eventId",
            "eventId.triggerId",
            "eventId.nickname",
            "params.*",
            "ini.*",
        ):
            self.assertIn(f"<code>{field}</code>", html)
        self.assertIn("job.name:GW150914*", html)

    def test_form_includes_selected_help_template(self):
        html = _render_search_form(search_help_template="bilbyui/_bilby_search_help.html")
        self.assertIn("<code>job.name</code>", html)
        self.assertNotIn("<code>analyses.waveform</code>", html)


class TestHelpOnAllSurfaces(BilbyTestCase):
    """The three job-list views render their respective help partial."""

    def setUp(self):
        self.authenticate()

    @mock.patch("bilbyui.views.list_gwflow_filter_options", return_value={"libraries": [], "review_statuses": []})
    @mock.patch("bilbyui.views.list_gwflow_jobs", return_value=_gwflow_ok_result())
    def test_gwflow_surface_renders_gwflow_help(self, mock_jobs, mock_options):
        response = self.client.get(reverse("bilbyui:gwflow_jobs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="search-help"')
        self.assertContains(response, "<code>analyses.waveform</code>")
        self.assertContains(response, 'hx-sync="#jobs-search-region:replace"')

    @mock.patch("bilbyui.views.list_user_jobs", return_value=_user_jobs_ok_result())
    def test_my_jobs_surface_renders_bilby_help(self, mock_jobs):
        response = self.client.get(reverse("bilbyui:my_jobs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="search-help"')
        self.assertContains(response, "<code>job.name</code>")
        self.assertContains(response, 'hx-sync="#jobs-search-region:replace"')

    @mock.patch("bilbyui.views.list_public_jobs", return_value=_public_jobs_ok_result())
    def test_public_jobs_surface_renders_bilby_help(self, mock_jobs):
        response = self.client.get(reverse("bilbyui:public_jobs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="search-help"')
        self.assertContains(response, "<code>job.name</code>")
        self.assertContains(response, 'hx-sync="#jobs-search-region:replace"')

    @mock.patch("bilbyui.views.list_gwflow_filter_options", return_value={"libraries": [], "review_statuses": []})
    @mock.patch("bilbyui.views.list_gwflow_jobs", return_value=_gwflow_ok_result())
    def test_gwflow_surface_shows_gwflow_selects(self, mock_jobs, mock_options):
        response = self.client.get(reverse("bilbyui:gwflow_jobs"))
        self.assertContains(response, 'name="library"')
        self.assertContains(response, 'name="review"')

    @mock.patch("bilbyui.views.list_user_jobs", return_value=_user_jobs_ok_result())
    def test_my_jobs_surface_hides_gwflow_selects(self, mock_jobs):
        response = self.client.get(reverse("bilbyui:my_jobs"))
        self.assertNotContains(response, 'name="library"')
        self.assertNotContains(response, 'name="review"')
