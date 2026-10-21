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
from html import escape
from pathlib import Path
from unittest import mock

from django.template.loader import get_template
from django.urls import reverse

from bilbyui.services.search_help import build_search_help
from bilbyui.templatetags.frontend_tags import code_spans
from bilbyui.tests.testcases import BilbyTestCase


def _render_search_form(**overrides):
    """Render ``_search_form.html`` directly with a full context."""
    context = {
        "jobs_list_url_name": "bilbyui:gwflow_jobs",
        "list_target_id": "gwflow-job-list",
        "search_help_template": "bilbyui/_gwflow_search_help.html",
        "search_help": build_search_help("gwflow"),
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

    def test_advanced_syntax_placeholder_is_surface_specific(self):
        gwflow_html = _render_search_form()
        bilby_html = _render_search_form(
            jobs_list_url_name="bilbyui:my_jobs",
            list_target_id="job-list",
            search_help_template="bilbyui/_bilby_search_help.html",
            search_help=build_search_help("bilby"),
            show_gwflow_filters=False,
        )

        self.assertIn('placeholder="Try sname:S2306*"', gwflow_html)
        self.assertNotIn('placeholder="Try job.name:GW150914*"', gwflow_html)
        self.assertIn('placeholder="Try job.name:GW150914*"', bilby_html)
        self.assertNotIn('placeholder="Try sname:S2306*"', bilby_html)
        for html in (gwflow_html, bilby_html):
            self.assertIn('placeholder="Find a superevent..."', html)
            self.assertIn('<label for="advanced-search">Advanced syntax:</label>', html)
            self.assertIn("(?)", html)

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
    """The help partials render generic registry data in nested collapses."""

    def _render_help(self, template_name, surface):
        return get_template(template_name).render({"search_help": build_search_help(surface)})

    def _assert_nested_disclosure(self, html):
        self.assertIn('class="collapse mt-2" id="search-help"', html)
        self.assertIn("Full supported field reference", html)
        self.assertIn('type="button"', html)
        self.assertIn('data-toggle="collapse"', html)
        self.assertIn('data-target="#search-help-full"', html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('aria-controls="search-help-full"', html)
        self.assertIn('class="collapse mt-2" id="search-help-full"', html)
        self.assertNotIn("data-bs-toggle", html)
        self.assertNotIn("data-bs-target", html)
        self.assertNotIn("aria-live=", html)
        self.assertNotIn('role="status"', html)

    def test_gwflow_help_renders_four_common_fields_from_registry(self):
        help_context = build_search_help("gwflow")
        html = self._render_help("bilbyui/_gwflow_search_help.html", "gwflow")

        self.assertIn(str(code_spans(help_context["syntax_hint"])), html)
        self.assertIn("<strong>Common fields</strong>", html)
        self.assertEqual(len(help_context["common"]), 4)
        for entry in help_context["common"]:
            self.assertIn(f"<code>{entry['advertised']}</code>", html)
            self.assertIn(str(code_spans(entry["description"])), html)
        self.assertEqual(
            sum(f"<code>{entry['advertised']}</code>" in html for entry in help_context["common"]),
            4,
        )
        examples_html = html.split("Examples:</p>", 1)[1].split("</ul>", 1)[0]
        self.assertEqual(
            re.findall(r"<code>(.*?)</code>", examples_html),
            [escape(example) for example in help_context["examples"]],
        )
        self.assertIn(str(code_spans(help_context["typed_note"])), html)
        self.assertIn(str(code_spans(help_context["alias_note"])), html)
        self.assertNotIn("metadata.ParameterEstimation", html)
        self.assertNotIn("metadata.GraceDB", html)
        self._assert_nested_disclosure(html)

    def test_bilby_help_renders_four_common_fields_from_registry(self):
        help_context = build_search_help("bilby")
        html = self._render_help("bilbyui/_bilby_search_help.html", "bilby")

        self.assertIn(str(code_spans(help_context["syntax_hint"])), html)
        self.assertIn("<strong>Common fields</strong>", html)
        self.assertEqual(len(help_context["common"]), 4)
        for entry in help_context["common"]:
            self.assertIn(f"<code>{entry['advertised']}</code>", html)
            self.assertIn(str(code_spans(entry["description"])), html)
        self.assertEqual(
            sum(f"<code>{entry['advertised']}</code>" in html for entry in help_context["common"]),
            4,
        )
        examples_html = html.split("Examples:</p>", 1)[1].split("</ul>", 1)[0]
        self.assertEqual(
            re.findall(r"<code>(.*?)</code>", examples_html),
            [escape(example) for example in help_context["examples"]],
        )
        self.assertIn(str(code_spans(help_context["typed_note"])), html)
        self._assert_nested_disclosure(html)

    def test_plain_help_renders_only_plain_hint(self):
        help_context = build_search_help("plain")
        html = self._render_help("bilbyui/_plain_search_help.html", "plain")

        self.assertIn(str(code_spans(help_context["syntax_hint"])), html)
        self.assertNotIn("Common fields", html)
        self.assertNotIn("Examples:", html)
        self.assertNotIn("Full supported field reference", html)
        self.assertNotIn('data-target="#search-help-full"', html)
        self.assertNotIn("<code>job.name</code>", html)

    def test_help_templates_contain_no_literal_registry_field_names(self):
        advertised_fields = {
            str(entry["advertised"])
            for surface in ("gwflow", "bilby")
            for entry in (
                build_search_help(surface)["common"]
                + [field for group in build_search_help(surface)["groups"] for field in group["fields"]]
            )
        }
        for template_name in (
            "_gwflow_search_help.html",
            "_bilby_search_help.html",
        ):
            source = (Path(__file__).parents[1] / "templates" / "bilbyui" / template_name).read_text()
            for field in advertised_fields:
                self.assertNotIn(field, source)

    def test_form_includes_selected_help_template(self):
        html = _render_search_form(
            search_help_template="bilbyui/_bilby_search_help.html",
            search_help=build_search_help("bilby"),
        )
        self.assertIn("<code>job.name</code>", html)
        self.assertIn("Full supported field reference", html)
        self.assertNotIn("metadata.ParameterEstimation", html)
        self.assertNotIn("metadata.GraceDB", html)

    def test_sync_script_defaults_time_range_to_all(self):
        html = get_template("bilbyui/_search_state_sync.html").render({})
        self.assertIn('name === "time_range" ? "all" : ""', html)
        self.assertNotIn(
            '"page"',
            html.split("forEach")[1].split(";")[0],
            "page must not be restored from the URL",
        )

    def test_sync_script_does_not_restore_page(self):
        html = get_template("bilbyui/_search_state_sync.html").render({})
        self.assertNotIn('"search", "library", "review", "time_range", "page"', html)
        self.assertIn('["search", "library", "review", "time_range"]', html)

    def test_sync_script_no_longer_listens_to_pushed_into_history(self):
        html = get_template("bilbyui/_search_state_sync.html").render({})
        self.assertNotIn("pushedIntoHistory", html)

    def test_sync_script_still_listens_to_popstate_and_history_restore(self):
        html = get_template("bilbyui/_search_state_sync.html").render({})
        self.assertIn("popstate", html)
        self.assertIn("htmx:historyRestore", html)


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
        self.assertContains(response, "<code>sname</code>")
        self.assertContains(response, 'hx-sync="#jobs-search-region:replace"')

    @mock.patch("bilbyui.views.list_user_jobs", return_value=_user_jobs_ok_result())
    def test_my_jobs_surface_renders_plain_help(self, mock_jobs):
        response = self.client.get(reverse("bilbyui:my_jobs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="search-help"')
        self.assertContains(response, "Search matches your job name and description.")
        self.assertNotContains(response, "<code>job.name</code>")
        self.assertNotContains(response, "Full supported field reference")
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


class TestListSurfaceLoadingContract(BilbyTestCase):
    surfaces = {
        "gwflow": {
            "url": "/gwflow/",
            "patch": "bilbyui.views.list_gwflow_jobs",
            "result": _gwflow_ok_result,
            "region": "gwflow-results-region",
            "target": "gwflow-job-list",
            "indicator": "gwflow-loading-indicator",
            "heading": "gwflow-results-heading",
            "status": "gwflow-results-status",
            "filters": True,
        },
        "my-jobs": {
            "url": "/job-list/",
            "patch": "bilbyui.views.list_user_jobs",
            "result": _user_jobs_ok_result,
            "region": "my-jobs-results-region",
            "target": "job-list",
            "indicator": "my-jobs-loading-indicator",
            "heading": "my-jobs-results-heading",
            "status": "my-jobs-results-status",
            "filters": False,
        },
        "public-jobs": {
            "url": "/",
            "patch": "bilbyui.views.list_public_jobs",
            "result": _public_jobs_ok_result,
            "region": "public-jobs-results-region",
            "target": "job-list",
            "indicator": "public-jobs-loading-indicator",
            "heading": "public-jobs-results-heading",
            "status": "public-jobs-results-status",
            "filters": False,
        },
    }

    def setUp(self):
        self.authenticate()

    def _page(self, spec):
        with mock.patch(spec["patch"], return_value=spec["result"]()):
            return self.client.get(spec["url"]).content.decode()

    def test_each_page_has_one_normative_owner_set(self):
        for surface, spec in self.surfaces.items():
            with self.subTest(surface=surface):
                html = self._page(spec)
                for identifier in (
                    spec["region"],
                    spec["target"],
                    spec["indicator"],
                    spec["heading"],
                    spec["status"],
                ):
                    self.assertEqual(html.count(f'id="{identifier}"'), 1)
                region = re.search(
                    rf'<div[^>]*id="{spec["region"]}"[^>]*>',
                    html,
                )
                self.assertIsNotNone(region)
                tag = region.group(0)
                self.assertIn('role="region"', tag)
                self.assertIn(f'aria-labelledby="{spec["heading"]}"', tag)
                self.assertIn('aria-busy="false"', tag)
                self.assertIn("data-list-region", tag)
                self.assertIn(f'data-list-target="{spec["target"]}"', tag)
                self.assertIn(f'data-list-indicator="{spec["indicator"]}"', tag)
                self.assertIn(f'data-list-heading="{spec["heading"]}"', tag)
                self.assertIn(f'data-list-status="{spec["status"]}"', tag)

    def test_search_advanced_and_filter_source_wiring(self):
        for surface, spec in self.surfaces.items():
            with self.subTest(surface=surface):
                html = self._page(spec)
                form = re.search(r'<form[^>]*class="gwflow-search-form"[^>]*>', html, re.S)
                self.assertIsNotNone(form)
                self.assertIn(f'hx-target="#{spec["target"]}"', form.group(0))
                self.assertIn(f'hx-indicator="#{spec["indicator"]}"', form.group(0))
                self.assertIn('hx-sync="#jobs-search-region:replace"', form.group(0))
                for control_id in ("search", "time_range"):
                    tag = re.search(
                        rf'<(?:input|select)[^>]*id="{control_id}"[^>]*>',
                        html,
                    )
                    self.assertIsNotNone(tag)
                    self.assertIn(
                        f'hx-indicator="#{spec["indicator"]}"',
                        tag.group(0),
                    )
                advanced = re.search(
                    r'<input[^>]*id="advanced-search"[^>]*>',
                    html,
                )
                self.assertIsNotNone(advanced)
                self.assertNotIn("hx-get", advanced.group(0))
                self.assertNotIn("hx-target", advanced.group(0))
                for control_id in ("library", "review"):
                    tag = re.search(rf'<select[^>]*id="{control_id}"[^>]*>', html)
                    if spec["filters"]:
                        self.assertIsNotNone(tag)
                        self.assertIn(
                            f'hx-indicator="#{spec["indicator"]}"',
                            tag.group(0),
                        )
                    else:
                        self.assertIsNone(tag)

    def test_surface_by_source_matrix_marks_absent_sources_na(self):
        # Conditionally rendered chip, Reset, pagination, and Retry sources are
        # covered by the dedicated all-surface wiring test in
        # test_active_filters_pagination.py.
        selectors = {
            "search": 'id="search"',
            "advanced mirror": 'id="advanced-search"',
            "Library": 'id="library"',
            "Review": 'id="review"',
            "Updated": 'id="time_range"',
        }
        expected = {
            "gwflow": {
                "search": True,
                "advanced mirror": True,
                "Library": True,
                "Review": True,
                "Updated": True,
            },
            "my-jobs": {
                "search": True,
                "advanced mirror": True,
                "Library": False,
                "Review": False,
                "Updated": True,
            },
            "public-jobs": {
                "search": True,
                "advanced mirror": True,
                "Library": False,
                "Review": False,
                "Updated": True,
            },
        }
        for surface, spec in self.surfaces.items():
            html = self._page(spec)
            for source, present in expected[surface].items():
                with self.subTest(surface=surface, source=source):
                    self.assertEqual(selectors[source] in html, present)
