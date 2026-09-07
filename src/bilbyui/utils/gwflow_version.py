import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def normalise_libraries(raw):
    """Return a list of trimmed, non-blank, case-sensitively deduplicated
    library names, preserving first-seen portal order.

    Non-string values and whitespace-only strings are dropped. Values are
    stored trimmed (leading/trailing whitespace removed) and compared
    case-sensitively against the stored (trimmed) form.
    """
    if raw is None:
        return []

    seen = set()
    result = []
    for value in raw:
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if not trimmed:
            continue
        if trimmed in seen:
            continue
        seen.add(trimmed)
        result.append(trimmed)
    return result


def normalise_current_history_timestamp(raw):
    """Return a timezone-aware UTC datetime for the portal commit timestamp, or
    None when the value is missing or malformed.

    Naive datetimes are treated as UTC. Offset-aware datetimes are converted
    to UTC. On malformed values a warning is logged and None is returned
    (job.last_updated is never substituted).
    """
    if raw is None:
        return None

    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str):
        value = raw.strip()
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
        except (ValueError, TypeError) as exc:
            logger.warning("Malformed current_history_timestamp %r: %s", raw, exc)
            return None
    else:
        logger.warning("Unsupported current_history_timestamp type %s: %r", type(raw).__name__, raw)
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt


def version_tuple(job):
    """Return (current_history_timestamp, current_history_id) used for version
    ordering and conflict detection."""
    return (job.current_history_timestamp, job.current_history_id)
