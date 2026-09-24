"""Inventory guard for accessibility interaction-contract sidecars."""

from django.test import SimpleTestCase

from bilbyui.tests.e2e.accessibility_cases import (
    CONTRACT_E2E,
    DISPOSITIONS,
    GATES,
    REASONED_DISPOSITIONS,
)
from bilbyui.tests.htmx_contract.registry import REGISTRY


class AccessibilitySidecarInventoryTest(SimpleTestCase):
    """Keep sidecar contracts and gate dispositions complete and truthful."""

    def test_registry_has_complete_countable_dispositions(self):
        registry_keys = {contract.name for contract in REGISTRY}
        sidecar_keys = set(CONTRACT_E2E)
        errors = []

        if sidecar_keys != registry_keys:
            errors.append(
                f"missing contracts={sorted(registry_keys - sidecar_keys)}; "
                f"unknown contracts={sorted(sidecar_keys - registry_keys)}"
            )

        expected_gates = set(GATES)
        for contract_name, entry in sorted(CONTRACT_E2E.items()):
            declared_gates = set(entry.dispositions)
            if declared_gates != expected_gates:
                errors.append(
                    f"{contract_name}: missing gates="
                    f"{sorted(expected_gates - declared_gates)}; unknown gates="
                    f"{sorted(declared_gates - expected_gates)}"
                )
            for gate, disposition in sorted(entry.dispositions.items()):
                token, _, reason = disposition.partition(":")
                if token not in DISPOSITIONS:
                    errors.append(
                        f"{contract_name}/{gate}: undocumented disposition "
                        f"{disposition!r}; expected one of {DISPOSITIONS!r}"
                    )
                elif token in REASONED_DISPOSITIONS and not reason.strip():
                    errors.append(f"{contract_name}/{gate}: {token} requires a reason: {disposition!r}")

        self.assertFalse(errors, "\n".join(errors))
