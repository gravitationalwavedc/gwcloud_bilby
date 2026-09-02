"""Direct unit tests for the URL-builder helpers in views.py.

Covers _build_jobs_list_url and _build_active_filters (issue #51, task-4):
URL quoting, empty-param removal, time_range == "all" skip, page reset to 1,
and the no-query URL fallback.
"""

from django.urls import reverse

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _build_active_filters, _build_jobs_list_url

URL_NAME = "bilbyui:gwflow_jobs"


class TestBuildJobsListUrl(BilbyTestCase):
    def test_no_params_returns_plain_url(self):
        self.assertEqual(_build_jobs_list_url(URL_NAME, {}), reverse(URL_NAME))

    def test_params_are_quoted(self):
        url = _build_jobs_list_url(URL_NAME, {"search": "S2306* & co"})
        self.assertEqual(url, f"{reverse(URL_NAME)}?search=S2306%2A%20%26%20co")

    def test_multiple_params_joined_with_ampersand(self):
        url = _build_jobs_list_url(URL_NAME, {"search": "foo", "page": 1})
        self.assertEqual(url, f"{reverse(URL_NAME)}?search=foo&page=1")


class TestBuildActiveFilters(BilbyTestCase):
    def test_no_active_filters_when_all_empty(self):
        self.assertEqual(_build_active_filters(URL_NAME, "", "", "", "all"), [])

    def test_time_range_all_produces_no_chip(self):
        filters = _build_active_filters(URL_NAME, "foo", "", "", "all")
        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0]["param_name"], "search")

    def test_each_filter_removes_only_itself_and_resets_page(self):
        filters = _build_active_filters(URL_NAME, "foo", "lib-a", "reviewed", "1d")
        self.assertEqual(len(filters), 4)
        for f in filters:
            self.assertIn("page=1", f["remove_url"])
            self.assertNotIn(f"{f['param_name']}={f['param_value']}", f["remove_url"])

    def test_remove_url_keeps_remaining_params(self):
        filters = _build_active_filters(URL_NAME, "foo", "lib-a", "", "")
        library_chip = next(f for f in filters if f["param_name"] == "library")
        self.assertEqual(
            library_chip["remove_url"],
            f"{reverse(URL_NAME)}?search=foo&page=1",
        )

    def test_remove_url_quotes_values(self):
        filters = _build_active_filters(URL_NAME, "S2306* & co", "lib-a", "", "")
        library_chip = next(f for f in filters if f["param_name"] == "library")
        self.assertEqual(
            library_chip["remove_url"],
            f"{reverse(URL_NAME)}?search=S2306%2A%20%26%20co&page=1",
        )
