"""Pure preparation and comparison helpers for GWFlow version history."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

DiffStatus = Literal[
    "semantic",
    "no_baseline",
    "cross_schema",
    "unsupported_shape",
    "unavailable",
    "failed",
]
ChangeKind = Literal["added", "removed", "changed"]
_MISSING = object()


@dataclass(frozen=True, slots=True)
class VersionSnapshot:
    full_sha: str
    short_sha: str
    schema_version: str
    recorded_at: datetime | None
    payload: Any
    is_current: bool


@dataclass(frozen=True, slots=True)
class ChangeRecord:
    path: tuple[str | int, ...]
    kind: ChangeKind
    baseline_present: bool
    baseline_value: Any
    selected_present: bool
    selected_value: Any


@dataclass(frozen=True, slots=True)
class DiffOutcome:
    status: DiffStatus
    changes: tuple[ChangeRecord, ...] = ()
    baseline_schema: str | None = None
    selected_schema: str | None = None
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


def prepare_version_snapshots(
    versions: Sequence[Mapping[str, Any]],
    *,
    current_sha: str = "",
) -> tuple[VersionSnapshot, ...]:
    """Create one deterministic oldest-to-newest snapshot from portal rows.

    Portal order is not treated as chronology. Parseable timestamps establish
    ordering; SHA provides deterministic tie handling without inventing a
    chronology. Rows without a timestamp retain their source order after dated
    rows.
    """

    prepared: list[tuple[int, VersionSnapshot]] = []
    for index, row in enumerate(versions):
        sha = str(row.get("commit_sha") or row.get("sha") or "").strip()
        if not sha:
            continue
        payload = row.get("payload", row.get("data"))
        snapshot = VersionSnapshot(
            full_sha=sha,
            short_sha=sha[:8],
            schema_version=str(row.get("schema_version") or ""),
            recorded_at=_timestamp(row.get("commit_timestamp") or row.get("timestamp")),
            payload=payload,
            is_current=bool(current_sha and sha == current_sha) or bool(row.get("is_current")),
        )
        prepared.append((index, snapshot))

    dated = [(index, item) for index, item in prepared if item.recorded_at is not None]
    undated = [(index, item) for index, item in prepared if item.recorded_at is None]
    dated.sort(key=lambda pair: (pair[1].recorded_at, pair[1].full_sha))
    ordered = [item for _, item in dated] + [item for _, item in undated]
    return tuple(ordered)


def _same_scalar(left: Any, right: Any) -> bool:
    return type(left) is type(right) and left == right


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _record(
    path: tuple[str | int, ...],
    kind: ChangeKind,
    baseline: Any = _MISSING,
    selected: Any = _MISSING,
) -> ChangeRecord:
    return ChangeRecord(
        path=path,
        kind=kind,
        baseline_present=baseline is not _MISSING,
        baseline_value=None if baseline is _MISSING else baseline,
        selected_present=selected is not _MISSING,
        selected_value=None if selected is _MISSING else selected,
    )


class _UnstableList(ValueError):
    pass


def _walk(baseline: Any, selected: Any, path: tuple[str | int, ...]) -> list[ChangeRecord]:
    if baseline is _MISSING:
        return [_record(path, "added", selected=selected)]
    if selected is _MISSING:
        return [_record(path, "removed", baseline=baseline)]

    baseline_mapping = isinstance(baseline, Mapping)
    selected_mapping = isinstance(selected, Mapping)
    baseline_list = _is_sequence(baseline)
    selected_list = _is_sequence(selected)

    if baseline_mapping != selected_mapping or baseline_list != selected_list:
        return [_record(path, "changed", baseline, selected)]

    if baseline_mapping:
        changes: list[ChangeRecord] = []
        keys = sorted(set(baseline) | set(selected), key=str)
        for key in keys:
            changes.extend(
                _walk(
                    baseline.get(key, _MISSING),
                    selected.get(key, _MISSING),
                    (*path, str(key)),
                )
            )
        return changes

    if baseline_list:
        if len(baseline) != len(selected):
            raise _UnstableList("list length changed")
        changes = []
        for index, (old, new) in enumerate(zip(baseline, selected, strict=True)):
            changes.extend(_walk(old, new, (*path, index)))
        return changes

    if not _same_scalar(baseline, selected):
        return [_record(path, "changed", baseline, selected)]
    return []


def diff_payloads(
    baseline: Any,
    selected: Any,
    *,
    baseline_schema: str | None = None,
    selected_schema: str | None = None,
) -> DiffOutcome:
    """Compare supported payload mappings without I/O or input mutation."""

    if baseline is None:
        return DiffOutcome(
            "no_baseline",
            baseline_schema=baseline_schema,
            selected_schema=selected_schema,
        )
    if selected is None:
        return DiffOutcome(
            "unavailable",
            baseline_schema=baseline_schema,
            selected_schema=selected_schema,
            reason="selected payload unavailable",
        )
    if baseline_schema and selected_schema and baseline_schema != selected_schema:
        return DiffOutcome(
            "cross_schema",
            baseline_schema=baseline_schema,
            selected_schema=selected_schema,
            reason="Diff may be incomplete across schema versions",
        )
    if not isinstance(baseline, Mapping) or not isinstance(selected, Mapping):
        return DiffOutcome(
            "unsupported_shape",
            baseline_schema=baseline_schema,
            selected_schema=selected_schema,
            reason="payload root must be a mapping",
        )
    try:
        changes = tuple(_walk(baseline, selected, ()))
    except _UnstableList as exc:
        return DiffOutcome(
            "unsupported_shape",
            baseline_schema=baseline_schema,
            selected_schema=selected_schema,
            reason=str(exc),
        )
    except (TypeError, ValueError, RecursionError) as exc:
        return DiffOutcome(
            "failed",
            baseline_schema=baseline_schema,
            selected_schema=selected_schema,
            reason=type(exc).__name__,
        )
    return DiffOutcome(
        "semantic",
        changes=changes,
        baseline_schema=baseline_schema,
        selected_schema=selected_schema,
    )


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
    "ChangeRecord",
    "DiffOutcome",
    "VersionSnapshot",
    "diff_payloads",
    "prepare_version_snapshots",
    "resolve_history_selection",
]
