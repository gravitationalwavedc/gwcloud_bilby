"""Django template tests for the GWFlow metadata presentation renderer."""

import re

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from bilbyui.services.gwflow_metadata import build_metadata_presentation


class GWFlowMetadataRendererTests(SimpleTestCase):
    """Exercise the root renderer using its presentation-model contract."""

    template_name = "bilbyui/_gwflow_metadata.html"

    def render(self, payload, *, historical=False):
        presentation = build_metadata_presentation(
            payload,
            historical=historical,
        )
        return render_to_string(
            self.template_name,
            {
                "presentation": presentation,
                "historical": historical,
            },
        )

    def test_sections_render_in_policy_order_and_absent_sections_are_omitted(self):
        payload = {
            "publications": {"notes": "Publications notes"},
            "rnp": {"notes": "RNP notes"},
            "cosmology": {"notes": "Cosmology notes"},
            "extreme_matter": {"notes": "Extreme matter notes"},
            "detchar": {"notes": "Detchar notes"},
            "lensing": {"notes": "Lensing notes"},
            "tgr": {"notes": "TGR notes"},
            "pe": {"notes": "PE notes"},
            "gracedb": {"notes": "GraceDB notes"},
            "info": {"notes": "Info notes"},
            "catalog_tracking": {"notes": "Catalogue notes"},
        }

        output = self.render(payload)
        expected_headings = (
            "Summary",
            "Info",
            "GraceDB",
            "Parameter estimation (PE)",
            "Tests of general relativity (TGR)",
            "Lensing",
            "Detector characterisation (Detchar)",
            "Extreme matter",
            "Cosmology",
            "Rapid neutron-star parameter estimation (RNP)",
            "Catalogue tracking",
            "Publications",
        )

        positions = [output.index(f">{heading}</h2>") for heading in expected_headings]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("Additional metadata", output)

        partial = self.render(
            {
                "gracedb": {"notes": "present"},
                "publications": {"notes": "also present"},
            }
        )
        self.assertIn(">Summary</h2>", partial)
        self.assertIn(">GraceDB</h2>", partial)
        self.assertIn(">Publications</h2>", partial)
        for omitted in (
            ">Info</h2>",
            ">Parameter estimation (PE)</h2>",
            ">Tests of general relativity (TGR)</h2>",
            ">Lensing</h2>",
            ">Detector characterisation (Detchar)</h2>",
            ">Extreme matter</h2>",
            ">Cosmology</h2>",
            ">Rapid neutron-star parameter estimation (RNP)</h2>",
            ">Catalogue tracking</h2>",
        ):
            self.assertNotIn(omitted, partial)

    def test_present_falsy_values_are_not_replaced_by_missing_marker(self):
        output = self.render(
            {
                "info": {
                    "notes": None,
                    "zero": 0,
                    "false_value": False,
                    "true_value": True,
                    "empty_string": "",
                }
            }
        )

        # Values render literally; None renders as an em dash. Template
        # whitespace may surround <dd> content, so match flexibly.
        self.assertRegex(output, r">\s*—\s*</dd>")
        self.assertIn(">0</dd>", output)
        self.assertIn(">✗ False</dd>", output)
        self.assertIn(">✓ True</dd>", output)
        self.assertIn('>&quot;&quot;</dd>', output)
        self.assertEqual(len(re.findall(r">\s*—\s*</dd>", output)), 1)

    def test_disclosure_has_count_and_accessible_control(self):
        output = self.render(
            {
                "info": {
                    "notes": "Visible detail",
                    "remaining": {
                        "first": "one",
                        "second": "two",
                        "third": "three",
                    },
                }
            }
        )

        self.assertIn("Show all 3 fields", output)
        self.assertIn('aria-expanded="false"', output)
        self.assertIn(':aria-expanded="open.toString()"', output)
        self.assertIn('aria-controls="metadata-disclosure-info"', output)
        self.assertIn('id="metadata-disclosure-info"', output)

        no_disclosure = self.render({"info": {"notes": "Only detail"}})
        self.assertNotIn("Show all 0 fields", no_disclosure)
        self.assertNotIn("metadata-disclosure", no_disclosure)

    def test_historical_banner_only_changes_historical_chrome(self):
        payload = {
            "info": {"notes": "Stable metadata body"},
            "gracedb": {"notes": "Stable GraceDB body"},
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
        output = self.render(
            {
                "info": {
                    "notes": unsafe,
                    "unregistered": unsafe,
                }
            }
        )

        self.assertNotIn("<script>", output)
        self.assertNotIn("<b>bold</b>", output)
        self.assertIn("&lt;script&gt;", output)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", output)

    def test_comparative_sets_render_accessible_real_tables(self):
        output = self.render(
            {
                "gracedb": {
                    "events": [
                        {
                            "uid": "G123",
                            "pipeline": "gstlal",
                            "state": "ready",
                        }
                    ]
                },
                "pe": {
                    "results": [
                        {
                            "uid": "PE123",
                            "inference_software": "bilby",
                            "run_status": "complete",
                        }
                    ]
                },
            }
        )

        self.assertEqual(output.count("<table"), 2)
        self.assertEqual(output.count("<caption>"), 2)
        self.assertEqual(output.count('scope="col"'), 20)
        self.assertEqual(output.count('role="region"'), 2)
        self.assertEqual(output.count("table-scroll-region"), 2)
        self.assertIn(
            'aria-label="GraceDB events, 12-column comparison"',
            output,
        )
        self.assertIn(
            'aria-label="Parameter estimation results, 8-column comparison"',
            output,
        )
        self.assertIn("GraceDB events comparison, 1 record", output)
        self.assertIn("Parameter estimation results comparison, 1 record", output)
