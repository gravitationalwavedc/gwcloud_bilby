"""Accessibility sidecar metadata for every registered interaction contract."""

from dataclasses import dataclass, field

VIEWPORT_WIDTHS = (320, 375, 768, 1024, 1440)
GATES = ("axe", "overflow", "contrast", "keyboard", "target_size", "reduced_motion")
DISPOSITIONS = ("covered", "journey_only", "not_applicable", "deferred")
REASONED_DISPOSITIONS = ("not_applicable", "deferred")

#: Shared reason for contracts outside the representative gate suite. Declared
#: per gate so an omitted gate is a validation failure, not a silent default.
DEFERRED = "deferred:not exercised by the representative gate suite"
JOURNEY_ONLY = "journey_only"


@dataclass(frozen=True)
class SidecarEntry:
    """Per-gate dispositions for one interaction contract."""

    dispositions: dict[str, str] = field(default_factory=dict)


CONTRACT_E2E: dict[str, SidecarEntry] = {
    "gwflow_list_search_filter_pagination": SidecarEntry(
        {
            "axe": "covered",
            "overflow": "covered",
            "contrast": "covered",
            "keyboard": DEFERRED,
            "target_size": "covered",
            "reduced_motion": "covered",
        }
    ),
    "my_jobs_list_search_filter_pagination": SidecarEntry(
        {
            "axe": DEFERRED,
            "overflow": DEFERRED,
            "contrast": DEFERRED,
            "keyboard": DEFERRED,
            "target_size": DEFERRED,
            "reduced_motion": DEFERRED,
        }
    ),
    "public_jobs_list_search_filter_pagination": SidecarEntry(
        {
            "axe": DEFERRED,
            "overflow": DEFERRED,
            "contrast": DEFERRED,
            "keyboard": DEFERRED,
            "target_size": DEFERRED,
            "reduced_motion": DEFERRED,
        }
    ),
    "gwflow_detail_metadata": SidecarEntry(
        {
            "axe": "covered",
            "overflow": "covered",
            "contrast": "covered",
            "keyboard": DEFERRED,
            "target_size": "covered",
            "reduced_motion": DEFERRED,
        }
    ),
    "gwflow_detail_files": SidecarEntry(
        {
            "axe": "covered",
            "overflow": "covered",
            "contrast": "covered",
            "keyboard": DEFERRED,
            "target_size": "covered",
            "reduced_motion": DEFERRED,
        }
    ),
    "gwflow_detail_history": SidecarEntry(
        {
            "axe": DEFERRED,
            "overflow": DEFERRED,
            "contrast": DEFERRED,
            "keyboard": JOURNEY_ONLY,
            "target_size": DEFERRED,
            "reduced_motion": DEFERRED,
        }
    ),
    "gwflow_version_select_compare": SidecarEntry(
        {
            "axe": DEFERRED,
            "overflow": DEFERRED,
            "contrast": DEFERRED,
            "keyboard": JOURNEY_ONLY,
            "target_size": DEFERRED,
            "reduced_motion": DEFERRED,
        }
    ),
    "event_id_modal_open": SidecarEntry(
        {
            "axe": DEFERRED,
            "overflow": DEFERRED,
            "contrast": DEFERRED,
            "keyboard": DEFERRED,
            "target_size": DEFERRED,
            "reduced_motion": DEFERRED,
        }
    ),
    "event_id_search": SidecarEntry(
        {
            "axe": DEFERRED,
            "overflow": DEFERRED,
            "contrast": DEFERRED,
            "keyboard": DEFERRED,
            "target_size": DEFERRED,
            "reduced_motion": DEFERRED,
        }
    ),
    "job_field_edits": SidecarEntry(
        {
            "axe": DEFERRED,
            "overflow": DEFERRED,
            "contrast": DEFERRED,
            "keyboard": JOURNEY_ONLY,
            "target_size": DEFERRED,
            "reduced_motion": DEFERRED,
        }
    ),
    "token_create": SidecarEntry(
        {
            "axe": DEFERRED,
            "overflow": DEFERRED,
            "contrast": DEFERRED,
            "keyboard": DEFERRED,
            "target_size": DEFERRED,
            "reduced_motion": DEFERRED,
        }
    ),
    "token_revoke": SidecarEntry(
        {
            "axe": DEFERRED,
            "overflow": DEFERRED,
            "contrast": DEFERRED,
            "keyboard": JOURNEY_ONLY,
            "target_size": DEFERRED,
            "reduced_motion": DEFERRED,
        }
    ),
    "token_copy": SidecarEntry(
        {
            "axe": DEFERRED,
            "overflow": DEFERRED,
            "contrast": DEFERRED,
            "keyboard": DEFERRED,
            "target_size": DEFERRED,
            "reduced_motion": DEFERRED,
        }
    ),
}
