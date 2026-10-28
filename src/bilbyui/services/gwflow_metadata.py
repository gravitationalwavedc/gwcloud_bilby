"""Declarative presentation registry for GWFlow portal metadata.

Canonical paths use ``.`` between mapping keys and ``[]`` after a key whose
value is a list of records, for example ``gracedb.events[].uid``.  Concrete
list indices never occur in registry paths.  Unknown paths are deliberately
not matched by wildcards, so callers can detect upstream schema drift.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
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
        "people",
        "reviews",
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
SECTION_ORDER: tuple[str, ...] = ("info", "gracedb", "pe", "detchar", "catalog_tracking")

SECTION_HEADINGS: Mapping[str, str] = MappingProxyType(
    {
        "info": "Info",
        "gracedb": "GraceDB",
        "pe": "Parameter estimation (PE)",
        "detchar": "Detector characterisation (DetChar)",
        "catalog_tracking": "Catalogue tracking",
    }
)

SECTION_SOURCES: Mapping[str, str] = MappingProxyType(
    {
        "gracedb": "gracedb_events",
        "pe": "analyses",
        "detchar": "detector_configurations",
        "catalog_tracking": "catalog_connections",
    }
)
INFO_KEYS = ("sname", "libraries", "version_number", "record_timestamp", "commit_sha", "is_current")
RECOGNISED_ROOT_KEYS = frozenset((*INFO_KEYS, *SECTION_SOURCES.values(), "raw_payload"))
RECOGNISED_NON_DISPLAYED_PATHS = frozenset(
    {
        "raw_payload",
        "analyses[].type",
        "analyses[].revision",
        "analyses[].suggested_detector_configuration_uids[]",
        "analyses[].analysts[].email_address",
        "analyses[].reviews[].reviewers[].email_address",
    }
)
COMPARATIVE_DESCENDANT_PATHS = frozenset(
    {
        "analyses[].analysts[].name",
        "analyses[].reviews[].occurrence_uid",
        "analyses[].reviews[].name",
        "analyses[].reviews[].description",
        "analyses[].reviews[].reviewers[].name",
        "analyses[].reviews[].passed_review",
        "analyses[].reviews[].completion_date",
        "analyses[].reviews[].review_status",
    }
)

UNKNOWN_SECTION_FALLBACK: Mapping[str, str] = MappingProxyType(
    {"heading": "Additional metadata", "tier": "disclosure", "formatter": "text"}
)

_GRACEDB_EVENT_FIELDS = (
    FieldSpec("gracedb_events[].event_name", "Event name", "text", "detail"),
    FieldSpec("gracedb_events[].has_ns", "Has neutron star (probability)", "probability", "detail"),
    FieldSpec("gracedb_events[].has_remnant", "Has remnant (probability)", "probability", "detail"),
    FieldSpec("gracedb_events[].has_mass_gap", "Has mass gap (probability)", "probability", "disclosure"),
    FieldSpec(
        "gracedb_events[].pipeline_has_ns",
        "Pipeline: has neutron star (probability)",
        "probability",
        "disclosure",
    ),
    FieldSpec(
        "gracedb_events[].pipeline_has_remnant",
        "Pipeline: has remnant (probability)",
        "probability",
        "disclosure",
    ),
    FieldSpec(
        "gracedb_events[].pipeline_has_mass_gap",
        "Pipeline: has mass gap (probability)",
        "probability",
        "disclosure",
    ),
)
_PE_RESULT_FIELDS = (
    FieldSpec("analyses[].uid", "UID", "text", "detail"),
    FieldSpec("analyses[].name", "Name", "text", "detail"),
    FieldSpec("analyses[].status", "Status", "status", "detail"),
    FieldSpec("analyses[].review_status", "Review status", "status", "detail"),
    FieldSpec("analyses[].deprecated", "Deprecated", "boolean", "detail"),
    FieldSpec("analyses[].description", "Description", "text", "disclosure"),
    FieldSpec("analyses[].software.name", "Software name", "text", "disclosure"),
    FieldSpec("analyses[].software.version", "Software version", "text", "disclosure"),
    FieldSpec("analyses[].analysts", "Analysts", "people", "disclosure"),
    FieldSpec("analyses[].reviews", "Reviews", "reviews", "disclosure"),
    FieldSpec("analyses[].configurations", "Configurations", "list", "disclosure"),
    FieldSpec("analyses[].input_files", "Input files", "list", "disclosure"),
    FieldSpec("analyses[].output_files", "Output files", "list", "disclosure"),
    FieldSpec("analyses[].in_catalog", "In catalog", "boolean", "disclosure"),
)

FIELD_REGISTRY: Mapping[str, tuple[FieldSpec, ...]] = MappingProxyType(
    {
        "info": (
            FieldSpec("sname", "Superevent name", "text", "summary"),
            FieldSpec("libraries", "Libraries", "list", "summary"),
            FieldSpec("version_number", "Version number", "text", "summary"),
            FieldSpec("record_timestamp", "Recorded", "utc_timestamp", "summary"),
            FieldSpec("commit_sha", "Commit", "text", "detail"),
            FieldSpec("is_current", "Current version", "boolean", "detail"),
        ),
        "gracedb": _GRACEDB_EVENT_FIELDS,
        "pe": _PE_RESULT_FIELDS,
        "detchar": (FieldSpec("detector_configurations[]", "Detector configurations", "text", "disclosure"),),
        "catalog_tracking": (FieldSpec("catalog_connections[]", "Catalog connections", "text", "disclosure"),),
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
                raise ValueError(f"unknown formatter {field.formatter!r} for {section}.{field.key}")
            if field.key in seen:
                raise ValueError(f"duplicate registry path: {section}.{field.key}")
            seen.add(field.key)


validate_registry()


def KNOWN_KEYS() -> frozenset[str]:
    """Return immutable canonical full leaf-path patterns for every tier."""

    return frozenset(field.key for section in SECTION_ORDER for field in FIELD_REGISTRY[section])


def _iter_leaf_paths(value: Any, path: str = "") -> tuple[str, ...]:
    """Return sorted, deduplicated canonical scalar leaf paths."""

    paths: set[str] = set()

    def walk(child: Any, child_path: str) -> None:
        if child_path == "raw_payload" or child_path.startswith("raw_payload."):
            return
        if isinstance(child, Mapping):
            for key, nested in child.items():
                nested_path = f"{child_path}.{key}" if child_path else str(key)
                walk(nested, nested_path)
            return

        if isinstance(child, Sequence) and not isinstance(child, (str, bytes, bytearray)):
            sequence_path = f"{child_path}[]"
            for nested in child:
                walk(nested, sequence_path)
            return

        if child_path:
            paths.add(child_path)

    walk(value, path)
    return tuple(sorted(paths))


def _unmapped_paths(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Return canonical scalar leaf paths absent from presentation policy."""

    known = KNOWN_KEYS()
    scalar_comparative_owners = frozenset(
        field.key
        for section_id in ("gracedb", "pe")
        for field in FIELD_REGISTRY[section_id]
        if field.formatter not in {"people", "reviews"}
    )

    def is_registered(path: str) -> bool:
        normalised = path.removesuffix("[]")
        if normalised in RECOGNISED_NON_DISPLAYED_PATHS:
            return True
        if normalised in COMPARATIVE_DESCENDANT_PATHS:
            return True
        if normalised in known:
            return True
        return any(path.startswith(f"{owner}.") or path.startswith(f"{owner}[]") for owner in scalar_comparative_owners)

    return tuple(sorted(path for path in _iter_leaf_paths(payload) if not is_registered(path)))


