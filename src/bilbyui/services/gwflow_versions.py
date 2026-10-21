"""Canonical GWFlow version summaries and semantic presentation types.

Version history snapshots are built only from canonical portal summary fields.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from bilbyui.utils.gwflow_es import _parse_portal_bool

SemanticPresentationStatus = Literal[
    "semantic",
    "semantic_empty",
    "no_baseline",
    "unavailable",
    "failed",
]

_ROOT_KEYS = {
    "sname",
    "baseline_version",
    "selected_version",
    "baseline_timestamp",
    "selected_timestamp",
    "changes",
}
_CHANGE_KEYS = {
    "entity_type",
    "identity",
    "kind",
    "before",
    "after",
    "field_diffs",
}
_ENTITY_RANKS = {
    "analysis": 0,
    "detector_configuration": 1,
    "gracedb_event": 2,
    "catalog_connection": 3,
    "review": 4,
}
_ANALYSIS_KINDS = {"added", "removed", "modified", "deprecated"}
_OTHER_KINDS = {"added", "removed", "modified"}
_REVIEW_IDENTITY_KEYS = {"analysis_uid", "occurrence_uid"}
_REVIEW_RECORD_KEYS = {
    "occurrence_uid",
    "name",
    "description",
    "reviewers",
    "passed_review",
    "completion_date",
    "review_status",
}
_REVIEWER_KEYS = {"name", "email_address"}
_REVIEW_STATUSES = {"pending", "approved", "rejected"}
_GRACEDB_NUMBER_KEYS = {
    "has_ns",
    "has_remnant",
    "has_mass_gap",
    "pipeline_has_ns",
    "pipeline_has_remnant",
    "pipeline_has_mass_gap",
}


@dataclass(frozen=True, slots=True)
class VersionSnapshot:
    full_sha: str
    short_sha: str
    version_number: int
    recorded_at: datetime | None
    is_current: bool


@dataclass(frozen=True, slots=True)
class SemanticPresentationRow:
    entity_type: str
    identity: Any
    kind: str
    before: Any
    after: Any
    field_diffs: Any


@dataclass(frozen=True, slots=True)
class SemanticPresentationOutcome:
    status: SemanticPresentationStatus
    rows: tuple[SemanticPresentationRow, ...] = ()
    sname: str | None = None
    baseline_version: int | None = None
    selected_version: int | None = None
    baseline_timestamp: str | None = None
    selected_timestamp: str | None = None
    reason: str | None = None


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace(" UTC", "+00:00").replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace(" UTC", "+00:00").replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _failed(reason: str) -> SemanticPresentationOutcome:
    return SemanticPresentationOutcome(status="failed", reason=reason[:64])


def _validate_review_record(value: Any, occurrence_uid: str) -> bool:
    if not isinstance(value, Mapping):
        return False
    if not _REVIEW_RECORD_KEYS.issubset(value):
        return False

    if not _non_empty_string(value["occurrence_uid"]):
        return False
    if value["occurrence_uid"] != occurrence_uid:
        return False
    if not all(isinstance(value[field], str) for field in ("name", "description")):
        return False

    reviewers = value["reviewers"]
    if not isinstance(reviewers, list):
        return False
    for reviewer in reviewers:
        if not isinstance(reviewer, Mapping):
            return False
        if set(reviewer) != _REVIEWER_KEYS:
            return False
        if not all(isinstance(reviewer[field], str) for field in _REVIEWER_KEYS):
            return False

    if value["passed_review"] is not None and not isinstance(value["passed_review"], bool):
        return False
    if value["completion_date"] is not None and not isinstance(value["completion_date"], str):
        return False
    review_status = value["review_status"]
    if not isinstance(review_status, str) or review_status not in _REVIEW_STATUSES:
        return False

    expected_decision = {
        "pending": None,
        "approved": True,
        "rejected": False,
    }[review_status]
    return value["passed_review"] is expected_decision


def _validate_gracedb_record(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, Mapping):
        return False
    for field in _GRACEDB_NUMBER_KEYS:
        if field not in value:
            continue
        number = value[field]
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float))):
            return False
    return True


def _identity_key(entity_type: str, identity: Any) -> str | tuple[str, str]:
    if entity_type == "review":
        return identity["analysis_uid"], identity["occurrence_uid"]
    return identity


def _validate_change(change: Any, index: int) -> tuple[SemanticPresentationRow | None, str | None]:
    path = f"changes[{index}]"
    if not isinstance(change, Mapping):
        return None, f"invalid_mapping:{path}"
    if set(change) != _CHANGE_KEYS:
        return None, f"invalid_keys:{path}"

    entity_type = change["entity_type"]
    if not isinstance(entity_type, str) or entity_type not in _ENTITY_RANKS:
        return None, f"invalid_enum:{path}.entity_type"

    identity = change["identity"]
    if entity_type == "review":
        if not isinstance(identity, Mapping):
            return None, f"invalid_identity:{path}"
        if set(identity) != _REVIEW_IDENTITY_KEYS:
            return None, f"invalid_identity:{path}"
        if not all(_non_empty_string(identity[field]) for field in ("analysis_uid", "occurrence_uid")):
            return None, f"invalid_identity:{path}"
    elif not _non_empty_string(identity):
        return None, f"invalid_identity:{path}"

    kind = change["kind"]
    allowed_kinds = _ANALYSIS_KINDS if entity_type == "analysis" else _OTHER_KINDS
    if not isinstance(kind, str) or kind not in allowed_kinds:
        return None, f"invalid_enum:{path}.kind"

    before = change["before"]
    after = change["after"]
    field_diffs = change["field_diffs"]
    if kind == "added":
        if before is not None or not isinstance(after, Mapping):
            return None, f"invalid_record_sides:{path}"
        if field_diffs != {}:
            return None, f"invalid_field_diff:{path}"
    elif kind == "removed":
        if not isinstance(before, Mapping) or after is not None:
            return None, f"invalid_record_sides:{path}"
        if field_diffs != {}:
            return None, f"invalid_field_diff:{path}"
    else:
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            return None, f"invalid_record_sides:{path}"
        if not isinstance(field_diffs, Mapping):
            return None, f"invalid_field_diff:{path}"

    if not isinstance(field_diffs, Mapping):
        return None, f"invalid_field_diff:{path}"
    for difference in field_diffs.values():
        if not isinstance(difference, Mapping):
            return None, f"invalid_field_diff:{path}"
        if set(difference) != {"baseline", "selected"}:
            return None, f"invalid_field_diff:{path}"

    if entity_type == "review":
        occurrence_uid = identity["occurrence_uid"]
        for side in (before, after):
            if side is not None and not _validate_review_record(side, occurrence_uid):
                return None, f"invalid_review_record:{path}"

    if entity_type == "gracedb_event":
        for side in (before, after):
            if not _validate_gracedb_record(side):
                return None, f"invalid_gracedb_record:{path}"

    return (
        SemanticPresentationRow(
            entity_type=entity_type,
            identity=identity,
            kind=kind,
            before=before,
            after=after,
            field_diffs=field_diffs,
        ),
        None,
    )


def adapt_semantic_diff(
    *,
    sname: str,
    baseline_version: int | None,
    selected_version: int,
    payload: Any,
    state: str,
) -> SemanticPresentationOutcome:
    """Validate and expose an authoritative portal semantic diff unchanged."""

    if baseline_version is None:
        return SemanticPresentationOutcome(
            status="no_baseline",
            sname=sname,
            baseline_version=None,
            selected_version=selected_version,
            reason="earlier_version_required",
        )
    if state == "down":
        return SemanticPresentationOutcome(
            status="unavailable",
            sname=sname,
            baseline_version=baseline_version,
            selected_version=selected_version,
            reason="service_unavailable",
        )
    if state in {"failed", "malformed"}:
        return SemanticPresentationOutcome(
            status="failed",
            sname=sname,
            baseline_version=baseline_version,
            selected_version=selected_version,
            reason=f"client_state:{state}",
        )
    if state not in {"live", "stale"}:
        return _failed("invalid_state:state")
    if payload is None:
        return _failed("missing_payload:payload")
    if not isinstance(payload, Mapping):
        return _failed("invalid_mapping:root")
    if set(payload) != _ROOT_KEYS:
        return _failed("invalid_keys:root")

    if not _non_empty_string(payload["sname"]):
        return _failed("invalid_string:sname")
    for field in ("baseline_version", "selected_version"):
        if not _is_int(payload[field]):
            return _failed(f"invalid_integer:{field}")
    for field in ("baseline_timestamp", "selected_timestamp"):
        if not _aware_timestamp(payload[field]):
            return _failed(f"invalid_timestamp:{field}")
    if not isinstance(payload["changes"], list):
        return _failed("invalid_list:changes")

    if payload["sname"] != sname:
        return _failed("request_mismatch:sname")
    if payload["baseline_version"] != baseline_version:
        return _failed("request_mismatch:baseline_version")
    if payload["selected_version"] != selected_version:
        return _failed("request_mismatch:selected_version")

    rows: list[SemanticPresentationRow] = []
    previous_order: tuple[int, str | tuple[str, str], str] | None = None
    for index, change in enumerate(payload["changes"]):
        row, reason = _validate_change(change, index)
        if reason is not None or row is None:
            return _failed(reason or f"invalid_change:changes[{index}]")

        if not isinstance(row.entity_type, str) or row.entity_type not in _ENTITY_RANKS:
            return _failed(f"invalid_enum:changes[{index}].entity_type")
        rank = _ENTITY_RANKS[row.entity_type]
        identity_key = _identity_key(row.entity_type, row.identity)
        if previous_order is not None:
            previous_rank, previous_identity, previous_kind = previous_order
            if rank < previous_rank:
                return _failed(f"invalid_order:changes[{index}].entity_type")
            if rank == previous_rank:
                if identity_key < previous_identity:
                    return _failed(f"invalid_order:changes[{index}].identity")
                if identity_key == previous_identity and row.kind < previous_kind:
                    return _failed(f"invalid_order:changes[{index}].kind")
        previous_order = rank, identity_key, row.kind
        rows.append(row)

    return SemanticPresentationOutcome(
        status="semantic" if rows else "semantic_empty",
        rows=tuple(rows),
        sname=payload["sname"],
        baseline_version=payload["baseline_version"],
        selected_version=payload["selected_version"],
        baseline_timestamp=payload["baseline_timestamp"],
        selected_timestamp=payload["selected_timestamp"],
    )


def prepare_version_snapshots(
    versions: Sequence[Mapping[str, Any]],
    *,
    current_sha: str = "",
) -> tuple[VersionSnapshot, ...]:
    """Create a deterministic oldest-to-newest canonical summary snapshot.

    Invalid canonical rows are rejected by raising ``ValueError`` rather than
    being skipped: ``version_number`` must be present and must be an integer,
    with booleans explicitly excluded. Portal order is not treated as
    chronology. Parseable timestamps establish ordering; SHA provides
    deterministic tie handling without inventing a chronology. Rows without a
    timestamp retain their source order after dated rows.
    """

    prepared: list[tuple[int, VersionSnapshot]] = []
    for index, row in enumerate(versions):
        version_number = row.get("version_number")
        if isinstance(version_number, bool) or not isinstance(version_number, int):
            raise ValueError("version_number must be an integer")

        sha = str(row.get("commit_sha") or "").strip()
        if not sha:
            continue
        snapshot = VersionSnapshot(
            full_sha=sha,
            short_sha=sha[:8],
            version_number=version_number,
            recorded_at=_timestamp(row.get("record_timestamp")),
            is_current=bool(current_sha and sha == current_sha) or _parse_portal_bool(row.get("is_current")),
        )
        prepared.append((index, snapshot))

    dated = [(index, item) for index, item in prepared if item.recorded_at is not None]
    undated = [(index, item) for index, item in prepared if item.recorded_at is None]
    dated.sort(key=lambda pair: (pair[1].recorded_at, pair[1].full_sha))
    ordered = [item for _, item in dated] + [item for _, item in undated]
    return tuple(ordered)


def resolve_version_number(snapshots: Sequence[VersionSnapshot], commit_sha: str) -> int:
    """Resolve a commit SHA to its canonical summary version number."""

    snapshot = next((item for item in snapshots if item.full_sha == commit_sha), None)
    if snapshot is None:
        raise LookupError("Version not found")
    return snapshot.version_number


def resolve_history_selection(
    snapshots: Sequence[VersionSnapshot],
    *,
    requested_sha: str | None,
    compare: str | None,
) -> tuple[VersionSnapshot, VersionSnapshot | None, str]:
    """Resolve selected and baseline versions inside one authorised snapshot."""

    mode = compare if compare in {"prev", "current"} else "prev"
    current = next((item for item in snapshots if item.is_current), None)
    if current is None and snapshots:
        current = snapshots[-1]
    if not snapshots or current is None:
        raise LookupError("No version history is available")
    if requested_sha:
        selected = next((item for item in snapshots if item.full_sha == requested_sha), None)
        if selected is None:
            raise LookupError("Version not found")
    else:
        selected = current

    if mode == "current":
        baseline = current
    else:
        selected_index = snapshots.index(selected)
        baseline = snapshots[selected_index - 1] if selected_index else None
    return selected, baseline, mode


__all__ = [
    "SemanticPresentationOutcome",
    "SemanticPresentationRow",
    "SemanticPresentationStatus",
    "VersionSnapshot",
    "adapt_semantic_diff",
    "prepare_version_snapshots",
    "resolve_history_selection",
    "resolve_version_number",
]
