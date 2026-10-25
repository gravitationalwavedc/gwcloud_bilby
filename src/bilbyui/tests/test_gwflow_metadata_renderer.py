"""Django template tests for the canonical GWFlow metadata renderer."""

import json
import re
from pathlib import Path

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from bilbyui.services.gwflow_metadata import build_metadata_presentation

CORPUS_FIXTURE = Path(__file__).parent / "fixtures" / "metadata_corpus" / "complete_curated.json"
# Keep this table in canonical SECTION_ORDER so expected section IDs also assert
# ordering while each case exercises a selector that is present with value ``[]``.
COLLECTION_SECTIONS = {
    "gracedb_events": ("gracedb", "GraceDB"),
    "analyses": ("pe", "Parameter estimation (PE)"),
    "detector_configurations": ("detchar", "Detector characterisation (DetChar)"),
    "catalog_connections": ("catalog_tracking", "Catalogue tracking"),
}


class GWFlowMetadataRendererTests(SimpleTestCase):
    template_name = "bilbyui/_gwflow_metadata.html"

    def render(self, payload, *, historical=False):
        presentation = build_metadata_presentation(payload, historical=historical)
        return render_to_string(
            self.template_name,
            {"payload": payload, "presentation": presentation, "historical": historical},
        )

    def test_sections_render_in_canonical_order_and_absent_sections_are_omitted(self):
        payload = {
            "sname": "S000001a",
            "gracedb_events": [{"event_name": "G000001"}],
            "analyses": [{"uid": "pe_1", "type": "pe"}],
            "detector_configurations": [{"uid": "H1"}],
            "catalog_connections": [{"catalog_number": 4, "catalog_version": 1}],
        }
        output = self.render(payload)
        headings = (
            "Summary",
            "Info",
            "GraceDB",
            "Parameter estimation (PE)",
            "Detector characterisation (DetChar)",
            "Catalogue tracking",
        )
        positions = [output.index(f">{heading}</h2>") for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("Additional metadata", output)

        partial = self.render(
            {
                "sname": "S000001a",
                "gracedb_events": [{"event_name": "G000001"}],
            }
        )
        self.assertIn(">Summary</h2>", partial)
        self.assertIn(">Info</h2>", partial)
        self.assertIn(">GraceDB</h2>", partial)
        for omitted in (
            ">Parameter estimation (PE)</h2>",
            ">Detector characterisation (DetChar)</h2>",
            ">Catalogue tracking</h2>",
        ):
            self.assertNotIn(omitted, partial)

    def test_each_present_empty_collection_omits_only_its_own_section(self):
        """Exercise the present ``[]`` branch, distinct from absent selectors above."""
        populated = json.loads(CORPUS_FIXTURE.read_text())
        populated.pop("future_section", None)

        for empty_key, (_empty_section, empty_heading) in COLLECTION_SECTIONS.items():
            with self.subTest(empty_collection=empty_key):
                payload = {**populated, empty_key: []}
                self.assertIn(empty_key, payload)
                self.assertEqual(payload[empty_key], [])

                presentation = build_metadata_presentation(payload)
                section_ids = [section.id for section in presentation.sections]
                expected_ids = [
                    "info",
                    *[section_id for key, (section_id, _heading) in COLLECTION_SECTIONS.items() if key != empty_key],
                ]
                self.assertEqual(section_ids, expected_ids)

                output = render_to_string(
                    self.template_name,
                    {"payload": payload, "presentation": presentation},
                )
                self.assertNotIn(f">{empty_heading}</h2>", output)
                for populated_key, (_section_id, populated_heading) in COLLECTION_SECTIONS.items():
                    if populated_key != empty_key:
                        self.assertIn(f">{populated_heading}</h2>", output)

    def test_all_present_empty_collections_with_raw_payload_render_info_only(self):
        """Prove four present empty arrays do not behave as unknown or absent data."""
        populated = json.loads(CORPUS_FIXTURE.read_text())
        populated.pop("future_section", None)
        payload = {
            **populated,
            **{collection: [] for collection in COLLECTION_SECTIONS},
            "raw_payload": {"GraceDB": {"events": [{"uid": "legacy-must-not-render"}]}},
        }
        for collection in COLLECTION_SECTIONS:
            self.assertIn(collection, payload)
            self.assertEqual(payload[collection], [])

        presentation = build_metadata_presentation(payload)
        self.assertEqual(
            [section.id for section in presentation.sections],
            ["info"],
        )

        output = render_to_string(
            self.template_name,
            {"payload": payload, "presentation": presentation},
        )
        self.assertIn(">Summary</h2>", output)
        self.assertIn(">Info</h2>", output)
        for _section_id, heading in COLLECTION_SECTIONS.values():
            self.assertNotIn(f">{heading}</h2>", output)
        self.assertNotIn("Additional metadata", output)
        self.assertNotIn("legacy-must-not-render", output)

    def test_present_falsy_values_are_not_replaced_by_missing_marker(self):
        output = self.render(
            {
                "sname": "",
                "version_number": 0,
                "commit_sha": None,
                "is_current": False,
            }
        )
        self.assertRegex(output, r">\s*—\s*</dd>")
        self.assertRegex(output, r">\s*0\s*</dd>")
        self.assertRegex(output, r">\s*✗ False\s*</dd>")
        self.assertRegex(output, r">\s*&quot;&quot;\s*</dd>")
        self.assertEqual(len(re.findall(r">\s*—\s*</dd>", output)), 1)

    def test_string_is_current_renders_as_canonical_boolean(self):
        output = self.render({"is_current": "true"})
        self.assertRegex(output, r">\s*✓ True\s*</dd>")
        self.assertNotRegex(output, r">\s*true\s*</dd>")

        output = self.render({"is_current": "false"})
        self.assertRegex(output, r">\s*✗ False\s*</dd>")

    def test_disclosure_has_count_accessible_control_and_identity_labels(self):
        output = self.render(
            {
                "detector_configurations": [{"uid": "H1", "frame_file": "H1.gwf", "subtype_state": "science"}],
                "catalog_connections": [
                    {
                        "catalog_number": 4,
                        "catalog_version": 1,
                        "catalog_url": "https://example.test/4/1",
                    }
                ],
            }
        )
        self.assertIn("Show all 3 fields", output)
        self.assertIn('aria-expanded="false"', output)
        self.assertIn(':aria-expanded="open.toString()"', output)
        self.assertIn('aria-controls="metadata-disclosure-detchar"', output)
        self.assertIn('id="metadata-disclosure-detchar"', output)
        self.assertIn(">H1</dt>", output)
        self.assertIn(">4:1</dt>", output)
        self.assertNotIn(">Item 1</dt>", output)

        no_disclosure = self.render({"sname": "S000001a"})
        self.assertNotIn("Show all 0 fields", no_disclosure)
        self.assertNotIn("metadata-disclosure", no_disclosure)

    def test_historical_banner_only_changes_historical_chrome(self):
        payload = {
            "sname": "S000001a",
            "gracedb_events": [{"event_name": "G000001"}],
        }
        current = self.render(payload)
        historical = self.render(payload, historical=True)
        banner = "Viewing historical metadata — not the current record"
        self.assertNotIn(banner, current)
        self.assertNotIn("gwflow-metadata--historical", current)
        self.assertIn(banner, historical)
        self.assertIn("gwflow-metadata--historical", historical)
        current_body = current[current.index('<section class="card') :]
        historical_body = historical[historical.index('<section class="card') :]
        self.assertEqual(current_body, historical_body)

    def test_unsafe_values_are_html_escaped(self):
        unsafe = '<script>alert("unsafe")</script><b>bold</b>'
        output = self.render({"sname": unsafe, "UnknownExtension": {"value": unsafe}})
        self.assertNotIn("<script>", output)
        self.assertNotIn("<b>bold</b>", output)
        self.assertIn("&lt;script&gt;", output)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", output)

    def test_scalar_list_disclosure_renders_items_and_empty_marker(self):
        output = self.render({"UnknownExtension": {"tags": ["a", "b"]}})
        self.assertIn(">a</dd>", output)
        self.assertIn(">b</dd>", output)

        empty = self.render({"UnknownExtension": {"tags": [], "note": "x"}})
        self.assertIn("Empty list", empty)

    def test_people_and_reviews_render_names_without_email_addresses(self):
        output = self.render(
            {
                "analyses": [
                    {
                        "uid": "pe_1",
                        "type": "pe",
                        "analysts": [{"name": "Analyst Name", "email_address": "analyst@example.test"}],
                        "reviews": [
                            {
                                "occurrence_uid": "review-occurrence-1",
                                "name": "Scientific review",
                                "description": "Canonical review description",
                                "passed_review": True,
                                "completion_date": "2026-08-31T12:00:00Z",
                                "review_status": "approved",
                                "reviewers": [{"name": "Reviewer Name", "email_address": "reviewer@example.test"}],
                            }
                        ],
                    }
                ]
            }
        )
        self.assertIn("Analyst Name", output)
        self.assertIn("Scientific review", output)
        for expected in (
            "review-occurrence-1",
            "Scientific review",
            "Canonical review description",
            "Reviewer Name",
            "✓ True",
            "2026-08-31 12:00:00 UTC",
            "approved",
        ):
            self.assertIn(expected, output)
        self.assertNotIn("analyst@example.test", output)
        self.assertNotIn("reviewer@example.test", output)

    def test_pe_status_review_and_deprecated_use_existing_badge_markup(self):
        output = self.render(
            {
                "analyses": [
                    {
                        "uid": "pe_1",
                        "type": "pe",
                        "status": "complete",
                        "review_status": "approved",
                        "deprecated": True,
                    }
                ]
            }
        )
        self.assertRegex(output, r'<span class="badge badge-dark">\s*Complete\s*</span>')
        self.assertRegex(output, r'<span class="badge badge-secondary">\s*approved\s*</span>')
        self.assertRegex(output, r'<span class="badge badge-dark">\s*✓ True\s*</span>')

    def test_comparative_sets_render_accessible_real_tables(self):
        output = self.render(
            {
                "gracedb_events": [
                    {
                        "event_name": "G000001",
                        "has_ns": 0,
                        "has_remnant": 0.25,
                        "has_mass_gap": None,
                        "pipeline_has_ns": 0.1,
                        "pipeline_has_remnant": 0.2,
                        "pipeline_has_mass_gap": 0.3,
                    }
                ],
                "analyses": [
                    {
                        "uid": "pe_1",
                        "type": "pe",
                        "name": "PE",
                        "status": "complete",
                        "review_status": "approved",
                        "deprecated": False,
                    }
                ],
            }
        )
        self.assertEqual(output.count("<table"), 2)
        self.assertEqual(output.count("<caption>"), 2)
        self.assertEqual(output.count('scope="col"'), 21)
        self.assertEqual(output.count('role="region"'), 2)
        self.assertIn('aria-label="GraceDB events, 7-column comparison"', output)
        self.assertIn(
            'aria-label="Parameter estimation results, 14-column comparison"',
            output,
        )
        self.assertIn("GraceDB events comparison, 1 record", output)
        self.assertIn("Parameter estimation results comparison, 1 record", output)
