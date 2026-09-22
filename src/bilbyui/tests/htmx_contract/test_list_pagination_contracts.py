"""Data-driven issue #77 list pagination accessibility contracts."""

from html.parser import HTMLParser
from pathlib import Path

from django.test import SimpleTestCase

from .registry import REGISTRY

TEMPLATES = Path(__file__).resolve().parents[2] / "templates" / "bilbyui"
SURFACES = {
    "gwflow_list_search_filter_pagination": (
        "gwflow_jobs.html",
        "_gwflow_job_list_fragment.html",
        "gwflow-results-region",
        "gwflow-results-heading",
        "gwflow-results-status",
    ),
    "my_jobs_list_search_filter_pagination": (
        "my_jobs.html",
        "_job_list_fragment.html",
        "my-jobs-results-region",
        "my-jobs-results-heading",
        "my-jobs-results-status",
    ),
    "public_jobs_list_search_filter_pagination": (
        "public_jobs.html",
        "_job_list_fragment.html",
        "public-jobs-results-region",
        "public-jobs-results-heading",
        "public-jobs-results-status",
    ),
}


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def by_id(self, element_id):
        return [attrs for _, attrs in self.tags if attrs.get("id") == element_id]


class ListPaginationContractTests(SimpleTestCase):
    def test_registry_declares_equivalent_focus_and_capabilities(self):
        contracts = {contract.name: contract for contract in REGISTRY}
        for name, (_, _, _, heading, _) in SURFACES.items():
            with self.subTest(surface=name):
                contract = contracts[name]
                self.assertEqual(contract.focus.rule, "explicit_pagination_heading")
                self.assertEqual(contract.focus.selector, f"#{heading}")
                self.assertTrue(
                    {"focus", "history", "announcement", "loading"}
                    <= contract.capabilities
                )

    def test_shell_has_one_persistent_heading_and_polite_atomic_status(self):
        for name, (page, _, region_id, heading_id, status_id) in SURFACES.items():
            with self.subTest(surface=name):
                parser = Markup()
                parser.feed((TEMPLATES / page).read_text())
                region = parser.by_id(region_id)
                heading = parser.by_id(heading_id)
                status = parser.by_id(status_id)
                self.assertEqual(len(region), 1)
                self.assertEqual(region[0]["data-list-heading"], heading_id)
                self.assertEqual(region[0]["data-list-status"], status_id)
                self.assertEqual(len(heading), 1)
                self.assertEqual(heading[0].get("tabindex"), "-1")
                self.assertEqual(len(status), 1)
                self.assertEqual(status[0].get("role"), "status")
                self.assertEqual(status[0].get("aria-live"), "polite")
                self.assertEqual(status[0].get("aria-atomic"), "true")

    def test_fragments_publish_title_and_page_message_without_live_list(self):
        for name, (_, fragment, _, _, _) in SURFACES.items():
            with self.subTest(surface=name):
                source = (TEMPLATES / fragment).read_text()
                parser = Markup()
                parser.feed(source)
                roots = [
                    attrs for _, attrs in parser.tags
                    if "data-settled-kind" in attrs
                ]
                self.assertTrue(roots)
                self.assertTrue(all("data-document-title" in root for root in roots))
                messages = [
                    root["data-settled-message"]
                    for root in roots if "data-settled-message" in root
                ]
                self.assertTrue(messages)
                self.assertTrue(any("pagination_page" in message for message in messages))
                list_roots = [
                    attrs
                    for _, attrs in parser.tags
                    if "list-fragment" in (attrs.get("class") or "").split()
                ]
                self.assertTrue(list_roots)
                self.assertFalse(any(
                    attrs.get("role") in {"status", "alert"}
                    or "aria-live" in attrs
                    for attrs in list_roots
                ))

    def test_pagination_links_are_focus_annotated_and_canonical(self):
        parser = Markup()
        parser.feed((TEMPLATES / "_pagination.html").read_text())
        links = [attrs for tag, attrs in parser.tags if tag == "a"]
        self.assertTrue(links)
        for link in links:
            self.assertEqual(link.get("data-pagination-focus"), "true")
            self.assertIn("data-page", link)
            self.assertIn("href", link)
            self.assertEqual(link.get("hx-boost"), "true")
            self.assertIn("hx-target", link)
            self.assertEqual(link.get("hx-swap"), "innerHTML")