@lru_cache(maxsize=512)
def _emit_unmapped_metadata_warning(sname: str, path: str) -> None:
    logger.warning(
        "unmapped gwflow metadata leaf",
        extra={"path": path, "sname": sname},
    )


def _reset_unmapped_warning_cache() -> None:
    """Clear process-local warning suppression state for isolated tests."""

    _emit_unmapped_metadata_warning.cache_clear()


def warn_unmapped_metadata_leaves(payload: Mapping[str, Any], *, sname: Any) -> None:
    """Rate-limit warnings by process-local sname and canonical leaf path."""

    if not isinstance(payload, Mapping):
        return

    normalised_sname = str(sname).strip() if sname is not None else ""
    normalised_sname = normalised_sname or "unknown"
    try:
        for path in _unmapped_paths(payload):
            _emit_unmapped_metadata_warning(normalised_sname, path)
    except RecursionError:
        logger.warning(
            "unmapped metadata leaf walk truncated: payload too deeply nested",
            extra={"sname": normalised_sname},
        )


_MISSING = object()


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


def _node(path: str, label: str, value: Any, identity_keys: tuple[str, ...] = ()) -> DisclosureNode:
    if isinstance(value, Mapping):
        children = tuple(_node(f"{path}.{key}", _raw_label(str(key)), child) for key, child in value.items())
        return DisclosureNode(
            path,
            label,
            "mapping",
            value=value if not value else None,
            children=children,
            leaf_count=sum(child.leaf_count for child in children),
        )
    if isinstance(value, list):
        children = []
        for index, child in enumerate(value):
            child_label = f"Item {index + 1}"
            if isinstance(child, Mapping) and identity_keys:
                identity = [child.get(key) for key in identity_keys]
                if all(item is not None for item in identity):
                    child_label = ":".join(str(item) for item in identity)
            children.append(_node(f"{path}[{index}]", child_label, child))
        children_tuple = tuple(children)
        shape = "record-list" if value and all(isinstance(item, Mapping) for item in value) else "scalar-list"
        return DisclosureNode(
            path,
            label,
            shape,
            value=() if not value else None,
            children=children_tuple,
            leaf_count=sum(child.leaf_count for child in children_tuple),
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


def _disclosure_value(key: str, value: Any) -> Any:
    """Remove deliberately non-displayed email fields without hiding other metadata."""
    if key == "analysts" and isinstance(value, list):
        return [
            {nested_key: nested for nested_key, nested in analyst.items() if nested_key != "email_address"}
            if isinstance(analyst, Mapping)
            else analyst
            for analyst in value
        ]

    if key == "reviews" and isinstance(value, list):
        sanitised_reviews = []
        for review in value:
            if not isinstance(review, Mapping):
                sanitised_reviews.append(review)
                continue
            sanitised_review = dict(review)
            reviewers = sanitised_review.get("reviewers")
            if isinstance(reviewers, list):
                sanitised_review["reviewers"] = [
                    {nested_key: nested for nested_key, nested in reviewer.items() if nested_key != "email_address"}
                    if isinstance(reviewer, Mapping)
                    else reviewer
                    for reviewer in reviewers
                ]
            sanitised_reviews.append(sanitised_review)
        return sanitised_reviews

    return value


def _comparative_residual(
    section_id: str,
    record_key: str,
    indexed_records: list[tuple[int, Any]],
    registered_keys: frozenset[str],
    disclosed_keys: frozenset[str] = frozenset(),
) -> tuple[DisclosureNode, ...]:
    """Preserve unregistered leaves inside comparative records as disclosure nodes."""
    nodes: list[DisclosureNode] = []
    for source_index, record in indexed_records:
        if not isinstance(record, Mapping):
            continue
        for key, child in record.items():
            key_text = str(key)
            if key_text in registered_keys and key_text not in disclosed_keys:
                continue
            nodes.append(
                _node(
                    f"{section_id}.{record_key}[{source_index}].{key}",
                    _raw_label(str(key)),
                    _disclosure_value(key_text, child),
                )
            )
    return tuple(nodes)


def _comparative(
    section_id: str,
    records: list[Any],
    record_key: str,
    specs: tuple[FieldSpec, ...],
    default_keys: frozenset[str],
) -> ComparativeSet | None:
    columns = tuple(
        ComparativeColumn(
            key=spec.key.removeprefix(f"{record_key}[]."),
            path=f"{section_id}.{spec.key}",
            label=spec.label,
            formatter=spec.formatter,
            default_visible=spec.key.removeprefix(f"{record_key}[].") in default_keys,
            identity=index == 0,
        )
        for index, spec in enumerate(specs)
    )
    rows = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        cells = []
        for spec in specs:
            relative_key = spec.key.removeprefix(f"{record_key}[].")
            raw = _lookup(record, relative_key)
            cells.append(_field(section_id, spec, None if raw is _MISSING else raw))
        cell_tuple = tuple(cells)
        rows.append(ComparativeRow(cell_tuple[0].raw_value if cell_tuple else None, cell_tuple))
    if not rows:
        return None
    return ComparativeSet(record_key, columns, tuple(rows))


def _build_info_section(payload: Mapping[str, Any]) -> MetadataSection:
    summary = []
    detail = []
    for spec in FIELD_REGISTRY["info"]:
        raw = _lookup(payload, spec.key)
        if raw is _MISSING:
            continue
        if spec.key == "libraries" and isinstance(raw, list):
            raw = sorted(raw, key=str)
        prepared = _field("info", spec, raw)
        (summary if spec.tier == "summary" else detail).append(prepared)
    return MetadataSection(
        id="info",
        source_key="",
        heading=SECTION_HEADINGS["info"],
        summary=tuple(summary),
        detail=tuple(detail),
        disclosure=(),
        disclosed_leaf_count=0,
        data_shape="scalar-mapping",
    )


def _build_section(section_id: str, source_key: str, value: Any) -> MetadataSection:
    disclosure: list[DisclosureNode] = []
    comparative_sets: list[ComparativeSet] = []

    if section_id == "gracedb" and isinstance(value, list):
        table = _comparative(
            section_id,
            value,
            source_key,
            _GRACEDB_EVENT_FIELDS,
            frozenset({"event_name", "has_ns", "has_remnant"}),
        )
        if table is not None:
            comparative_sets.append(table)
        disclosure.extend(
            _comparative_residual(
                section_id,
                source_key,
                list(enumerate(value)),
                frozenset(spec.key.removeprefix(f"{source_key}[].").split(".", 1)[0] for spec in _GRACEDB_EVENT_FIELDS),
            )
        )
    elif section_id == "pe" and isinstance(value, list):
        indexed_records = [
            (source_index, record)
            for source_index, record in enumerate(value)
            if isinstance(record, Mapping) and record.get("type") == "pe"
        ]
        records = [record for _source_index, record in indexed_records]
        table = _comparative(
            section_id,
            records,
            source_key,
            _PE_RESULT_FIELDS,
            frozenset({"uid", "name", "status", "review_status", "deprecated"}),
        )
        if table is not None:
            comparative_sets.append(table)
        disclosure.extend(
            _comparative_residual(
                section_id,
                source_key,
                indexed_records,
                frozenset(spec.key.removeprefix(f"{source_key}[].").split(".", 1)[0] for spec in _PE_RESULT_FIELDS),
                frozenset(
                    {
                        "analysts",
                        "reviews",
                        "configurations",
                        "input_files",
                        "output_files",
                    }
                ),
            )
        )
    elif section_id == "detchar":
        disclosure.append(
            _node(
                f"{section_id}.{source_key}",
                FIELD_REGISTRY[section_id][0].label,
                value,
                ("uid",),
            )
        )
    elif section_id == "catalog_tracking":
        disclosure.append(
            _node(
                f"{section_id}.{source_key}",
                FIELD_REGISTRY[section_id][0].label,
                value,
                ("catalog_number", "catalog_version"),
            )
        )

    if comparative_sets:
        shape = "comparative"
    elif isinstance(value, list):
        shape = "record-list" if value and all(isinstance(item, Mapping) for item in value) else "scalar-list"
    else:
        shape = "scalar"

    return MetadataSection(
        id=section_id,
        source_key=source_key,
        heading=SECTION_HEADINGS[section_id],
        summary=(),
        detail=(),
        disclosure=tuple(disclosure),
        disclosed_leaf_count=sum(node.leaf_count for node in disclosure),
        data_shape=shape,
        comparative_sets=tuple(comparative_sets),
    )


def build_metadata_presentation(payload: Mapping[str, Any], *, historical: bool = False) -> MetadataPresentation:
    """Build immutable template-ready metadata without I/O or request state."""

    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")

    try:
        return _build_presentation(payload, historical=historical)
    except RecursionError:
        logger.warning(
            "metadata presentation truncated: payload too deeply nested",
            extra={"payload_keys": list(payload.keys()) if isinstance(payload, Mapping) else None},
        )
        return MetadataPresentation(bool(historical), (), ())


def _build_presentation(payload: Mapping[str, Any], *, historical: bool) -> MetadataPresentation:
    sections: list[MetadataSection] = []
    root_summary: list[PresentationField] = []

    info = _build_info_section(payload)
    if info.summary or info.detail:
        sections.append(info)
        root_summary.extend(info.summary)

    for section_id in SECTION_ORDER[1:]:
        source_key = SECTION_SOURCES[section_id]
        value = payload.get(source_key, _MISSING)
        if value is _MISSING or value == []:
            continue
        section = _build_section(section_id, source_key, value)
        if section_id in {"gracedb", "pe"} and not section.comparative_sets:
            continue
        sections.append(section)

    for source_key, value in payload.items():
        if source_key in RECOGNISED_ROOT_KEYS:
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

    return MetadataPresentation(bool(historical), tuple(root_summary), tuple(sections))
