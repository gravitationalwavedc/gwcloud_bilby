"""Declarative presentation registry for GWFlow portal metadata.

Canonical paths use ``.`` between mapping keys and ``[]`` after a key whose
value is a list of records, for example ``gracedb.events[].uid``.  Concrete
list indices never occur in registry paths.  Unknown paths are deliberately
not matched by wildcards, so callers can detect upstream schema drift.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

logger = logging.getLogger(__name__)

Tier = Literal["summary", "detail", "disclosure"]
TIERS = frozenset({"summary", "detail", "disclosure"})
FORMATTER_NAMES = frozenset(
    {
        "boolean",
        "link",
        "list",
        "person",
        "probability",
        "scientific",
        "status",
        "text",
        "utc_timestamp",
    }
)


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Curated presentation policy for one section-relative portal path."""

    key: str
    label: str
    formatter: str
    tier: Tier


@dataclass(frozen=True, slots=True)
class PresentationField:
    path: str
    label: str
    raw_value: Any
    formatter: str
    tier: str


@dataclass(frozen=True, slots=True)
class DisclosureNode:
    path: str
    label: str
    shape: str
    value: Any = None
    children: tuple[DisclosureNode, ...] = ()
    leaf_count: int = 0


@dataclass(frozen=True, slots=True)
class ComparativeColumn:
    key: str
    path: str
    label: str
    formatter: str
    default_visible: bool
    identity: bool = False


@dataclass(frozen=True, slots=True)
class ComparativeRow:
    identity: Any
    cells: tuple[PresentationField, ...]


@dataclass(frozen=True, slots=True)
class ComparativeSet:
    kind: str
    columns: tuple[ComparativeColumn, ...]
    rows: tuple[ComparativeRow, ...]


@dataclass(frozen=True, slots=True)
class MetadataSection:
    id: str
    source_key: str
    heading: str
    summary: tuple[PresentationField, ...]
    detail: tuple[PresentationField, ...]
    disclosure: tuple[DisclosureNode, ...]
    disclosed_leaf_count: int
    data_shape: str
    comparative_sets: tuple[ComparativeSet, ...] = ()
    fallback: bool = False


@dataclass(frozen=True, slots=True)
class MetadataPresentation:
    historical: bool
    summary: tuple[PresentationField, ...]
    sections: tuple[MetadataSection, ...]


# Identifiers are stable policy keys. Visible first-use expansions live in
# SECTION_HEADINGS rather than being inferred from source keys.
SECTION_ORDER: tuple[str, ...] = (
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
)

SECTION_HEADINGS: Mapping[str, str] = MappingProxyType(
    {
        "info": "Info",
        "gracedb": "GraceDB",
        "pe": "Parameter estimation (PE)",
        "tgr": "Tests of general relativity (TGR)",
        "lensing": "Lensing",
        "detchar": "Detector characterisation (Detchar)",
        "extreme_matter": "Extreme matter",
        "cosmology": "Cosmology",
        "rnp": "Rapid neutron-star parameter estimation (RNP)",
        "catalog_tracking": "Catalogue tracking",
        "publications": "Publications",
    }
)

SECTION_ALIASES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "info": ("info", "Info"),
        "gracedb": ("gracedb", "GraceDB"),
        "pe": ("pe", "ParameterEstimation"),
        "tgr": ("tgr", "TGR"),
        "lensing": ("lensing", "Lensing"),
        "detchar": ("detchar", "DetectorCharacterization", "DetectorCharacterisation"),
        "extreme_matter": ("extreme_matter", "ExtremeMatter"),
        "cosmology": ("cosmology", "Cosmology"),
        "rnp": ("rnp", "RapidParameterEstimation"),
        "catalog_tracking": ("catalog_tracking", "CatalogTracking", "CatalogueTracking"),
        "publications": ("publications", "Publications"),
    }
)

# Presentation-only policy for source sections absent from SECTION_ALIASES.
UNKNOWN_SECTION_FALLBACK: Mapping[str, str] = MappingProxyType(
    {"heading": "Additional metadata", "tier": "disclosure", "formatter": "text"}
)

