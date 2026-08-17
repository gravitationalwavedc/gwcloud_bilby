"""Pure Django template tests for the A8 metadata renderer.

These tests exercise ``bilbyui/_gwflow_metadata.html`` (and its section
includes) directly via ``render_to_string``. They do NOT touch the database,
authentication, or Elasticsearch, so they deliberately do not extend
``BilbyTestCase``.
"""

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from bilbyui.templatetags.gwflow_tags import get_item, human_value, sort_items

FULL_PAYLOAD = {
    "schema_version": "3",
    "commit_sha": "abcdefgh12345678",
    "commit_timestamp": "2024-01-02T03:04:05Z",
    "info": {"notes": "Info notes here."},
    "gracedb": {
        "events": [
            {
                "uid": "E1",
                "pipeline": "gstlal",
                "state": "CREATED",
                "gps_time": 1234567890.0,
                "far": 1e-6,
                "network_snr": 12.3,
                "h1_snr": 9.1,
                "l1_snr": 8.2,
                "v1_snr": 5.0,
                "pastro": 0.99,
                "p_bbh": 0.9,
                "p_bns": 0.05,
                "p_nsbh": 0.05,
                "mass_1": 35.0,
                "mass_2": 30.0,
            }
        ],
        "instruments": ["H1", "L1"],
        "advok": "ADVOK-1",
        "superevent_far": 1e-7,
        "superevent_pastro": 0.999,
        "notes": "GraceDB notes.",
    },
    "pe": {
        "results": [
            {
                "uid": "PE1",
                "inference_software": "bilby",
                "waveform_approximant": "IMRPhenomXPHM",
                "run_status": "complete",
                "review_status": "reviewed",
                "analysts": [{"name": "Alice"}, {"name": "Bob"}],
                "reviewers": [{"name": "Carol"}],
                "deprecated": True,
                "notes": "PE notes.",
            }
        ],
        "analysts": "Alice, Bob",
        "reviewers": "Carol",
        "status": "complete",
        "notes": "PE section notes.",
    },
    "tgr": {
        "imrct_analyses": [
            {
                "uid": "I1",
                "description": "IMRCT analysis",
                "analysis_software": "imrct",
                "analysts": [{"name": "Alice"}],
                "notes": "imrct notes",
            }
        ],
        "tiger_analyses": [
            {
                "uid": "T1",
                "description": "TIGER analysis",
                "analysis_software": "tiger",
                "analysts": [{"name": "Bob"}],
                "notes": "tiger notes",
            }
        ],
        "notes": "TGR notes.",
    },
    "lensing": {
        "multiplet_groups": [{"companion_sname": "S230601ag"}],
        "singlet_analyses": [{"uid": "S1"}],
        "notes": "Lensing notes.",
    },
    "detchar": {
        "glitch": "no",
        "notes": "Detchar notes.",
    },
    "extreme_matter": {
        "tidal_deformability": "400.0",
        "notes": "Extreme matter notes.",
    },
    "cosmology": {
        "hubble_constant": "67.4",
        "notes": "Cosmology notes.",
    },
    "rnp": {
        "has_remnant": "yes",
        "notes": "RNP notes.",
    },
    "catalog_tracking": {
        "catalog": "GWTC-3",
        "notes": "Catalog tracking notes.",
    },
    "publications": {
        "papers": [{"arxiv_id": "1234.5678", "title": "A paper"}],
        "notes": "Publications notes.",
    },
}

A7_CURRENT_PAYLOAD = {
    "schema_version": "3",
    "commit_sha": "abcdefgh12345678",
    "commit_timestamp": "2024-01-02T03:04:05Z",
    "gracedb": {"events": [{"uid": "E1", "pipeline": "gstlal"}]},
}

A9_HISTORICAL_PAYLOAD = {
    "gracedb": {"events": [{"uid": "E1", "pipeline": "gstlal", "state": "CREATED"}]},
}


