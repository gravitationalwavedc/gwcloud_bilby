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