_GRACEDB_EVENT_FIELDS = (
    FieldSpec("events[].uid", "Event identifier", "text", "detail"),
    FieldSpec("events[].pipeline", "Pipeline", "text", "detail"),
    FieldSpec("events[].state", "State", "status", "detail"),
    FieldSpec("events[].gps_time", "GPS time", "text", "disclosure"),
    FieldSpec("events[].far", "False-alarm rate (FAR)", "scientific", "detail"),
    FieldSpec("events[].network_snr", "Network signal-to-noise ratio", "scientific", "detail"),
    FieldSpec("events[].pastro", "Astrophysical probability", "probability", "disclosure"),
    FieldSpec("events[].p_bbh", "Binary black-hole probability", "probability", "disclosure"),
    FieldSpec("events[].p_bns", "Binary neutron-star probability", "probability", "disclosure"),
    FieldSpec("events[].p_nsbh", "Neutron-star–black-hole probability", "probability", "disclosure"),
    FieldSpec("events[].mass_1", "Primary mass", "scientific", "disclosure"),
    FieldSpec("events[].mass_2", "Secondary mass", "scientific", "disclosure"),
)
_PE_RESULT_FIELDS = (
    FieldSpec("results[].uid", "Result identifier", "text", "detail"),
    FieldSpec("results[].inference_software", "Inference software", "text", "detail"),
    FieldSpec("results[].waveform_approximant", "Waveform approximant", "text", "detail"),
    FieldSpec("results[].run_status", "Run status", "status", "detail"),
    FieldSpec("results[].review_status", "Review status", "status", "detail"),
    FieldSpec("results[].analysts", "Analysts", "list", "disclosure"),
    FieldSpec("results[].reviewers", "Reviewers", "list", "disclosure"),
    FieldSpec("results[].deprecated", "Deprecated", "boolean", "disclosure"),
)

FIELD_REGISTRY: Mapping[str, tuple[FieldSpec, ...]] = MappingProxyType(
    {
        "info": (
            FieldSpec("status", "Overall status", "status", "summary"),
            FieldSpec("notes", "Notes", "text", "detail"),
        ),
        "gracedb": (
            FieldSpec("instruments", "Instruments", "list", "summary"),
            FieldSpec("advok", "ADVOK state", "status", "summary"),
            FieldSpec("superevent_far", "False-alarm rate (FAR)", "scientific", "summary"),
            FieldSpec(
                "superevent_pastro",
                "Astrophysical probability (p_astro) classification",
                "probability",
                "summary",
            ),
            FieldSpec("notes", "Notes", "text", "detail"),
            *_GRACEDB_EVENT_FIELDS,
        ),
        "pe": (
            FieldSpec("status", "Parameter-estimation status", "status", "detail"),
            FieldSpec("analysts", "Analysts", "list", "detail"),
            FieldSpec("reviewers", "Reviewers", "list", "detail"),
            FieldSpec("notes", "Notes", "text", "detail"),
            *_PE_RESULT_FIELDS,
        ),
        "tgr": (
            FieldSpec("notes", "Notes", "text", "detail"),
            FieldSpec("results[].uid", "Analysis identifier", "text", "detail"),
            FieldSpec("results[].analysis_software", "Analysis software", "text", "detail"),
            FieldSpec("results[].analysts", "Analysts", "list", "disclosure"),
            FieldSpec("results[].description", "Description", "text", "disclosure"),
        ),
        "lensing": (
            FieldSpec("notes", "Notes", "text", "detail"),
            FieldSpec("multiplet_groups[].companion_sname", "Companion superevent", "text", "detail"),
            FieldSpec("singlet_analyses[].uid", "Singlet analysis identifier", "text", "detail"),
        ),
        "detchar": (FieldSpec("notes", "Notes", "text", "detail"),),
        "extreme_matter": (FieldSpec("notes", "Notes", "text", "detail"),),
        "cosmology": (FieldSpec("notes", "Notes", "text", "detail"),),
        "rnp": (FieldSpec("notes", "Notes", "text", "detail"),),
        "catalog_tracking": (FieldSpec("notes", "Notes", "text", "detail"),),
        "publications": (FieldSpec("notes", "Notes", "text", "detail"),),
    }
)


def validate_registry(
    registry: Mapping[str, tuple[FieldSpec, ...]] = FIELD_REGISTRY,
) -> None:
    """Reject invalid registry policy eagerly and independently of rendering."""

    for section, fields in registry.items():
        seen: set[str] = set()
        for field in fields:
            if field.tier not in TIERS:
                raise ValueError(f"unknown tier {field.tier!r} for {section}.{field.key}")
            if field.formatter not in FORMATTER_NAMES:
                raise ValueError(
                    f"unknown formatter {field.formatter!r} for {section}.{field.key}"
                )
            if field.key in seen:
                raise ValueError(f"duplicate registry path: {section}.{field.key}")
            seen.add(field.key)


validate_registry()


def KNOWN_KEYS() -> frozenset[str]:
    """Return immutable canonical full leaf-path patterns for every tier."""

    return frozenset(
        f"{section}.{field.key}"
        for section in SECTION_ORDER
        for field in FIELD_REGISTRY[section]
    )