class GWFlowMetadataRendererTests(SimpleTestCase):
    """Direct template rendering tests for the A8 metadata renderer."""

    def _render(self, payload, stale=False):
        return render_to_string(
            "bilbyui/_gwflow_metadata.html",
            {"payload": payload, "stale": stale},
        )

    def test_full_v3_fixture_renders_all_sections(self):
        output = self._render(FULL_PAYLOAD)

        for section in [
            "Info",
            "GraceDB",
            "Parameter Estimation",
            "TGR",
            "Lensing",
            "Detchar",
            "Extreme Matter",
            "Cosmology",
            "RNP",
            "Catalog Tracking",
            "Publications",
        ]:
            self.assertIn(section, output)

        for value in [
            "Info notes here.",
            "E1",
            "gstlal",
            "CREATED",
            "1234567890.0",
            "H1, L1",
            "GraceDB notes.",
            "PE1",
            "bilby",
            "IMRPhenomXPHM",
            "complete",
            "reviewed",
            "Alice, Bob",
            "Carol",
            "PE section notes.",
            "I1",
            "T1",
            "TGR notes.",
            "S1",
            "S230601ag",
            "Lensing notes.",
            "glitch",
            "no",
            "Detchar notes.",
            "tidal_deformability",
            "400.0",
            "Extreme matter notes.",
            "hubble_constant",
            "67.4",
            "Cosmology notes.",
            "has_remnant",
            "yes",
            "RNP notes.",
            "catalog",
            "GWTC-3",
            "Catalog tracking notes.",
            "arxiv_id",
            "1234.5678",
            "A paper",
            "Publications notes.",
        ]:
            self.assertIn(value, output)

    def test_empty_dict_renders_fallback_without_cards(self):
        output = self._render({})

        self.assertNotIn("card", output)
        self.assertIn("No metadata available.", output)

    def test_none_sections_render_without_error_or_empty_cards(self):
        output = self._render({"gracedb": None})

        self.assertNotIn("card", output)
        self.assertNotIn("No metadata available.", output)

    def test_truthy_non_dict_sections_render_without_error(self):
        output = self._render(
            {
                "tgr": "unexpected-string",
                "detchar": ["item1", "item2"],
                "gracedb": {"events": [{"uid": "E1", "pipeline": "gstlal"}]},
            }
        )

        self.assertIn("E1", output)
        self.assertIn("gstlal", output)
        self.assertNotIn("unexpected-string", output)

    def test_generic_section_notes_rendered_once(self):
        output = self._render({"detchar": {"foo": "bar", "notes": "Detchar notes."}})

        self.assertEqual(output.count("Detchar notes."), 1)

    def test_generic_section_list_of_scalars_rendered_as_text(self):
        output = self._render({"detchar": {"instruments": ["H1", "L1"]}})

        self.assertIn("H1, L1", output)
        self.assertNotIn("['H1'", output)

    def test_pe_section_level_analysts_list_of_dicts_rendered_as_names(self):
        output = self._render(
            {
                "pe": {
                    "analysts": [{"name": "Alice"}, {"name": "Bob"}],
                    "reviewers": [{"name": "Carol"}],
                }
            }
        )

        self.assertIn("Analysts: Alice, Bob", output)
        self.assertIn("Reviewers: Carol", output)
        self.assertNotIn("[{'name'", output)

    def test_unknown_extra_keys_ignored(self):
        output = self._render(
            {
                "sname": "S230601ag",
                "foo": "bar",
                "gracedb": {"events": [{"uid": "E1", "pipeline": "gstlal"}]},
            }
        )

        self.assertNotIn("foo", output)
        self.assertNotIn("bar", output)
        self.assertNotIn("S230601ag", output)
        self.assertIn("E1", output)
        self.assertIn("gstlal", output)

    def test_analyst_names_joined_with_commas(self):
        output = self._render(
            {
                "pe": {
                    "results": [
                        {
                            "uid": "PE1",
                            "analysts": [{"name": "Alice"}, {"name": "Bob"}, {"name": "Carol"}],
                            "reviewers": [{"name": "Dave"}],
                        }
                    ]
                }
            }
        )

        self.assertIn("Alice, Bob, Carol", output)
        self.assertIn("Dave", output)

    def test_deprecated_badge_rendered(self):
        output = self._render(
            {
                "pe": {
                    "results": [
                        {
                            "uid": "PE1",
                            "analysts": [{"name": "Alice"}],
                            "deprecated": True,
                        }
                    ]
                }
            }
        )

        self.assertIn("deprecated", output)
        self.assertIn("badge-warning", output)

    def test_same_include_renders_current_and_historical_shapes(self):
        current = self._render(A7_CURRENT_PAYLOAD)
        historical = self._render(A9_HISTORICAL_PAYLOAD)

        self.assertIn("E1", current)
        self.assertIn("gstlal", current)
        self.assertIn("E1", historical)
        self.assertIn("gstlal", historical)

    def test_stale_note_only_rendered_when_stale(self):
        stale_output = self._render({"gracedb": {"notes": "x"}}, stale=True)
        live_output = self._render({"gracedb": {"notes": "x"}}, stale=False)

        self.assertIn("Showing cached copy.", stale_output)
        self.assertNotIn("Showing cached copy.", live_output)

    def test_tgr_list_keys_rendered_in_alphabetical_order(self):
        output = self._render(
            {
                "tgr": {
                    "tiger_analyses": [
                        {
                            "uid": "T1",
                            "description": "TIGER analysis",
                            "analysis_software": "tiger",
                            "analysts": [{"name": "Bob"}],
                        }
                    ],
                    "imrct_analyses": [
                        {
                            "uid": "I1",
                            "description": "IMRCT analysis",
                            "analysis_software": "imrct",
                            "analysts": [{"name": "Alice"}],
                        }
                    ],
                    "notes": "TGR notes.",
                }
            }
        )

        self.assertLess(
            output.index("imrct_analyses"),
            output.index("tiger_analyses"),
        )

    def test_header_strip_renders_schema_commit_sha_and_timestamp(self):
        output = self._render(
            {
                "schema_version": "3",
                "commit_sha": "abcdefgh12345678",
                "commit_timestamp": "2024-01-02T03:04:05Z",
            }
        )

        self.assertIn("v3", output)
        self.assertIn("abcdefgh", output)
        self.assertNotIn("12345678", output)
        self.assertIn("2024-01-02T03:04:05Z", output)


