from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from django import template
from django.utils.dateparse import parse_datetime
from django.utils.html import format_html

register = template.Library()

EMPTY_STRING = '""'
EMPTY_LIST = "Empty list"
EMPTY_MAPPING = "Empty mapping"
MISSING_VALUE = "—"

_STATUS_LABELS = {
    "complete": "Complete",
    "completed": "Completed",
    "failed": "Failed",
    "processing": "Processing",
    "queued": "Queued",
    "ready": "Ready",
    "running": "Running",
    "submitted": "Submitted",
}

_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def _presence_text(value: Any) -> str | None:
    if value is None:
        return MISSING_VALUE
    if value is True:
        return "✓ True"
    if value is False:
        return "✗ False"
    if value == "":
        return EMPTY_STRING
    if isinstance(value, Mapping) and not value:
        return EMPTY_MAPPING
    if _is_sequence(value) and not value:
        return EMPTY_LIST
    return None


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def text(value: Any) -> str:
    """Format an arbitrary scalar while preserving every present falsy value."""
    presence = _presence_text(value)
    if presence is not None:
        return presence
    if isinstance(value, Mapping):
        return ", ".join(f"{key}: {text(item)}" for key, item in value.items())
    if _is_sequence(value):
        return ", ".join(text(item) for item in value)
    return str(value)


def boolean(value: Any) -> str:
    presence = _presence_text(value)
    if presence is not None:
        return presence
    return text(value)


def utc_timestamp(value: Any) -> str:
    presence = _presence_text(value)
    if presence is not None:
        return presence

    parsed = value
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is None:
            return f"Invalid timestamp: {value}"
    if not isinstance(parsed, datetime):
        return f"Invalid timestamp: {text(value)}"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return f"Unknown timezone: {parsed.isoformat(sep=' ')}"
    converted = parsed.astimezone(UTC)
    return converted.strftime("%Y-%m-%d %H:%M:%S UTC")


def person(value: Any) -> str:
    presence = _presence_text(value)
    if presence is not None:
        return presence
    if not isinstance(value, Mapping):
        return text(value)

    for key in ("display_name", "displayName", "full_name", "fullName", "name"):
        candidate = value.get(key)
        if candidate is not None and candidate != "":
            return text(candidate)

    components = [value.get(key) for key in ("title", "first_name", "firstName", "given_name", "givenName")]
    surname = next(
        (
            value.get(key)
            for key in ("last_name", "lastName", "family_name", "familyName", "surname")
            if value.get(key) is not None
        ),
        None,
    )
    parts = [str(component) for component in components if component not in (None, "")]
    if surname not in (None, ""):
        parts.append(str(surname))
    if parts:
        return " ".join(parts)

    email = value.get("email")
    if email not in (None, ""):
        return text(email)
    return text(value)


def probability(value: Any, precision: int = 3) -> str:
    presence = _presence_text(value)
    if presence is not None:
        return presence
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return text(value)
    if not number.is_finite() or number < 0 or number > 1:
        return text(value)
    if number == 0:
        return "0"
    if number == 1:
        return "1"
    rendered = f"{number:.{precision}f}".rstrip("0").rstrip(".")
    return rendered


def scientific(value: Any, unit: str = "", precision: int = 3) -> str:
    presence = _presence_text(value)
    if presence is not None:
        return presence
    if isinstance(value, Mapping) and "value" in value:
        unit = text(value.get("unit", unit)) if value.get("unit", unit) else ""
        value = value["value"]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _with_unit(text(value), unit)
    if not math.isfinite(number):
        return _with_unit(text(value), unit)
    if number == 0:
        return _with_unit("0", unit)

    exponent = math.floor(math.log10(abs(number)))
    coefficient = number / (10**exponent)
    significant_decimals = max(0, precision - 1)
    coefficient_text = f"{coefficient:.{significant_decimals}f}".rstrip("0").rstrip(".")
    rendered = f"{coefficient_text}×10{str(exponent).translate(_SUPERSCRIPT)}"
    return _with_unit(rendered, unit)


def _with_unit(value: str, unit: str) -> str:
    return f"{value} {unit}" if unit else value


def list_value(value: Any, limit: int = 3) -> str:
    presence = _presence_text(value)
    if presence is not None:
        return presence
    if not _is_sequence(value):
        return text(value)
    try:
        safe_limit = max(0, int(limit))
    except (TypeError, ValueError):
        safe_limit = 3
    preview = ", ".join(text(item) for item in value[:safe_limit])
    remaining = len(value) - safe_limit
    if remaining > 0:
        return f"{preview}{', ' if preview else ''}+{remaining} more"
    return preview


def list_accessible(value: Any, limit: int = 3) -> str:
    """Render a preview and an adjacent accessible expansion containing every item."""
    presence = _presence_text(value)
    if presence is not None:
        return presence
    if not _is_sequence(value):
        return text(value)
    preview = list_value(value, limit)
    all_items = "; ".join(text(item) for item in value)
    return format_html(
        '<span aria-hidden="true">{}</span><span class="sr-only">All items: {}</span>',
        preview,
        all_items,
    )


def link(value: Any, label: str = "") -> str:
    presence = _presence_text(value)
    if presence is not None:
        return presence
    if not isinstance(value, str):
        return text(value)

    try:
        parsed = urlsplit(value)
    except ValueError:
        return text(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return text(value)

    accessible_label = label or value
    return format_html(
        '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
        value,
        accessible_label,
    )


def status(value: Any) -> str:
    presence = _presence_text(value)
    if presence is not None:
        return presence
    raw = text(value)
    return _STATUS_LABELS.get(raw.casefold(), raw)


def human_value(value: Any) -> str:
    """Legacy compatibility path using the same non-dropping presence semantics."""
    if isinstance(value, Mapping):
        return text(value)
    if _is_sequence(value):
        return ", ".join(person(item) if isinstance(item, Mapping) else text(item) for item in value) or EMPTY_LIST
    return text(value)


FORMATTERS = {
    "boolean": boolean,
    "link": link,
    "list": list_value,
    "person": person,
    "probability": probability,
    "scientific": scientific,
    "status": status,
    "text": text,
    "utc_timestamp": utc_timestamp,
}


def format_value(value: Any, formatter: str, **options: Any) -> str:
    try:
        formatter_function = FORMATTERS[formatter]
    except KeyError as error:
        raise ValueError(f"Unknown metadata formatter: {formatter}") from error
    return formatter_function(value, **options)


@register.filter
def get_item(value, key):
    if isinstance(value, dict):
        return value.get(key)
    return None


@register.filter
def sort_items(value):
    if isinstance(value, dict):
        return sorted(value.items())
    return []


register.filter("human_value", human_value)
register.filter("text", text)
register.filter("boolean", boolean)
register.filter("utc_timestamp", utc_timestamp)
register.filter("person", person)
register.filter("probability", probability)
register.filter("status", status)
register.simple_tag(name="scientific")(scientific)
register.simple_tag(name="list")(list_accessible)
register.simple_tag(name="link")(link)
register.simple_tag(name="format_value")(format_value)
