"""Curated search-field help for the GWFlow and Bilby search surfaces.

This module is deliberately data-only. It does not inspect Django models or call
Elasticsearch. New mapped fields remain undocumented until they are reviewed and
added here.
"""

from __future__ import annotations

from collections.abc import Mapping
from fnmatch import fnmatch

from .search_fields import SEARCH_FIELDS

SURFACES = ("gwflow", "bilby")

GWFLOW_GROUPS = (
    "Identifiers and collections",
    "Parameter estimation and review",
    "GraceDB event and significance",
    "Source classification and detector network",
    "Catalogue and detector characterisation",
    "Specialist analyses, provenance, and notes",
    "Stable GWCloud envelope",
)

BILBY_GROUPS = (
    "Job, event, and labels",
    "Waveform, likelihood, and detectors",
    "Priors and fiducial parameters",
    "Frequency, timing, and data settings",
    "Marginalisation, calibration, and reduced-order quadrature",
    "Cosmology and software provenance",
    "Scheduler and INI configuration",
)

GROUPS: Mapping[str, tuple[str, ...]] = {
    "gwflow": GWFLOW_GROUPS,
    "bilby": BILBY_GROUPS,
}

TYPED_NOTES: Mapping[str, str] = {
    "gwflow": ("Numeric, date, and boolean fields support exact values and ranges, for example `snr:>10`."),
    "bilby": (
        "Numeric, date, and boolean fields support exact values and ranges, "
        "for example `params.sampling_frequency:>=4096`."
    ),
}

ES_PSEUDO_FIELDS = frozenset(
    {
        "_id",
        "_routing",
        "_doc_count",
        "_index",
        "_nested_path",
        "_ignored",
        "_field_names",
        "_feature",
        "_data_stream_timestamp",
    }
)

DENIED_PREFIXES = (
    "metadata.raw_payload.",
    "_private_info_.",
    "user.",
    "params.meta_data.command_line_args.",
)

DENIED_EXACT_PATHS = frozenset(
    {
        "metadata.raw_payload",
        "_private_info_",
        "user",
        "ini.email",
        "ini.accounting_user",
        "params.meta_data.command_line_args",
    }
)

DENIED_GLOBS = (
    "*.path",
    "*.md5_sum",
    "*.public_html",
    "*.date_last_modified",
    "*.xml",
    "*.frame_file",
)

# Legacy GWFlow alias/default-field declarations relocated from the deleted
# command and consumed by verify_search_fields.py.
GWFLOW_ALIASES: dict[str, str] = {
    "sname": "_gwcloud.sname",
    "libraries": "_gwcloud.libraries",
    "review_statuses": "_gwcloud.reviewStatuses",
    "event_trigger_id": "_gwcloud.eventTriggerId",
    "search_trigger_time": "_gwcloud.searchTriggerTime",
    "last_updated_time": "_gwcloud.lastUpdatedTime",
    "is_pruned": "_gwcloud.isPruned",
    # Short aliases for the GraceDB event fields, so fielded queries read
    # compactly (e.g. `instruments:(L1 V1) snr:[40 TO 60]`).
    "instruments": "metadata.gracedb.instruments",
    "snr": "metadata.gracedb.events.network_snr",
    "far": "metadata.gracedb.events.far",
    "pipeline": "metadata.gracedb.events.pipeline",
    "pastro": "metadata.gracedb.events.pastro",
}

_DEFAULT_FIELD = [
    "_gwcloud.sname",
    "_gwcloud.eventTriggerId",
    "_gwcloud.libraries",
    "_gwcloud.reviewStatuses",
    "metadata.gracedb.events.uid",
    "metadata.pe.results.uid",
    "metadata.pe.results.inference_software",
    "metadata.pe.results.waveform_approximant",
    "metadata.pe.results.run_status",
    "metadata.pe.results.review_status",
    "metadata.pe.status",
    "metadata.gracedb.events.pipeline",
    "metadata.gracedb.events.state",
    "metadata.gracedb.instruments",
]


def is_denied(path: str) -> bool:
    """Return whether a mapped path is intentionally excluded from help."""

    if path in ES_PSEUDO_FIELDS or path in DENIED_EXACT_PATHS:
        return True
    if "__gwcloud_type__" in path or "__gwcloud_schema__" in path:
        return True
    if path.startswith(DENIED_PREFIXES):
        return True
    return any(fnmatch(path, pattern) for pattern in DENIED_GLOBS)


def _surface_fields(surface: str) -> list[dict[str, object]]:
    if surface not in SURFACES:
        raise ValueError(f"Unknown search surface: {surface}")
    records = []
    for entry in SEARCH_FIELDS:
        if entry["surface"] != surface or is_denied(str(entry["path"])):
            continue
        record = dict(entry)
        record["alias_path"] = documented_alias_path(entry)
        records.append(record)
    return records


def documented_alias_path(entry: Mapping[str, object]) -> str | None:
    """Return the underlying field path for a user-facing alias, else None.

    Only aliases whose target is a researcher-meaningful field are surfaced in
    the help (e.g. `snr` → `metadata.gracedb.events.network_snr`). The internal
    `_gwcloud.*` stable-envelope aliases are never exposed, and non-alias fields
    return None.
    """
    advertised = str(entry["advertised"])
    path = str(entry["path"])
    if advertised == path or path.startswith("_gwcloud."):
        return None
    return path


def common_fields(surface: str) -> list[dict[str, object]]:
    """Return display-ordered common fields for a surface."""

    return [entry for entry in _surface_fields(surface) if entry["visibility"] == "common"]


def grouped_fields(surface: str) -> list[dict[str, object]]:
    """Return the complete field reference, grouped in the approved heading order.

    Includes the common fields as well, so the reference is literally complete
    and every alias mapping — including common ones such as `snr` — is visible.
    """

    entries = _surface_fields(surface)
    groups = []
    for group_name in GROUPS[surface]:
        fields = sorted(
            (entry for entry in entries if entry["group"] == group_name),
            key=lambda entry: (int(entry["tier"]), str(entry["advertised"])),
        )
        groups.append({"name": group_name, "fields": fields})
    return groups


def typed_note(surface: str) -> str:
    """Return the curated typed-query note for a surface."""

    if surface not in SURFACES:
        raise ValueError(f"Unknown search surface: {surface}")
    return TYPED_NOTES[surface]
