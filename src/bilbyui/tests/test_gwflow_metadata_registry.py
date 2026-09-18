from types import MappingProxyType

from django.test import SimpleTestCase

from bilbyui.services.gwflow_metadata import (
    FIELD_REGISTRY,
    FORMATTER_NAMES,
    KNOWN_KEYS,
    SECTION_HEADINGS,
    SECTION_ORDER,
    TIERS,
    FieldSpec,
    build_metadata_presentation,
    validate_registry,
)


class GWFlowMetadataRegistryTests(SimpleTestCase):
    def test_exact_researcher_section_order(self):
        self.assertEqual(
            SECTION_ORDER,
            (
                "info",
                "gracedb",
                "pe",
                "tgr",
                "lensing",
                "detchar",
                "extreme_matter",
                "cosmology",
                "rnp",
                "catalog_tracking",
                "publications",
            ),
        )
        self.assertEqual(
            tuple(SECTION_HEADINGS[section] for section in SECTION_ORDER),
            (
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
            ),
        )
        self.assertEqual(tuple(FIELD_REGISTRY), SECTION_ORDER)

    def test_tier_is_closed_set(self):
        self.assertEqual(TIERS, {"summary", "detail", "disclosure"})
        for fields in FIELD_REGISTRY.values():
            for field in fields:
                self.assertIn(field.tier, TIERS)

        bad = MappingProxyType({"info": (FieldSpec("status", "Status", "status", "other"),)})
        with self.assertRaisesRegex(ValueError, "unknown tier"):
            validate_registry(bad)

    def test_duplicate_paths_are_rejected(self):
        duplicated = MappingProxyType(
            {
                "info": (
                    FieldSpec("status", "Status", "status", "summary"),
                    FieldSpec("status", "Status again", "text", "detail"),
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "duplicate registry path"):
            validate_registry(duplicated)

    def test_unknown_formatter_is_rejected(self):
        self.assertIn("scientific", FORMATTER_NAMES)
        bad = MappingProxyType({"info": (FieldSpec("status", "Status", "magic", "summary"),)})
        with self.assertRaisesRegex(ValueError, "unknown formatter"):
            validate_registry(bad)

    def test_known_keys_is_deterministic_immutable_and_covers_all_tiers(self):
        first = KNOWN_KEYS()
        second = KNOWN_KEYS()
        self.assertIsInstance(first, frozenset)
        self.assertEqual(first, second)
        self.assertIn("gracedb.events[].uid", first)
        self.assertIn("info.status", first)
        self.assertIn("pe.results[].deprecated", first)
        represented_tiers = {
            field.tier
            for section, fields in FIELD_REGISTRY.items()
            for field in fields
            if f"{section}.{field.key}" in first
        }
        self.assertEqual(represented_tiers, TIERS)

    def test_builder_preserves_falsy_values_aliases_and_unknown_fallback(self):
        payload = {
            "Info": {"status": ""},
            "GraceDB": {
                "superevent_far": 0,
                "advok": False,
                "extra": {"nullable": None},
            },
            "UnmappedProbe": {"deep": {"sentinel": "UX8_PROBE"}},
        }
        result = build_metadata_presentation(payload, historical=True)
        self.assertTrue(result.historical)
        self.assertEqual([section.id for section in result.sections], ["info", "gracedb", "unknown:UnmappedProbe"])
        self.assertEqual([field.raw_value for field in result.summary], ["", False, 0])
        gracedb = result.sections[1]
        self.assertEqual(gracedb.disclosed_leaf_count, 1)
        unknown = result.sections[2]
        self.assertTrue(unknown.fallback)
        self.assertEqual(unknown.disclosed_leaf_count, 1)
        self.assertNotIn("UnmappedProbe.deep.sentinel", KNOWN_KEYS())

    def test_builder_discloses_non_mapping_section_values_without_raising(self):
        scalar = build_metadata_presentation({"info": "scalar-value"})
        scalar_section = scalar.sections[0]
        self.assertEqual(scalar_section.id, "info")
        self.assertEqual(scalar_section.data_shape, "scalar")
        self.assertEqual(scalar_section.disclosure[0].path, "info")
        self.assertEqual(scalar_section.disclosure[0].value, "scalar-value")
        self.assertEqual(scalar_section.disclosure[0].leaf_count, 1)

        scalar_list = build_metadata_presentation({"info": ["a", "b"]})
        scalar_list_section = scalar_list.sections[0]
        self.assertEqual(scalar_list_section.data_shape, "scalar-list")
        self.assertEqual(scalar_list_section.disclosure[0].shape, "scalar-list")
        self.assertEqual(len(scalar_list_section.disclosure[0].children), 2)

        record_list = build_metadata_presentation({"info": [{"a": 1}]})
        record_list_section = record_list.sections[0]
        self.assertEqual(record_list_section.data_shape, "record-list")
        self.assertEqual(record_list_section.disclosure[0].shape, "record-list")

    def test_builder_comparative_contracts_are_explicit(self):
        payload = {
            "gracedb": {"events": [{"uid": "G1", "far": 0}]},
            "pe": {"results": [{"uid": "P1", "deprecated": False}]},
        }
        result = build_metadata_presentation(payload)
        grace, pe = result.sections
        self.assertEqual(len(grace.comparative_sets[0].columns), 12)
        self.assertEqual(len(pe.comparative_sets[0].columns), 8)
        self.assertEqual(grace.comparative_sets[0].rows[0].identity, "G1")
        self.assertEqual(pe.comparative_sets[0].rows[0].identity, "P1")
