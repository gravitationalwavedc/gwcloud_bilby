import json
from html.parser import HTMLParser
from pathlib import Path

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from bilbyui.services.gwflow_metadata import build_metadata_presentation

FIXTURE = Path(__file__).parent / "fixtures" / "metadata_corpus" / "complete_curated.json"

GRACEDB_COLUMNS = (
    "event_name",
    "has_ns",
    "has_remnant",
    "has_mass_gap",
    "pipeline_has_ns",
    "pipeline_has_remnant",
    "pipeline_has_mass_gap",
)
GRACEDB_DEFAULTS = {"event_name", "has_ns", "has_remnant"}
PE_COLUMNS = (
    "uid",
    "name",
    "status",
    "review_status",
    "deprecated",
    "description",
    "software.name",
    "software.version",
    "analysts",
    "reviews",
    "configurations",
    "input_files",
    "output_files",
    "in_catalog",
)
PE_DEFAULTS = {"uid", "name", "status", "review_status", "deprecated"}


class StructureParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class GWFlowMetadataComparativeTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        presentation = build_metadata_presentation(json.loads(FIXTURE.read_text()))
        sections = {section.id: section for section in presentation.sections}
        cls.grace = sections["gracedb"].comparative_sets[0]
        cls.pe = sections["pe"].comparative_sets[0]

    def render(self, template_name, comparative_set):
        return render_to_string(template_name, {"comparative_set": comparative_set})

    def assert_table_contract(
        self,
        html,
        expected_columns,
        expected_defaults,
        region_label,
        table_id,
    ):
        parser = StructureParser()
        parser.feed(html)
        elements = parser.elements
        regions = [attrs for tag, attrs in elements if tag == "div" and attrs.get("role") == "region"]
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["aria-label"], region_label)
        self.assertEqual(regions[0]["tabindex"], "0")
        self.assertIn("table-scroll-region", regions[0]["class"].split())

        tables = [attrs for tag, attrs in elements if tag == "table" and attrs.get("id") == table_id]
        self.assertEqual(len(tables), 1)
        self.assertIn("<caption>", html)
        self.assertIn("1 record", html)

        headers = [attrs for tag, attrs in elements if tag == "th" and attrs.get("scope") == "col"]
        self.assertEqual(
            tuple(header["data-column-key"] for header in headers),
            expected_columns,
        )
        defaults = {header["data-column-key"] for header in headers if header["data-default-visible"] == "true"}
        self.assertEqual(defaults, expected_defaults)
        for header in headers:
            if header["data-column-key"] in expected_defaults:
                self.assertNotIn("x-show", header)
            else:
                self.assertEqual(header.get("x-show"), "columnsExpanded")

        row_headers = [attrs for tag, attrs in elements if tag == "th" and attrs.get("scope") == "row"]
        self.assertEqual(len(row_headers), 1)
        self.assertIn("table-sticky-identity", row_headers[0]["class"].split())
        self.assertIn("table-sticky-identity", headers[0]["class"].split())

        cells = [
            attrs
            for tag, attrs in elements
            if tag in {"td", "th"} and attrs.get("data-column-key") in expected_columns and attrs.get("scope") != "col"
        ]
        self.assertEqual(
            tuple(cell["data-column-key"] for cell in cells),
            expected_columns,
        )

        buttons = [attrs for tag, attrs in elements if tag == "button" and attrs.get("aria-controls") == table_id]
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0]["type"], "button")
        self.assertEqual(buttons[0]["aria-expanded"], "false")
        self.assertEqual(
            buttons[0][":aria-expanded"],
            "columnsExpanded.toString()",
        )
        self.assertIn("Show all columns ⌄", html)
        self.assertIn("Show fewer columns ⌃", html)
        self.assertNotIn("record-stack", html)
        self.assertEqual(html.count("<table"), 1)

    def test_gracedb_table_structure_and_registry_columns(self):
        self.assertEqual(tuple(column.key for column in self.grace.columns), GRACEDB_COLUMNS)
        self.assertEqual(
            {column.key for column in self.grace.columns if column.default_visible},
            GRACEDB_DEFAULTS,
        )
        html = self.render(
            "bilbyui/_gwflow_metadata_gracedb_comparison_hook.html",
            self.grace,
        )
        self.assert_table_contract(
            html,
            GRACEDB_COLUMNS,
            GRACEDB_DEFAULTS,
            f"GraceDB events, {len(GRACEDB_COLUMNS)}-column comparison",
            "gracedb-comparison-table",
        )

    def test_pe_table_structure_and_registry_columns(self):
        self.assertEqual(tuple(column.key for column in self.pe.columns), PE_COLUMNS)
        self.assertEqual(
            {column.key for column in self.pe.columns if column.default_visible},
            PE_DEFAULTS,
        )
        html = self.render(
            "bilbyui/_gwflow_metadata_pe_comparison_hook.html",
            self.pe,
        )
        self.assert_table_contract(
            html,
            PE_COLUMNS,
            PE_DEFAULTS,
            f"Parameter estimation results, {len(PE_COLUMNS)}-column comparison",
            "pe-comparison-table",
        )

    def test_all_columns_are_server_rendered_without_javascript(self):
        for template_name, comparative_set, columns in (
            (
                "bilbyui/_gwflow_metadata_gracedb_comparison_hook.html",
                self.grace,
                GRACEDB_COLUMNS,
            ),
            ("bilbyui/_gwflow_metadata_pe_comparison_hook.html", self.pe, PE_COLUMNS),
        ):
            with self.subTest(template=template_name):
                html = self.render(template_name, comparative_set)
                for column in columns:
                    self.assertEqual(html.count(f'data-column-key="{column}"'), 2)
                self.assertNotIn(" x-cloak", html)
                self.assertNotIn(" hidden", html)

    def test_comparative_residual_preserves_unknown_record_fields(self):
        presentation = build_metadata_presentation(
            {
                "gracedb_events": [
                    "malformed",
                    {"event_name": "G1", "custom_field": {"value": "kept"}},
                ]
            }
        )
        section = next(section for section in presentation.sections if section.id == "gracedb")
        self.assertEqual(len(section.comparative_sets[0].rows), 1)
        self.assertIn(
            "gracedb.gracedb_events[1].custom_field",
            {node.path for node in section.disclosure},
        )

    def test_pe_residual_paths_keep_source_analysis_index(self):
        presentation = build_metadata_presentation(
            {
                "analyses": [
                    {"uid": "validation", "type": "event_validation"},
                    {"uid": "pe_1", "type": "pe", "extra": "kept"},
                ]
            }
        )
        pe = next(section for section in presentation.sections if section.id == "pe")
        self.assertIn(
            "pe.analyses[1].extra",
            {node.path for node in pe.disclosure},
        )

    def test_pe_residual_hides_recognised_non_displayed_paths(self):
        presentation = build_metadata_presentation(
            {
                "analyses": [
                    {
                        "uid": "pe_1",
                        "type": "pe",
                        "revision": 3,
                        "suggested_detector_configuration_uids": ["H1"],
                        "extra": "kept",
                    }
                ]
            }
        )
        pe = next(section for section in presentation.sections if section.id == "pe")
        paths = {node.path for node in pe.disclosure}
        self.assertIn("pe.analyses[0].extra", paths)
        self.assertNotIn("pe.analyses[0].type", paths)
        self.assertNotIn("pe.analyses[0].revision", paths)
        self.assertNotIn("pe.analyses[0].suggested_detector_configuration_uids", paths)

    def test_gracedb_with_no_mapping_records_is_omitted(self):
        for value in ("not-a-list", ["malformed"]):
            with self.subTest(value=value):
                presentation = build_metadata_presentation({"gracedb_events": value})
                self.assertNotIn("gracedb", {section.id for section in presentation.sections})

    def test_pe_filters_non_pe_and_non_mapping_records(self):
        presentation = build_metadata_presentation(
            {
                "analyses": [
                    "malformed",
                    {"uid": "validation", "type": "event_validation"},
                    {"uid": "pe_1", "type": "pe"},
                ]
            }
        )
        pe = next(section for section in presentation.sections if section.id == "pe")
        self.assertEqual([row.identity for row in pe.comparative_sets[0].rows], ["pe_1"])

    def test_detchar_and_catalog_tracking_never_build_comparative_sets(self):
        presentation = build_metadata_presentation(
            {
                "detector_configurations": [{"uid": "H1", "custom": 1}],
                "catalog_connections": [{"catalog_number": 4, "catalog_version": 1, "custom": 2}],
            }
        )
        sections = {section.id: section for section in presentation.sections}
        for section_id in ("detchar", "catalog_tracking"):
            with self.subTest(section=section_id):
                self.assertEqual(sections[section_id].comparative_sets, ())
                self.assertTrue(sections[section_id].disclosure)
