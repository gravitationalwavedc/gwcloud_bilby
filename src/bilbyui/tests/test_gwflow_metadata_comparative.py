import json
from html.parser import HTMLParser
from pathlib import Path

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from bilbyui.services.gwflow_metadata import build_metadata_presentation

FIXTURE = Path(__file__).parent / "fixtures" / "metadata_corpus" / "complete_curated.json"

GRACEDB_COLUMNS = (
    "uid",
    "pipeline",
    "state",
    "gps_time",
    "far",
    "network_snr",
    "pastro",
    "p_bbh",
    "p_bns",
    "p_nsbh",
    "mass_1",
    "mass_2",
)
GRACEDB_DEFAULTS = {"uid", "pipeline", "state", "far", "network_snr"}
PE_COLUMNS = (
    "uid",
    "inference_software",
    "waveform_approximant",
    "run_status",
    "review_status",
    "analysts",
    "reviewers",
    "deprecated",
)
PE_DEFAULTS = {"uid", "inference_software", "run_status", "review_status"}


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
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        presentation = build_metadata_presentation(payload)
        sections = {section.id: section for section in presentation.sections}
        cls.grace = sections["gracedb"].comparative_sets[0]
        cls.pe = sections["pe"].comparative_sets[0]

    def render(self, template_name, comparative_set):
        return render_to_string(
            template_name,
            {"comparative_set": comparative_set},
        )

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
        self.assertEqual(regions[0].get("aria-label"), region_label)
        self.assertEqual(regions[0].get("tabindex"), "0")
        self.assertIn(
            "table-scroll-region",
            regions[0].get("class", "").split(),
        )

        tables = [attrs for tag, attrs in elements if tag == "table" and attrs.get("id") == table_id]
        self.assertEqual(len(tables), 1)
        self.assertIn("<caption>", html)
        self.assertIn("1 record", html)

        column_headers = [attrs for tag, attrs in elements if tag == "th" and attrs.get("scope") == "col"]
        self.assertEqual(
            tuple(header["data-column-key"] for header in column_headers),
            expected_columns,
        )
        self.assertEqual(len(column_headers), len(expected_columns))

        default_visible = {
            header["data-column-key"] for header in column_headers if header["data-default-visible"] == "true"
        }
        self.assertEqual(default_visible, expected_defaults)
        for header in column_headers:
            if header["data-column-key"] in expected_defaults:
                self.assertNotIn("x-show", header)
            else:
                self.assertEqual(header.get("x-show"), "columnsExpanded")

        row_headers = [attrs for tag, attrs in elements if tag == "th" and attrs.get("scope") == "row"]
        self.assertEqual(len(row_headers), 1)
        self.assertIn(
            "table-sticky-identity",
            row_headers[0].get("class", "").split(),
        )
        self.assertIn(
            "table-sticky-identity",
            column_headers[0].get("class", "").split(),
        )
        self.assertFalse(
            any("table-sticky-identity" in header.get("class", "").split() for header in column_headers[1:])
        )

        body_cells = [
            attrs
            for tag, attrs in elements
            if tag in {"td", "th"} and attrs.get("data-column-key") in expected_columns and attrs.get("scope") != "col"
        ]
        self.assertEqual(len(body_cells), len(expected_columns))
        self.assertEqual(
            tuple(cell["data-column-key"] for cell in body_cells),
            expected_columns,
        )
        for cell in body_cells[1:]:
            if cell["data-column-key"] in expected_defaults:
                self.assertNotIn("x-show", cell)
            else:
                self.assertEqual(cell.get("x-show"), "columnsExpanded")

        buttons = [attrs for tag, attrs in elements if tag == "button" and attrs.get("aria-controls") == table_id]
        self.assertEqual(len(buttons), 1)
        button = buttons[0]
        self.assertEqual(button.get("type"), "button")
        self.assertEqual(button.get("aria-expanded"), "false")
        self.assertEqual(
            button.get(":aria-expanded"),
            "columnsExpanded.toString()",
        )
        self.assertEqual(
            button.get("@click"),
            "columnsExpanded = !columnsExpanded",
        )
        self.assertIn("@keydown.enter.prevent", button)
        self.assertIn("@keydown.space.prevent", button)
        self.assertIn("Show all columns ⌄", html)
        self.assertIn("Show fewer columns ⌃", html)

        self.assertNotIn("record-stack", html)
        self.assertNotIn("card", html)
        self.assertNotIn("first-five", html)
        self.assertEqual(html.count("<table"), 1)

    def test_gracedb_table_structure_and_locked_columns(self):
        self.assertEqual(
            tuple(column.key for column in self.grace.columns),
            GRACEDB_COLUMNS,
        )
        self.assertEqual(
            {column.key for column in self.grace.columns if column.default_visible},
            GRACEDB_DEFAULTS,
        )
        html = self.render(
            "bilbyui/_gwflow_metadata_gracedb_comparison_hook.html",
            self.grace,
        )
        self.assertIn("GraceDB events comparison", html)
        self.assert_table_contract(
            html,
            GRACEDB_COLUMNS,
            GRACEDB_DEFAULTS,
            "GraceDB events, 12-column comparison",
            "gracedb-comparison-table",
        )

    def test_pe_table_structure_and_locked_columns(self):
        self.assertEqual(
            tuple(column.key for column in self.pe.columns),
            PE_COLUMNS,
        )
        self.assertEqual(
            {column.key for column in self.pe.columns if column.default_visible},
            PE_DEFAULTS,
        )
        html = self.render(
            "bilbyui/_gwflow_metadata_pe_comparison_hook.html",
            self.pe,
        )
        self.assertIn("Parameter estimation results comparison", html)
        self.assert_table_contract(
            html,
            PE_COLUMNS,
            PE_DEFAULTS,
            "Parameter estimation results, 8-column comparison",
            "pe-comparison-table",
        )

    def test_comparative_residual_skips_non_dict_records(self):
        payload = {
            "gracedb": {
                "events": [
                    "malformed-non-dict-entry",
                    {
                        "uid": "G-SANITISED-001",
                        "pipeline": "gstlal",
                        "state": "preferred",
                        "far": {"value": 1.1e-10, "unit": "Hz"},
                        "network_snr": 18.4,
                        "custom_field": {"value": "kept"},
                    },
                ]
            }
        }
        presentation = build_metadata_presentation(payload)
        section = next(section for section in presentation.sections if section.id == "gracedb")
        self.assertEqual(section.data_shape, "comparative")
        self.assertEqual(len(section.comparative_sets), 1)
        self.assertEqual(len(section.comparative_sets[0].rows), 1)
        residual_paths = {node.path for node in section.disclosure}
        self.assertIn("gracedb.events[1].custom_field", residual_paths)
        self.assertNotIn("gracedb.events[0].custom_field", residual_paths)

    def test_all_columns_are_server_rendered_for_no_javascript_access(self):
        for template_name, comparative_set, columns in (
            (
                "bilbyui/_gwflow_metadata_gracedb_comparison_hook.html",
                self.grace,
                GRACEDB_COLUMNS,
            ),
            (
                "bilbyui/_gwflow_metadata_pe_comparison_hook.html",
                self.pe,
                PE_COLUMNS,
            ),
        ):
            with self.subTest(template=template_name):
                html = self.render(template_name, comparative_set)
                for column in columns:
                    self.assertEqual(
                        html.count(f'data-column-key="{column}"'),
                        2,
                    )
                self.assertNotIn(" x-cloak", html)
                self.assertNotIn(" hidden", html)
