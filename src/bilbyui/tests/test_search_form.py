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
            "libraries": {
                "values": ["cbc-workflow-o4a", "cbc-workflow-o4c"],
                "state": "ok",
            },
            "review_statuses": {
                "values": ["reviewed", "unreviewed", "pending", "approved"],
                "state": "ok",
            },
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

    def test_search_trigger_is_composition_aware(self):
        """The search trigger must be composition-aware (issue #75 / UX-17):
        incomplete IME composition must not submit, and compositionend makes
        the final composed value eligible for the trailing search."""
        html = _render_search_form()
        self.assertTrue(
            "isComposing" in html or "compositionend" in html or "compositionstart" in html,
            "search trigger must be composition-aware",
        )

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


class TestSearchFormPerFacetStates(BilbyTestCase):
    """Per-facet filter-option rendering (issue #72 / ES-3, task-3).

    Each facet (Library, Review status) renders independently per its
    ``ok`` / ``stale`` / ``unavailable`` state:

    * ``ok``: enabled select; empty option set shows neutral "No options
      available" so successful emptiness is distinct from failure.
    * ``stale``: enabled select with cached values + adjacent "Options may be
      out of date", announced once via a shared ``role="alert"`` region.
    * ``unavailable``: disabled select + "Options are temporarily
      unavailable" associated via ``aria-describedby`` (a service problem,
      not a validation error).

    Degraded facets share ONE ``role="alert"`` region so at most one
    assertive announcement is made per settled interaction (Frontend Bible §5).
    """

    def _library_select(self, html):
        match = re.search(r"<select\b[^>]*name=\"library\"[^>]*>", html)
        return match.group(0) if match else ""

    def _review_select(self, html):
        match = re.search(r"<select\b[^>]*name=\"review\"[^>]*>", html)
        return match.group(0) if match else ""

    def test_ok_state_renders_enabled_select_with_values(self):
        html = _render_search_form()
        self.assertNotIn("disabled", self._library_select(html))
        self.assertNotIn("disabled", self._review_select(html))
        self.assertIn("cbc-workflow-o4a", html)
        self.assertIn("reviewed", html)
        self.assertNotIn("No options available", html)
        self.assertNotIn("Options may be out of date", html)
        self.assertNotIn("Options are temporarily unavailable", html)
        self.assertNotIn('role="alert"', html)

    def test_ok_state_empty_set_shows_neutral_copy(self):
        html = _render_search_form(
            filter_options={
                "libraries": {"values": [], "state": "ok"},
                "review_statuses": {"values": [], "state": "ok"},
            }
        )
        self.assertNotIn("disabled", self._library_select(html))
        self.assertNotIn("disabled", self._review_select(html))
        self.assertEqual(html.count("No options available"), 2)
        self.assertNotIn("Options are temporarily unavailable", html)
        self.assertNotIn('role="alert"', html)

    def test_stale_state_renders_enabled_select_with_cached_values_and_alert(self):
        html = _render_search_form(
            filter_options={
                "libraries": {"values": ["cbc-workflow-o4a"], "state": "stale"},
                "review_statuses": {"values": ["reviewed"], "state": "ok"},
            }
        )
        self.assertNotIn("disabled", self._library_select(html))
        self.assertIn("cbc-workflow-o4a", html)
        self.assertIn("Options may be out of date", html)
        self.assertIn('role="alert"', html)
        self.assertEqual(html.count('role="alert"'), 1, "exactly one assertive announcement")

    def test_unavailable_state_renders_disabled_select_with_aria_describedby(self):
        html = _render_search_form(
            filter_options={
                "libraries": {"values": [], "state": "unavailable"},
                "review_statuses": {"values": ["reviewed"], "state": "ok"},
            }
        )
        self.assertIn("disabled", self._library_select(html))
        self.assertNotIn("disabled", self._review_select(html))
        self.assertIn("Options are temporarily unavailable", html)
        self.assertIn('aria-describedby="library-options-status"', html)
        self.assertIn('id="library-options-status"', html)
        self.assertIn('role="alert"', html)
        self.assertEqual(html.count('role="alert"'), 1, "exactly one assertive announcement")
        self.assertNotIn("Error:", html)
        self.assertNotIn("is-invalid", html)

    def test_select_disabled_only_for_unavailable(self):
        for state in ("ok", "stale"):
            html = _render_search_form(
                filter_options={
                    "libraries": {"values": ["cbc-workflow-o4a"], "state": state},
                    "review_statuses": {"values": ["reviewed"], "state": "ok"},
                }
            )
            self.assertNotIn("disabled", self._library_select(html), f"library must be enabled when {state}")
        html = _render_search_form(
            filter_options={
                "libraries": {"values": [], "state": "unavailable"},
                "review_statuses": {"values": ["reviewed"], "state": "ok"},
            }
        )
        self.assertIn("disabled", self._library_select(html))

    def test_both_facets_unavailable_consolidate_to_single_alert(self):
        html = _render_search_form(
            filter_options={
                "libraries": {"values": [], "state": "unavailable"},
                "review_statuses": {"values": [], "state": "unavailable"},
            }
        )
        self.assertEqual(html.count('role="alert"'), 1, "one consolidated announcement")
        self.assertIn("Library options are temporarily unavailable.", html)
        self.assertIn("Review status options are temporarily unavailable.", html)
        self.assertIn("disabled", self._library_select(html))
        self.assertIn("disabled", self._review_select(html))

    def test_both_facets_stale_consolidate_to_single_alert(self):
        html = _render_search_form(
            filter_options={
                "libraries": {"values": ["cbc-workflow-o4a"], "state": "stale"},
                "review_statuses": {"values": ["reviewed"], "state": "stale"},
            }
        )
        self.assertEqual(html.count('role="alert"'), 1, "one consolidated announcement")
        self.assertIn("Library options may be out of date.", html)
        self.assertIn("Review status options may be out of date.", html)
        self.assertNotIn("disabled", self._library_select(html))
        self.assertNotIn("disabled", self._review_select(html))

    def test_mixed_degraded_facets_consolidate_to_single_alert(self):
        html = _render_search_form(
            filter_options={
                "libraries": {"values": [], "state": "unavailable"},
                "review_statuses": {"values": ["reviewed"], "state": "stale"},
            }
        )
        self.assertEqual(html.count('role="alert"'), 1, "one consolidated announcement")
        self.assertIn("Library options are temporarily unavailable.", html)
        self.assertIn("Review status options may be out of date.", html)
        self.assertIn("disabled", self._library_select(html))
        self.assertNotIn("disabled", self._review_select(html))

    def test_exact_copy_per_state(self):
        ok_html = _render_search_form(
            filter_options={
                "libraries": {"values": [], "state": "ok"},
                "review_statuses": {"values": ["reviewed"], "state": "ok"},
            }
        )
        self.assertIn("No options available", ok_html)
        stale_html = _render_search_form(
            filter_options={
                "libraries": {"values": ["cbc-workflow-o4a"], "state": "stale"},
                "review_statuses": {"values": ["reviewed"], "state": "ok"},
            }
        )
        self.assertIn("Options may be out of date", stale_html)
        unavailable_html = _render_search_form(
            filter_options={
                "libraries": {"values": [], "state": "unavailable"},
                "review_statuses": {"values": ["reviewed"], "state": "ok"},
            }
        )
        self.assertIn("Options are temporarily unavailable", unavailable_html)

    def test_no_alert_when_both_facets_ok(self):
        html = _render_search_form()
        self.assertNotIn('role="alert"', html)


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

    def test_sync_script_no_longer_listens_to_pushed_into_history(self):
        """Issue #75 / UX-17: the ``htmx:pushedIntoHistory`` write-back is
        removed so a settled history push can never clobber the live input."""
        html = get_template("bilbyui/_search_state_sync.html").render({})
        self.assertNotIn("pushedIntoHistory", html)

    def test_sync_script_still_listens_to_popstate_and_history_restore(self):
        """URL -> form sync is retained only for genuine back/forward and
        htmx history restoration."""
        html = get_template("bilbyui/_search_state_sync.html").render({})
        self.assertIn("popstate", html)
        self.assertIn("htmx:historyRestore", html)

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

    @mock.patch(
        "bilbyui.views.list_gwflow_filter_options",
        return_value={
            "libraries": {"values": [], "state": "ok"},
            "review_statuses": {"values": [], "state": "ok"},
        },
    )
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

    @mock.patch(
        "bilbyui.views.list_gwflow_filter_options",
        return_value={
            "libraries": {"values": [], "state": "ok"},
            "review_statuses": {"values": [], "state": "ok"},
        },
    )
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