class TestGWFlowTagsFilters(SimpleTestCase):
    def test_get_item_returns_value_for_existing_key(self):
        self.assertEqual(get_item({"a": 1}, "a"), 1)

    def test_get_item_returns_none_for_missing_key(self):
        self.assertIsNone(get_item({"a": 1}, "b"))

    def test_get_item_returns_none_for_non_dict(self):
        self.assertIsNone(get_item(None, "a"))
        self.assertIsNone(get_item([1, 2], "a"))
        self.assertIsNone(get_item("string", "a"))

    def test_sort_items_sorts_dict_items(self):
        self.assertEqual(sort_items({"b": 2, "a": 1}), [("a", 1), ("b", 2)])

    def test_sort_items_returns_empty_for_non_dict(self):
        self.assertEqual(sort_items("string"), [])
        self.assertEqual(sort_items(None), [])
        self.assertEqual(sort_items([1, 2]), [])

    def test_human_value_passes_scalars_through(self):
        self.assertEqual(human_value("text"), "text")
        self.assertEqual(human_value(5), 5)

    def test_human_value_returns_none_for_none_and_dict(self):
        self.assertIsNone(human_value(None))
        self.assertIsNone(human_value({"a": 1}))

    def test_human_value_joins_list_of_dict_names(self):
        self.assertEqual(human_value([{"name": "Alice"}, {"name": "Bob"}]), "Alice, Bob")

    def test_human_value_joins_list_of_scalars(self):
        self.assertEqual(human_value(["H1", "L1"]), "H1, L1")
