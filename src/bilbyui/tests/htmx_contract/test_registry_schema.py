"""Fail-closed schema tests for the semantic endpoint registry."""

from dataclasses import replace
from types import MappingProxyType

from django.test import SimpleTestCase

from .registry import (
    REGISTRY,
    AnnouncementExpectation,
    validate_registry,
)


class RegistrySchemaTests(SimpleTestCase):
    def test_production_registry_is_valid(self):
        validate_registry(REGISTRY)

    def test_duplicate_names_have_actionable_diagnostic(self):
        with self.assertRaisesRegex(ValueError, "duplicate contract name"):
            validate_registry((REGISTRY[0], replace(REGISTRY[1], name=REGISTRY[0].name)))

    def test_ambiguous_url_region_has_actionable_diagnostic(self):
        duplicate_resolution = replace(
            REGISTRY[1],
            name="other_metadata",
        )
        with self.assertRaisesRegex(ValueError, "ambiguous url/region resolution"):
            validate_registry((REGISTRY[1], duplicate_resolution))

    def test_unknown_state_has_actionable_diagnostic(self):
        invalid = replace(
            REGISTRY[0],
            not_applicable=MappingProxyType({"invented": "not a contract state"}),
        )
        with self.assertRaisesRegex(ValueError, "unknown states: invented"):
            validate_registry((invalid,))

    def test_unclassified_state_has_actionable_diagnostic(self):
        invalid = replace(
            REGISTRY[0],
            response_states=REGISTRY[0].response_states - {"empty"},
        )
        with self.assertRaisesRegex(ValueError, "unclassified states: empty"):
            validate_registry((invalid,))

    def test_invalid_announcement_role_has_actionable_diagnostic(self):
        announcements = dict(REGISTRY[0].announcement)
        announcements["content"] = AnnouncementExpectation(role="log")
        invalid = replace(REGISTRY[0], announcement=MappingProxyType(announcements))
        with self.assertRaisesRegex(ValueError, "invalid announcement role 'log'"):
            validate_registry((invalid,))

    def test_incomplete_record_has_actionable_diagnostic(self):
        invalid = replace(REGISTRY[0], target=None)
        with self.assertRaisesRegex(ValueError, "incomplete record: target is required"):
            validate_registry((invalid,))

    def test_reachable_retry_requires_semantics(self):
        invalid = replace(REGISTRY[0], retry=None)
        with self.assertRaisesRegex(ValueError, "reachable retry requires retry semantics"):
            validate_registry((invalid,))
