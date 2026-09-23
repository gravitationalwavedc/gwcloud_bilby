"""Accessibility sidecar metadata for every registered interaction contract."""

from dataclasses import dataclass, field

VIEWPORT_WIDTHS = (320, 375, 768, 1024, 1440)
GATES = ("axe", "overflow", "contrast", "keyboard", "target_size", "reduced_motion")
DISPOSITIONS = ("covered", "journey_only", "not_applicable", "deferred")
REASONED_DISPOSITIONS = ("not_applicable", "deferred")

_DEFERRED = "deferred:not exercised by the representative gate suite"


def _gates(**overrides: str) -> dict[str, str]:
    """Return a complete gate disposition mapping with per-gate overrides."""
    dispositions = {gate: _DEFERRED for gate in GATES}
    dispositions.update(overrides)
    return dispositions


@dataclass(frozen=True)
class SidecarEntry:
    """Per-gate dispositions for one interaction contract."""

    dispositions: dict[str, str] = field(default_factory=dict)


CONTRACT_E2E: dict[str, SidecarEntry] = {
    "gwflow_list_search_filter_pagination": SidecarEntry(
        _gates(
            axe="covered",
            overflow="covered",
            contrast="covered",
            target_size="covered",
            reduced_motion="covered",
        )
    ),
    "my_jobs_list_search_filter_pagination": SidecarEntry(_gates()),
    "public_jobs_list_search_filter_pagination": SidecarEntry(_gates()),
    "gwflow_detail_metadata": SidecarEntry(
        _gates(axe="covered", overflow="covered", contrast="covered", target_size="covered")
    ),
    "gwflow_detail_files": SidecarEntry(
        _gates(axe="covered", overflow="covered", contrast="covered", target_size="covered")
    ),
    "gwflow_detail_history": SidecarEntry(_gates(keyboard="journey_only")),
    "gwflow_version_select_compare": SidecarEntry(_gates(keyboard="journey_only")),
    "event_id_modal_open": SidecarEntry(_gates()),
    "event_id_search": SidecarEntry(_gates()),
    "job_field_edits": SidecarEntry(_gates(keyboard="journey_only")),
    "token_create": SidecarEntry(_gates()),
    "token_revoke": SidecarEntry(_gates(keyboard="journey_only")),
    "token_copy": SidecarEntry(_gates()),
}
