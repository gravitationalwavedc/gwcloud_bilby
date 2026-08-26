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
