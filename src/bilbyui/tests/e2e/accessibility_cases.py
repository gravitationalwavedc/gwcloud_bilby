"""Accessibility sidecar metadata for every registered interaction contract."""

from dataclasses import dataclass, field

VIEWPORT_WIDTHS = (320, 375, 768, 1024, 1440)
GATES = ("axe", "overflow", "contrast", "keyboard", "target_size", "reduced_motion")
DISPOSITIONS = ("covered", "journey_only", "not_applicable")


def _covered(*, keyboard: str = "covered") -> dict[str, str]:
    """Return a complete, independent gate disposition mapping."""
    return {
        "axe": "covered",
        "overflow": "covered",
        "contrast": "covered",
        "keyboard": keyboard,
        "target_size": "covered",
        "reduced_motion": "covered",
    }


@dataclass(frozen=True)
class SidecarEntry:
    """Browser setup facts and gate dispositions for one interaction contract."""

    setup: str | None
    materialiser: str | None
    readiness: str
    content_scope: str
    dispositions: dict[str, str] = field(default_factory=dict)


CONTRACT_E2E: dict[str, SidecarEntry] = {
    "gwflow_list_search_filter_pagination": SidecarEntry(None, None, "", "", _covered()),
    "my_jobs_list_search_filter_pagination": SidecarEntry(None, None, "", "", _covered()),
    "public_jobs_list_search_filter_pagination": SidecarEntry(None, None, "", "", _covered()),
    "gwflow_detail_metadata": SidecarEntry(None, None, "", "", _covered()),
    "gwflow_detail_files": SidecarEntry(None, None, "", "", _covered()),
    "gwflow_detail_history": SidecarEntry(None, None, "", "", _covered()),
    "gwflow_version_select_compare": SidecarEntry(None, None, "", "", _covered()),
    "event_id_modal_open": SidecarEntry(None, None, "", "", _covered()),
    "event_id_search": SidecarEntry(None, None, "", "", _covered()),
    "job_field_edits": SidecarEntry(None, None, "", "", _covered(keyboard="journey_only")),
    "token_create": SidecarEntry(None, None, "", "", _covered()),
    "token_revoke": SidecarEntry(None, None, "", "", _covered(keyboard="journey_only")),
    "token_copy": SidecarEntry(None, None, "", "", _covered(keyboard="journey_only")),
}