def _canonical_leaf_paths(value: Any, path: str = "") -> Any:
    """Yield canonical scalar leaf paths, using ``[]`` for list indices."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _canonical_leaf_paths(child, child_path)
        return
    if isinstance(value, list):
        list_path = f"{path}[]"
        for child in value:
            yield from _canonical_leaf_paths(child, list_path)
        return
    yield path


def _has_registered_owner(path: str, known: frozenset[str]) -> bool:
    """Return True if ``path`` is, or descends from, a registered leaf path."""
    return any(
        path == candidate
        or path.startswith(f"{candidate}.")
        or path.startswith(f"{candidate}[]")
        for candidate in known
    )


def _unmapped_paths(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Return sorted, deduplicated canonical paths not covered by the registry."""
    known = KNOWN_KEYS()
    return tuple(
        sorted(
            {
                path
                for path in _canonical_leaf_paths(payload)
                if not _has_registered_owner(path, known)
            }
        )
    )


_MISSING = object()


def _find_source(payload: Mapping[str, Any], section_id: str) -> tuple[str, Any]:
    for alias in SECTION_ALIASES[section_id]:
        if alias in payload:
            return alias, payload[alias]
    return "", _MISSING


def _lookup(value: Any, path: str) -> Any:
    """Resolve canonical mapping and record-list paths without losing records."""

    current = value
    for part in path.split("."):
        if part.endswith("[]"):
            key = part.removesuffix("[]")
            if not isinstance(current, Mapping) or key not in current:
                return _MISSING
            current = current[key]
            if not isinstance(current, list):
                return _MISSING
            continue

        if isinstance(current, list):
            selected = []
            for record in current:
                if not isinstance(record, Mapping) or part not in record:
                    return _MISSING
                selected.append(record[part])
            current = selected
            continue

        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current

def _raw_label(key: str) -> str:
    return key.replace("_", " ").strip() or "Unnamed field"


def _node(path: str, label: str, value: Any) -> DisclosureNode:
    if isinstance(value, Mapping):
        children = tuple(
            _node(f"{path}.{key}", _raw_label(str(key)), child)
            for key, child in value.items()
        )
        return DisclosureNode(
            path, label, "mapping", children=children,
            leaf_count=sum(child.leaf_count for child in children),
        )
    if isinstance(value, list):
        children = tuple(
            _node(f"{path}[{index}]", f"Item {index + 1}", child)
            for index, child in enumerate(value)
        )
        shape = "record-list" if value and all(isinstance(item, Mapping) for item in value) else "scalar-list"
        return DisclosureNode(
            path, label, shape, value=() if not value else None, children=children,
            leaf_count=sum(child.leaf_count for child in children),
        )
    return DisclosureNode(path, label, "scalar", value=value, leaf_count=1)


def _field(section: str, spec: FieldSpec, value: Any) -> PresentationField:
    return PresentationField(
        path=f"{section}.{spec.key}",
        label=spec.label,
        raw_value=value,
        formatter=spec.formatter,
        tier=spec.tier,
    )


def _top_registered_key(path: str) -> str:
    return path.split(".", 1)[0].removesuffix("[]")


def _comparative_residual(
    section_id: str,
    record_key: str,
    records: list,
    registered_keys: frozenset[str],
) -> tuple[DisclosureNode, ...]:
    """Preserve unregistered leaves inside comparative records as disclosure nodes."""
    nodes: list[DisclosureNode] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            continue
        for key, child in record.items():
            if str(key) in registered_keys:
                continue
            nodes.append(
                _node(
                    f"{section_id}.{record_key}[{index}].{key}",
                    _raw_label(str(key)),
                    child,
                )
            )
    return tuple(nodes)


def _comparative(
    section_id: str,
    section: Mapping[str, Any],
    record_key: str,
    specs: tuple[FieldSpec, ...],
    default_keys: frozenset[str],
) -> ComparativeSet | None:
    records = section.get(record_key, _MISSING)
    if not isinstance(records, list):
        return None
    columns = tuple(
        ComparativeColumn(
            key=spec.key.rsplit(".", 1)[-1],
            path=f"{section_id}.{spec.key}",
            label=spec.label,
            formatter=spec.formatter,
            default_visible=spec.key.rsplit(".", 1)[-1] in default_keys,
            identity=index == 0,
        )
        for index, spec in enumerate(specs)
    )
    rows = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        cells = tuple(
            _field(
                section_id,
                spec,
                record.get(spec.key.rsplit(".", 1)[-1], None),
            )
            for spec in specs
        )
        rows.append(ComparativeRow(cells[0].raw_value if cells else None, cells))
    return ComparativeSet(record_key, columns, tuple(rows))


