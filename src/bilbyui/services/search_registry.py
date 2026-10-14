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
    "gwflow": (
        "Numeric, date, and boolean fields support exact values and ranges, "
        "for example metadata.gracedb.events.network_snr:>10."
    ),
    "bilby": (
        "Numeric, date, and boolean fields support exact values and ranges, "
        "for example params.sampling_frequency:>=4096."
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
    return [dict(entry) for entry in SEARCH_FIELDS if entry["surface"] == surface and not is_denied(str(entry["path"]))]


def common_fields(surface: str) -> list[dict[str, object]]:
    """Return display-ordered common fields for a surface."""

    return [entry for entry in _surface_fields(surface) if entry["visibility"] == "common"]


def grouped_fields(surface: str) -> list[dict[str, object]]:
    """Return full-reference fields grouped in the approved heading order."""

    entries = [entry for entry in _surface_fields(surface) if entry["visibility"] == "full"]
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
