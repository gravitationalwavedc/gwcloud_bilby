from datetime import UTC, datetime

from django import template
from django.utils.dateparse import parse_datetime

register = template.Library()

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M UTC"


def _to_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@register.filter
def basename(value):
    """Return the substring after the last "/" in a path-like value.

    Presentation defaulting for the technical-value primitive — malformed or
    awkward data degrades instead of raising in templates:

    - str (or anything coercible via str()): the text after the final "/";
      when there is no "/" at all, or the value ends with one (the result
      would be empty), the input string is returned unchanged.
    - None: rendered as "".
    """
    if value is None:
        return ""
    value = str(value)
    _, separator, tail = value.rpartition("/")
    return tail if separator and tail else value


@register.filter
def parent_dir(value):
    """Return the substring before the last "/" in a path-like value.

    Presentation defaulting for the technical-value primitive — malformed or
    awkward data degrades instead of raising in templates:

    - str (or anything coercible via str()): the text before the final "/",
      with no trailing slash; when there is no "/" at all, "" is returned.
    - None: rendered as "".
    """
    if value is None:
        return ""
    value = str(value)
    head, separator, _ = value.rpartition("/")
    return head if separator else ""


@register.filter
def mirrored_count(files):
    """Count fully mirrored files in a GWFlow file list (uploaded == True)."""
    return sum(1 for f in files if getattr(f, "uploaded", False))


@register.filter
def pending_count(files):
    """Count files still waiting to be mirrored in a GWFlow file list."""
    return sum(1 for f in files if not getattr(f, "uploaded", False))


@register.filter
def utc_timestamp(value):
    """Format a datetime or ISO-8601 string as "YYYY-MM-DD HH:MM UTC".

    Input contract (deliberate for a presentation formatter — malformed data
    renders as empty rather than raising in templates):

    - aware datetime: converted to UTC, then formatted.
    - naive datetime: assumed to already be UTC.
    - str: parsed as ISO-8601 (naive strings treated as UTC).
    - None, empty/whitespace-only string, unparseable string, or any other
      type: rendered as "".
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return ""
    if isinstance(value, datetime):
        return _to_utc(value).strftime(TIMESTAMP_FORMAT)
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is None:
            return ""
        return _to_utc(parsed).strftime(TIMESTAMP_FORMAT)
    return ""