def _build_section(
    section_id: str,
    source_key: str,
    value: Any,
) -> MetadataSection:
    specs = FIELD_REGISTRY[section_id]
    mapping = value if isinstance(value, Mapping) else {}
    summary: list[PresentationField] = []
    detail: list[PresentationField] = []
    disclosure: list[DisclosureNode] = []
    consumed_top: set[str] = set()
    comparative_sets: list[ComparativeSet] = []

    comparative_roots = {"events"} if section_id == "gracedb" else {"results"} if section_id == "pe" else set()
    for spec in specs:
        top = _top_registered_key(spec.key)
        if top in comparative_roots:
            consumed_top.add(top)
            continue
        raw = _lookup(mapping, spec.key)
        if raw is _MISSING:
            continue
        consumed_top.add(top)
        prepared = _field(section_id, spec, raw)
        if "[]" in spec.key:
            # Ordinary record-list fields remain labelled recursive groups.
            # GraceDB and PE comparative roots are consumed before this branch.
            disclosure.append(_node(prepared.path, prepared.label, raw))
        elif spec.tier == "summary":
            summary.append(prepared)
        elif spec.tier == "detail":
            detail.append(prepared)
        else:
            disclosure.append(_node(prepared.path, prepared.label, raw))

    if section_id == "gracedb":
        table = _comparative(
            section_id,
            mapping,
            "events",
            _GRACEDB_EVENT_FIELDS,
            frozenset({"uid", "pipeline", "state", "far", "network_snr"}),
        )
        if table is not None:
            comparative_sets.append(table)
            records = mapping.get("events")
            if isinstance(records, list):
                disclosure.extend(
                    _comparative_residual(
                        section_id,
                        "events",
                        records,
                        frozenset(
                            spec.key.rsplit(".", 1)[-1]
                            for spec in _GRACEDB_EVENT_FIELDS
                        ),
                    )
                )
    elif section_id == "pe":
        table = _comparative(
            section_id,
            mapping,
            "results",
            _PE_RESULT_FIELDS,
            frozenset({"uid", "inference_software", "run_status", "review_status"}),
        )
        if table is not None:
            comparative_sets.append(table)
            records = mapping.get("results")
            if isinstance(records, list):
                disclosure.extend(
                    _comparative_residual(
                        section_id,
                        "results",
                        records,
                        frozenset(
                            spec.key.rsplit(".", 1)[-1]
                            for spec in _PE_RESULT_FIELDS
                        ),
                    )
                )

    for key, child in mapping.items():
        if str(key) not in consumed_top:
            disclosure.append(_node(f"{section_id}.{key}", _raw_label(str(key)), child))

    if not isinstance(value, Mapping):
        disclosure.append(_node(section_id, SECTION_HEADINGS[section_id], value))

    if comparative_sets:
        shape = "comparative"
    elif isinstance(value, Mapping) and all(
        not isinstance(child, (Mapping, list)) for child in value.values()
    ):
        shape = "scalar-mapping"
    elif isinstance(value, Mapping):
        shape = "nested"
    elif isinstance(value, list):
        shape = "record-list" if value and all(isinstance(item, Mapping) for item in value) else "scalar-list"
    else:
        shape = "scalar"

    return MetadataSection(
        id=section_id,
        source_key=source_key,
        heading=SECTION_HEADINGS[section_id],
        summary=tuple(summary),
        detail=tuple(detail),
        disclosure=tuple(disclosure),
        disclosed_leaf_count=sum(node.leaf_count for node in disclosure),
        data_shape=shape,
        comparative_sets=tuple(comparative_sets),
    )


def build_metadata_presentation(
    payload: Mapping[str, Any], *, historical: bool = False
) -> MetadataPresentation:
    """Build immutable template-ready metadata without I/O or request state."""

    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")

    sections: list[MetadataSection] = []
    root_summary: list[PresentationField] = []
    recognised_sources: set[str] = set()
    for section_id in SECTION_ORDER:
        source_key, value = _find_source(payload, section_id)
        if value is _MISSING:
            continue
        recognised_sources.add(source_key)
        section = _build_section(section_id, source_key, value)
        sections.append(section)
        root_summary.extend(section.summary)

    for source_key, value in payload.items():
        if source_key in recognised_sources:
            continue
        node = _node(str(source_key), _raw_label(str(source_key)), value)
        sections.append(
            MetadataSection(
                id=f"unknown:{source_key}",
                source_key=str(source_key),
                heading=f"{UNKNOWN_SECTION_FALLBACK['heading']}: {_raw_label(str(source_key))}",
                summary=(),
                detail=(),
                disclosure=(node,),
                disclosed_leaf_count=node.leaf_count,
                data_shape=node.shape,
                fallback=True,
            )
        )

    unmapped = _unmapped_paths(payload)
    if unmapped:
        logger.warning(
            "unmapped gwflow metadata leaf paths: %s",
            ", ".join(unmapped),
        )

    return MetadataPresentation(bool(historical), tuple(root_summary), tuple(sections))
