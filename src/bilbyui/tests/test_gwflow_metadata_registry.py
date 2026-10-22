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
            ("info", "gracedb", "pe", "detchar", "catalog_tracking"),
        )
        self.assertEqual(
            tuple(SECTION_HEADINGS[section] for section in SECTION_ORDER),
            (
                "Info",
                "GraceDB",
                "Parameter estimation (PE)",
                "Detector characterisation (DetChar)",
                "Catalogue tracking",
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
        self.assertIn("sname", first)
        self.assertIn("gracedb_events[].event_name", first)
        self.assertIn("analyses[].software.name", first)
        self.assertIn("detector_configurations[]", first)
        self.assertIn("catalog_connections[]", first)
        self.assertNotIn("raw_payload", first)
        self.assertEqual(
            {field.tier for fields in FIELD_REGISTRY.values() for field in fields},
            TIERS,
        )

    def test_canonical_root_fields_select_exactly_their_sections(self):
        cases = (
            ({"sname": "S000001a"}, "info"),
            ({"gracedb_events": [{"event_name": "G000001"}]}, "gracedb"),
            ({"analyses": [{"uid": "pe_1", "type": "pe"}]}, "pe"),
            ({"detector_configurations": [{"uid": "H1"}]}, "detchar"),
            (
                {"catalog_connections": [{"catalog_number": 4, "catalog_version": 1}]},
                "catalog_tracking",
            ),
        )
        for payload, expected_section in cases:
            with self.subTest(expected_section=expected_section):
                result = build_metadata_presentation(payload)
                self.assertEqual(
                    [section.id for section in result.sections],
                    [expected_section],
                )

    def test_raw_payload_never_selects_renders_suppresses_or_reorders(self):
        canonical = {
            "sname": "S000001a",
            "gracedb_events": [{"event_name": "G000001"}],
            "analyses": [{"uid": "pe_1", "type": "pe"}],
            "detector_configurations": [{"uid": "H1"}],
            "catalog_connections": [{"catalog_number": 4, "catalog_version": 1}],
        }
        expected = ["info", "gracedb", "pe", "detchar", "catalog_tracking"]

        for raw_payload in (
            None,
            {
                "Info": {"status": "legacy"},
                "GraceDB": {"events": [{"uid": "legacy-event"}]},
            },
        ):
            with self.subTest(raw_payload=raw_payload):
                result = build_metadata_presentation(
                    {"raw_payload": raw_payload, **canonical},
                )
                self.assertEqual([section.id for section in result.sections], expected)
                self.assertFalse(
                    any(
                        field.path.startswith("raw_payload")
                        for section in result.sections
                        for field in (*section.summary, *section.detail)
                    )
                )
                self.assertFalse(
                    any(
                        node.path.startswith("raw_payload")
                        for section in result.sections
                        for node in section.disclosure
                    )
                )

        only_raw = build_metadata_presentation({"raw_payload": {"sname": "shadow"}})
        self.assertEqual(only_raw.sections, ())
        self.assertEqual(only_raw.summary, ())

    def test_unknown_root_key_renders_after_all_five_known_sections(self):
        payload = {
            "UnmappedProbe": {"deep": {"sentinel": "UX8_PROBE"}},
            "catalog_connections": [{"catalog_number": 4, "catalog_version": 1}],
            "detector_configurations": [{"uid": "H1"}],
            "analyses": [{"uid": "pe_1", "type": "pe"}],
            "gracedb_events": [{"event_name": "G000001"}],
            "sname": "S000001a",
        }

        result = build_metadata_presentation(payload, historical=True)

        self.assertTrue(result.historical)
        self.assertEqual(
            [section.id for section in result.sections],
            [
                "info",
                "gracedb",
                "pe",
                "detchar",
                "catalog_tracking",
                "unknown:UnmappedProbe",
            ],
        )
        unknown = result.sections[-1]
        self.assertTrue(unknown.fallback)
        self.assertEqual(unknown.heading, "Additional metadata: UnmappedProbe")
        self.assertEqual(unknown.disclosed_leaf_count, 1)
        self.assertEqual(
            unknown.disclosure[0].children[0].children[0].value,
            "UX8_PROBE",
        )
        self.assertNotIn("UnmappedProbe.deep.sentinel", KNOWN_KEYS())
